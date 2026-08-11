#!/usr/bin/env python3
"""FASHN VTON v1.5 Try-On Backend Service

Standalone Flask server wrapping the FASHN VTON v1.5 pipeline.
Designed to run on a separate GPU host (HF Space, Colab, Modal, RunPod, etc).

Architecture:
  GOLAZOX (Railway, CPU) -> THIS SERVICE (GPU host) -> FASHN VTON v1.5 pipeline

Env vars:
  PORT                 - Listen port (default 7860)
  FASHN_HOME           - Directory containing weights/ (default ./weights)
  TRYON_DEV            - If "1", run without real model for plumbing tests
  FASHN_MAX_QUEUE      - Max queued jobs before rejecting (default 4)
  FASHN_REQUEST_TIMEOUT - Max seconds per inference (default 300)

API:
  GET  /health         -> {ok, model_loaded, queue_depth}
  POST /tryon/jobs     -> multipart: person_image, garment_image, category, garment_photo_type, num_timesteps, guidance_scale, segmentation_free, seed
                          -> {job_id}
  GET  /tryon/jobs/<id> -> {status, result?: {image}, error?: {code, message}}
"""

import os
import sys
import json
import uuid
import time
import shutil
import base64
import tempfile
import threading
import logging
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory
from PIL import Image

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
log = logging.getLogger("tryon")

FASHN_HOME = os.environ.get("FASHN_HOME", os.path.join(os.path.dirname(__file__), "weights"))
TRYON_DEV = (os.environ.get("TRYON_DEV", "") or "").strip() == "1"
MAX_QUEUE = int(os.environ.get("FASHN_MAX_QUEUE", "4"))
REQUEST_TIMEOUT = int(os.environ.get("FASHN_REQUEST_TIMEOUT", "300"))

pipeline = None
pipeline_lock = threading.Lock()
jobs = {}
jobs_lock = threading.Lock()


def _load_pipeline():
    global pipeline
    if pipeline is not None:
        return pipeline
    if TRYON_DEV:
        log.info("TRYON_DEV=1: skipping real model load")
        return None
    try:
        from fashn_vton import TryOnPipeline
        log.info("Loading FASHN VTON v1.5 pipeline from %s ...", FASHN_HOME)
        pipeline = TryOnPipeline(weights_dir=FASHN_HOME)
        log.info("Pipeline loaded successfully")
        return pipeline
    except Exception as e:
        log.error("Failed to load pipeline: %s", e)
        raise


def _run_inference(person_img, garment_img, category, garment_photo_type,
                   num_samples, num_timesteps, guidance_scale, seed, segmentation_free):
    if TRYON_DEV:
        return _dev_result(person_img)
    p = _load_pipeline()
    result = p(
        person_image=person_img,
        garment_image=garment_img,
        category=category,
        garment_photo_type=garment_photo_type,
        num_samples=num_samples,
        num_timesteps=num_timesteps,
        guidance_scale=guidance_scale,
        seed=seed,
        segmentation_free=segmentation_free,
    )
    return result.images[0]


def _dev_result(person_img):
    w, h = person_img.size
    max_s = 576
    scale = min(1, max_s / max(w, h))
    nw, nh = int(w * scale), int(h * scale)
    out = Image.new("RGB", (nw, nh), (40, 40, 40))
    try:
        resized = person_img.resize((nw, nh), Image.LANCZOS)
        out.paste(resized)
    except Exception:
        pass
    return out


def _image_to_base64(img):
    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _worker():
    while True:
        job_id = None
        with jobs_lock:
            for jid, job in jobs.items():
                if job["status"] == "queued":
                    job["status"] = "running"
                    job_id = jid
                    break
        if not job_id:
            time.sleep(0.5)
            continue
        job = jobs[job_id]
        start_t = time.time()
        try:
            person_path = job["person_path"]
            garment_path = job["garment_path"]
            person_img = Image.open(person_path).convert("RGB")
            garment_img = Image.open(garment_path).convert("RGB")
            log.info("Job %s: starting inference", job_id[:8])
            with pipeline_lock:
                result_img = _run_inference(
                    person_img, garment_img,
                    job["category"], job["garment_photo_type"],
                    job["num_samples"], job["num_timesteps"],
                    job["guidance_scale"], job["seed"], job["segmentation_free"]
                )
            elapsed = time.time() - start_t
            log.info("Job %s: done in %.1fs", job_id[:8], elapsed)
            with jobs_lock:
                jobs[job_id]["status"] = "done"
                jobs[job_id]["result"] = _image_to_base64(result_img)
        except Exception as e:
            log.error("Job %s: error %s", job_id[:8], e)
            with jobs_lock:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = {"code": "inference_failed", "message": str(e)[:200]}
        finally:
            for key in ("person_path", "garment_path"):
                try:
                    p = job.get(key)
                    if p and os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
            with jobs_lock:
                jobs[job_id].pop("person_path", None)
                jobs[job_id].pop("garment_path", None)


