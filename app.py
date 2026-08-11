# -*- coding: utf-8 -*-
"""
golazox — Premium Football Club Store (Flask)
Light default + Dark mode, font sizes, full cart+checkout+WhatsApp, order ticket &
tracking, size stock + notify-me, search/filters, favorites, badges, dynamic club
theme, ratings, request-a-product, image search, GOAL POINTS, YOU CHOOSE poll,
NEW DROP countdown, MATCHDAY mode, admin panel.
"""
import os
import json
import time
import datetime
import random
from flask import Flask, request, redirect, Response, send_file, session, url_for

import cfg
import db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "golazox-secret-2026")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=30)


def reload_products():
    """Merge admin-managed product overrides into cfg.PRODUCTS in place."""
    cfg.PRODUCTS[:] = db.merge_products(cfg.PRODUCTS)


db.init_db(cfg.PRODUCTS, cfg.ORDER_PREFIX)
reload_products()
STOCK = db.get_stock()  # {product: {size: qty}}

STATIC_IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img")

# Color filter palette: (key, label, hex). First 6 are visible; the rest appear behind "المزيد +".
COLOR_FILTERS = [
    ("white", "أبيض", "#FFFFFF"), ("black", "أسود", "#0B0B0C"), ("red", "أحمر", "#DC2626"),
    ("blue", "أزرق", "#2563EB"), ("yellow", "أصفر", "#EAB308"), ("green", "أخضر", "#16A34A"),
    ("purple", "بنفسجي", "#8B5CF6"), ("gold", "ذهبي", "#C9A24B"),
]


def hex_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (0, 0, 0)


def nearest_color(hexc):
    """Return the palette hex closest to the given hex (used for the color filter)."""
    rgb = hex_rgb(hexc)
    best, bd = COLOR_FILTERS[0][2], 10 ** 9
    for _, _, pc in COLOR_FILTERS:
        p = hex_rgb(pc)
        d = sum((a - b) ** 2 for a, b in zip(rgb, p))
        if d < bd:
            best, bd = pc, d
    return best



# ============================== HELPERS ==============================
def lang():
    c = request.cookies.get("lang")
    if c in ("ar", "en"):
        return c
    a = request.args.get("lang")
    if a in ("ar", "en"):
        return a
    return "ar"


def has_lang():
    return request.cookies.get("lang") in ("ar", "en")


def t(k):
    return cfg.L[lang()].get(k, cfg.L["ar"].get(k, k))


def json_d(o):
    return json.dumps(o, ensure_ascii=False)


def eff_stock(p):
    s = dict(p.get("stock", {}))
    ov = STOCK.get(p["id"], {})
    for k, v in ov.items():
        s[k] = v
    return s


def eff_price(p):
    if p["kind"] == "mug":
        return cfg.PRICE_MUG
    return cfg.PRICE_JERSEY


def total_avail(p):
    return sum(eff_stock(p).values())


def cur():
    return cfg.CURRENCY_EN if lang() == "en" else cfg.CURRENCY_AR


def fmt_cur(v):
    return "%.3f %s" % (v, cur())


def prod_json(p):
    s = eff_stock(p)
    c = cfg.club_of(p)
    return {
        "id": p["id"], "kind": p["kind"], "club_id": p.get("club_id"),
        "club_ar": cfg.club_name(p, False), "club_en": cfg.club_name(p, True),
        "name_ar": p["name_ar"], "name_en": p["name_en"],
        "desc_ar": p.get("desc_ar", ""), "desc_en": p.get("desc_en", ""),
        "price": eff_price(p), "badges": p.get("badges", []),
        "stock": s, "imgs": p["imgs"], "colors": p["colors"], "emoji": p["emoji"],
    }


def gx_data():
    products = [prod_json(p) for p in cfg.PRODUCTS if not p.get("hidden")]
    clubs = {k: dict(v) for k, v in cfg.CLUBS.items()}
    m = match_info()
    d = drop_info()
    poll = poll_active()
    u = current_user()
    user = {"id": u["id"], "role": u["role"]} if u else None
    return {
        "lang": lang(), "cur": cur(), "wa": cfg.WHATSAPP,
        "delivery": cfg.DELIVERY_FEE,
        "sizes": cfg.SIZE_ORDER, "chart": cfg.SIZE_CHART, "rewards": cfg.REWARDS,
        "products": products, "clubs": clubs, "points_per": cfg.POINTS_PER_BHD,
        "match": m, "drop": d, "poll": poll, "now": datetime.datetime.now().isoformat(),
        "user": user,
        "T": cfg.L[lang()],
    }


