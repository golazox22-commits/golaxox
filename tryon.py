import os
import json
import time
import urllib.request
import urllib.error

class TryOnError(Exception):
    pass

class TryOnNotConfigured(TryOnError):
    pass

REPLICATE_API = "https://api.replicate.com/v1"
REPLICATE_FILES = REPLICATE_API + "/files"

def provider():
    return (os.environ.get("TRYON_PROVIDER", "") or "").strip().lower()

def configured():
    p = provider()
    if p == "replicate":
        return bool((os.environ.get("REPLICATE_API_TOKEN", "") or "").strip()
                    and (os.environ.get("TRYON_MODEL", "") or "").strip())
    return False

def _token():
    return (os.environ.get("REPLICATE_API_TOKEN", "") or "").strip()

def _model():
    return (os.environ.get("TRYON_MODEL", "") or "").strip()

def _source_key():
    return (os.environ.get("TRYON_SOURCE_KEY", "") or "").strip() or "source_image"

def _target_key():
    return (os.environ.get("TRYON_TARGET_KEY", "") or "").strip() or "target_image"

def _http(method, url, headers=None, body=None, timeout=120):
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        raise TryOnError("network: %s" % type(e).__name__)

def _upload_file(data_bytes, fname):
    headers = {
        "Authorization": "Bearer " + _token(),
        "Content-Type": "application/octet-stream",
    }
    code, body = _http("POST", REPLICATE_FILES, headers=headers, body=data_bytes)
    if code not in (200, 201, 202):
        raise TryOnError("upload_failed:%s" % code)
    try:
        obj = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        raise TryOnError("upload_bad_json")
    url = (obj.get("urls") or {}).get("get")
    if not url:
        raise TryOnError("upload_no_url")
    return url

def start(user_bytes, model_bytes):
    if provider() != "replicate":
        raise TryOnNotConfigured()
    if not configured():
        raise TryOnNotConfigured()
    src_url = _upload_file(user_bytes, "user.jpg")
    tgt_url = _upload_file(model_bytes, "model.jpg")
    owner, sep, name = _model().partition("/")
    if not sep:
        raise TryOnError("bad_model")
    payload = json.dumps({"input": {_source_key(): src_url, _target_key(): tgt_url}}).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + _token(),
        "Content-Type": "application/json",
    }
    code, body = _http("POST", REPLICATE_API + "/models/%s/%s/predictions" % (owner, name),
                       headers=headers, body=payload)
    if code not in (200, 201):
        raise TryOnError("start_failed:%s" % code)
    try:
        obj = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        raise TryOnError("start_bad_json")
    pid = obj.get("id")
    poll_url = (obj.get("urls") or {}).get("get")
    if not pid or not poll_url:
        raise TryOnError("start_no_prediction")
    return {"prediction": pid, "poll_url": poll_url}

def poll(job):
    headers = {"Authorization": "Bearer " + _token()}
    code, body = _http("GET", job["poll_url"], headers=headers, timeout=60)
    if code != 200:
        return "failed", None, "poll_failed:%s" % code
    try:
        obj = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return "failed", None, "poll_bad_json"
    status = obj.get("status", "")
    if status == "succeeded":
        out = obj.get("output")
        urls = []
        if isinstance(out, list):
            urls = [u for u in out if isinstance(u, str)]
        elif isinstance(out, str):
            urls = [out]
        if not urls:
            return "failed", None, "no_output"
        c2, b2 = _http("GET", urls[0], timeout=180)
        if c2 == 200 and b2:
            return "succeeded", b2, None
        return "failed", None, "download_failed:%s" % c2
    if status in ("failed", "canceled"):
        err = obj.get("error") or status
        if isinstance(err, dict):
            err = err.get("detail") or err.get("message") or status
        return "failed", None, str(err)[:200]
    return status, None, None

def poll_until_done(job, timeout=480, interval=2.5):
    start_t = time.time()
    while time.time() - start_t < timeout:
        status, data, err = poll(job)
        if status == "succeeded":
            return data
        if status == "failed":
            raise TryOnError(err or "provider_failed")
        time.sleep(interval)
    raise TryOnError("timeout")