worker_thread = threading.Thread(target=_worker, daemon=True)
worker_thread.start()


@app.route("/health")
def health():
    loaded = pipeline is not None or TRYON_DEV
    depth = sum(1 for j in jobs.values() if j["status"] in ("queued", "running"))
    return jsonify({"ok": True, "model_loaded": loaded, "queue_depth": depth, "dev_mode": TRYON_DEV})


@app.route("/tryon/jobs", methods=["POST"])
def create_job():
    depth = sum(1 for j in jobs.values() if j["status"] in ("queued", "running"))
    if depth >= MAX_QUEUE:
        return jsonify({"error": "queue_full", "message": "Too many jobs queued"}), 429
    person_file = request.files.get("person_image")
    garment_file = request.files.get("garment_image")
    if not person_file or not garment_file:
        return jsonify({"error": "missing_images", "message": "person_image and garment_image required"}), 400
    category = request.form.get("category", "tops")
    if category not in ("tops", "bottoms", "one-pieces"):
        category = "tops"
    garment_photo_type = request.form.get("garment_photo_type", "flat-lay")
    if garment_photo_type not in ("model", "flat-lay"):
        garment_photo_type = "flat-lay"
    num_samples = min(4, max(1, int(request.form.get("num_samples", "1"))))
    num_timesteps = min(100, max(1, int(request.form.get("num_timesteps", "30"))))
    guidance_scale = float(request.form.get("guidance_scale", "1.5"))
    seed = int(request.form.get("seed", str(int(time.time()) % 2147483647)))
    segmentation_free = request.form.get("segmentation_free", "true").lower() != "false"
    tmp_dir = tempfile.mkdtemp(prefix="tryon_")
    person_path = os.path.join(tmp_dir, "person.jpg")
    garment_path = os.path.join(tmp_dir, "garment.jpg")
    person_file.save(person_path)
    garment_file.save(garment_path)
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "person_path": person_path,
            "garment_path": garment_path,
            "category": category,
            "garment_photo_type": garment_photo_type,
            "num_samples": num_samples,
            "num_timesteps": num_timesteps,
            "guidance_scale": guidance_scale,
            "seed": seed,
            "segmentation_free": segmentation_free,
            "created": time.time(),
        }
    return jsonify({"job_id": job_id, "status": "queued"}), 201


@app.route("/tryon/jobs/<job_id>")
def get_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "not_found", "message": "Job not found"}), 404
    resp = {"job_id": job_id, "status": job["status"]}
    if job["status"] == "done":
        resp["result"] = {"image": job["result"]}
    elif job["status"] == "error":
        resp["error"] = job.get("error", {"code": "unknown", "message": "Unknown error"})
    return jsonify(resp)


@app.route("/tryon/jobs", methods=["GET"])
def list_jobs():
    with jobs_lock:
        active = {jid: j["status"] for jid, j in jobs.items() if j["status"] in ("queued", "running")}
    return jsonify({"active": active, "count": len(active)})


@app.route("/tryon/cleanup", methods=["POST"])
def cleanup_jobs():
    cutoff = time.time() - 3600
    removed = 0
    with jobs_lock:
        to_del = [jid for jid, j in jobs.items() if j["status"] in ("done", "error") and j.get("created", 0) < cutoff]
        for jid in to_del:
            del jobs[jid]
            removed += 1
    return jsonify({"removed": removed})


@app.route("/")
def index():
    return jsonify({"service": "FASHN VTON v1.5 Try-On Backend", "version": "1.0.0", "dev_mode": TRYON_DEV})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    log.info("Starting try-on backend on port %d (dev=%s)", port, TRYON_DEV)
    if not TRYON_DEV:
        try:
            _load_pipeline()
        except Exception as e:
            log.warning("Could not load pipeline at startup: %s (will retry on first request)", e)
    app.run(host="0.0.0.0", port=port, debug=False)