def match_info():
    m = db.settings_get("match")
    if not m:
        m = cfg.MATCHES[0] if cfg.MATCHES else None
    if not m or not m.get("kickoff"):
        return None
    try:
        ko = datetime.datetime.strptime(m["kickoff"], "%Y-%m-%d %H:%M")
    except Exception:
        return None
    now = datetime.datetime.now()
    if now < ko - datetime.timedelta(hours=cfg.MATCHDAY_START_HOURS):
        return None
    if now > ko + datetime.timedelta(hours=cfg.MATCHDAY_END_HOURS):
        return None
    return {"home": m.get("home"), "away": m.get("away"),
            "kickoff_iso": ko.isoformat(), "result": m.get("result"),
            "live": bool(now >= ko and not m.get("result"))}


def drop_info():
    d = db.settings_get("drop")
    if not d:
        d = cfg.DROP
    if not d or not d.get("target"):
        return None
    try:
        tg = datetime.datetime.strptime(d["target"], "%Y-%m-%d %H:%M")
    except Exception:
        return None
    return {"ar": d.get("ar", ""), "en": d.get("en", ""), "img": d.get("img", ""),
            "ids": d.get("product_ids", []), "target_iso": tg.isoformat(),
            "passed": datetime.datetime.now() >= tg}


def poll_active():
    polls = db.polls_list()
    if not polls:
        return None
    now = datetime.datetime.now()
    p = polls[0]
    data = p["data"]
    try:
        st = datetime.datetime.strptime(p["start"], "%Y-%m-%d %H:%M") if p["start"] else None
        en = datetime.datetime.strptime(p["end"], "%Y-%m-%d %H:%M") if p["end"] else None
    except Exception:
        st = en = None
    if p["status"] == "open":
        if st and now < st:
            return None
        if en and now > en:
            p["status"] = "closed"
        return {"id": p["id"], "data": data, "status": p["status"],
                "start": p["start"], "end": p["end"], "votes": db.votes_count(p["id"]),
                "total": db.votes_total(p["id"]), "ended": bool(en and now > en)}
    return {"id": p["id"], "data": data, "status": p["status"],
            "start": p["start"], "end": p["end"], "votes": db.votes_count(p["id"]),
            "total": db.votes_total(p["id"]), "ended": True}


# ============================== AUTH / ROLES ==============================
ORDER_FLOW = ["pending", "confirmed", "preparing", "delivering", "delivered"]


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    u = db.user_by_id(uid)
    if not u or u.get("status") != "active":
        return None
    return u


def admin_role():
    if session.get("admin_ok"):
        return "super_admin"
    u = current_user()
    if not u:
        return None
    return u.get("role") if u.get("role") in ("admin", "super_admin") else None


def fix_phone(ph):
    p = normal_phone(ph)
    if p.startswith("+"):
        return p
    if p.isdigit():
        return "+" + p
    return p


def seed_super_admin():
    phone = fix_phone(os.environ.get("SUPER_ADMIN_PHONE") or os.environ.get("ADMIN_PHONE") or cfg.WHATSAPP)
    name = os.environ.get("SUPER_ADMIN_NAME", "Owner")
    u = db.user_by_phone(phone)
    if not u:
        bare = phone[1:] if phone.startswith("+") else phone
        legacy = db.user_by_phone(bare)
        if legacy:
            db.user_update(legacy["id"], phone=phone)
            u = legacy
    if not u:
        uid = db.user_create(phone, name, "super_admin")
        db.user_update(uid, password=cfg.ADMIN_PASS)
        return uid
    if u.get("role") != "super_admin":
        db.user_update(u["id"], role="super_admin", name=name)
    if not u.get("password"):
        db.user_update(u["id"], password=cfg.ADMIN_PASS)
    return u["id"]


def order_stage(o):
    status = o["status"]
    if status == "cancelled":
        return (-1, False)
    return (ORDER_FLOW.index(status) if status in ORDER_FLOW else -1, status == "delivered")


def normal_phone(ph):
    return "".join(ch for ch in str(ph or "") if ch.isdigit() or ch == "+")


# ============================== IMAGES ==============================
def placeholder_svg(p, label, sub):
    cols = p.get("colors", ["#E2E8F0", "#94A3B8"])
    emoji = p.get("emoji", "⚽")
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="COL1"/><stop offset="1" stop-color="COL2"/>
</linearGradient></defs>
<rect width="600" height="600" fill="url(#g)"/>
<circle cx="545" cy="55" r="90" fill="#FFFFFF" opacity="0.08"/>
<circle cx="70" cy="540" r="120" fill="#000000" opacity="0.10"/>
<text x="300" y="285" font-size="150" text-anchor="middle">EMOJI</text>
<rect x="150" y="395" rx="26" width="300" height="54" fill="#FFFFFF" opacity="0.18"/>
<text x="300" y="431" font-size="30" font-family="Arial, sans-serif" font-weight="700" fill="#FFFFFF" text-anchor="middle">LABEL</text>
<text x="300" y="485" font-size="22" font-family="Arial, sans-serif" fill="#FFFFFF" opacity="0.9" text-anchor="middle">SUB</text>
<text x="300" y="545" font-size="20" font-family="Arial, sans-serif" font-weight="900" letter-spacing="4" fill="#FFFFFF" opacity="0.5" text-anchor="middle">GOLAZOX</text>
</svg>""".replace("COL1", cols[0]).replace("COL2", cols[1]).replace("EMOJI", emoji) \
        .replace("LABEL", label).replace("SUB", sub)


@app.route("/img/<name>")
def img(name):
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".avif"):
        for base_dir in (STATIC_IMG, os.path.dirname(os.path.abspath(__file__))):
            pth = os.path.join(base_dir, name + ext)
            if os.path.exists(pth):
                return send_file(pth)
    base = name.split("_")[0]
    p = next((x for x in cfg.PRODUCTS if x["id"] == base), None)
    if not p:
        p = {"colors": ["#E2E8F0", "#94A3B8"], "emoji": "⚽"}
    en = lang() == "en"
    label = (p.get("name_en") if en else p.get("name_ar")) or "golazox"
    sub = "PHOTO SOON" if en else "الصورة قريبًا"
    return Response(placeholder_svg(p, label, sub), mimetype="image/svg+xml")


# ============================== PAGE TEMPLATES ==============================
CSS = """<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
:root { --bg:#F3F6FB; --card:#FFFFFF; --card2:#EDF1F8; --line:#E2E8F0; --txt:#0F172A; --mut:#5B6782;
  --brand1:#E11D48; --brand2:#F97316; --green:#25D366; --gold:#C9A24B; --ok:#16A34A; --err:#DC2626;
  --ac:var(--brand1); --ac2:var(--brand2); --sh:0 8px 28px rgba(15,23,42,.08); --sh2:0 18px 44px rgba(15,23,42,.14);
  --fs:16px; }
html[data-theme="dark"] { --bg:#0B0F19; --card:#141B2B; --card2:#1B2437; --line:#263049; --txt:#F8FAFC;
  --mut:#9AA7BD; --sh:0 8px 28px rgba(0,0,0,.4); --sh2:0 18px 44px rgba(0,0,0,.55); }
html[data-font="a"] { --fs:14px; }
html[data-font="c"] { --fs:18px; }
html { font-size: var(--fs); }
body { font-family:'FONT','Segoe UI',Tahoma,sans-serif; background:var(--bg); color:var(--txt);
  min-height:100vh; transition:background .45s ease, color .45s ease; }
a { text-decoration:none; color:inherit; } img { display:block; }
button { font-family:inherit; cursor:pointer; }
html[data-club] .hd { border-bottom:1px solid var(--line); }
html[data-club] .hd::after { content:''; display:block; height:3px;
  background:linear-gradient(90deg, var(--ac), var(--ac2)); }
.wrap { max-width:1120px; margin:0 auto; padding:22px 18px 80px; }
.hd { position:sticky; top:0; z-index:95; background:var(--card); border-bottom:1px solid var(--line);
  box-shadow:0 2px 14px rgba(15,23,42,.05);
  transition:background .45s ease, border-color .45s ease, box-shadow .45s ease; }
.hd-in { max-width:1120px; margin:0 auto; padding:10px 16px; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.logo { font-size:1.4rem; font-weight:900; display:flex; align-items:center; gap:6px; color:var(--txt); }
.logo .ball { font-size:1.3rem; }
.nav { display:flex; gap:2px; flex:1; flex-wrap:wrap; }
.nv { padding:7px 12px; border-radius:999px; font-size:.86rem; font-weight:700; color:var(--mut); cursor:pointer; white-space:nowrap; background:none; border:none; }
.nv:hover { color:var(--txt); background:var(--card2); }
.nv.on { background:linear-gradient(90deg,var(--ac),var(--ac2)); color:#fff; }
.hbtn { background:var(--card2); border:1px solid var(--line); color:var(--txt); font-size:.83rem; font-weight:700;
  padding:7px 13px; border-radius:999px; }
.hbtn:hover { border-color:var(--ac); }
.hicon { position:relative; }
.hcount { position:absolute; top:-6px; inset-inline-end:-6px; background:var(--brand1); color:#fff; font-size:.62rem;
  font-weight:900; min-width:18px; height:18px; border-radius:999px; display:none; align-items:center; justify-content:center; padding:0 4px; }
/* hero */
.hero { position:relative; overflow:hidden; border:1px solid var(--line); border-radius:26px;
  background:linear-gradient(120deg, var(--card) 0%, #F8FAFF 55%), repeating-linear-gradient(0deg, transparent 0 30px, rgba(15,23,42,.02) 30px 32px);
  padding:46px 34px; margin-bottom:26px; transition:background .45s ease; }
html[data-club] .hero { background:linear-gradient(120deg, var(--tint, rgba(225,29,72,.06)) 0%, transparent 68%), linear-gradient(120deg, var(--card) 0%, #F8FAFF 55%); }
html[data-theme="dark"] .hero { background:linear-gradient(120deg, var(--card) 0%, #101828 55%); }
html[data-theme="dark"][data-club] .hero { background:linear-gradient(120deg, var(--tint, rgba(225,29,72,.06)) 0%, transparent 68%), linear-gradient(120deg, var(--card) 0%, #101828 55%); }
.hero h1 { font-size:2.4rem; line-height:1.15; font-weight:900; }
.hero h1 .g { background:linear-gradient(90deg, var(--ac), var(--ac2)); -webkit-background-clip:text; background-clip:text; color:transparent; }
.hero p { margin-top:12px; color:var(--mut); font-size:1rem; line-height:1.9; max-width:640px; }
.hero-btns { margin-top:22px; display:flex; gap:12px; flex-wrap:wrap; }
.btn { display:inline-flex; align-items:center; gap:8px; font-weight:800; font-size:.95rem; padding:12px 24px;
  border-radius:999px; border:none; }
.btn.pri { background:linear-gradient(90deg, var(--ac), var(--ac2)); color:#fff;
  box-shadow:0 12px 30px var(--glow, rgba(225,29,72,.28));
  transition:transform .16s ease, box-shadow .45s ease; }
.btn.pri:hover { transform:translateY(-2px); }
.btn.ghost { background:var(--card); border:1.5px solid var(--line); color:var(--txt); }
.btn.ghost:hover { border-color:var(--ac); color:var(--ac); }
.btn.wa { background:var(--green); color:#073a1f; box-shadow:0 12px 30px rgba(37,211,102,.3); }
.btn.wa:hover { transform:translateY(-2px); }
.btn.big { width:100%; justify-content:center; padding:14px; font-size:1rem; }
.btn.sm { padding:8px 16px; font-size:.85rem; }
.btn.block { width:100%; justify-content:center; }
.sec { margin-bottom:34px; }
.sec-head { display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:16px; }
.sec-head h2 { font-size:1.4rem; font-weight:900; display:flex; align-items:center; gap:10px; }
.sec-head h2 .bar { width:6px; height:1.4rem; border-radius:4px; background:linear-gradient(180deg, var(--ac), var(--ac2)); transition:background .45s ease; }
.sec-sub { color:var(--mut); font-size:.86rem; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(238px,1fr)); gap:20px; }
.pcard { position:relative; background:var(--card); border:1px solid var(--line); border-radius:20px; overflow:hidden;
  transition:transform .16s ease, box-shadow .16s ease, border-color .16s ease; }
.pcard:hover { transform:translateY(-5px); border-color:color-mix(in srgb, var(--ac) 55%, var(--line)); box-shadow:var(--sh2); }
.pimg { height:230px; display:flex; align-items:center; justify-content:center; overflow:hidden; background:var(--card2); }
.pimg img { width:100%; height:100%; object-fit:cover; transition:transform .3s ease; }
.pcard:hover .pimg img { transform:scale(1.05); }
.pbody { padding:14px 15px 15px; }
.pcat { font-size:.7rem; font-weight:800; letter-spacing:.4px; text-transform:uppercase; color:var(--ac); }
.ads-strip { display:flex; flex-direction:column; gap:10px; margin:16px 0; }
.ads-item { display:block; background:linear-gradient(135deg,var(--ac,#E11D48),var(--ac2,#F97316)); color:#fff; border-radius:14px; padding:12px 16px; text-decoration:none; box-shadow:0 6px 18px rgba(225,29,72,.18); }
.ads-item .ads-txt { font-weight:800; font-size:.95rem; }
.ads-item:hover { opacity:.94; }
.pbody h3 { font-size:1.02rem; font-weight:800; margin-top:4px; line-height:1.4; }
.pfoot { display:flex; align-items:center; justify-content:space-between; margin-top:11px; gap:8px; }
.pfoot b { font-size:1.05rem; color:var(--ac); }
.pview { font-size:.8rem; font-weight:800; color:var(--mut); }
.pcard:hover .pview { color:var(--ac); }
.tryme { width:100%; margin-top:10px; padding:8px 10px; border:1.5px dashed var(--ac,#E11D48); background:rgba(225,29,72,.05); color:var(--ac,#E11D48); border-radius:12px; font-family:inherit; font-size:.82rem; font-weight:800; cursor:pointer; }
.tryme:hover { background:var(--ac,#E11D48); color:#fff; }
.badges { position:absolute; top:10px; inset-inline-start:10px; display:flex; flex-direction:column; gap:5px; z-index:2; }
.badge { font-size:.68rem; font-weight:900; padding:4px 9px; border-radius:999px; color:#fff; width:max-content; }
.badge.new { background:linear-gradient(90deg,#8B5CF6,#A78BFA); }
.badge.best { background:linear-gradient(90deg,#EA580C,#F97316); }
.badge.offer { background:linear-gradient(90deg,#16A34A,#22C55E); }
.badge.soldout { background:#475569; }
.heart { position:absolute; top:10px; inset-inline-end:10px; z-index:3; width:34px; height:34px; border-radius:50%;
  background:rgba(255,255,255,.92); border:none; font-size:16px; display:flex; align-items:center; justify-content:center;
  box-shadow:0 4px 12px rgba(15,23,42,.15); }
.heart.on { color:#E11D48; }
/* search & filters */
.sb { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-bottom:16px; }
.sbox { flex:1; min-width:220px; display:flex; background:var(--card); border:1.5px solid var(--line); border-radius:14px;
  align-items:center; padding:0 6px 0 14px; }
.sbox input { flex:1; border:none; outline:none; background:none; color:var(--txt); font-family:inherit; font-size:.95rem; padding:12px 4px; }
.sbox button { background:var(--ac); color:#fff; border:none; border-radius:10px; padding:9px 14px; font-weight:800; font-size:.85rem; }
.filters { display:flex; gap:8px; flex-wrap:wrap; }
.fbtn { margin-bottom:10px; }
.sort-lbl { font-size:.82rem; font-weight:800; color:var(--mut); margin-inline-start:4px; }
select.sort { font-weight:800; }
.search-none { text-align:center; padding:34px 16px; border:1.5px dashed var(--line); border-radius:18px; margin-bottom:18px; }
.search-none .sn-ic { font-size:40px; margin-bottom:10px; }
.search-none .mnote { margin-bottom:14px; font-weight:800; }
.chip { background:var(--card); border:1.5px solid var(--line); color:var(--mut); border-radius:999px; padding:7px 14px;
  font-size:.8rem; font-weight:700; }
.chip:hover { border-color:var(--ac); }
.chip.on { background:var(--ac); border-color:transparent; color:#fff; }
.sel { background:var(--card); border:1.5px solid var(--line); color:var(--txt); border-radius:12px; padding:8px 12px;
  font-size:.82rem; font-weight:700; font-family:inherit; }
/* info cards */
.quick { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:18px; }
.qcard { background:var(--card); border:1px solid var(--line); border-radius:20px; padding:22px; cursor:pointer;
  transition:transform .16s ease, border-color .16s ease; }
.qcard:hover { transform:translateY(-4px); border-color:var(--ac); }
.qic { width:52px; height:52px; border-radius:14px; display:flex; align-items:center; justify-content:center; font-size:24px;
  background:var(--card2); margin-bottom:14px; }
.qcard h3 { font-size:1.02rem; font-weight:800; }
.qcard p { color:var(--mut); font-size:.84rem; line-height:1.7; margin:7px 0 12px; }
.qview { color:var(--ac); font-weight:800; font-size:.86rem; }
/* footer */
.ft { border-top:1px solid var(--line); background:var(--card); }
.ft-in { max-width:1120px; margin:0 auto; padding:36px 18px 30px; text-align:center; }
.ft-brand { font-size:1.4rem; font-weight:900; }
.ft-title { color:var(--mut); font-size:.85rem; margin-top:16px; font-weight:800; }
.ft-links { display:flex; gap:8px 22px; justify-content:center; flex-wrap:wrap; margin-top:12px; }
.ft-links a { color:var(--mut); font-size:.85rem; font-weight:700; cursor:pointer; }
.ft-links a:hover { color:var(--ac); }
.ft-copy { color:var(--mut); font-size:.8rem; margin-top:20px; }
/* product page */
.pg { display:grid; grid-template-columns:1fr 1fr; gap:30px; align-items:start; }
.gal { position:sticky; top:86px; }
.gmain { position:relative; border:1px solid var(--line); border-radius:22px; overflow:hidden; cursor:zoom-in; background:var(--card); }
.gmain img { width:100%; height:470px; object-fit:cover; }
.gar { position:absolute; top:50%; transform:translateY(-50%); width:42px; height:42px; border-radius:50%;
  background:rgba(15,23,42,.55); color:#fff; border:none; font-size:18px; z-index:2; }
.gar:hover { background:var(--ac); }
.gar.r { inset-inline-end:12px; } .gar.l { inset-inline-start:12px; }
.gthumb { display:flex; gap:10px; margin-top:12px; }
.gthumb img { width:72px; height:72px; object-fit:cover; border-radius:12px; border:2px solid var(--line); cursor:pointer; opacity:.75; }
.gthumb img.on { border-color:var(--ac); opacity:1; }
.gcount { position:absolute; bottom:10px; inset-inline-start:10px; background:rgba(15,23,42,.72); color:#fff; font-size:.72rem;
  font-weight:700; padding:4px 10px; border-radius:999px; }
.pinfo h1 { font-size:1.7rem; font-weight:900; line-height:1.3; }
.pcatline { color:var(--ac); font-weight:800; font-size:.78rem; letter-spacing:.5px; text-transform:uppercase; margin-top:6px; }
.pprice { margin-top:12px; font-size:1.5rem; font-weight:900; color:var(--ac); }
.trust { display:flex; gap:6px 10px; flex-wrap:wrap; margin-top:12px; }
.tbadge { font-size:.72rem; font-weight:800; color:var(--mut); background:var(--card2); border:1px solid var(--line);
  padding:4px 10px; border-radius:999px; }
.tbadge.warn { color:#C2410C; border-color:#FDBA74; background:#FFF7ED; }
html[data-theme="dark"] .tbadge.warn { background:#3B1D0B; border-color:#7C2D12; color:#FDBA74; }
.szsec { margin-top:22px; }
.szsec .lbl { font-weight:800; font-size:.95rem; margin-bottom:10px; display:flex; align-items:center; justify-content:space-between; gap:10px; }
.szlink { color:var(--ac); font-weight:800; font-size:.84rem; cursor:pointer; }
.sizes { display:flex; gap:8px; flex-wrap:wrap; }
.size-chip { min-width:52px; padding:12px 6px; text-align:center; background:var(--card); border:1.5px solid var(--line);
  border-radius:12px; font-weight:800; font-size:.9rem; cursor:pointer; color:var(--txt); position:relative; }
.size-chip:hover { border-color:var(--ac); }
.size-chip.on { background:linear-gradient(90deg,var(--ac),var(--ac2)); border-color:transparent; color:#fff; }
.size-chip.oos { opacity:.42; text-decoration:line-through; cursor:not-allowed; }
.size-chip .xs { position:absolute; top:-7px; inset-inline-end:-7px; background:#DC2626; color:#fff; width:16px; height:16px;
  border-radius:50%; font-size:.6rem; font-weight:900; display:flex; align-items:center; justify-content:center; }
.qtysec { margin-top:20px; }
.qtysec .lbl { font-weight:800; font-size:.95rem; margin-bottom:10px; }
.qty { display:inline-flex; align-items:center; gap:4px; background:var(--card); border:1px solid var(--line); border-radius:14px; overflow:hidden; }
.qty button { width:42px; height:42px; background:none; border:none; color:var(--txt); font-size:1.1rem; font-weight:800; }
.qty button:hover { background:var(--card2); }
.qty .qn { min-width:42px; text-align:center; font-size:1rem; font-weight:900; }
.orderbtn { width:100%; margin-top:22px; }
.links3 { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-top:20px; }
.link3 { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:13px 8px; text-align:center;
  font-weight:800; font-size:.8rem; cursor:pointer; color:var(--mut); }
.link3:hover { color:var(--ac