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
    ov = db.get_price_override(p["id"])
    return ov if ov is not None else p["price"]


def total_avail(p):
    return sum(eff_stock(p).values())


def cur():
    return cfg.CURRENCY_EN if lang() == "en" else cfg.CURRENCY_AR


def fmt_cur(v):
    if v == int(v):
        return "%.0f %s" % (v, cur())
    return "%.2f %s" % (v, cur())


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
        "lang": lang(), "cur": cur(), "wa": cfg.WHATSAPP, "tg": cfg.TG_LINK, "tg_user": cfg.TG_USER,
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
.btn.tg { background:#229ED9; color:#fff; box-shadow:0 12px 30px rgba(34,158,217,.3); }
.btn.tg:hover { transform:translateY(-2px); background:#1e8fc4; }
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
.pbody h3 { font-size:1.02rem; font-weight:800; margin-top:4px; line-height:1.4; }
.pfoot { display:flex; align-items:center; justify-content:space-between; margin-top:11px; gap:8px; }
.pfoot b { font-size:1.05rem; color:var(--ac); }
.pview { font-size:.8rem; font-weight:800; color:var(--mut); }
.pcard:hover .pview { color:var(--ac); }
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
.link3:hover { color:var(--ac); border-color:var(--ac); }
.link3 .ic { display:block; font-size:1.3rem; margin-bottom:5px; }
.zoom-hint { color:var(--mut); font-size:.74rem; margin-top:8px; text-align:center; }
.back { display:inline-flex; align-items:center; gap:6px; color:var(--mut); font-weight:800; font-size:.86rem; margin-bottom:16px; }
.back:hover { color:var(--ac); }
.notifybox { background:var(--card2); border:1px dashed var(--line); border-radius:14px; padding:14px; margin-top:18px; text-align:center; }
.notifybox .nb-btn { background:var(--ac); color:#fff; border:none; border-radius:10px; padding:10px 18px; font-weight:800; font-size:.88rem; }
/* ratings */
.rat-sec { margin-top:34px; }
.rat-head { display:flex; align-items:center; gap:18px; flex-wrap:wrap; margin-bottom:16px; }
.rat-avg { font-size:2rem; font-weight:900; color:var(--ac); }
.rat-stars { color:#F59E0B; font-size:1.1rem; letter-spacing:2px; }
.rat-note { color:var(--mut); font-size:.84rem; }
.rv { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:14px 16px; margin-bottom:12px; }
.rv-top { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.rv-name { font-weight:800; font-size:.95rem; }
.rv-stars { color:#F59E0B; font-size:.9rem; }
.rv-date { color:var(--mut); font-size:.72rem; }
.rv-txt { color:var(--txt); font-size:.9rem; line-height:1.7; margin-top:8px; }
.rv-photo { margin-top:10px; }
.rv-photo img { max-height:180px; border-radius:12px; cursor:zoom-in; }
.rv-report { margin-top:8px; background:none; border:none; color:var(--mut); font-size:.72rem; cursor:pointer; }
.rv-report:hover { color:var(--err); }
.rat-form { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:16px; margin-top:16px; }
.rat-form input, .rat-form textarea { width:100%; background:var(--card2); border:1px solid var(--line); border-radius:10px;
  padding:11px 13px; color:var(--txt); font-family:inherit; font-size:.9rem; margin-bottom:10px; }
.rat-form textarea { min-height:70px; resize:vertical; }
.stars-in { display:flex; gap:4px; font-size:1.4rem; margin-bottom:10px; }
.stars-in span { cursor:pointer; color:var(--line); }
.stars-in span.on { color:#F59E0B; }
.photos-sec { margin-top:30px; }
.photogrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); gap:12px; }
.photogrid img { width:100%; height:140px; object-fit:cover; border-radius:14px; cursor:zoom-in; }
.youlike { margin-top:34px; }
/* modals */
.mback { position:fixed; inset:0; background:rgba(15,23,42,.6); backdrop-filter:blur(4px); z-index:400;
  display:none; align-items:center; justify-content:center; padding:18px; }
.mback.open { display:flex; }
.mbox { background:var(--card); border:1px solid var(--line); border-radius:22px; width:100%; max-width:560px;
  max-height:88vh; display:flex; flex-direction:column; animation:pop .18s ease; box-shadow:var(--sh2); }
.mbox.wide { max-width:720px; }
@keyframes pop { from { transform:scale(.96); opacity:0; } to { transform:scale(1); opacity:1; } }
.mhead { display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid var(--line); }
.mhead h3 { font-size:1.05rem; font-weight:900; }
.mx { width:32px; height:32px; border-radius:50%; background:var(--card2); border:1px solid var(--line); color:var(--txt); }
.mbody { padding:20px; overflow-y:auto; }
.mnote { color:var(--mut); font-size:.88rem; line-height:1.8; margin-bottom:12px; }
.mwarning { background:#FFF7ED; border:1px solid #FDBA74; color:#C2410C; border-radius:14px; padding:12px 15px;
  font-size:.84rem; line-height:1.8; margin-top:14px; }
html[data-theme="dark"] .mwarning { background:#3B1D0B; border-color:#7C2D12; color:#FDBA74; }
.mtip { background:rgba(201,162,75,.1); border:1px solid rgba(201,162,75,.4); color:var(--gold); border-radius:14px;
  padding:12px 15px; font-size:.84rem; line-height:1.8; margin-top:14px; }
.szt { width:100%; border-collapse:collapse; margin:6px 0 16px; }
.szt th { background:var(--card2); color:var(--txt); padding:10px 8px; font-size:.82rem; text-align:center; }
.szt td { padding:10px 8px; font-size:.84rem; text-align:center; border-bottom:1px solid var(--line); color:var(--mut); }
.szt td.sz { font-weight:900; color:var(--ac); font-size:.92rem; }
.szt tr:hover td { background:var(--card2); }
.szill-wrap { display:flex; justify-content:center; margin:6px 0 16px; }
.szt-ill { width:220px; height:auto; }
.msec { font-weight:900; font-size:.95rem; margin:6px 0 10px; }
.steps { list-style:none; counter-reset:st; }
.steps li { counter-increment:st; position:relative; padding:8px 0 8px 44px; font-size:.9rem; color:var(--mut); line-height:1.8; }
.steps li:before { content:counter(st); position:absolute; inset-inline-start:0; top:8px; width:30px; height:30px; border-radius:50%;
  background:linear-gradient(135deg,var(--ac),var(--ac2)); color:#fff; font-weight:900; font-size:.86rem;
  display:flex; align-items:center; justify-content:center; }
.steps li b { color:var(--txt); }
.ret { list-style:none; }
.ret li { position:relative; padding:10px 0 10px 22px; border-bottom:1px dashed var(--line); font-size:.88rem; color:var(--mut); line-height:1.8; }
.ret li:last-child { border-bottom:none; }
.ret li:before { content:'→'; position:absolute; inset-inline-start:0; color:var(--ac); font-weight:900; }
.ret li b { color:var(--txt); }
.cnum { text-align:center; color:var(--mut); font-weight:800; margin-top:12px; }
.fld { margin-bottom:12px; }
.fld label { display:block; font-weight:800; font-size:.85rem; margin-bottom:6px; }
.fld input, .fld select, .fld textarea { width:100%; background:var(--card2); border:1px solid var(--line); border-radius:12px;
  padding:12px 14px; color:var(--txt); font-family:inherit; font-size:.92rem; }
.fld textarea { min-height:70px; resize:vertical; }
.frow { display:flex; gap:10px; }
.frow .fld { flex:1; }
.radios { display:flex; gap:8px; flex-wrap:wrap; }
.radio { background:var(--card); border:1.5px solid var(--line); border-radius:999px; padding:8px 14px; font-size:.82rem;
  font-weight:700; color:var(--mut); cursor:pointer; }
.radio.on { background:var(--ac); border-color:transparent; color:#fff; }
/* cart */
.co { position:fixed; inset:0; background:rgba(15,23,42,.5); z-index:350; display:none; }
.co.open { display:block; }
.cd { position:fixed; top:0; bottom:0; inset-inline-end:0; width:400px; max-width:94vw; background:var(--card); z-index:351;
  display:none; flex-direction:column; box-shadow:-12px 0 40px rgba(0,0,0,.18); }
.cd.open { display:flex; }
.cd-head { display:flex; align-items:center; justify-content:space-between; padding:14px 18px; border-bottom:1px solid var(--line); }
.cd-head b { font-size:1.05rem; }
.cd-body { flex:1; overflow-y:auto; padding:12px 18px; }
.cd-empty { text-align:center; color:var(--mut); padding:40px 10px; font-size:.9rem; }
.ci { display:flex; align-items:center; gap:12px; padding:12px 0; border-bottom:1px dashed var(--line); }
.ci-emoji { font-size:1.6rem; }
.ci-tx { flex:1; min-width:0; }
.ci-tx b { display:block; font-size:.88rem; }
.ci-tx span { font-size:.8rem; color:var(--mut); }
.qty2 { display:flex; align-items:center; gap:8px; }
.qty2 button { width:26px; height:26px; border-radius:50%; border:1px solid var(--line); background:var(--card); color:var(--txt); font-size:.95rem; font-weight:800; }
.qty2 .qn { min-width:18px; text-align:center; font-weight:800; }
.cd-foot { padding:14px 18px; border-top:1px solid var(--line); background:var(--card2); }
.row-t { display:flex; justify-content:space-between; font-size:.88rem; margin-bottom:8px; color:var(--mut); }
.row-t b { color:var(--txt); }
.row-t.total { font-size:1.05rem; font-weight:900; color:var(--txt); margin-top:6px; }
.pts-row { background:rgba(201,162,75,.1); border:1px dashed rgba(201,162,75,.5); border-radius:10px; padding:8px 12px;
  font-size:.8rem; margin-bottom:10px; color:var(--gold); }
.pts-row select { background:var(--card); border:1px solid var(--line); border-radius:8px; color:var(--txt); padding:4px 6px; font-size:.78rem; margin-top:6px; }
/* fab */
.fab { position:fixed; bottom:20px; inset-inline-end:20px; z-index:300; width:58px; height:58px; border-radius:50%;
  background:var(--green); border:none; font-size:26px; box-shadow:0 12px 30px rgba(37,211,102,.4); display:flex;
  align-items:center; justify-content:center; }
.fab:hover { transform:scale(1.06); }
/* matchday */
.md-banner { background:linear-gradient(120deg,var(--ac) 0%, var(--ac2) 100%); color:#fff; border-radius:22px; padding:26px 28px;
  margin-bottom:26px; display:flex; align-items:center; gap:20px; flex-wrap:wrap; justify-content:space-between; }
.md-teams { display:flex; align-items:center; gap:16px; font-weight:900; font-size:1.2rem; }
.md-teams .md-vs { color:rgba(255,255,255,.85); font-size:.9rem; }
.md-count { font-size:1.1rem; font-weight:900; letter-spacing:2px; font-variant-numeric:tabular-nums; }
.md-bar { background:var(--ac); color:#fff; text-align:center; padding:7px 12px; font-size:.82rem; font-weight:800;
  display:flex; gap:10px; align-items:center; justify-content:center; flex-wrap:wrap; }
.md-bar .md-t { font-weight:900; }
/* drop */
.drop-banner { background:linear-gradient(120deg, #7C3AED 0%, #DB2777 100%); color:#fff; border-radius:22px; padding:26px 28px;
  margin-bottom:26px; text-align:center; position:relative; overflow:hidden; }
.drop-banner h2 { font-size:1.6rem; font-weight:900; }
.drop-count { display:flex; gap:12px; justify-content:center; margin-top:16px; flex-wrap:wrap; }
.drop-cell { background:rgba(255,255,255,.16); border-radius:14px; padding:10px 16px; min-width:72px; }
.drop-cell b { display:block; font-size:1.4rem; font-variant-numeric:tabular-nums; }
.drop-cell span { font-size:.72rem; opacity:.9; }
/* poll */
.poll { background:var(--card); border:1px solid var(--line); border-radius:20px; padding:24px; }
.poll-opt { display:flex; align-items:center; gap:12px; background:var(--card2); border:1.5px solid var(--line);
  border-radius:14px; padding:13px 16px; margin-bottom:10px; cursor:pointer; position:relative; overflow:hidden; }
.poll-opt:hover { border-color:var(--ac); }
.poll-opt .pf { width:40px; height:40px; border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:1.1rem; }
.poll-opt .pt { flex:1; font-weight:800; font-size:.92rem; }
.poll-opt .pv { font-weight:800; font-size:.8rem; color:var(--mut); }
.poll-opt .pbar { position:absolute; inset-block:0; inset-inline-start:0; width:0; background:color-mix(in srgb, var(--ac) 18%, transparent); transition:width .5s ease; z-index:0; }
.poll-opt > * { position:relative; z-index:1; }
.poll-win { text-align:center; padding:20px; }
.poll-win .big { font-size:2rem; font-weight:900; }
/* lightbox */
.lb { position:fixed; inset:0; background:rgba(4,7,12,.94); z-index:500; display:none; align-items:center; justify-content:center; cursor:zoom-out; }
.lb.open { display:flex; }
.lb img { max-width:92vw; max-height:92vh; border-radius:12px; }
/* welcome */
.welc { min-height:100vh; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center;
  padding:30px 20px; position:relative; overflow:hidden; background:var(--bg); }
.welc .ball { font-size:72px; }
.welc h1 { font-size:2rem; font-weight:900; margin-top:16px; line-height:1.5; }
.welc p { color:var(--mut); margin-top:12px; font-size:1rem; line-height:1.9; }
.wlang { display:flex; gap:14px; justify-content:center; margin-top:28px; flex-wrap:wrap; }
.wlang a { padding:14px 32px; border-radius:16px; font-weight:900; font-size:1rem; border:1.5px solid var(--line);
  background:var(--card); color:var(--txt); }
.wlang a:hover { border-color:var(--ac); transform:translateY(-2px); }
.wlang a:first-child { background:linear-gradient(90deg,var(--ac),var(--ac2)); border-color:transparent; color:#fff; }
.brand { margin-top:24px; color:var(--mut); font-size:.8rem; font-weight:800; letter-spacing:2px; }
/* ticket & track */
.ticket { max-width:640px; margin:0 auto; }
.tk { background:var(--card); border:1.5px solid var(--line); border-radius:24px; overflow:hidden; box-shadow:var(--sh2); }
.tk-top { padding:20px 24px; display:flex; align-items:center; justify-content:space-between; gap:10px; }
.tk-top .tlogo { font-weight:900; font-size:1.2rem; }
.tk-stub { position:relative; border-top:2px dashed var(--line); border-bottom:2px dashed var(--line); padding:18px 24px; }
.tk-stub:before, .tk-stub:after { content:''; position:absolute; width:22px; height:22px; border-radius:50%; background:var(--bg); top:50%; }
.tk-stub:before { inset-inline-start:-12px; transform:translateY(-50%); }
.tk-stub:after { inset-inline-end:-12px; transform:translateY(-50%); }
.tk-code { font-size:1.7rem; font-weight:900; text-align:center; color:var(--ac); }
.tk-row { display:flex; justify-content:space-between; gap:10px; font-size:.85rem; margin-top:6px; color:var(--mut); }
.tk-row b { color:var(--txt); }
.tk-items { padding:16px 24px; }
.tk-item { display:flex; justify-content:space-between; gap:10px; font-size:.88rem; padding:6px 0; border-bottom:1px dashed var(--line); }
.tk-item span { color:var(--mut); }
.tk-total { display:flex; justify-content:space-between; font-weight:900; font-size:1.05rem; padding:12px 24px; }
.tk-status { display:flex; align-items:center; justify-content:space-between; padding:14px 24px; background:var(--card2);
  font-weight:900; }
.tk-status .pill { background:var(--ok); color:#fff; padding:5px 12px; border-radius:999px; font-size:.78rem; }
.tk-qr { display:flex; justify-content:center; padding:18px; background:#fff; }
.tk-btns { display:grid; grid-template-columns:1fr 1fr; gap:10px; padding:16px 24px 22px; }
.tk-btns .btn { justify-content:center; }
.tk-foot { text-align:center; color:var(--mut); font-size:.74rem; padding-bottom:18px; }
.timeline { max-width:520px; margin:0 auto; }
.tl { display:flex; gap:16px; position:relative; padding-bottom:22px; }
.tl:last-child { padding-bottom:0; }
.tl .dot { width:22px; height:22px; border-radius:50%; background:var(--line); flex:none; margin-top:2px; position:relative; z-index:1; }
.tl.done .dot { background:var(--ok); }
.tl.cur .dot { background:var(--ac); box-shadow:0 0 0 5px color-mix(in srgb, var(--ac) 22%, transparent); }
.tl .dot:after { content:''; position:absolute; top:22px; inset-inline-start:10px; width:2px; height:1000px; background:var(--line); }
.tl:last-child .dot:after { display:none; }
.tl.done .dot:after { background:var(--ok); }
.tl .lt { font-weight:800; font-size:.95rem; }
.tl .ls { color:var(--mut); font-size:.82rem; }
/* settings modal rows */
.set-row { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px 0; border-bottom:1px solid var(--line); }
.set-row .st { font-weight:800; font-size:.92rem; }
.set-row .st small { display:block; color:var(--mut); font-weight:600; font-size:.76rem; }
.seg { display:flex; gap:6px; flex-wrap:wrap; }
.seg button { background:var(--card); border:1.5px solid var(--line); border-radius:999px; padding:8px 14px; font-size:.8rem;
  font-weight:800; color:var(--mut); }
.seg button.on { background:var(--ac); border-color:transparent; color:#fff; }
/* admin */
.adm { max-width:1080px; margin:0 auto; padding:24px 18px 60px; }
.adm-card { background:var(--card); border:1px solid var(--line); border-radius:18px; padding:18px; margin-bottom:16px; }
.adm-card h3 { font-size:1.05rem; font-weight:900; margin-bottom:12px; }
.adm table { width:100%; border-collapse:collapse; font-size:.85rem; }
.adm th { text-align:start; padding:8px; color:var(--mut); border-bottom:1px solid var(--line); }
.adm td { padding:8px; border-bottom:1px dashed var(--line); }
.adm input, .adm select { background:var(--card2); border:1px solid var(--line); border-radius:8px; color:var(--txt);
  padding:7px 10px; font-size:.85rem; font-family:inherit; }
.adm .mini { width:70px; }
.stat-cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-bottom:18px; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:16px; }
.stat b { font-size:1.5rem; display:block; }
.stat span { color:var(--mut); font-size:.8rem; }
.msg { background:#ECFDF5; border:1px solid #A7F3D0; color:#065F46; border-radius:12px; padding:10px 14px; margin-bottom:14px; font-size:.88rem; }
/* toast */
.toast { position:fixed; bottom:24px; inset-inline-start:50%; transform:translateX(-50%) translateY(80px); background:var(--txt);
  color:var(--bg); padding:12px 20px; border-radius:12px; font-weight:800; font-size:.9rem; z-index:600; opacity:0;
  transition:transform .25s ease, opacity .25s ease; max-width:90vw; text-align:center; }
.toast.show { transform:translateX(-50%) translateY(0); opacity:1; }
.img-search-tip { color:var(--mut); font-size:.78rem; margin-top:8px; }
.res-card { display:flex; align-items:center; gap:12px; background:var(--card); border:1px solid var(--line);
  border-radius:14px; padding:10px 14px; margin-bottom:10px; }
.res-card img { width:64px; height:64px; object-fit:cover; border-radius:10px; }
.res-card .rc-t { flex:1; }
.res-card .rc-t b { display:block; font-size:.92rem; }
.res-card .rc-t span { font-size:.8rem; color:var(--mut); }
.res-card .rc-p { font-weight:900; color:var(--ac); }
.res-card .rc-s { font-size:.72rem; color:var(--ok); font-weight:800; }
@media (max-width:900px) {
  .pg { grid-template-columns:1fr; }
  .gal { position:static; }
  .gmain img { height:340px; }
  .hero h1 { font-size:1.8rem; }
  .nav { order:3; width:100%; justify-content:center; }
}
/* success page */
.okpage { max-width:620px; margin:0 auto; }
.ok-card { background:var(--card); border:1px solid var(--line); border-radius:24px; padding:44px 24px; text-align:center; box-shadow:var(--sh2); }
.ok-anim { font-size:58px; animation:bounce .8s ease; }
@keyframes bounce { 0%{transform:scale(0)} 60%{transform:scale(1.25)} 100%{transform:scale(1)} }
.ok-card h1 { font-size:1.6rem; font-weight:900; margin-top:12px; }
.ok-code { font-size:1.5rem; font-weight:900; color:var(--ac); margin-top:10px; letter-spacing:1px; }
.ok-btns { display:flex; gap:10px; flex-wrap:wrap; justify-content:center; margin-top:24px; }
.ok-btns .btn { flex:1; min-width:200px; justify-content:center; }
/* penalty */
.pen-std { max-width:620px; margin:0 auto; text-align:center; }
.pen-head { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.pen-code { font-weight:900; font-size:1.15rem; color:var(--ac); }
.pen-pitch { position:relative; height:400px; border-radius:22px; overflow:hidden;
  background:linear-gradient(180deg,#14532d,#166534 55%,#15803d); box-shadow:var(--sh); user-select:none; }
.pen-stripes { position:absolute; inset:0; background:repeating-linear-gradient(0deg,transparent 0 46px,rgba(255,255,255,.05) 46px 92px); }
.pen-crowd { position:absolute; top:0; left:0; right:0; height:34px; background:repeating-linear-gradient(90deg,#0b3d23 0 26px,#123f2b 26px 52px); opacity:.7; }
.pen-lights { position:absolute; top:-40px; left:8%; width:42px; height:130px; background:linear-gradient(180deg,rgba(255,255,255,.9),transparent); border-radius:0 0 20px 20px; filter:blur(2px); opacity:.5; }
.pen-lights.right { left:auto; right:8%; }
.pen-goal { position:absolute; left:50%; top:44px; transform:translateX(-50%); width:340px; height:150px; border:5px solid #fff; border-top:none; border-radius:0 0 10px 10px;
  background:repeating-linear-gradient(90deg,rgba(255,255,255,.3) 0 18px,transparent 18px 36px),repeating-linear-gradient(0deg,rgba(255,255,255,.3) 0 18px,transparent 18px 36px); }
.pen-zone { position:absolute; width:70px; height:46px; transform:translate(-50%,-50%); border:2px dashed rgba(255,255,255,.55); border-radius:12px; cursor:pointer;
  display:flex; align-items:center; justify-content:center; font-size:.7rem; color:#fff; font-weight:800; background:rgba(0,0,0,.22); z-index:4; }
.pen-zone:hover { background:rgba(255,255,255,.25); }
.pen-zone.on { background:var(--ac); border-color:#fff; border-style:solid; }
.pen-ball { position:absolute; left:50%; top:352px; transform:translate(-50%,-50%); width:38px; height:38px; font-size:36px; line-height:38px; z-index:2;
  transition:left .5s cubic-bezier(.2,.8,.3,1), top .5s cubic-bezier(.2,.8,.3,1); }
.pen-keeper { position:absolute; left:50%; top:168px; transform:translate(-50%,-50%); width:76px; height:118px; z-index:3;
  filter:drop-shadow(0 8px 12px rgba(0,0,0,.4)); transition:left .5s cubic-bezier(.2,.8,.3,1), top .5s cubic-bezier(.2,.8,.3,1); }
.pen-keeper .kb { position:absolute; bottom:0; width:76px; height:94px; border-radius:20px 20px 10px 10px; background:linear-gradient(180deg,#facc15,#ca8a04); }
.pen-keeper .kh { position:absolute; top:2px; left:50%; transform:translateX(-50%); width:36px; height:34px; border-radius:50%; background:#fcd9b8; }
.pen-keeper .kd { position:absolute; top:46px; width:24px; height:30px; border-radius:12px; background:#facc15; }
.pen-keeper .kd.l { left:-12px; transform:rotate(28deg); } .pen-keeper .kd.r { right:-12px; transform:rotate(-28deg); }
.pen-ctrl { margin-top:16px; }
.pen-cta { display:flex; gap:10px; flex-wrap:wrap; justify-content:center; margin-top:14px; }
.pen-cta .btn { min-width:180px; justify-content:center; }
.pen-result { display:none; align-items:center; flex-direction:column; gap:10px; position:absolute; inset:0; background:rgba(2,6,23,.74); color:#fff; z-index:6; justify-content:center; border-radius:22px; }
.pen-result.show { display:flex; }
.pen-result .big { font-size:2.6rem; font-weight:900; }
.pen-result .pts { background:rgba(255,255,255,.14); border-radius:999px; padding:8px 20px; font-weight:900; }
.pen-note { color:var(--mut); font-size:.82rem; margin-top:10px; }
/* try it on */
.try-stage { position:relative; border-radius:16px; overflow:hidden; background:#0F172A; }
.try-stage canvas { display:block; width:100%; max-height:380px; }
.try-ai { position:absolute; top:10px; inset-inline-start:10px; background:rgba(0,0,0,.65); color:#fff; font-size:.72rem; font-weight:900; padding:5px 12px; border-radius:999px; }
/* reviews v2 */
.rat-dims { flex:1; min-width:220px; display:flex; flex-direction:column; gap:7px; }
.rv2-dim { display:flex; align-items:center; gap:10px; font-size:.8rem; font-weight:700; }
.rv2-dim .bar { flex:1; height:9px; border-radius:999px; background:var(--card2); overflow:hidden; }
.rv2-dim .bar i { display:block; height:100%; background:linear-gradient(90deg,var(--ac),var(--ac2)); border-radius:999px; }
.rv2-dim b { min-width:34px; text-align:end; color:var(--ac); }
.rv2-row { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:8px; }
.rv2-lbl { font-weight:800; font-size:.9rem; }
.rv-ver { display:inline-block; background:rgba(22,163,74,.12); color:var(--ok); border:1px solid rgba(22,163,74,.4); font-size:.66rem; font-weight:800; padding:2px 8px; border-radius:999px; margin-inline-start:6px; }
.rv-pend { display:inline-block; background:rgba(245,158,11,.12); color:#D97706; border:1px solid rgba(245,158,11,.5); font-size:.66rem; font-weight:800; padding:2px 8px; border-radius:999px; margin-inline-start:6px; }
.rv-meta { color:var(--mut); font-size:.76rem; margin-top:6px; }
/* order stadium */
.os-card { background:var(--card); border:1px solid var(--line); border-radius:20px; padding:22px 16px; margin-bottom:20px; }
.os-title { text-align:center; font-weight:900; font-size:1.05rem; letter-spacing:1px; }
.os-path { display:flex; align-items:center; justify-content:space-between; margin-top:28px; position:relative; }
.os-station { display:flex; flex-direction:column; align-items:center; gap:6px; font-size:.7rem; font-weight:800; color:var(--mut); text-align:center; width:76px; z-index:2; }
.os-station .ic { width:46px; height:46px; border-radius:50%; background:var(--card2); border:2px solid var(--line); display:flex; align-items:center; justify-content:center; font-size:1.3rem; }
.os-station.on .ic { background:linear-gradient(90deg,var(--ac),var(--ac2)); border-color:transparent; box-shadow:0 6px 16px color-mix(in srgb, var(--ac) 40%, transparent); }
.os-station.on { color:var(--txt); }
.os-seg { flex:1; height:6px; background:var(--line); border-radius:99px; position:relative; margin:0 4px; }
.os-seg.on { background:linear-gradient(90deg,var(--ac),var(--ac2)); }
.os-ball { position:absolute; top:-16px; left:0; transform:translateX(-50%); font-size:26px; transition:left 1s cubic-bezier(.3,.8,.3,1); z-index:3; }
.os-msg { text-align:center; font-weight:800; font-size:.95rem; margin-top:32px; min-height:24px; }
.os-goal { display:none; text-align:center; font-size:1.6rem; font-weight:900; color:var(--ac); margin-top:8px; position:relative; }
.os-rate { display:none; text-align:center; margin-top:14px; }
/* confetti */
.cf { position:absolute; top:-10px; width:9px; height:14px; border-radius:2px; z-index:7; animation:cfFall linear forwards; }
@keyframes cfFall { to { transform:translateY(120vh) rotate(720deg); opacity:0; } }
/* my alerts */
.al-box { max-width:560px; margin:0 auto; }
.al-item { display:flex; align-items:center; gap:12px; background:var(--card); border:1px solid var(--line); border-radius:16px; padding:14px 16px; margin-bottom:10px; }
.al-item .at { flex:1; }
.al-item .at b { display:block; font-size:.92rem; }
.al-item .at span { font-size:.78rem; color:var(--mut); }
.al-item .st { font-size:.74rem; font-weight:900; }
.al-item .st.wait { color:var(--gold); }
.al-item .st.sent { color:var(--ok); }
/* cheer */
.cheer-pop { position:fixed; inset:0; display:flex; align-items:center; justify-content:center; z-index:100; pointer-events:none; }
.cheer-pop span { font-size:3rem; font-weight:900; color:var(--ac); text-shadow:0 6px 30px rgba(0,0,0,.25); animation:cheerPop 1.4s ease; }
@keyframes cheerPop { 0%{transform:scale(.4);opacity:0} 25%{transform:scale(1.15);opacity:1} 55%{transform:scale(1);opacity:1} 100%{transform:scale(1.6);opacity:0} }
/* account */
.acc-nav { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:18px; }
.acc-btn { background:var(--card); border:1px solid var(--line); border-radius:999px; padding:9px 16px; font-weight:800; font-size:.85rem; cursor:pointer; color:var(--txt); }
.acc-btn:hover { border-color:var(--ac); }
.acc-sec { display:none; }
.acc-sec.on { display:block; }
.acc-szlist { display:flex; flex-direction:column; gap:10px; }
.acc-szrow { display:flex; align-items:center; justify-content:space-between; gap:12px; background:var(--card); border:1px solid var(--line); border-radius:14px; padding:12px 16px; }
.acc-szrow a { text-decoration:none; color:var(--txt); font-weight:800; }
.acc-szrow a:hover { color:var(--ac); }
.acc-box { max-width:740px; margin:0 auto; }
.acc-card { background:var(--card); border:1px solid var(--line); border-radius:18px; padding:16px; margin-bottom:12px; }
.acc-ord { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
.acc-ord .ao { flex:1; min-width:200px; }
.acc-ord .ao b { display:block; }
.acc-ord .ao span { font-size:.78rem; color:var(--mut); }
.acc-hero { background:linear-gradient(120deg,var(--ac),var(--ac2)); color:#fff; border-radius:22px; padding:22px; margin-bottom:18px; position:relative; overflow:hidden; }
.acc-hero h2 { font-size:1.5rem; font-weight:900; }
.acc-hero p { opacity:.92; font-size:.85rem; margin-top:6px; }
/* passport */
.pp-card { background:linear-gradient(135deg,#0B0F19,#1E3A5F); color:#fff; border-radius:20px; padding:22px; position:relative; overflow:hidden; }
.pp-card::after { content:'⚽'; position:absolute; font-size:7rem; opacity:.08; inset-inline-end:12px; bottom:-14px; }
.pp-id { letter-spacing:2px; font-weight:900; color:#F7D033; font-size:.9rem; }
.pp-level { font-size:1.4rem; font-weight:900; margin-top:6px; }
.pp-stamps { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
.pp-stamp { width:56px; height:56px; border-radius:14px; display:flex; align-items:center; justify-content:center; font-size:1.5rem; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.3); }
.pp-stamp.lock { filter:grayscale(1); opacity:.35; }
.pp-prog { height:10px; border-radius:999px; background:rgba(255,255,255,.16); margin-top:14px; overflow:hidden; }
.pp-prog i { display:block; height:100%; background:linear-gradient(90deg,#F7D033,#F97316); border-radius:999px; }
/* dna */
.dna-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:12px; }
.dna-cell { background:var(--card2); border:1px solid var(--line); border-radius:16px; padding:14px; text-align:center; }
.dna-cell b { display:block; font-size:1.05rem; margin-bottom:4px; }
.dna-cell span { font-size:.74rem; color:var(--mut); }
/* reorder */
.ro-item { display:flex; justify-content:space-between; gap:10px; background:var(--card2); border:1px solid var(--line); border-radius:12px; padding:10px 12px; margin-bottom:8px; }
.ro-item b { font-size:.9rem; } .ro-item span { font-size:.8rem; color:var(--mut); }
/* auth modal */
.auth-box { text-align:center; }
.auth-step2 { display:none; }
.auth-demo { display:none; background:#FEF3C7; border:1px solid #FCD34D; color:#78350F; border-radius:12px; padding:10px 12px; margin-top:10px; font-size:.82rem; }
.auth-demo b { font-size:1.3rem; letter-spacing:3px; }
.auth-new { display:none; font-size:.8rem; color:var(--mut); margin-top:8px; }
.phone-row { display:flex; gap:8px; }
.phone-row .cc-sel { flex:0 0 112px; border:1.5px solid var(--line); border-radius:12px; padding:0 10px; font-size:.9rem; font-weight:800; background:#fff; color:var(--txt); font-family:inherit; }
.phone-row input { flex:1; min-width:0; }
.auth-sent { font-size:.88rem; color:var(--mut); margin-bottom:12px; line-height:1.7; }
.auth-sent b { color:var(--txt); font-weight:900; }
.auth-actions { display:flex; gap:8px; justify-content:center; margin-top:12px; flex-wrap:wrap; }
.auth-actions .hbtn { font-size:.82rem; }
.btn[disabled] { opacity:.6; cursor:not-allowed; transform:none !important; }
/* ticket journey */
.tj { display:flex; align-items:center; gap:6px; margin-top:16px; flex-wrap:wrap; }
.tj .tj-step { flex:1; min-width:80px; text-align:center; }
.tj .tj-step b { display:block; font-size:.62rem; letter-spacing:1px; color:var(--mut); font-weight:900; margin-top:4px; }
.tj .tj-dot { width:26px; height:26px; border-radius:999px; margin:0 auto; background:var(--card2); border:2px solid var(--line); display:flex; align-items:center; justify-content:center; font-size:.8rem; }
.tj .tj-step.done .tj-dot { background:var(--ok); border-color:var(--ok); color:#fff; }
.tj .tj-step.cur .tj-dot { background:var(--ac); border-color:var(--ac); color:#fff; animation:pulse 1.4s infinite; }
@keyframes pulse { 0%,100%{box-shadow:0 0 0 0 rgba(225,29,72,.4)} 50%{box-shadow:0 0 0 8px rgba(225,29,72,0)} }
@media (max-width:560px) {
  .grid { grid-template-columns:repeat(2,1fr); gap:12px; }
  .pimg { height:170px; }
  .hero { padding:30px 20px; }
  .links3 { grid-template-columns:1fr; }
  .gmain img { height:300px; }
  .tk-btns { grid-template-columns:1fr; }
  #filtersBar { position:fixed; left:0; right:0; bottom:0; z-index:80; flex-direction:column; align-items:stretch;
    background:var(--card,#fff); border-top:1.5px solid var(--line,#e5e7eb); padding:18px 16px calc(18px + env(safe-area-inset-bottom));
    border-radius:20px 20px 0 0; box-shadow:0 -14px 40px rgba(2,6,23,.18);
    transform:translateY(110%); transition:transform .28s ease; }
  #filtersBar.open { transform:translateY(0); }
}
/* ============================== FOOTBALL STADIUM ATMOSPHERE ============================== */
body { overflow-x:hidden; }
.wrap { position:relative; z-index:1; }
.stadium-bg { position:fixed; inset:0; z-index:0; overflow:hidden; pointer-events:none; }
.stadium-bg .atm-lines { position:absolute; inset:0; opacity:.55;
  background:
    repeating-linear-gradient(0deg, transparent 0 68px, rgba(15,23,42,.03) 68px 69px),
    repeating-linear-gradient(90deg, transparent 0 68px, rgba(15,23,42,.03) 68px 69px); }
.stadium-bg .atm-circle { position:absolute; left:50%; top:56%; width:560px; height:560px; margin:-280px 0 0 -280px;
  border:3px dashed rgba(15,23,42,.06); border-radius:50%; }
.stadium-bg .atm-glow { position:absolute; border-radius:50%; filter:blur(80px); animation:atmGlow 16s ease-in-out infinite; }
.stadium-bg .atm-glow.g1 { width:430px; height:430px; left:-130px; top:-130px;
  background:radial-gradient(circle, var(--glow2, rgba(225,29,72,.16)), transparent 70%); }
.stadium-bg .atm-glow.g2 { width:390px; height:390px; right:-110px; top:26%;
  background:radial-gradient(circle, var(--glow3, rgba(56,130,246,.13)), transparent 70%); animation-delay:-5s; }
.stadium-bg .atm-glow.g3 { width:480px; height:480px; left:32%; bottom:-230px;
  background:radial-gradient(circle, rgba(37,211,102,.09), transparent 70%); animation-delay:-9s; }
@keyframes atmGlow { 0%,100% { transform:translate(0,0) scale(1); } 50% { transform:translate(46px,-34px) scale(1.1); } }
.stadium-bg .atm-ball { position:absolute; opacity:.15; filter:blur(.4px); animation:atmFloat linear infinite; }
@keyframes atmFloat {
  0% { transform:translate(0,0) rotate(0deg); }
  25% { transform:translate(28px,-42px) rotate(16deg); }
  50% { transform:translate(-18px,-84px) rotate(30deg); }
  75% { transform:translate(-34px,-42px) rotate(16deg); }
  100% { transform:translate(0,0) rotate(0deg); }
}
.stadium-bg .atm-dot { position:absolute; width:6px; height:6px; border-radius:50%; background:var(--ac,#E11D48);
  opacity:.16; animation:atmDot linear infinite; }
@keyframes atmDot { 0% { transform:translateY(0) scale(1); opacity:.14; } 50% { transform:translateY(-76px) scale(1.5); opacity:.32; } 100% { transform:translateY(0) scale(1); opacity:.14; } }
html[data-club] .stadium-bg .atm-dot { background:var(--ac); }
html[data-club] .stadium-bg .atm-circle { border-color:color-mix(in srgb, var(--ac) 22%, transparent); }
html[data-club] .stadium-bg .atm-glow.g1 { background:radial-gradient(circle, var(--glow, rgba(225,29,72,.2)), transparent 70%); }
html[data-club] .stadium-bg .atm-glow.g2 { background:radial-gradient(circle, color-mix(in srgb, var(--ac2) 26%, transparent), transparent 70%); }
@media (prefers-reduced-motion: reduce) {
  .stadium-bg .atm-ball, .stadium-bg .atm-dot, .stadium-bg .atm-glow, .stadium-bg .atm-circle, .stadium-bg .atm-lines { animation:none !important; }
  *, *::before, *::after { transition-duration:.01ms !important; animation-duration:.01ms !important; animation-iteration-count:1 !important; }
}
/* ============================== STICKY GLASS NAVBAR ============================== */
.hd { transition:background .3s ease, box-shadow .3s ease, border-color .3s ease; }
.hd.scrolled { background:rgba(255,255,255,.82); backdrop-filter:blur(16px) saturate(1.5);
  -webkit-backdrop-filter:blur(16px) saturate(1.5); box-shadow:0 6px 28px rgba(15,23,42,.08); border-bottom-color:transparent; }
html[data-theme="dark"] .hd.scrolled { background:rgba(11,15,25,.82); }
/* ============================== HERO ============================== */
.hero { background:
  radial-gradient(130% 110% at 12% 0%, color-mix(in srgb, var(--ac) 15%, transparent), transparent 58%),
  radial-gradient(110% 100% at 92% 100%, rgba(37,211,102,.07), transparent 60%),
  linear-gradient(120deg, var(--card) 0%, #F8FAFF 60%),
  repeating-linear-gradient(0deg, transparent 0 32px, rgba(15,23,42,.022) 32px 33px); }
.hero-tag { display:inline-flex; align-items:center; gap:9px; background:var(--card); border:1px solid var(--line);
  color:var(--ac); font-size:.72rem; font-weight:900; letter-spacing:2px; padding:7px 15px; border-radius:999px;
  margin-bottom:18px; box-shadow:var(--sh); }
.hero-tag .pulse { width:8px; height:8px; border-radius:50%; background:var(--ok); animation:pulse 2s infinite; }
.hero-ball { position:absolute; inset-inline-end:7%; top:50%; transform:translateY(-50%); width:150px; height:150px;
  font-size:150px; line-height:150px; text-align:center; filter:drop-shadow(0 24px 36px rgba(15,23,42,.3));
  animation:heroBall 9s ease-in-out infinite; pointer-events:none; }
.hero-ball .ring { position:absolute; inset:-20px; border-radius:50%; border:2px dashed color-mix(in srgb, var(--ac) 45%, transparent); animation:spin 26s linear infinite; }
@keyframes heroBall { 0%,100% { transform:translateY(-50%) translateX(0) rotate(-6deg); } 50% { transform:translateY(-60%) translateX(-16px) rotate(7deg); } }
@keyframes spin { to { transform:rotate(360deg); } }
html[data-club] .hero-ball { filter:drop-shadow(0 24px 36px var(--glow, rgba(225,29,72,.3))); }
/* ============================== CLUB PICKER ============================== */
#clubs { scroll-margin-top:92px; }
.clubs { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:16px; }
.clubcard { position:relative; display:flex; flex-direction:column; align-items:center; gap:9px; text-align:center;
  background:var(--card); border:1px solid var(--line); border-radius:22px; padding:22px 12px 18px; cursor:pointer;
  text-decoration:none; overflow:hidden; transition:transform .2s ease, box-shadow .28s ease, border-color .28s ease; }
.clubcard::before { content:''; position:absolute; inset:0;
  background:radial-gradient(130% 130% at 50% 0%, color-mix(in srgb, var(--cc,#E11D48) 18%, transparent), transparent 62%);
  opacity:0; transition:opacity .3s ease; }
.clubcard:hover { transform:translateY(-6px);
  border-color:color-mix(in srgb, var(--cc,#E11D48) 55%, var(--line));
  box-shadow:0 20px 44px color-mix(in srgb, var(--cc,#E11D48) 30%, transparent); }
.clubcard:hover::before { opacity:1; }
.cc-logo { width:66px; height:66px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:30px;
  background:linear-gradient(135deg, var(--cc,#E11D48), var(--cc2,#F97316)); box-shadow:0 12px 26px color-mix(in srgb, var(--cc,#E11D48) 38%, transparent);
  position:relative; z-index:1; }
.cc-logo .em { filter:drop-shadow(0 4px 8px rgba(15,23,42,.28)); line-height:1; }
.clubcard b { font-size:.95rem; font-weight:800; color:var(--txt); position:relative; z-index:1; }
.cc-count { font-size:.72rem; font-weight:700; color:var(--mut); position:relative; z-index:1; }
.cc-go { position:relative; z-index:1; font-size:.76rem; font-weight:900; color:var(--cc,#E11D48);
  opacity:0; transform:translateY(6px); transition:opacity .25s ease, transform .25s ease; }
.clubcard:hover .cc-go { opacity:1; transform:none; }
/* ============================== CLUB PAGE ============================== */
.club-banner { border-radius:26px; padding:40px 26px; color:#fff; text-align:center; position:relative; overflow:hidden;
  box-shadow:0 22px 50px var(--glow, rgba(225,29,72,.25)); }
.club-banner::after { content:''; position:absolute; inset:0;
  background:radial-gradient(120% 130% at 50% 0%, rgba(255,255,255,.14), transparent 55%); }
.club-banner .cb-emoji { font-size:64px; position:relative; z-index:1; display:block; filter:drop-shadow(0 10px 18px rgba(0,0,0,.28)); }
.club-banner h1 { font-size:2rem; font-weight:900; position:relative; z-index:1; margin-top:8px; }
.club-banner p { opacity:.92; position:relative; z-index:1; margin-top:6px; }
.club-banner .lightbtn { position:relative; z-index:1; margin-top:18px; background:#fff; color:#0F172A; }
.club-in { animation:clubIn .7s ease .55s both; }
@keyframes clubIn { from { opacity:0; transform:translateY(16px); } to { opacity:1; transform:none; } }
.bs-wrap { position:fixed; inset:0; pointer-events:none; z-index:400; overflow:hidden; }
.bs-wrap .bs-ball { position:absolute; top:44%; left:-70px; font-size:46px; animation:bsAcross 1s cubic-bezier(.25,.7,.25,1) .05s both;
  filter:drop-shadow(0 8px 16px rgba(0,0,0,.32)); }
@keyframes bsAcross { 0% { left:-70px; transform:translateY(0) rotate(0); opacity:1; } 70% { opacity:1; } 100% { left:calc(100% + 50px); transform:translateY(-30px) rotate(360deg); opacity:.2; } }
/* ============================== PRODUCT CARDS ============================== */
.scroll-row { display:flex; gap:18px; overflow-x:auto; padding-bottom:12px; scroll-snap-type:x proximity; scrollbar-width:thin; }
.scroll-row .pcard { flex:0 0 260px; scroll-snap-align:start; }
.pcard { transition:transform .18s ease, box-shadow .24s ease, border-color .24s ease; }
.pcard:hover { transform:translateY(-6px);
  box-shadow:0 22px 48px color-mix(in srgb, var(--pc, var(--ac)) 32%, transparent);
  border-color:color-mix(in srgb, var(--pc, var(--ac)) 55%, var(--line)); }
.pover { position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
  background:rgba(2,6,23,.34); opacity:0; transition:opacity .22s ease; z-index:2; }
.pover .pover-btn { background:#fff; color:#0F172A; font-weight:900; font-size:.86rem; padding:11px 22px; border-radius:999px;
  box-shadow:0 12px 28px rgba(0,0,0,.32); transform:translateY(8px); transition:transform .22s ease; }
.pcard:hover .pover { opacity:1; }
.pcard:hover .pover .pover-btn { transform:none; }
/* ============================== PRODUCT PAGE ENTRANCE ============================== */
.pg .gmain { box-shadow:0 26px 60px var(--glow, rgba(225,29,72,.2)); animation:prodIn .6s ease .15s both; }
@keyframes prodIn { from { opacity:0; transform:scale(.96) translateY(12px); } to { opacity:1; transform:none; } }
/* ============================== LOYALTY TEST ============================== */
.loyal { background:linear-gradient(135deg, var(--card), var(--card2)); border:1px solid var(--line);
  border-radius:26px; padding:32px 20px; text-align:center; position:relative; overflow:hidden; }
.loyal .loyal-q { font-size:1.3rem; font-weight:900; margin:10px auto 4px; max-width:640px; }
.loyal .loyal-sub { color:var(--mut); font-size:.88rem; }
.loyal-pick { display:flex; gap:10px; flex-wrap:wrap; justify-content:center; margin-top:20px; }
.loy-btn { display:flex; flex-direction:column; align-items:center; gap:6px; width:88px; padding:12px 6px;
  background:var(--card); border:1.5px solid var(--line); border-radius:16px; cursor:pointer; color:var(--txt);
  transition:transform .16s ease, border-color .2s ease, box-shadow .22s ease; }
.loy-btn .lb-em { font-size:26px; line-height:1; }
.loy-btn .lb-t { font-size:.68rem; font-weight:800; }
.loy-btn:hover { transform:translateY(-3px); border-color:color-mix(in srgb, var(--cc,#E11D48) 55%, var(--line)); }
.loy-btn.on { transform:translateY(-3px) scale(1.04); border-color:var(--cc,#E11D48);
  box-shadow:0 16px 32px color-mix(in srgb, var(--cc,#E11D48) 32%, transparent); }
.loyal-out { display:none; margin-top:18px; }
.loyal-out .great { font-size:1.2rem; font-weight:900; color:var(--ac); }
.loyal-out .loyal-go { margin-top:14px; }
/* ============================== SIZE BANNER ============================== */
.szsec-banner { display:flex; align-items:center; gap:18px; background:linear-gradient(120deg, var(--ac), var(--ac2));
  border-radius:24px; padding:26px 26px; color:#fff; box-shadow:0 20px 44px var(--glow, rgba(225,29,72,.32));
  position:relative; overflow:hidden; }
.szsec-banner::after { content:'👕'; position:absolute; font-size:7rem; opacity:.12; inset-inline-end:6%; top:-18px; }
.szsec-banner .big-ic { font-size:46px; }
.szsec-banner h2 { font-size:1.35rem; font-weight:900; }
.szsec-banner p { opacity:.94; font-size:.88rem; margin-top:4px; }
.szsec-banner .btn-light { margin-inline-start:auto; background:#fff; color:var(--ac); border:none; }
/* ============================== HOW TO ORDER STEPS ============================== */
.steps-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:16px; }
.step-card { position:relative; background:var(--card); border:1px solid var(--line); border-radius:20px;
  padding:24px 18px 20px; overflow:hidden; transition:transform .18s ease, box-shadow .22s ease, border-color .22s ease; }
.step-card:hover { transform:translateY(-4px); border-color:color-mix(in srgb, var(--ac) 45%, var(--line)); box-shadow:var(--sh2); }
.step-card .step-num { position:absolute; top:-16px; inset-inline-end:-6px; font-size:5rem; font-weight:900;
  color:var(--ac); opacity:.08; line-height:1; }
.step-card .step-ic { width:50px; height:50px; border-radius:15px; display:flex; align-items:center; justify-content:center;
  font-size:25px; background:linear-gradient(135deg, var(--ac), var(--ac2)); box-shadow:0 12px 24px var(--glow, rgba(225,29,72,.28)); }
.step-card h3 { font-size:1rem; font-weight:900; margin-top:13px; }
.step-card p { color:var(--mut); font-size:.82rem; line-height:1.7; margin-top:6px; }
/* ============================== DARK PITCH CTA ============================== */
.pitch-sec { position:relative; border-radius:28px; overflow:hidden; color:#fff; padding:60px 24px; text-align:center;
  background:radial-gradient(130% 150% at 50% 0%, #16340f 0%, #0b2410 55%, #07170d 100%); }
.pitch-sec .pitch-lines { position:absolute; inset:0;
  background:repeating-linear-gradient(0deg, transparent 0 52px, rgba(255,255,255,.05) 52px 53px),
  repeating-linear-gradient(90deg, transparent 0 52px, rgba(255,255,255,.05) 52px 53px); }
.pitch-sec .pitch-mid { position:absolute; left:50%; top:50%; width:400px; height:400px; transform:translate(-50%,-50%);
  border:2px solid rgba(255,255,255,.1); border-radius:50%; }
.pitch-sec .pitch-half { position:absolute; left:50%; top:0; bottom:0; width:400px; transform:translateX(-50%);
  border-left:2px solid rgba(255,255,255,.08); border-right:2px solid rgba(255,255,255,.08); }
.pitch-sec .pitch-ball { position:absolute; bottom:16px; inset-inline-end:24px; font-size:54px; opacity:.3; animation:atmFloat 12s linear infinite; }
.pitch-sec h2 { font-size:1.95rem; font-weight:900; position:relative; z-index:1; line-height:1.35; }
.pitch-sec .btn { position:relative; z-index:1; margin-top:22px; }
html[data-theme="dark"] .pitch-sec { background:radial-gradient(130% 150% at 50% 0%, #12310f 0%, #0a2010 55%, #05100a 100%); }
/* ============================== FOOTER ============================== */
.ft-in { text-align:right; }
.ft-grid { display:grid; grid-template-columns:1.4fr 1fr 1fr 1fr; gap:26px; text-align:right; }
.ft-col h4 { font-size:.95rem; font-weight:900; margin-bottom:14px; color:var(--txt); }
.ft-col a, .ft-col span.lk { display:block; color:var(--mut); font-size:.84rem; font-weight:700; margin-bottom:9px; cursor:pointer; }
.ft-col a:hover, .ft-col span.lk:hover { color:var(--ac); }
.ft-brand { font-size:1.5rem; font-weight:900; }
.ft-desc { color:var(--mut); font-size:.84rem; line-height:1.8; margin-top:10px; max-width:280px; }
.ft-social { display:flex; gap:10px; margin-top:14px; }
.ft-social a { width:38px; height:38px; border-radius:50%; background:var(--card2); border:1px solid var(--line);
  display:flex; align-items:center; justify-content:center; font-size:16px; }
.ft-copy { border-top:1px solid var(--line); margin-top:26px; padding-top:18px; text-align:center; }
html[dir="ltr"] .ft-in, html[dir="ltr"] .ft-grid, html[dir="ltr"] .ft-col { text-align:left; }
/* ============================== REVEAL + RESPONSIVE ============================== */
.rv { opacity:0; transform:translateY(22px); transition:opacity .6s ease, transform .6s ease; }
.rv.in { opacity:1; transform:none; }
@media (max-width:900px) {
  .ft-grid { grid-template-columns:1fr 1fr; }
}
@media (max-width:640px) {
  .hero-ball { width:96px; height:96px; font-size:96px; line-height:96px; opacity:.55; inset-inline-end:2%; }
  .hero-tag { font-size:.62rem; }
  .clubs { grid-template-columns:repeat(auto-fill,minmax(108px,1fr)); gap:10px; }
  .clubcard { padding:16px 8px 14px; }
  .cc-logo { width:56px; height:56px; font-size:26px; }
  .club-banner { padding:30px 16px; }
  .szsec-banner { flex-direction:column; align-items:flex-start; gap:12px; }
  .szsec-banner .btn-light { margin-inline-start:0; }
  .pitch-sec h2 { font-size:1.4rem; }
  .ft-grid { grid-template-columns:1fr; gap:22px; }
  .ft-desc { max-width:100%; }
}
/* ============================== LUXURY THEME (BLACK / WHITE / GOLD) ============================== */
:root {
  --bg:#FFFFFF; --card:#FFFFFF; --card2:#F6F6F4; --line:#E7E5E0; --txt:#0C0C0D; --mut:#6B6B74;
  --brand1:#C9A24B; --brand2:#A8852E; --green:#25D366; --gold:#C9A24B; --ok:#16A34A; --err:#DC2626;
  --ac:#C9A24B; --ac2:#A8852E; --dark:#0B0B0C;
  --sh:0 6px 24px rgba(12,12,13,.07); --sh2:0 16px 42px rgba(12,12,13,.13);
  --glow:rgba(201,162,75,.35);
}
html[data-theme="dark"] { --bg:#0C0C0D; --card:#141416; --card2:#1D1D21; --line:#2A2A30; --txt:#F5F5F4; --mut:#A1A1AA; }
/* header */
.hd { background:#0B0B0C; border-bottom:1px solid #232326; box-shadow:0 2px 18px rgba(0,0,0,.28); }
html[data-club] .hd::after { background:linear-gradient(90deg,#C9A24B,#F5D97A); }
.logo { color:#fff; }
.logo .ball { filter:drop-shadow(0 0 6px rgba(201,162,75,.6)); }
.nv { color:#B8B8BF; }
.nv:hover { color:#fff; background:rgba(255,255,255,.08); }
.nv.on { background:linear-gradient(90deg,#C9A24B,#E2C26C); color:#0B0B0C; }
.hbtn { background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.14); color:#E9E9EC; }
.hbtn:hover { border-color:#C9A24B; color:#fff; }
.hcount { background:#C9A24B; color:#0B0B0C; }
.hd-search { width:100%; display:flex; justify-content:center; margin-top:8px; }
.hd-sbox { max-width:560px; width:100%; background:rgba(255,255,255,.07); border:1.5px solid rgba(255,255,255,.16); }
.hd-sbox input { color:#fff; }
.hd-sbox input::placeholder { color:#8F8F96; }
.hd-sbox button { background:linear-gradient(90deg,#C9A24B,#E2C26C); color:#0B0B0C; border-radius:10px; }
/* buttons */
.btn.pri { background:linear-gradient(90deg,#C9A24B,#E2C26C); color:#0B0B0C; box-shadow:0 12px 30px rgba(201,162,75,.35); }
.btn.pri:hover { transform:translateY(-2px); }
.btn.dark { background:#0B0B0C; color:#fff; border:1px solid #0B0B0C; box-shadow:0 12px 28px rgba(12,12,13,.22); }
.btn.dark:hover { transform:translateY(-2px); background:#1D1D20; }
.btn.ghost { background:#fff; border:1.5px solid #DCD8CF; color:#0B0B0C; }
.btn.ghost:hover { border-color:#C9A24B; color:#A8852E; }
/* hero: night stadium */
.hero { border:1px solid var(--line); border-radius:26px; position:relative; overflow:hidden;
  background:radial-gradient(1100px 520px at 78% -20%, rgba(226,194,108,.20), transparent 60%),
             radial-gradient(900px 500px at 8% 120%, rgba(201,162,75,.10), transparent 55%),
             linear-gradient(120deg,#101014 0%, #1A1A1F 58%, #26201A 100%);
  color:#F5F5F4; padding:54px 44px; margin-bottom:26px; }
.hero::before { content:''; position:absolute; inset:0; pointer-events:none; opacity:.5;
  background:repeating-linear-gradient(0deg, transparent 0 34px, rgba(255,255,255,.025) 34px 36px),
             radial-gradient(circle at 50% 125%, rgba(226,194,108,.28), transparent 55%);
  animation:luxGlow 12s ease-in-out infinite; }
@keyframes luxGlow { 0%,100% { opacity:.35; } 50% { opacity:.6; } }
.hero h1 { color:#F5F5F4; font-size:2.5rem; position:relative; z-index:1; }
.hero h1 .g { background:linear-gradient(90deg,#E2C26C,#C9A24B); -webkit-background-clip:text; background-clip:text; color:transparent; }
.hero p { color:#C9C9CF; position:relative; z-index:1; }
.hero-tag { color:#E2C26C; position:relative; z-index:1; }
.hero .btn.ghost { background:rgba(255,255,255,.06); border-color:rgba(255,255,255,.2); color:#F5F5F4; }
.hero .btn.ghost:hover { border-color:#E2C26C; color:#E2C26C; }
.hero-btns { position:relative; z-index:1; }
.hero-ball { opacity:.2; position:absolute; inset-inline-end:6%; top:50%; transform:translateY(-50%); }
/* features strip */
.feat-bar { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; background:#fff; border:1px solid var(--line);
  border-radius:20px; padding:20px 18px; margin-bottom:30px; box-shadow:var(--sh); }
.feat { display:flex; align-items:center; gap:12px; }
.feat .fic { width:46px; height:46px; border-radius:14px; background:#0B0B0C; color:#E2C26C; font-size:21px;
  display:flex; align-items:center; justify-content:center; flex:none; }
.feat b { font-size:.92rem; font-weight:800; display:block; }
.feat span { font-size:.78rem; color:var(--mut); }
@media (max-width:720px){ .feat-bar { grid-template-columns:1fr 1fr; gap:14px 10px; } .feat .fic{ width:40px; height:40px; font-size:18px; } }
/* shop layout */
.shop-wrap { display:grid; grid-template-columns:268px 1fr; gap:26px; align-items:start; }
.shop-main { min-width:0; }
@media (max-width:900px){ .shop-wrap { grid-template-columns:1fr; } }
/* filter panel */
.filters-panel { background:#fff; border:1px solid var(--line); border-radius:20px; padding:18px 16px; box-shadow:var(--sh); }
.fp-title { font-weight:900; font-size:1.02rem; display:flex; align-items:center; gap:8px;
  padding-bottom:12px; border-bottom:2px solid #0B0B0C; margin-bottom:14px; }
.fp-sec { margin-bottom:16px; }
.fp-lbl { font-size:.84rem; font-weight:800; margin-bottom:10px; display:flex; align-items:center; gap:6px; color:var(--txt); }
.fp-colors { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.col-dot { width:26px; height:26px; border-radius:50%; border:2px solid #fff; box-shadow:0 0 0 1.5px var(--line);
  cursor:pointer; transition:transform .15s ease, box-shadow .15s ease; }
.col-dot:hover { transform:scale(1.15); }
.col-dot.on { box-shadow:0 0 0 2.5px #0B0B0C; transform:scale(1.1); }
.col-dot.hide { display:none; }
.col-more { background:none; border:none; color:#A8852E; font-weight:800; font-size:.78rem; cursor:pointer; padding:4px 2px; }
.fp-cats { display:flex; flex-direction:column; gap:8px; }
.cat-opt { display:flex; align-items:center; gap:9px; font-size:.88rem; font-weight:700; color:var(--mut); cursor:pointer; }
.cat-opt input { accent-color:#0B0B0C; width:16px; height:16px; }
.cat-opt.on { color:var(--txt); }
.fp-clubs { display:flex; flex-direction:column; gap:6px; }
.club-opt { display:flex; align-items:center; gap:8px; font-size:.85rem; font-weight:700; color:var(--mut);
  cursor:pointer; padding:6px 8px; border-radius:10px; }
.club-opt:hover { background:var(--card2); }
.club-opt.on { background:#0B0B0C; color:#fff; }
.fp-sizes { display:flex; flex-wrap:wrap; gap:7px; }
.sz-btn { min-width:38px; text-align:center; padding:7px 8px; border-radius:9px; border:1.5px solid var(--line);
  background:#fff; font-weight:800; font-size:.8rem; cursor:pointer; color:var(--txt); }
.sz-btn:hover { border-color:#C9A24B; }
.sz-btn.on { background:#0B0B0C; border-color:#0B0B0C; color:#fff; }
details.fp-acc { border-top:1px solid var(--line); padding-top:12px; }
details.fp-acc summary { list-style:none; cursor:pointer; font-size:.84rem; font-weight:800;
  display:flex; justify-content:space-between; align-items:center; }
details.fp-acc summary::-webkit-details-marker { display:none; }
details.fp-acc summary::after { content:'+'; color:#A8852E; font-weight:900; }
details.fp-acc[open] summary::after { content:'−'; }
.fp-colors.show .col-dot.hide { display:inline-flex; }
.btn.dark { background:linear-gradient(90deg,#0B0B0C,#1F1F24); color:#E2C26C; border:1.5px solid #C9A24B; }
.btn.dark:hover { transform:translateY(-2px); box-shadow:0 12px 26px rgba(12,12,13,.3); }
.fp-apply { width:100%; justify-content:center; margin-top:8px; font-size:.92rem; }
@media (min-width:561px) { .fbtn { display:none !important; } }
/* sort bar */
.sort-bar { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:16px; }
.sort-bar .sort-lbl { font-size:.9rem; font-weight:800; color:var(--txt); }
select.sort { border:1.5px solid var(--line); border-radius:12px; padding:9px 14px; font-size:.85rem;
  font-weight:800; background:#fff; color:var(--txt); font-family:inherit; }
/* product card */
.pcard { background:#fff; border:1px solid var(--line); border-radius:18px; overflow:hidden; box-shadow:var(--sh); }
.pcard:hover { transform:translateY(-5px); box-shadow:var(--sh2); border-color:#D8D3C6; }
.pimg { height:210px; background:#FBFBFA; }
.badge.best { background:linear-gradient(90deg,#0B0B0C,#2A2A2E); color:#E2C26C; }
.badge.new { background:linear-gradient(90deg,#C9A24B,#E2C26C); color:#0B0B0C; }
.badge.offer { background:linear-gradient(90deg,#1F7A4D,#2E9B63); color:#fff; }
.badge.soldout { background:#8A8A90; }
.heart { background:rgba(255,255,255,.94); box-shadow:0 4px 12px rgba(12,12,13,.14); }
.heart.on { color:#C0344E; }
.pbody { padding:13px 14px 14px; }
.pcat { color:#A8852E; }
.pbody h3 { font-size:1rem; }
.pfoot b { font-size:1rem; color:#0B0B0C; }
.pview { color:#6B6B74; }
.pcard:hover .pview { color:#A8852E; }
.sizes-row { display:flex; gap:6px; flex-wrap:wrap; margin-top:9px; }
.sz-pill { min-width:30px; text-align:center; font-size:.68rem; font-weight:800; padding:4px 5px;
  border-radius:7px; border:1px solid var(--line); color:var(--mut); background:#fff; }
.sz-pill.oos { opacity:.35; text-decoration:line-through; }
.pcols { display:flex; gap:6px; margin-top:9px; align-items:center; }
.pdot { width:14px; height:14px; border-radius:50%; border:1px solid rgba(0,0,0,.14); }
.sel { background:#fff; border:1.5px solid var(--line); }
.chip { background:#fff; border:1.5px solid var(--line); color:var(--mut); }
.chip.on { background:#0B0B0C; color:#fff; }
.sec-head h2 .bar { background:linear-gradient(180deg,#C9A24B,#E2C26C); }
/* footer */
.ft { background:#0B0B0C; border-top:none; color:#D6D6DC; }
.ft-brand { color:#fff; }
.ft-copy, .ft-col a, .ft-col span.lk, .ft-title, .ft-desc, .ft-links a { color:#9A9AA3; }
.ft-col a:hover, .ft-col span.lk:hover, .ft-links a:hover { color:#E2C26C; }
.ft-social a { background:rgba(255,255,255,.07); border-color:rgba(255,255,255,.12); }
.ft-copy { border-color:#232326; }
</style>"""

BASE_JS = """<script>
var GX = __GX__;
function gxT(k){ return GX.T[k]||k; }
function $(id){ return document.getElementById(id); }
function toast(m){ var t=$('toast'); if(!t){ t=document.createElement('div'); t.id='toast'; t.className='toast'; document.body.appendChild(t);} t.textContent=m; t.classList.add('show'); clearTimeout(t._h); t._h=setTimeout(function(){ t.classList.remove('show'); },2600); }
function gxGet(k,d){ try{ var v=localStorage.getItem(k); return v===null?d:JSON.parse(v);}catch(e){return d;} }
function gxSet(k,v){ try{ localStorage.setItem(k,JSON.stringify(v)); }catch(e){} }
function gxDev(){ var d=gxGet('gx_device',null); if(!d){ d='d'+Math.random().toString(36).slice(2)+Date.now().toString(36); gxSet('gx_device',d); } return d; }
/* ---------- theme & font ---------- */
function applyPrefs(){
  var th=gxGet('gx_theme','light'); document.documentElement.setAttribute('data-theme',th);
  var fs=gxGet('gx_font','b'); document.documentElement.setAttribute('data-font',fs);
  var club=gxGet('gx_club',null); if(club) document.documentElement.setAttribute('data-club',club);
}
function setTheme(t){ gxSet('gx_theme',t); applyPrefs(); syncPrefs(); }
function setFont(f){ gxSet('gx_font',f); applyPrefs(); syncPrefs(); }
function setMyClub(cid){ gxSet('gx_club',cid); applyPrefs(); syncPrefs(); if(cid) toast(gxT('md_choice_ok')); }
function syncPrefs(){
  var th=gxGet('gx_theme','light'), fs=gxGet('gx_font','b'), club=gxGet('gx_club',null);
  var rows=document.querySelectorAll('.seg[data-seg]');
  rows.forEach(function(row){
    var name=row.getAttribute('data-seg'); var val = name==='theme'?th:(name==='font'?fs:club);
    row.querySelectorAll('button').forEach(function(b){ b.classList.toggle('on', b.getAttribute('data-v')===val); });
  });
}
function setLang(l){ document.cookie='lang='+l+';path=/;max-age=31536000;SameSite=Lax'; location.href='/home'; }
function scrollTop(){ window.scrollTo({top:0,behavior:'smooth'}); }
function goSec(id){ var el=$(id); if(el) el.scrollIntoView({behavior:'smooth'}); }
function openModal(id){ var m=$(id); if(m) m.classList.add('open'); }
function closeModal(id){ var m=$(id); if(m) m.classList.remove('open'); }
function toggleMenu(){ var n=$('topnav'); if(n) n.classList.toggle('open'); }
function closeMenu(){ var n=$('topnav'); if(n) n.classList.remove('open'); }
/* ---------- stadium atmosphere: glass navbar + scroll reveal ---------- */
function onScrollHeader(){ var hd=document.querySelector('.hd'); if(hd) hd.classList.toggle('scrolled', window.scrollY>10); }
window.addEventListener('scroll', onScrollHeader, {passive:true});
onScrollHeader();
function initReveal(){
  var els=document.querySelectorAll('.rv');
  if(!('IntersectionObserver' in window)){ els.forEach(function(el){ el.classList.add('in'); }); return; }
  var io=new IntersectionObserver(function(es){ es.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); } }); }, {threshold:.08});
  els.forEach(function(el){ io.observe(el); });
}
document.addEventListener('DOMContentLoaded', initReveal);
/* ---------- loyalty test ---------- */
function pickLoyal(cid,btn){
  document.querySelectorAll('.loy-btn').forEach(function(b){ b.classList.remove('on'); });
  if(btn) btn.classList.add('on');
  var go=$('loyGo'), out=$('loyOut'), msg=$('loyMsg');
  if(msg && GX.clubs && GX.clubs[cid]) msg.textContent=GX.clubs[cid][GX.lang==='ar'?'ar':'en'];
  if(go) go.href='/club/'+cid;
  if(out) out.style.display='block';
}
function esc(s){ var d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }
function pmoney(v){ return (Math.round(v*100)/100); }
/* ---------- search & filters ---------- */
var filters={club:'all',type:'all',size:'all',color:'all',cat:'all',fav:false};
function gxStock(c){ try{ return JSON.parse(c.getAttribute('data-stock')||'{}'); }catch(e){ return {}; } }
function applyFilters(){
  var q=((($('sq')||{}).value)||'').trim().toLowerCase();
  var cards=document.querySelectorAll('.pcard');
  var shown=0;
  cards.forEach(function(c){
    var ok=true;
    if(filters.fav && gxGet('gx_favs',[]).indexOf(c.getAttribute('data-id'))===-1) ok=false;
    if(ok && filters.club!=='all' && c.getAttribute('data-club')!==filters.club) ok=false;
    if(ok && filters.size!=='all'){
      var st=gxStock(c); if(!(st[filters.size]>0)) ok=false;
    }
    if(ok && filters.color!=='all' && c.getAttribute('data-col')!==filters.color) ok=false;
    if(ok && filters.cat!=='all' && !hasB(c,filters.cat)) ok=false;
    if(ok && q){
      var hay=((c.getAttribute('data-name')||'')+' '+(c.getAttribute('data-clubn')||'')).toLowerCase();
      if(hay.indexOf(q)===-1) ok=false;
    }
    c.style.display=ok?'':'none'; if(ok) shown++;
  });
  var e=$('searchNone'); if(e){ e.style.display=shown?'none':'block'; }
}
function setColorFilter(el){
  var v=el.getAttribute('data-col');
  filters.color=(filters.color===v?'all':v);
  document.querySelectorAll('.col-dot').forEach(function(x){x.classList.toggle('on',x===el&&filters.color!=='all');});
  applyFilters();
}
function moreColors(){
  var pc=document.querySelector('.fp-colors'); if(!pc) return;
  pc.classList.add('show');
  var cm=$('colMore'); if(cm) cm.style.display='none';
}
function setFilter(k,v,el){
  filters[k]=(filters[k]===v?'all':v);
  if(el){
    var par=el.parentElement;
    par.querySelectorAll('.club-opt,.sz-btn').forEach(function(x){x.classList.remove('on');});
    if(filters[k]!=='all') el.classList.add('on');
  }
  applyFilters();
}
function clearFilters(){
  filters={club:'all',type:'all',size:'all',color:'all',cat:'all',fav:false};
  document.querySelectorAll('.club-opt.on,.sz-btn.on,.col-dot.on').forEach(function(x){x.classList.remove('on');});
  document.querySelectorAll('input[name="fpcat"]').forEach(function(r){r.checked=false;});
  var sq=$('sq'); if(sq) sq.value='';
  applyFilters();
}
/* ---------- sorting & filters drawer ---------- */
function hasB(c,b){ return (','+((c.getAttribute('data-badge'))||'')+',').indexOf(','+b+',')>-1; }
function applySort(){
  var v=((($('sortSel')||{}).value)||'best');
  document.querySelectorAll('.grid').forEach(function(g){
    var cards=[].slice.call(g.querySelectorAll('.pcard'));
    if(!cards.length) return;
    if(v==='lo') cards.sort(function(a,b){return (parseFloat(a.getAttribute('data-price'))||0)-(parseFloat(b.getAttribute('data-price'))||0);});
    else if(v==='hi') cards.sort(function(a,b){return (parseFloat(b.getAttribute('data-price'))||0)-(parseFloat(a.getAttribute('data-price'))||0);});
    else if(v==='best') cards.sort(function(a,b){return (hasB(a,'best')?0:1)-(hasB(b,'best')?0:1);});
    else if(v==='new') cards.sort(function(a,b){return (parseInt(b.getAttribute('data-order'))||0)-(parseInt(a.getAttribute('data-order'))||0);});
    cards.forEach(function(c){ g.appendChild(c); });
  });
  applyFilters();
}
function toggleFilters(force){
  var bar=$('filtersBar'); if(!bar) return;
  var open=(force===false)?false:(bar.classList.toggle('open'));
  if(force===false) bar.classList.remove('open');
  else if(force===true) bar.classList.add('open');
  var fb=document.querySelector('.fbtn'); if(fb){ fb.classList.toggle('on',bar.classList.contains('open')); }
}
/* ---------- favorites ---------- */
function toggleFav(id,btn){
  var f=gxGet('gx_favs',[]); var i=f.indexOf(id);
  if(i>-1){ f.splice(i,1); } else { f.push(id); }
  gxSet('gx_favs',f);
  if(btn) btn.classList.toggle('on', i===-1);
  if(btn){ btn.innerHTML = i===-1?'❤':'🤍'; }
  renderFavs();
  if(filters.fav) applyFilters();
  if(GX.user){ favSync(f); }
}
function favSync(f){
  fetch('/api/favs',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({favs:f})}).catch(function(){});
}
function renderFavs(){ var n=gxGet('gx_favs',[]).length; var b=$('favcount'); if(b){ b.textContent=n; b.style.display=n?'flex':'none'; } }
function openFavs(){
  var onHome=!!document.querySelector('.grid') && location.pathname==='/home';
  if(onHome){
    if(!filters.fav){
      filters.fav=true;
      applyFilters();
    }
    window.scrollTo({top:0,behavior:'smooth'});
  } else { location.href='/favorites'; }
}
function renderFavPageGuest(){
  var box=$('favPage'); if(!box) return;
  var favs=gxGet('gx_favs',[]);
  var html='';
  if(!favs.length){ box.innerHTML='<p class="mnote">'+gxT('fav_empty')+'</p>'; return; }
  favs.forEach(function(id){
    var p=GX.products.find(function(x){return x.id===id;}); if(!p) return;
    html+='<div class="pcard" data-id="'+p.id+'">'
      +'<button class="heart on" onclick="toggleFav(\''+p.id+'\',this)">❤</button>'
      +'<a href="/product/'+p.id+'"><div class="pimg" style="background:linear-gradient(135deg,'+p.colors[0]+','+p.colors[1]+')">'
      +'<img src="/img/'+p.imgs[0]+'" alt=""></div></a>'
      +'<div class="pbody"><span class="pcat">'+(p.kind==='mug'?gxT('cat_mug'):gxT('cat_jersey'))+'</span><h3>'+esc(p[GX.lang==='ar'?'name_ar':'name_en'])+'</h3>'
      +'<div class="pfoot"><b>'+p.price+' '+GX.cur+'</b><a class="pview" href="/product/'+p.id+'">'+gxT('view')+' ←</a></div></div></div>';
  });
  box.innerHTML=html;
}
/* ---------- gallery ---------- */
var gi=0,gN=0;
function setGal(i,arr){ gi=i; gN=arr.length; var img=$('gmain'); if(!img) return;
  img.src='/img/'+arr[i]; var gc=$('gcount'); if(gc) gc.textContent=(i+1)+' '+gxT('img_of')+' '+gN;
  var t=$('gthumbs'); if(t){ var h=''; for(var k=0;k<gN;k++){ h+="<img src='/img/"+arr[k]+"' class='"+(k===i?'on':'')+"' onclick='setGal("+k+",GARR)' alt=''>"; } t.innerHTML=h; }
  var g1=$('garr'); if(g1) g1.style.display=gN>1?'':'none'; var g2=$('garr2'); if(g2) g2.style.display=gN>1?'':'none';
}
function movGal(d){ if(!gN) return; setGal((gi+d+gN)%gN,GARR); }
function openLB(src){ var img=$('lbimg'); img.src=src; $('lb').classList.add('open'); }
function closeLB(){ $('lb').classList.remove('open'); }
/* ---------- product page: size, stock, cart ---------- */
var selSize=null;
function stockOf(pid){ var p=GX.products.find(function(x){return x.id===pid;}); return p?p.stock:{}; }
function availOf(pid){ var s=stockOf(pid), out=[]; for(var k in s){ if(s[k]>0) out.push(k);} return out; }
function selectSize(el){
  if(el.classList.contains('oos')){
    var pid=$('prod_id')?$('prod_id').value:'';
    notifyModal(pid,el.getAttribute('data-sz'));
    return;
  }
  document.querySelectorAll('.size-chip').forEach(function(x){x.classList.remove('on');});
  el.classList.add('on'); selSize=el.getAttribute('data-sz');
}
function chgQ(d){ var q=$('qty'); if(!q) return; var v=parseInt(q.textContent,10)+d; if(v<1)v=1; if(v>99)v=99; q.textContent=v; }
function notifyModal(pid,size){ $('nf_prod').value=pid; $('nf_size').value=size; openModal('m-notify'); }
function submitNotify(){
  var p=$('nf_prod').value, sz=$('nf_size').value, ph=$('nf_phone').value.trim(), cc=$('nf_cc').value;
  if(ph.length<6){ toast(gxT('co_required')); return; }
  fetch('/api/notify',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({product:p,size:sz,phone:cc+ph})}).then(function(r){return r.json();}).then(function(d){
    closeModal('m-notify'); toast(gxT('notify_ok'));
  });
}
function addCart(id,size,qty){
  if(!size){ toast(gxT('size_required')); return; }
  if(GX.user) saveSize(id,size);
  var cart=gxGet('gx_cart',[]); var f=cart.find(function(x){return x.id===id&&x.size===size;});
  if(f){ f.qty+=qty; } else { cart.push({id:id,size:size,qty:qty}); }
  gxSet('gx_cart',cart); renderCart(); toast(gxT('add')+' ✓');
}
function saveSize(pid,sz){
  fetch('/api/size/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product:pid,size:sz})})
  .catch(function(){});
}
function changeCart(id,size,d){ var cart=gxGet('gx_cart',[]); var i=cart.findIndex(function(x){return x.id===id&&x.size===size;});
  if(i>-1){ cart[i].qty+=d; if(cart[i].qty<=0) cart.splice(i,1); } gxSet('gx_cart',cart); renderCart(); }
function clearCart(){ gxSet('gx_cart',[]); renderCart(); }
function cartCount(){ return gxGet('gx_cart',[]).reduce(function(a,x){return a+x.qty;},0); }
function cartTotals(){
  var cart=gxGet('gx_cart',[]); var sub=0;
  cart.forEach(function(x){ var p=GX.products.find(function(y){return y.id===x.id;}); if(p) sub+=p.price*x.qty; });
  return {sub:sub, delivery: cart.length? GX.delivery : 0, total: sub + (cart.length? GX.delivery:0)};
}
function openCart(){ renderCart(); $('co').classList.add('open'); $('cd').classList.add('open'); }
function closeCart(){ $('co').classList.remove('open'); $('cd').classList.remove('open'); }
function pname(p,sz){ return p.name_ar||p.name_en; }
function renderCart(){
  var n=cartCount(); var b=$('cbadge'); if(b){ b.textContent=n; b.style.display=n?'flex':'none'; }
  var box=$('cdb'); if(!box) return;
  var cart=gxGet('gx_cart',[]);
  if(!cart.length){ box.innerHTML='<div class="cd-empty">🛒<br>'+gxT('cart_empty')+'</div>'; fillFoot(); return; }
  var html='';
  cart.forEach(function(x){ var p=GX.products.find(function(y){return y.id===x.id;}); if(!p) return;
    html+='<div class="ci"><div class="ci-emoji">'+p.emoji+'</div><div class="ci-tx"><b>'+esc(pname(p,x.size))+'</b>'
      +'<span>'+(p.kind!=='mug'? (gxT('size_w')+x.size+' · ') : '')+gxT('qty_w')+x.qty+'</span></div>'
      +'<div class="qty2"><button onclick="changeCart(\''+p.id+'\',\''+x.size+'\',-1)">−</button><span class="qn">'+x.qty+'</span>'
      +'<button onclick="changeCart(\''+p.id+'\',\''+x.size+'\',1)">+</button></div>'
      +'<b style="color:var(--ac)">'+pmoney(p.price*x.qty)+' '+GX.cur+'</b></div>';
  });
  box.innerHTML=html; fillFoot();
}
function renderCartPage(){
  var box=$('cartPage'); if(!box) return;
  var cart=gxGet('gx_cart',[]);
  var html='';
  if(!cart.length){
    box.innerHTML='<div class="cd-empty" style="padding:60px 0">🛒<br>'+gxT('cart_empty')+'</div>'
      +'<div style="text-align:center;margin-top:8px"><a class="btn pri" href="/products">'+gxT('hero_cta_j')+'</a></div>';
    return;
  }
  cart.forEach(function(x){ var p=GX.products.find(function(y){return y.id===x.id;}); if(!p) return;
    html+='<div class="ci"><div class="ci-emoji">'+p.emoji+'</div><div class="ci-tx"><b>'+esc(pname(p,x.size))+'</b>'
      +'<span>'+(p.kind!=='mug'? (gxT('size_w')+x.size+' · ') : '')+gxT('qty_w')+x.qty+'</span></div>'
      +'<div class="qty2"><button onclick="changeCart(\''+p.id+'\',\''+x.size+'\',-1)">−</button><span class="qn">'+x.qty+'</span>'
      +'<button onclick="changeCart(\''+p.id+'\',\''+x.size+'\',1)">+</button></div>'
      +'<b style="color:var(--ac)">'+pmoney(p.price*x.qty)+' '+GX.cur+'</b>'
      +'<button class="ci-x" onclick="changeCart(\''+p.id+'\',\''+x.size+'\',-100)">✕</button></div>';
  });
  var tot=cartTotals();
  html+='<div class="row-t"><span>'+gxT('cart_subtotal')+'</span><b>'+pmoney(tot.sub)+' '+GX.cur+'</b></div>'
    +'<div class="row-t"><span>'+gxT('cart_delivery')+'</span><b>'+pmoney(tot.delivery)+' '+GX.cur+'</b></div>'
    +'<div class="row-t total"><span>'+gxT('cart_total')+'</span><b>'+pmoney(tot.total)+' '+GX.cur+'</b></div>'
    +'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px">'
    +'<button class="btn wa" style="flex:1" onclick="openCheckout()">'+gxT('cart_checkout')+'</button>'
    +'<button class="btn tg" style="flex:1" onclick="orderCartTG()">✈️ '+gxT('order_tg')+'</button>'
    +'<button class="btn ghost" onclick="clearCart()">🗑 '+gxT('cart_clear')+'</button></div>';
  box.innerHTML=html;
}
var rewardSel=null;
function fillFoot(){
  var cart=gxGet('gx_cart',[]); var ft=$('cdf'); if(!ft) return;
  var tot=cartTotals(); var disc=rewardSel?rewardSel.discount:0; var fin=Math.max(0,tot.total-disc);
  var pts=gxGet('gx_points',0);
  var html='';
  if(cart.length){
    html+='<div class="row-t"><span>'+gxT('cart_subtotal')+'</span><b>'+pmoney(tot.sub)+' '+GX.cur+'</b></div>'
      +'<div class="row-t"><span>'+gxT('cart_delivery')+'</span><b>'+pmoney(tot.delivery)+' '+GX.cur+'</b></div>';
    if(disc>0) html+='<div class="row-t"><span>'+gxT('pts_discount')+'</span><b style="color:var(--ok)">−'+pmoney(disc)+' '+GX.cur+'</b></div>';
    html+='<div class="row-t total"><span>'+gxT('cart_total')+'</span><b>'+pmoney(fin)+' '+GX.cur+'</b></div>';
    if(pts>=GX.rewards[0].points){
      html+='<div class="pts-row">'+gxT('pts_avail').replace('{n}',pts)
        +'<select onchange="pickReward(this)"><option value="">'+gxT('pts_use')+'</option>';
      GX.rewards.forEach(function(r){ if(pts>=r.points){ html+='<option value="'+r.points+'">'+r.points+' '+gxT('points')+' — '+r[GX.lang==='ar'?'ar':'en']+'</option>'; } });
      html+='</select></div>';
    }
  }
  html+='<button class="btn wa block" '+(cart.length?'':'disabled style="opacity:.5"')+' onclick="openCheckout()">'+gxT('cart_checkout')+'</button>'
    +'<button class="btn tg block" '+(cart.length?'':'disabled style="opacity:.5"')+' onclick="orderCartTG()" style="margin-top:8px">✈️ '+gxT('order_tg')+'</button>'
    +'<div style="text-align:center;margin-top:8px"><button class="hbtn" onclick="clearCart()">🗑 '+gxT('cart_clear')+'</button></div>';
  ft.innerHTML=html;
}
function pickReward(sel){
  var pts=parseInt(sel.value,10); rewardSel=null;
  if(pts){ var r=GX.rewards.find(function(x){return x.points===pts;}); if(r) rewardSel=r; }
  fillFoot();
}
/* ---------- checkout ---------- */
function openCheckout(){ var cart=gxGet('gx_cart',[]); if(!cart.length) return; openModal('m-checkout'); }
function submitOrder(){
  var name=($('co_name').value||'').trim(), phone=($('co_phone').value||'').trim(),
      area=($('co_area').value||'').trim(), addr=($('co_addr').value||'').trim();
  if(!name||!phone||!area||!addr){ toast(gxT('co_required')); return; }
  var cart=gxGet('gx_cart',[]); var tot=cartTotals(); var disc=rewardSel?rewardSel.discount:0;
  var items=cart.map(function(x){ var p=GX.products.find(function(y){return y.id===x.id;});
    return {id:x.id, size:x.size, qty:x.qty, name:p?pname(p,x.size):x.id, price:p?p.price:0, emoji:p?p.emoji:'⚽', kind:p?p.kind:'jersey'}; });
  var fin=Math.max(0,tot.total-disc);
  fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    items:items,name:name,phone:phone,area:area,address:addr,
    notes:($('co_notes').value||'').trim(),delivery:tot.delivery,discount:disc,total:fin,reward:rewardSel?rewardSel.points:0,
    device:gxDev()
  })}).then(function(r){return r.json();}).then(function(d){
    if(d.code){
      var earned=Math.floor(fin*GX.points_per); addPoints(earned, gxT('pts_earn'));
      var msg=waOrderMsg(d.code, items, name, phone, area, addr, tot.delivery, disc, fin);
      clearCart(); closeModal('m-checkout');
      window.open('https://wa.me/'+GX.wa+'?text='+encodeURIComponent(msg),'_blank');
      location.href='/order/success?code='+d.code;
    } else { toast('Error'); }
  });
}
function waOrderMsg(code,items,name,phone,area,addr,del,disc,total){
  var l=[]; l.push('HELLO_LN'.indexOf('X')>-1?'':gxT('hello').trim()+' 👋'); l.push('');
  l.push(gxT('code_w')+code);
  items.forEach(function(it){
    l.push(''); l.push('• '+it.emoji+' '+it.name);
    if(it.kind!=='mug') l.push('  '+gxT('size_w')+it.size);
    l.push('  '+gxT('qty_w')+it.qty+' · '+pmoney(it.price*it.qty)+' '+GX.cur);
  });
  l.push(''); l.push('🚚 '+gxT('cart_delivery')+': '+pmoney(del)+' '+GX.cur);
  if(disc>0) l.push(gxT('pts_discount')+': −'+pmoney(disc)+' '+GX.cur);
  l.push('💰 '+gxT('cart_total')+': '+pmoney(total)+' '+GX.cur);
  l.push(''); l.push('👤 '+gxT('co_name').replace(/[^\u0600-\u06FF\\w\\s]/g,'')+': '+name);
  l.push('📱 '+gxT('co_phone').replace(/[^\u0600-\u06FF\\w\\s]/g,'')+': '+phone);  l.push('📍 '+gxT('co_area').replace(/[^\u0600-\u06FF\\w\\s]/g,'')+': '+area);
  l.push('🏠 '+gxT('co_address').replace(/[^\u0600-\u06FF\\w\\s]/g,'')+': '+addr);
  return l.join('\\n');
}
/* ---------- order via Telegram ---------- */
function tgOrderMsg(code,items,del,disc,total){
  var l=[]; l.push(gxT('hello').trim()+' 👋'); l.push('');
  l.push(gxT('code_w')+code);
  items.forEach(function(it){
    l.push(''); l.push('• '+it.emoji+' '+it.name);
    if(it.kind!=='mug') l.push('  '+gxT('size_w')+it.size);
    l.push('  '+gxT('qty_w')+it.qty+' · '+pmoney(it.price*it.qty)+' '+GX.cur);
  });
  l.push(''); l.push('🚚 '+gxT('cart_delivery')+': '+pmoney(del)+' '+GX.cur);
  if(disc>0) l.push(gxT('pts_discount')+': −'+pmoney(disc)+' '+GX.cur);
  l.push('💰 '+gxT('cart_total')+': '+pmoney(total)+' '+GX.cur);
  return l.join('\\n');
}
function orderCartTG(){
  var cart=gxGet('gx_cart',[]); if(!cart.length) return;
  var tot=cartTotals(); var disc=rewardSel?rewardSel.discount:0;
  var fin=Math.max(0,tot.total-disc);
  var items=cart.map(function(x){ var p=GX.products.find(function(y){return y.id===x.id;});
    return {id:x.id,size:x.size,qty:x.qty,name:p?pname(p,x.size):x.id,price:p?p.price:0,emoji:p?p.emoji:'⚽',kind:p?p.kind:'jersey'}; });
  fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    items:items,name:'',phone:'',area:'',address:'',notes:'',delivery:tot.delivery,discount:disc,total:fin,reward:rewardSel?rewardSel.points:0,fast:1,device:gxDev()})})
  .then(function(r){return r.json();}).then(function(d){
    if(d.code){
      var msg=tgOrderMsg(d.code,items,tot.delivery,disc,fin);
      window.open(GX.tg+'?text='+encodeURIComponent(msg),'_blank');
      location.href='/order/success?code='+d.code;
    } else { toast('Error'); }
  });
}
function orderTG(pid){
  var p=GX.products.find(function(x){return x.id===pid;});
  if(!p) return;
  var q=parseInt(document.getElementById('qty').textContent,10);
  var chip=document.querySelector('.size-chip.on'); var sz=chip?chip.getAttribute('data-sz'):null;
  if(p.kind!=='mug' && !sz){ toast(gxT('size_required')); return; }
  var items=[{id:pid,size:sz||'OS',qty:q,name:p[GX.lang==='ar'?'name_ar':'name_en'],price:p.price,emoji:p.emoji,kind:p.kind}];
  var tot=(p.price*q)+GX.delivery;
  fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    items:items,name:'',phone:'',area:'',address:'',notes:'',delivery:GX.delivery,discount:0,total:tot,reward:0,fast:1,device:gxDev()})})
  .then(function(r){return r.json();}).then(function(d){
    if(d.code){
      var msg=gxT('hello').trim()+':\n'+items[0].emoji+' '+items[0].name;
      if(sz) msg+='\n'+gxT('size_w')+sz;
      msg+='\n'+gxT('qty_w')+q+' · '+pmoney(p.price*q)+' '+GX.cur+'\n\n'+gxT('code_w')+d.code;
      window.open(GX.tg+'?text='+encodeURIComponent(msg),'_blank');
      location.href='/order/success?code='+d.code;
    }
  });
}
/* ---------- points ---------- */
function addPoints(n,label){
  var pts=gxGet('gx_points',0)+n; gxSet('gx_points',pts);
  var h=gxGet('gx_ptslog',[]); h.unshift({d:n,l:label,t:new Date().toLocaleDateString()}); h=h.slice(0,50);
  gxSet('gx_ptslog',h);
}
function openPoints(){
  var pts=gxGet('gx_points',0), h=gxGet('gx_ptslog',[]);
  var next=GX.rewards.find(function(r){return r.points>pts;});
  var nb=next? (next.points-pts) : 0;
  var box=$('ptsBox'); if(!box) return;
  var html='<div class="set-row"><span class="st">'+gxT('pts_title')+'</span><b style="color:var(--ac);font-size:1.3rem">'+pts+'</b></div>';
  if(next){ html+='<p class="mnote">'+gxT('pts_next').replace('{n}',nb)+'</p>'
    +'<div style="height:12px;background:var(--card2);border-radius:999px;overflow:hidden;margin:10px 0"><div style="height:100%;width:'+Math.min(100,Math.round(pts/next.points*100))+'%;background:linear-gradient(90deg,var(--ac),var(--ac2));"></div></div>'
    +'<p class="mnote" style="text-align:center;font-weight:800">'+gxT('pts_prog').replace('{cur}',pts).replace('{next}',next.points)+'</p>'; }
  if(h.length){ html+='<h4 class="msec">'+gxT('pts_history')+'</h4>';
    h.forEach(function(e){ html+='<div class="row-t"><span>'+esc(e.l)+' <small style="color:var(--mut)">'+e.t+'</small></span><b style="color:'+(e.d>0?'var(--ok)':'var(--err)')+'">'+(e.d>0?'+':'')+e.d+'</b></div>'; }); }
  box.innerHTML=html; openModal('m-points');
}
/* ---------- request a product ---------- */
var reqPhoto=null;
function openRequest(img){
  reqPhoto=img||null; openModal('m-request');
  if(reqPhoto){ var ph=$('req_photo'); if(ph){ ph.src=reqPhoto; ph.style.display='block'; } }
}
function pickReqType(v){ document.querySelectorAll('.radio[data-g=rty]').forEach(function(x){x.classList.toggle('on',x.getAttribute('data-v')===v);}); }
function pickReqVer(v){ document.querySelectorAll('.radio[data-g=ver]').forEach(function(x){x.classList.toggle('on',x.getAttribute('data-v')===v);}); }
function submitRequest(){
  var club=($('req_club').value||'').trim(); if(!club){ toast(gxT('co_required')); return; }
  var ty=document.querySelector('.radio[data-g=rty].on'); ty=ty?ty.getAttribute('data-v'):'jersey';
  var ver=document.querySelector('.radio[data-g=ver].on'); ver=ver?ver.getAttribute('data-v'):'';
  var size=($('req_size').value||'').trim(); var qty=($('req_qty').textContent||'1');
  var notes=($('req_notes').value||'').trim();
  fetch('/api/request',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    club:club,type:ty,version:ver,size:size,qty:qty,notes:notes,photo:reqPhoto?reqPhoto.substring(0,2000):''})})
  .then(function(r){return r.json();}).then(function(d){
    var msg='';
    msg+=gxT('hello').trim()+'\\n'+gxT('req_title')+'\\n';
    msg+='• '+gxT('req_club')+': '+club+'\\n';
    msg+='• '+gxT('req_type')+': '+gxT('type_'+ty)+'\\n';
    if(ver) msg+='• '+gxT('req_version')+': '+ver+'\\n';
    if(size) msg+='• '+gxT('req_size')+': '+size+'\\n';
    msg+='• '+gxT('req_qty')+': '+qty+'\\n';
    if(notes) msg+='• '+gxT('req_notes')+': '+notes;
    window.open('https://wa.me/'+GX.wa+'?text='+encodeURIComponent(msg),'_blank');
    closeModal('m-request'); toast(gxT('req_ok')+' — '+d.ref);
  });
}
/* ---------- votes ---------- */
function votePoll(opt){
  var pid=GX.poll.id; var dev=gxGet('gx_device',null);
  if(!dev){ dev='d'+Math.random().toString(36).slice(2)+Date.now().toString(36); gxSet('gx_device',dev); }
  fetch('/api/vote',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({poll:pid,option:opt,device:dev})}).then(function(r){return r.json();}).then(function(d){
    if(d.ok){ toast(gxT('poll_vote')); location.reload(); } else { toast(gxT('poll_voted')); }
  });
}
/* ---------- countdowns ---------- */
function tickCountdown(){
  var now=Date.now();
  document.querySelectorAll('[data-ctarget]').forEach(function(el){
    var diff=new Date(el.getAttribute('data-ctarget')).getTime()-now;
    var out=el.querySelector('.cdout'); if(!out) return;
    if(diff<=0){ out.textContent='00:00:00:00'; return; }
    var s=Math.floor(diff/1000); var d=Math.floor(s/86400); s%=86400;
    var h=Math.floor(s/3600); s%=3600; var m=Math.floor(s/60); s%=60;
    var pad=function(x){return (x<10?'0':'')+x;};
    out.textContent=pad(d)+':'+pad(h)+':'+pad(m)+':'+pad(s);
  });
  document.querySelectorAll('[data-ms]').forEach(function(el){
    var diff=new Date(el.getAttribute('data-ms')).getTime()-now;
    var out=el.querySelector('.msout'); if(!out) return;
    if(diff<=0){ out.textContent='00:00:00'; return; }
    var s=Math.floor(diff/1000); var h=Math.floor(s/3600); s%=3600; var m=Math.floor(s/60); s%=60;
    var pad=function(x){return (x<10?'0':'')+x;};
    out.textContent=pad(h)+':'+pad(m)+':'+pad(s);
  });
}
/* ---------- matchday ---------- */
function pickSide(cid){ setMyClub(cid); gxSet('gx_team',cid); document.querySelectorAll('.md-side').forEach(function(x){x.style.display='none';}); }
/* ---------- image search ---------- */
function isOpen(){ openModal('m-imgsearch'); }
function isHandleFile(input,isCam){
  var f=input.files[0]; if(!f) return;
  var fr=new FileReader(); fr.onload=function(){ isAnalyze(fr.result); }; fr.readAsDataURL(f);
}
function isAnalyze(dataUrl){
  var img=new Image(); img.onload=function(){
    var cv=document.createElement('canvas'); cv.width=64; cv.height=64;
    var cx=cv.getContext('2d'); cx.drawImage(img,0,0,64,64);
    var d=cx.getImageData(0,0,64,64).data; var R=0,G=0,B=0,n=d.length/4;
    for(var i=0;i<d.length;i+=4){ R+=d[i]; G+=d[i+1]; B+=d[i+2]; }
    R=Math.round(R/n); G=Math.round(G/n); B=Math.round(B/n);
    var desc=($('is_desc').value||'').trim().toLowerCase();
    var scores=GX.products.map(function(p){
      var best=0; p.colors.forEach(function(hex){ var d2=hex2rgb(hex); if(!d2) return;
        var dist=Math.sqrt((R-d2[0])*(R-d2[0])+(G-d2[1])*(G-d2[1])+(B-d2[2])*(B-d2[2]));
        var sim=Math.max(0,1-dist/441.7); if(sim>best) best=sim; });
      var sc=best*100;
      if(desc){ var hay=((p.name_ar||'')+' '+(p.name_en||'')+' '+(p.club_ar||'')+' '+(p.club_en||'')).toLowerCase();
        var boost = hay.indexOf(desc)>-1?12:0; sc=Math.min(99,sc*0.8+boost); }
      return {p:p, sc:Math.round(sc)};
    }).sort(function(a,b){return b.sc-a.sc;});
    $('is_analyzing').style.display='none';
    var out=$('is_resultsBox'); var html='';
    var top=scores[0];
    if(top.sc<40){ html+='<p class="mnote">'+gxT('is_notfound')+'</p><p class="mnote">'+gxT('is_near')+'</p>'; }
    else { html+='<h4 class="msec">'+gxT('is_best')+'</h4>' + isCard(top) + '<h4 class="msec" style="margin-top:14px">'+gxT('is_similar')+'</h4>'; }
    scores.slice(1,4).forEach(function(s){ html+=isCard(s); });
    html+='<div style="text-align:center;margin-top:14px"><button class="btn pri sm" onclick="closeModal(\'m-imgsearch\');openRequest(\''+dataUrl+'\')">'+gxT('is_request')+'</button></div>';
    html+='<p class="img-search-tip">'+gxT('is_priv')+'</p>';
    out.innerHTML=html;
  };
  img.src=dataUrl;
}
function hex2rgb(hex){ if(!hex) return null; hex=hex.replace('#',''); if(hex.length===3) hex=hex.split('').map(function(c){return c+c;}).join('');
  var n=parseInt(hex,16); if(isNaN(n)) return null; return [(n>>16)&255,(n>>8)&255,n&255]; }
function isCard(s){
  var p=s.p;
  return '<div class="res-card"><img src="/img/'+p.imgs[0]+'" alt=""><div class="rc-t"><b>'+esc(p.name_ar||p.name_en)+'</b>'
    +'<span>'+gxT('cat_'+(p.kind==='mug'?'mug':'jersey'))+'</span></div>'
    +'<div><b class="rc-p">'+p.price+' '+GX.cur+'</b><br><span class="rc-s">'+gxT('is_sim').replace('{p}',s.sc)+'</span></div></div>';
}
/* ---------- professional reviews ---------- */
var revDims=['design','fabric','quality','fit'];
var revDimVals={design:0,fabric:0,quality:0,fit:0};
var revFit='';
function setDim(dim,n){ revDimVals[dim]=n; document.querySelectorAll('.stars-in[data-dim="'+dim+'"] span').forEach(function(x,i){ x.classList.toggle('on', i<n); }); }
function setRevFit(v){ revFit=v; document.querySelectorAll('.radio[data-g=rvfit]').forEach(function(x){ x.classList.toggle('on', x.getAttribute('data-v')===v); }); }
function toggleRatForm(){ var f=$('ratForm'); if(!f) return; f.style.display = f.style.display==='none'?'block':'none'; }
function revStars(n){ var s=''; for(var i=0;i<5;i++) s+=(i<n?'★':'☆'); return s; }
function buildReviews(pid){
  fetch('/api/reviews/'+pid+'?device='+encodeURIComponent(gxDev())).then(function(r){return r.json();}).then(function(d){
    var avgEl=$('ratAvg'); if(avgEl) avgEl.textContent=d.avg.toFixed(1);
    var stEl=$('ratStars'); if(stEl) stEl.textContent=revStars(Math.round(d.avg));
    var note=$('ratNote'); if(note) note.textContent=gxT('rat_based').replace('{n}',d.n);
    var dims=''; revDims.forEach(function(dm){ var v=(d.dims[dm]||0); dims+='<div class="rv2-dim"><span>'+gxT('rv2_'+dm)+'</span><div class="bar"><i style="width:'+Math.round(v/5*100)+'%"></i></div><b>'+v.toFixed(1)+'</b></div>'; });
    var fd=$('ratDims'); if(fd) fd.innerHTML=dims;
    var box=$('ratList'); if(!box) return;
    var html='';
    if(!d.list.length){ html='<p class="mnote">'+gxT('rat_empty')+'</p>'; }
    d.list.forEach(function(r){
      html+='<div class="rv"><div class="rv-top"><div><b class="rv-name">'+esc(r.name||'—')+'</b> <span class="rv-stars">'+revStars(Math.round(r.overall))+'</span>'
        +(r.verified?' <span class="rv-ver">'+gxT('rv2_ver')+'</span>':'')
        +(r.pending?' <span class="rv-pend">'+gxT('rv2_pend')+'</span>':'')
        +'</div><span class="rv-date">'+esc(r.created)+'</span></div>'
        +'<p class="rv-meta">'+gxT('rv2_design')+' '+r.design+'★ · '+gxT('rv2_fabric')+' '+r.fabric+'★ · '+gxT('rv2_quality')+' '+r.quality+'★ · '+gxT('rv2_fit')+' '+r.fit_dim+'★'+(r.fit?' · '+esc(r.fit):'')+'</p>'
        +(r.text?'<p class="rv-txt">'+esc(r.text)+'</p>':'')
        +(r.photo?'<div class="rv-photo"><img src="'+r.photo+'" onclick="openLB(this.src)" alt=""></div>':'')
        +(r.mine?'<button class="rv-report" onclick="reportRev2(\''+r.id+'\')">'+gxT('rat_report')+'</button>':'')
        +'</div>';
    });
    box.innerHTML=html;
    var ph=$('custPhotos'); if(!ph) return;
    var phh='';
    if(!d.photos.length){ phh='<p class="mnote">'+gxT('photos_empty')+'</p>'; }
    else { phh='<div class="photogrid">'; d.photos.forEach(function(x){ phh+='<img src="'+x+'" onclick="openLB(this.src)" alt="">'; }); phh+='</div>'; }
    ph.innerHTML=phh;
  });
}
function submitReview(pid){
  var name=($('rat_name').value||'').trim()||'—';
  var txt=($('rat_txt').value||'').trim();
  for(var i=0;i<revDims.length;i++){ if(!revDimVals[revDims[i]]){ toast(gxT('co_required')); return; } }
  if(!revFit){ toast(gxT('co_required')); return; }
  var ph=$('rat_photo').files[0]; var consent=($('rat_consent')&&$('rat_consent').checked);
  if(ph && !consent){ toast(gxT('co_required')); return; }
  if(ph){ resizeImage(ph,function(dataUrl){ postReview(pid,name,txt,dataUrl); }); }
  else { postReview(pid,name,txt,null); }
}
function postReview(pid,name,txt,photo){
  fetch('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    product:pid,device:gxDev(),name:name,
    design:revDimVals.design,fabric:revDimVals.fabric,quality:revDimVals.quality,size_rating:revDimVals.fit,
    fit:revFit,text:txt,photo:photo?photo:null})}).then(function(r){return r.json();}).then(function(d){
    toast(gxT('rat_thanks')); toggleRatForm(); buildReviews(pid);
  });
}
function resizeImage(file,cb){
  var fr=new FileReader(); fr.onload=function(){
    var img=new Image(); img.onload=function(){
      var w=img.width,h=img.height,scale=Math.min(1,560/Math.max(w,h)); w=Math.round(w*scale); h=Math.round(h*scale);
      var cv=document.createElement('canvas'); cv.width=w; cv.height=h;
      cv.getContext('2d').drawImage(img,0,0,w,h); cb(cv.toDataURL('image/jpeg',0.82));
    }; img.src=fr.result;
  }; fr.readAsDataURL(file);
}
function reportRev2(id){ fetch('/api/review/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})}).then(function(){ toast(gxT('rat_reported')); }); }
/* ---------- price drop alert ---------- */
function openPriceDrop(pid){ $('pd_prod').value=pid; openModal('m-pricedrop'); }
function submitPriceDrop(){
  var ph=($('pd_phone').value||'').trim(); var pid=$('pd_prod').value;
  if(ph.length<6){ toast(gxT('co_required')); return; }
  fetch('/api/alerts',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({product:pid,phone:ph,device:gxDev()})}).then(function(r){return r.json();}).then(function(d){
    closeModal('m-pricedrop'); toast(gxT('pd_ok'));
  });
}
/* ---------- try it on (AI preview) ---------- */
var TRY={img:null,pid:null,cv:null};
function tryOpen(pid){ TRY.pid=pid; openModal('m-tryit'); }
function tryHandle(input,cam){
  var f=input.files[0]; if(!f) return;
  var fr=new FileReader(); fr.onload=function(){ TRY.img=new Image(); TRY.img.onload=function(){ tryPrep(); }; TRY.img.src=fr.result; };
  fr.readAsDataURL(f);
}
function tryPrep(){
  var wrap=$('tryCanvasWrap'); wrap.style.display='block';
  var cv=$('tryCanvas'); if(!cv) return;
  var W=Math.min(460,TRY.img.width||460), H=Math.min(460,TRY.img.height||460);
  cv.width=W; cv.height=H; TRY.cv=cv;
  var ctx=cv.getContext('2d'); ctx.fillStyle='#0F172A'; ctx.fillRect(0,0,W,H);
  ctx.drawImage(TRY.img,0,0,W,H);
  drawJersey(ctx,W,H);
}
function drawJersey(ctx,W,H){
  var img=TRY.pid? GX.products.find(function(x){return x.id===TRY.pid;}):null;
  if(!img) return;
  var ji=new Image();
  ji.onload=function(){
    ctx.save(); ctx.globalAlpha=.92;
    ctx.beginPath();
    var tw=W*0.66, th=H*0.34, x=(W-tw)/2, y=H*0.28;
    ctx.moveTo(x+tw*0.12,y); ctx.lineTo(x+tw*0.88,y);
    ctx.lineTo(x+tw*0.72,y+th); ctx.lineTo(x+tw*0.28,y+th); ctx.closePath();
    ctx.clip();
    ctx.drawImage(ji,x,y,tw,th);
    ctx.restore();
    ctx.strokeStyle='rgba(255,255,255,.6)'; ctx.lineWidth=2;
    ctx.beginPath(); ctx.moveTo(x+tw*0.12,y); ctx.lineTo(x+tw*0.88,y); ctx.lineTo(x+tw*0.72,y+th); ctx.lineTo(x+tw*0.28,y+th); ctx.closePath(); ctx.stroke();
  };
  ji.src='/img/'+img.imgs[0];
}
function tryAdd(){ if(!TRY.pid) return; var q=parseInt($('qty').textContent,10); addCart(TRY.pid, selSize||'', q); }
function tryShare(){
  var cv=$('tryCanvas'); if(!cv) return;
  cv.toBlob(function(blob){
    var file=new File([blob],'golazox-preview.png',{type:'image/png'});
    if(navigator.share && navigator.canShare && navigator.canShare({files:[file]})){
      navigator.share({files:[file]});
    } else {
      var a=document.createElement('a'); a.href=cv.toDataURL('image/png'); a.download='golazox-preview.png'; a.click(); toast(gxT('try_share'));
    }
  });
}
function tryReset(){ $('tryCanvasWrap').style.display='none'; var f=$('tryfile'); if(f) f.value=''; }
/* ---------- drop remind ---------- */
function submitDropRemind(){
  var ph=($('dr_phone').value||'').trim();
  if(ph.length<6){ toast(gxT('co_required')); return; }
  fetch('/api/notify',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({product:'drop',size:'drop',phone:ph})}).then(function(r){return r.json();}).then(function(){
    closeModal('m-drop'); toast(gxT('drop_ok'));
  });
}
/* ---------- account / auth ---------- */
function openLogin(){ openModal('m-login'); }
function authTab(t){
  document.querySelectorAll('.auth-tabs .atab').forEach(function(x){ x.classList.toggle('on', x.getAttribute('data-tab')===t); });
  document.querySelectorAll('.auth-pane').forEach(function(x){ x.style.display='none'; });
  $('auth_pane_'+t).style.display='block';
}
function authContact(){ return (($('au_email').value||'')||'').trim(); }
function isEmail(v){
  var r=/^[^\\s@]+@[^\\s@]+\\.[^\\s@]{2,}$/;
  return r.test(v);
}
function maskEmail(em){
  var at=em.indexOf('@');
  if(at<=1) return em;
  return em.charAt(0)+'***'+em.substr(at-1);
}
var auth_timer=null;
function authTimer(secs){
  var b=$('au_resendbtn');
  if(!b) return;
  if(auth_timer) clearInterval(auth_timer);
  var t=secs;
  b.disabled=true;
  function tick(){
    b.textContent='🔄 '+gxT('auth_resend_in').replace('{s}',t);
    t--;
    if(t<0){
      clearInterval(auth_timer);
      if(b){ b.disabled=false; b.textContent='🔄 '+gxT('auth_resend'); }
    }
  }
  tick();
  auth_timer=setInterval(tick,1000);
}
function authSendCode(){
  var full=authContact();
  if(!isEmail(full)){ toast(gxT('auth_bad_phone')); return; }
  var btn=$('au_sendbtn');
  if(btn){ btn.disabled=true; btn.textContent=gxT('auth_loading'); }
  fetch('/api/auth/otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:full})})
  .then(function(r){return r.json();}).then(function(d){
    if(d.ok===false){
      var em = d.error==='sms_notcfg'?gxT('auth_sms_notcfg') :
               (d.error==='rate_limit'||d.error==='rate_gap')?gxT('auth_rate_limit') : gxT('auth_sms_fail');
      toast(em);
      return;
    }
    $('au_step1').style.display='none'; $('au_step2').style.display='block';
    var st=$('au_sentto'); if(st) st.textContent=maskEmail(full);
    $('au_demo').style.display= d.demo?'block':'none';
    if(d.demo){
      $('au_democode').textContent=d.otp;
      if($('au_code')) $('au_code').value=d.otp;
      var dl=$('au_demo_note'); if(dl) dl.style.display='block';
    }
    $('au_newbox').style.display= d.registered?'none':'block';
    toast(gxT('auth_sent_ok'));
    authTimer(30);
  }).catch(function(){
    toast(gxT('auth_otp_fail'));
  }).then(function(){
    if(btn){ btn.disabled=false; btn.textContent=gxT('auth_continue'); }
  });
}
function authResend(){ authSendCode(); }
function authChangePhone(){
  var s2=$('au_step2'); if(s2){ s2.style.display='none'; }
  var s1=$('au_step1'); if(s1){ s1.style.display='block'; }
  var ac=$('au_code'); if(ac) ac.value='';
}
function authVerify(){
  var em=authContact(), code=($('au_code').value||'').trim();
  var name=($('au_name').value||'').trim();
  if(code.length<4){ toast(gxT('auth_otp_short')); return; }
  var btn=$('au_vbtn');
  if(btn){ btn.disabled=true; btn.textContent=gxT('auth_verifying'); }
  fetch('/api/auth/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em,code:code,name:name})})
  .then(function(r){return r.json();}).then(function(d){
    if(d.ok){ afterLogin(); return; }
    var rm = d.reason==='blocked'?gxT('auth_blocked') :
             d.reason==='expired'?gxT('auth_expired') :
             d.reason==='rate'?gxT('auth_rate_limit') : gxT('auth_wrong');
    toast(rm);
    if(btn){ btn.disabled=false; btn.textContent=gxT('auth_verify'); }
  }).catch(function(){
    toast(gxT('auth_otp_fail'));
    if(btn){ btn.disabled=false; btn.textContent=gxT('auth_verify'); }
  });
}
function authPwLogin(){
  var em=(($('pw_email').value||'')||'').trim(), pw=($('pw_pass').value||'').trim();
  if(!isEmail(em)||!pw){ toast(gxT('auth_bad_phone')); return; }
  fetch('/api/auth/password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em,password:pw})})
  .then(function(r){return r.json();}).then(function(d){
    if(d.ok){ afterLogin(); } else { toast(gxT('auth_pw_wrong')); }
  });
}
function afterLogin(){
  closeModal('m-login');
  fetch('/api/me').then(function(r){return r.json();}).then(function(d){
    if(d.ok&&d.favs) gxSet('gx_favs',d.favs);
    renderFavs();
  }).catch(function(){});
  location.href='/account';
}
function authOut(){ fetch('/api/auth/logout').then(function(){ location.href='/home'; }); }
/* ---------- reorder ---------- */
function openReorder(code){
  fetch('/api/reorder?code='+encodeURIComponent(code)).then(function(r){return r.json();}).then(function(d){
    var html='';
    d.items.forEach(function(it){
      var alts=it.sizes||[];
      html+='<div class="ro-item"><b>'+it.emoji+' '+it.name+'</b><span>'+gxT('size_w')+it.size+'</span></div>'
        +'<div class="fld" style="margin-bottom:12px"><label>'+gxT('ro_alt')+'</label><select data-ro="'+it.id+'">'
        +'<option value="'+it.size+'">'+it.size+'</option>'
        +alts.map(function(s){ return '<option value="'+s+'">'+s+'</option>'; }).join('')
        +'</select></div>';
    });
    var body='<div id="ro_body">'+html+'</div>'
      +'<button class="btn pri big" onclick="doReorder(\''+code+'\')">'+gxT('ro_add')+'</button>';
    openModal('m-reorder'); $('ro_body').innerHTML=body;
  });
}
function doReorder(code){
  var sizes={};
  document.querySelectorAll('#ro_body select').forEach(function(s){ sizes[s.getAttribute('data-ro')]=s.value; });
  fetch('/api/reorder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:code,sizes:sizes})})
  .then(function(r){return r.json();}).then(function(d){
    if(d.ok&&d.cart.length){ gxSet('gx_cart',d.cart); toast(gxT('ro_added')); closeModal('m-reorder'); renderCart(); }
    else { toast(gxT('ro_none')); }
  });
}
/* ---------- confetti / cheer ---------- */
function confetti(n){
  n=n||28; var wrap=$('fxWrap');
  if(!wrap){ wrap=document.createElement('div'); wrap.id='fxWrap'; wrap.style.cssText='position:fixed;inset:0;pointer-events:none;overflow:hidden;z-index:99'; document.body.appendChild(wrap); }
  var cols=['#E11D48','#F97316','#C9A24B','#16A34A','#1C2C5B','#A50044','#F7D033'];
  for(var i=0;i<n;i++){
    var c=document.createElement('div'); c.className='cf';
    c.style.left=(Math.random()*100)+'vw';
    c.style.background=cols[Math.floor(Math.random()*cols.length)];
    c.style.animationDuration=(0.9+Math.random()*1.1)+'s';
    c.style.animationDelay=(Math.random()*0.5)+'s';
    wrap.appendChild(c); (function(el){ setTimeout(function(){ el.remove(); },2600); })(c);
  }
}
function cheerNow(){
  var txts=[gxT('ch_t1'),gxT('ch_t2'),gxT('ch_t3'),gxT('ch_t4')];
  var sp=document.createElement('div'); sp.className='cheer-pop'; sp.innerHTML='<span>'+txts[Math.floor(Math.random()*txts.length)]+'</span>';
  document.body.appendChild(sp); setTimeout(function(){ sp.remove(); },2500);
  confetti(30);
  if(gxGet('gx_mute')!=='1') cheerSound();
}
var cheerCtx=null;
function cheerSound(){
  try{
    cheerCtx=cheerCtx||new (window.AudioContext||window.webkitAudioContext)();
    var dur=1.3, len=Math.floor(cheerCtx.sampleRate*dur), buf=cheerCtx.createBuffer(1,len,cheerCtx.sampleRate);
    var ch=buf.getChannelData(0);
    for(var i=0;i<len;i++){ var env=1-i/len; ch[i]=(Math.random()*2-1)*env*env*(0.55+0.45*Math.sin(i/1600)); }
    var src=cheerCtx.createBufferSource(); src.buffer=buf;
    var f=cheerCtx.createBiquadFilter(); f.type='bandpass'; f.frequency.value=850; f.Q.value=0.5;
    var g=cheerCtx.createGain(); g.gain.value=0.4;
    src.connect(f); f.connect(g); g.connect(cheerCtx.destination); src.start();
  }catch(e){}
}
function cheerToggle(){
  var m=gxGet('gx_mute')==='1'; gxSet('gx_mute',m?'0':'1');
  var b=$('cheerBtn'); if(b) b.textContent=m?gxT('ch_btn'):('🔇 '+gxT('ch_mute'));
}
/* ---------- account sections ---------- */
function loadFavs(){
  var box=$('favsBox'); if(!box) return;
  var favs=gxGet('gx_favs',[]);
  if(!favs.length){ box.innerHTML='<p class="mnote">'+gxT('acc_empty_favs')+'</p>'; return; }
  box.innerHTML='<div class="grid">'+favs.map(dnaCard).join('')+'</div>';
}
function loadAlerts(){
  var box=$('alertsBox'); if(!box) return;
  fetch('/api/alerts?device='+encodeURIComponent(gxDev())).then(function(r){return r.json();}).then(function(d){
    if(!d.alerts.length){ box.innerHTML='<p class="mnote">'+gxT('pd_empty')+'</p>'; return; }
    var html='';
    d.alerts.forEach(function(a){
      var p=findProd(a.product);
      html+='<div class="al-item"><div class="at"><b>'+(p?p.name_ar:a.product)+'</b>'
        +'<span>'+gxT('pd_now').replace('{p}',(p?p.price+' '+GX.cur:'—'))+'</span></div>'
        +'<span class="st '+(a.triggered?'sent':'wait')+'">'+(a.triggered?gxT('pd_sent'):gxT('pd_waiting'))+'</span>'
        +(a.active?'<button class="hbtn" onclick="cancelAlert('+a.id+')">'+gxT('pd_cancel')+'</button>':'')
        +'</div>';
    });
    box.innerHTML=html;
  });
}
function cancelAlert(id){
  fetch('/api/alerts/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,device:gxDev()})})
  .then(function(){ loadAlerts(); });
}
function loadPoints(){
  var box=$('pointsBox'); if(!box) return;
  fetch('/api/points?device='+encodeURIComponent(gxDev())).then(function(r){return r.json();}).then(function(d){
    var next=GX.rewards.find(function(r){return r.points>d.total;});
    box.innerHTML='<div class="dna-grid">'
      +'<div class="dna-cell"><b>'+d.total+'</b><span>'+gxT('pts_bal').replace('{n}',d.total)+'</span></div>'
      +(next?'<div class="dna-cell"><b>'+(next.points-d.total)+'</b><span>'+gxT('pts_next').replace('{n}',next.points-d.total)+'</span></div>':'')
      +'</div>';
  });
}
function saveAccountData(){
  var name=($('pd_name').value||'').trim(), area=($('pd_area').value||'').trim(), addr=($('pd_addr').value||'').trim();
  fetch('/api/account/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name,area:area,address:addr,theme:gxGet('gx_theme','light'),font:gxGet('gx_font','b')})})
  .then(function(r){return r.json();}).then(function(d){ if(d.ok) toast(gxT('ok_saved')); });
}
function accTab(id){
  document.querySelectorAll('.acc-sec').forEach(function(s){ s.classList.remove('on'); });
  document.querySelectorAll('.acc-btn').forEach(function(b){ b.classList.remove('on'); });
  var el=$(id); if(el) el.classList.add('on');
  var bt=document.querySelector('.acc-btn[data-tab="'+id+'"]'); if(bt) bt.classList.add('on');
}
/* ---------- football dna ---------- */
function trackView(pid){
  var v=gxGet('gx_views',[]); if(v.indexOf(pid)===-1){ v.push(pid); v=v.slice(-200); gxSet('gx_views',v); }
}
function dnaCard(id){
  var p=findProd(id); if(!p) return '';
  return '<a class="card" href="/product/'+p.id+'" style="text-decoration:none"><div class="pimg" style="background:linear-gradient(135deg,'+(p.colors[0]||'#E2E8F0')+','+(p.colors[1]||'#94A3B8')+')">'
    +'<img loading="lazy" src="/img/'+p.imgs[0]+'" alt=""><span class="pfav'+(gxGet('gx_favs',[]).indexOf(p.id)>-1?' on':'')+'" onclick="event.preventDefault();event.stopPropagation();toggleFav(\''+p.id+'\')">❤</span></div>'
    +'<div class="pbody"><b class="pname">'+p.name_ar+'</b><span class="pcat">'+gxT('cat_'+(p.kind==='mug'?'mug':'jersey'))+'</span>'
    +'<div class="pprice"><b>'+p.price+' '+GX.cur+'</b></div></div></a>';
}
function loadDNA(){
  var box=$('dnaBox'); if(!box) return;
  fetch('/api/dna').then(function(r){return r.json();}).then(function(d){
    var favs=gxGet('gx_favs',[]), views=gxGet('gx_views',[]);
    var jv=0, mv=0, clubs={}, sizes={};
    function addC(c){ if(c) clubs[c]=(clubs[c]||0)+1; }
    function addS(s){ if(s&&s!=='OS') sizes[s]=(sizes[s]||0)+1; }
    function addKind(k){ if(k==='mug') mv++; else jv++; }
    views.forEach(function(id){ var p=findProd(id); if(!p) return; addKind(p.kind); addC(p.club_id); });
    favs.forEach(function(id){ var p=findProd(id); if(!p) return; addKind(p.kind); addC(p.club_id); });
    d.orders.forEach(function(it){ addKind(it.kind); addC(it.club); addS(it.size); });
    var jTot=jv+mv;
    var kindLabel=jTot? (jv/jTot>0.7?gxT('dna_jersey'):(mv/jTot>0.7?gxT('dna_mug'):gxT('dna_both'))) : gxT('dna_both');
    var topClub=null, topN=0;
    Object.keys(clubs).forEach(function(c){ if(clubs[c]>topN){ topN=clubs[c]; topClub=c; } });
    var clubName=topClub&&GX.clubs[topClub]?GX.clubs[topClub][GX.lang==='ar'?'ar':'en']:'—';
    var topSize=null, topS=0;
    Object.keys(sizes).forEach(function(s){ if(sizes[s]>topS){ topS=sizes[s]; topSize=s; } });
    box.innerHTML='<div class="dna-grid">'
      +'<div class="dna-cell"><b>'+kindLabel+'</b><span>'+gxT('dna_ratio')+'</span></div>'
      +'<div class="dna-cell"><b>'+clubName+'</b><span>'+gxT('dna_club')+'</span></div>'
      +'<div class="dna-cell"><b>'+(topSize||'—')+'</b><span>'+gxT('dna_size')+'</span></div>'
      +'<div class="dna-cell"><b>'+gxT('lv_'+d.level)+'</b><span>'+gxT('dna_level')+'</span></div>'
      +'</div>';
    var rec=$('dnaRec');
    if(rec&&d.rec.length){ rec.innerHTML='<h4 style="margin:18px 0 10px">'+gxT('dna_pick')+'</h4><div class="grid">'+d.rec.map(dnaCard).join('')+'</div>'; }
    else if(rec){ rec.innerHTML='<p class="mnote">'+gxT('dna_empty')+'</p>'; }
  });
}
function findProd(id){ var r=null; GX.products.forEach(function(p){ if(p.id===id) r=p; }); return r; }
/* ---------- init ---------- */
function syncServerFavs(){
  if(!GX.user) return;
  fetch('/api/me').then(function(r){return r.json();}).then(function(d){
    if(d.ok && d.favs) gxSet('gx_favs',d.favs);
    renderFavs();
  }).catch(function(){});
}
document.addEventListener('DOMContentLoaded',function(){
  applyPrefs(); syncPrefs(); gxDev(); renderFavs(); syncServerFavs();
  if($('sq')){ $('sq').addEventListener('input',applyFilters); }
  if($('prod_id')){ trackView($('prod_id').value); }
  applyFilters(); renderCart(); tickCountdown(); setInterval(tickCountdown,1000);
  if($('dnaBox')) loadDNA();
  if(location.search.indexOf('fav=1')>-1){
    filters.fav=true;
    document.querySelectorAll('.chip').forEach(function(x){ if(x.textContent.indexOf('❤')>-1) x.classList.add('on'); });
    applyFilters();
    window.scrollTo({top:0});
  }
});
</script>"""


def hex_rgba(h, a):
    h = (h or "#E11D48").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        r, g, b = 225, 29, 72
    return "rgba(%d,%d,%d,%s)" % (r, g, b, a)


def club_themes():
    """merged per-club themes: cfg defaults overridden by DB settings."""
    out = {}
    for cid, t in cfg.CLUB_THEMES.items():
        merged = dict(t)
        db_t = db.club_theme_get(cid)
        if db_t and isinstance(db_t, dict):
            merged.update({k: v for k, v in db_t.items() if v})
        out[cid] = merged
    return out


def club_theme_css():
    rules = ""
    for cid, t in club_themes().items():
        rules += ('html[data-club="%s"] { --ac:%s; --ac2:%s; --glow:%s; --tint:%s; }\n'
                  % (cid, t.get("ac", "#E11D48"), t.get("ac2", "#F97316"),
                     hex_rgba(t.get("glow"), 0.32), hex_rgba(t.get("tint"), 0.08)))
    return rules


def atmos_html(mode="full"):
    """Football stadium atmosphere: decorative floating balls, particles and soft
    glows behind all content. pointer-events:none, honours prefers-reduced-motion."""
    balls = ""
    spec = [
        ("8%", "16%", "34px", "24s", "0s"), ("88%", "10%", "26px", "30s", "-7s"),
        ("93%", "60%", "40px", "26s", "-13s"), ("5%", "66%", "22px", "32s", "-19s"),
        ("50%", "4%", "20px", "28s", "-4s"), ("70%", "40%", "18px", "34s", "-16s"),
    ]
    if mode == "light":
        spec = spec[:3]
    for x, y, sz, dur, delay in spec:
        balls += ('<span class="atm-ball" style="left:%s;top:%s;font-size:%s;'
                  'animation-duration:%s;animation-delay:%s">⚽</span>' % (x, y, sz, dur, delay))
    dots_spec = [
        ("12%", "30%", "11s", "0s"), ("80%", "24%", "13s", "-4s"), ("64%", "74%", "10s", "-8s"),
        ("30%", "82%", "12s", "-2s"), ("20%", "54%", "9s", "-6s"), ("70%", "14%", "10s", "-9s"),
        ("45%", "38%", "8s", "-5s"), ("90%", "44%", "11s", "-11s"), ("10%", "86%", "10s", "-7s"),
        ("55%", "92%", "9s", "-3s"),
    ]
    if mode == "light":
        dots_spec = dots_spec[:6]
    dots = "".join('<span class="atm-dot" style="left:%s;top:%s;animation-duration:%s;animation-delay:%s"></span>'
                   % (x, y, dur, delay) for x, y, dur, delay in dots_spec)
    return ('<div class="stadium-bg" aria-hidden="true">'
            '<span class="atm-lines"></span><span class="atm-circle"></span>'
            '<span class="atm-glow g1"></span><span class="atm-glow g2"></span><span class="atm-glow g3"></span>'
            + balls + dots + '</div>')


def base_page(body, active="", page_js="", extra_club=None):
    en = lang() == "en"
    d = cfg.L[lang()]
    gx = gx_data()
    if extra_club:
        gx["club_page"] = extra_club
    gx_json = json_d(gx)
    js = BASE_JS.replace("__GX__", gx_json)
    head_extra = "<style>" + club_theme_css() + "</style>"
    if extra_club:
        head_extra += '<script>document.documentElement.setAttribute("data-club","%s");</script>' % extra_club
    match = gx.get("match")
    drop = gx.get("drop")
    pre = ""
    if match and not match.get("result"):
        mhome = cfg.CLUBS.get(match["home"], {})
        maway = cfg.CLUBS.get(match["away"], {})
        pre += (
            '<div class="md-banner" data-md><div class="md-teams">'
            '<span>{hem} {ha}</span><span class="md-vs">{vs}</span><span>{ae} {aa}</span></div>'
            '<div class="md-side" style="font-size:.95rem">'
            '<div class="md-count">{starts}</div><div class="md-count msout" data-ms="{iso}">--:--:--</div></div>'
            '<div style="display:flex;gap:10px;flex-wrap:wrap">'
            '<button class="btn sm" style="background:rgba(255,255,255,.2)" onclick="pickSide(\'{hid}\')">{hs}</button>'
            '<button class="btn sm" style="background:rgba(255,255,255,.2)" onclick="pickSide(\'{aid}\')">{asb}</button>'
            '</div></div>'
        ).format(hem=mhome.get("emoji", ""), ha=mhome.get(en and "en" or "ar", ""),
                 ae=maway.get("emoji", ""), aa=maway.get(en and "en" or "ar", ""),
                 vs=d["md_vs"], starts=d["md_starts"], iso=match["kickoff_iso"],
                 hid=match["home"], aid=match["away"],
                 hs=d["md_shop"].replace("👕", "") + " " + mhome.get(en and "en" or "ar", ""),
                 asb=d["md_shop"].replace("👕", "") + " " + maway.get(en and "en" or "ar", ""))
    if drop and not drop["passed"]:
        pre += (
            '<div class="drop-banner"><h2>{ic} {name}</h2>'
            '<p style="opacity:.95;margin-top:6px;font-weight:700">{msg}</p>'
            '<div class="drop-count" data-ctarget="{iso}"><span class="cdout" style="font-size:1.5rem;font-weight:900;font-variant-numeric:tabular-nums">--:--:--:--</span></div>'
            '<div style="margin-top:14px"><button class="btn ghost" onclick="openModal(\'m-drop\')">{rem}</button></div></div>'
        ).format(ic=d["drop_title"].split(" ")[0] or "🔥", name=drop.get(en and "en" or "ar", ""),
                 msg=d["drop_coming"], iso=drop["target_iso"], rem=d["drop_remind"])
    elif drop and drop["passed"]:
        pre += ('<div class="drop-banner"><h2>{a}</h2><p style="margin-top:8px">{b}</p>'
                '<div style="margin-top:14px"><a class="btn pri" href="/home#jerseys">{c}</a></div></div>'
                ).format(a=d["drop_live"], b=drop.get(en and "en" or "ar", ""), c=d["drop_shop"])
    return """<!DOCTYPE html>
<html lang="LANG" dir="DIR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>golazox</title>
<meta name="description" content="golazox — football club jerseys & sports mugs, order on WhatsApp">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚽</text></svg>">
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Poppins:wght@400;600;700;800;900&display=swap" rel="stylesheet">
CSS
HEADEXTRA
</head>
<body>
HEADER
PRE
BODY
FOOTER
MODALS
<div class="co" id="co" onclick="closeCart()"></div>
<div class="cd" id="cd"><div class="cd-head"><b>🛒 T_CART</b><button class="mx" onclick="closeCart()">✕</button></div>
<div class="cd-body" id="cdb"></div><div class="cd-foot" id="cdf"></div></div>
<div class="lb" id="lb" onclick="closeLB()"><img id="lbimg" alt=""></div>
<a class="fab" target="_blank" rel="noopener" href="https://wa.me/WA" title="WhatsApp">💬</a>
PAGEJS
JS
</body>
</html>""".replace("LANG", "en" if en else "ar") \
        .replace("DIR", "ltr" if en else "rtl") \
        .replace("FONT", "Poppins" if en else "Cairo") \
        .replace("CSS", CSS) \
        .replace("HEADEXTRA", head_extra) \
        .replace("HEADER", header_html(active)) \
        .replace("PRE", pre) \
        .replace("BODY", body) \
        .replace("FOOTER", footer_html()) \
        .replace("MODALS", modals_html()) \
        .replace("T_CART", d["cart_title"]) \
        .replace("WA", cfg.WHATSAPP) \
        .replace("PAGEJS", page_js) \
        .replace("JS", js)


def header_html(active=""):
    en = lang() == "en"
    d = cfg.L[lang()]
    def nv(id_, key, href):
        cls = " on" if id_ == active else ""
        return '<button class="nv%s" onclick="location.href=\'%s\'">%s</button>' % (cls, href, d[key])
    links = (nv("home", "nav_home", "/home")
             + nv("products", "nav_jerseys", "/products")
             + nv("mugs", "nav_mugs", "/mugs")
             + nv("sizes", "nav_sizes", "/size-guide")
             + nv("order", "nav_order", "/how-to-order")
             + '<button class="nv" onclick="openModal(\'m-contact\')">' + d["nav_contact"] + '</button>')
    other = "ar" if en else "en"
    me = current_user()
    if me:
        if me.get("role") in ("admin", "super_admin"):
            acc_btn = '<a href="/admin" class="hbtn admin-btn">👑 ' + d["admin_dash_short"] + '</a>'
        else:
            acc_btn = '<a href="/account" class="hbtn">👤 ' + esc(me.get("name") or d["ac_account"]) + '</a>'
    else:
        acc_btn = '<a href="/login" class="hbtn">👤 ' + d["ac_login"] + '</a>'
    cheer = ('<button class="hbtn" id="cheerBtn" onclick="cheerNow()" title="' + d["ch_title"] + '">⚽ ' + d["ch_btn"] + '</button>') if match_info() else ""
    fav_btn = '<button class="hbtn hicon" onclick="openFavs()" title="' + d["fav_filter"] + '">❤️<span class="hcount" id="favcount">0</span></button>'
    return ('<div class="hd"><div class="hd-in">'
            '<a href="/home" class="logo"><span class="ball">⚽</span>golazox</a>'
            '<nav class="nav" id="topnav">%s'
            '<button class="nv nv-close" onclick="toggleMenu()">✕</button></nav>'
            '<button class="hbtn hmenu" onclick="toggleMenu()">☰</button>'
            '%s'
            '<button class="hbtn hicon" onclick="openModal(\'m-settings\')">⚙️<span class="hcount" id="cbadge">0</span></button>'
            '<button class="hbtn hicon" onclick="openCart()">🛒<span class="hcount" id="cbadge2">0</span></button>'
            '<button class="hbtn" onclick="setLang(\'%s\')">%s</button>'
            '<div class="hd-search"><div class="sbox hd-sbox">'
            '<input id="sq" placeholder="%s" onkeydown="if(event.key===\'Enter\')applyFilters()">'
            '<button onclick="applyFilters()">🔍</button></div></div>'
            '</div></div>') % (links, fav_btn + cheer + acc_btn, other, d["lang_name"], d["search_ph"])


def footer_html():
    en = lang() == "en"
    d = cfg.L[lang()]
    club_links = "".join('<a href="/club/{cid}">{em} {nm}</a>'.format(
        cid=cid, em=c.get("emoji", ""), nm=c.get(en and "en" or "ar", ""))
        for cid, c in cfg.CLUBS.items())
    col_links = ("<a href='/home'>{h}</a><a href='/products'>{j}</a><a href='/mugs'>{m}</a>"
                 "<a href='/size-guide'>{s}</a><a href='/how-to-order'>{o}</a>").format(
        h=d["nav_home"], j=d["nav_jerseys"], m=d["nav_mugs"], s=d["nav_sizes"], o=d["nav_order"])
    col_help = ("<a href='/care'>{a}</a><a href='/return-policy'>{b}</a>"
                "<a onclick='openModal(\"m-contact\")'>{c}</a>"
                "<a href='/favorites'>❤️ {f}</a><a href='/cart'>🛒 {cart}</a>").format(
        a=d["wash_title"], b=d["ret_title"], c=d["nav_contact"], f=d["fav_filter"],
        cart=d["cart_title"])
    return ('<footer class="ft"><div class="ft-in">'
            '<div class="ft-grid">'
            '<div class="ft-col"><div class="ft-brand">⚽ golazox</div>'
            '<p class="ft-desc">{badge}</p>'
            '<div class="ft-social">'
            '<a target="_blank" rel="noopener" href="https://wa.me/{wa}" title="{wa_title}">💬</a>'
            '<a target="_blank" rel="noopener" href="{tg}" title="{tg_title}">✈️</a>'
            '<a onclick="setLang(\'{other}\')" title="{lang}">{langname}</a>'
            '</div></div>'
            '<div class="ft-col"><h4>{t1}</h4>{col_links}</div>'
            '<div class="ft-col"><h4>{t2}</h4>{club_links}</div>'
            '<div class="ft-col"><h4>{t3}</h4>{col_help}'
            '<a target="_blank" rel="noopener" href="{tg}" style="margin-top:10px;font-weight:800">{tg_txt} ✈️</a>'
            '</div></div>'
            '<p class="ft-copy">{copy}</p>'
            '</div></footer>').format(
        badge=d["badge"], wa=cfg.WHATSAPP, wa_title=d["ft_wa"], tg=cfg.TG_LINK,
        tg_title=d["ft_tg"], tg_txt=d["order_tg"], other="ar" if en else "en",
        lang=d["lang_name"], langname=d["lang_name"],
        t1=d["ft_links"], col_links=col_links, t2=d["ft_clubs"], club_links=club_links,
        t3=d["ft_help"], col_help=col_help, copy=d["footer_copy"])


def size_table_html(chart):
    d = cfg.L[lang()]
    head = ("<tr><th>{s}</th><th>{l}</th><th>{w}</th><th>{h}</th><th>{wg}</th></tr>").format(
        s=d["szt_size"], l=d["szt_length"], w=d["szt_width"], h=d["szt_height"], wg=d["szt_weight"])
    rows = ""
    for sz in cfg.SIZE_ORDER:
        if sz not in chart:
            continue
        r = chart[sz]
        rows += ("<tr><td class='sz'>{sz}</td><td>{l} {cm}</td><td>{w} {cm}</td>"
                 "<td>{h}</td><td>{wg} {kg}</td></tr>").format(
            sz=sz, l=r["length"], w=r["width"], h=r["height"], wg=r["weight"],
            cm=d["szt_cm"], kg=d["szt_kg"])
    return "<table class='szt'>" + head + rows + "</table>"


def size_diagram():
    en = lang() == "en"
    chest = "عرض الصدر" if not en else "Chest"
    length = "طول التيشرت" if not en else "Length"
    return """<svg class="szt-ill" viewBox="0 0 260 250">
<path d="M62 34 L98 20 L120 46 L140 46 L162 20 L198 34 L212 84 L182 98 L176 212 L84 212 L78 98 L48 84 Z"
      fill="var(--card2)" stroke="var(--txt)" stroke-width="3" stroke-linejoin="round"/>
<line x1="52" y1="120" x2="208" y2="120" stroke="#F59E0B" stroke-width="3"/>
<polygon points="52,120 62,115 62,125" fill="#F59E0B"/>
<polygon points="208,120 198,115 198,125" fill="#F59E0B"/>
<text x="130" y="111" text-anchor="middle" font-size="15" font-weight="700" fill="#F59E0B" font-family="Arial">CHEST</text>
<line x1="238" y1="30" x2="238" y2="214" stroke="#3B82F6" stroke-width="3"/>
<polygon points="238,30 233,40 243,40" fill="#3B82F6"/>
<polygon points="238,214 233,204 243,204" fill="#3B82F6"/>
<text x="251" y="122" text-anchor="middle" font-size="15" font-weight="700" fill="#3B82F6" font-family="Arial" transform="rotate(90 251 122)">LEN</text>
</svg>""".replace("CHEST", chest).replace("LEN", length)


def auth_box_html():
    d = cfg.L[lang()]
    return ('<div class="auth-box">'
            '<p class="mnote">{sub}</p>'
            '<div class="auth-tabs">'
            '<button class="atab on" data-tab="otp" onclick="authTab(\'otp\')">{t1}</button>'
            '<button class="atab" data-tab="pw" onclick="authTab(\'pw\')">{t2}</button></div>'
            '<div class="auth-pane" id="auth_pane_otp">'
            '<div class="auth-step1" id="au_step1">'
            '<div class="fld"><label>{em}</label>'
            '<input id="au_email" type="email" inputmode="email" placeholder="{emph}" autocomplete="off"></div>'
            '<button class="btn pri big" id="au_sendbtn" onclick="authSendCode()">{ct}</button></div>'
            '<div class="auth-step2" id="au_step2">'
            '<p class="auth-sent">📨 {sent} <b id="au_sentto"></b></p>'
            '<div class="fld"><label>{otp}</label><input id="au_code" inputmode="numeric" maxlength="6"></div>'
            '<div class="fld" id="au_newbox"><label>{nm}</label><input id="au_name"></div>'
            '<div class="auth-new" id="au_new">{new}</div>'
            '<div class="auth-demo" id="au_demo">{demo} <b id="au_democode"></b>'
            '<div id="au_demo_note" style="display:none;margin-top:6px;font-weight:800">✅ {fill}</div></div>'
            '<button class="btn pri big" id="au_vbtn" onclick="authVerify()">{v}</button>'
            '<div class="auth-actions">'
            '<button class="hbtn" id="au_resendbtn" onclick="authResend()">🔄 {resend}</button>'
            '<button class="hbtn" onclick="authChangePhone()">↩ {chg}</button></div></div>'
            '</div>'
            '<div class="auth-pane" id="auth_pane_pw" style="display:none">'
            '<div class="fld"><label>{em}</label>'
            '<input id="pw_email" type="email" inputmode="email" placeholder="{emph}" autocomplete="off"></div>'
            '<div class="fld"><label>{pw}</label><input id="pw_pass" type="password"></div>'
            '<button class="btn pri big" onclick="authPwLogin()">{pb}</button></div>'
            '</div>'
            ).format(sub=d["auth_sub"], t1=d["auth_tab_otp"], t2=d["auth_tab_pw"],
                     em=d["auth_email"], emph=d["auth_email_ph"], ct=d["auth_continue"], sent=d["auth_sent_to"],
                     otp=d["auth_otp_ph"], nm=d["auth_name_ph"], new=d["auth_new"], demo=d["auth_demo_note"],
                     fill=d["auth_demo_fill"], v=d["auth_verify"], resend=d["auth_resend"], chg=d["auth_change_num"],
                     pw=d["auth_pw_ph"], pb=d["auth_pw_btn"])


def modals_html():
    d = cfg.L[lang()]
    en = lang() == "en"
    def modal(mid, title, body, wide=False):
        return ('<div class="mback" id="{id}" onclick="closeModal(\'{id}\')">'
                '<div class="mbox {w}" onclick="event.stopPropagation()">'
                '<div class="mhead"><h3>{t}</h3><button class="mx" onclick="closeModal(\'{id}\')">✕</button></div>'
                '<div class="mbody">{b}</div></div></div>').format(id=mid, w="wide" if wide else "", t=title, b=body)

    wash_steps = "".join("<li><b>{n}</b> {txt}</li>".format(n=i + 1, txt=d["wash_" + str(i + 1)]) for i in range(8))
    ret_items = "".join("<li><b>{t}</b> — {x}</li>".format(t=d["ret_" + str(i) + "t"], x=d["ret_" + str(i) + "d"]) for i in range(1, 5))

    size_body = ("<p class='mnote'>{note}</p>".format(note=d["szt_note"]) + size_table_html(cfg.SIZE_CHART)
                 + "<h4 class='msec'>{m}</h4>".format(m=d["szt_measure"]) + "<div class='szill-wrap'>" + size_diagram() + "</div>"
                 + "<ol class='steps'><li>{a}</li><li>{b}</li></ol>".format(a=d["szt_measure_1"], b=d["szt_measure_2"])
                 + "<div class='mwarning'>💡 {t}<br>{x}</div>".format(t=d["szt_between"], x=d["szt_between_txt"]))
    wash_body = "<ol class='steps'>" + wash_steps + "</ol>" + "<div class='mwarning'>⚠️ {w}</div>".format(w=d["wash_warn"])
    ret_body = "<ul class='ret'>" + ret_items + "</ul>" + "<div class='mwarning'>⚠️ {w}</div>".format(w=d["ret_warn"])
    how_body = ("<ol class='steps'>" + "".join("<li>{x}</li>".format(x=d["how_" + str(i + 1)]) for i in range(4)) + "</ol>")
    contact_body = ("<p class='mnote'>{sub}</p>".format(sub=d["contact_sub"])
                    + "<a class='btn wa big' target='_blank' rel='noopener' href='https://wa.me/{num}'>💬 {wa}</a>".format(num=cfg.WHATSAPP, wa=d["contact_wa"])
                    + "<p class='cnum'>{n}</p>".format(n=d["contact_num"]))

    theme_seg = ('<div class="seg" data-seg="theme">'
                 '<button data-v="light" onclick="setTheme(\'light\')">{a}</button>'
                 '<button data-v="dark" onclick="setTheme(\'dark\')">{b}</button></div>').format(a=d["theme_light"], b=d["theme_dark"])
    font_seg = ('<div class="seg" data-seg="font">'
                '<button data-v="a" onclick="setFont(\'a\')">{a}</button>'
                '<button data-v="b" onclick="setFont(\'b\')">{b}</button>'
                '<button data-v="c" onclick="setFont(\'c\')">{c}</button></div>').format(a=d["font_small"], b=d["font_med"], c=d["font_large"])
    club_opts = "".join('<button data-v="%s">%s %s</button>' % (cid, c.get("emoji", ""), c.get(en and "en" or "ar")) for cid, c in cfg.CLUBS.items())
    club_seg = ('<div class="seg" data-seg="club" style="gap:6px">'
                '<button data-v="null" onclick="setMyClub(null)">{all}</button>' + club_opts + '</div>').format(all=d["filter_all"])
    settings_body = ('<div class="set-row"><span class="st">{lg}</span><span style="font-weight:800;color:var(--ac)">{langname}</span></div>'
                     '<div class="set-row"><span class="st">{th}</span>{theme}</div>'
                     '<div class="set-row"><span class="st">{ft}</span>{font}</div>'
                     '<div class="set-row"><span class="st">{team}<small>{favorite}</small></span>{club}</div>'
                     ).format(lg=d["set_lang"], langname=d["lang_name"], th=d["set_theme"], theme=theme_seg,
                              ft=d["set_font"], font=font_seg, team=d["md_support"], favorite=d["nav_jerseys"],
                              club=club_seg)

    checkout_body = ('<p class="mnote">{sub}</p>'
                     '<div class="fld"><label>{name}</label><input id="co_name"></div>'
                     '<div class="fld"><label>{phone}</label><input id="co_phone" inputmode="tel"></div>'
                     '<div class="frow"><div class="fld"><label>{area}</label><input id="co_area"></div>'
                     '<div class="fld"><label>{addr}</label><input id="co_addr"></div></div>'
                     '<div class="fld"><label>{notes}</label><textarea id="co_notes"></textarea></div>'
                     '<button class="btn wa big" onclick="submitOrder()">{btn}</button>'
                     ).format(sub=d["cart_total"], name=d["co_name"], phone=d["co_phone"],
                              area=d["co_area"], addr=d["co_address"], notes=d["co_notes"], btn=d["co_submit"])

    notify_body = ('<p class="mnote">{sub}</p>'
                   '<input type="hidden" id="nf_prod"><input type="hidden" id="nf_size">'
                   '<div class="fld"><label>{cl}</label><select id="nf_cc"><option value="+973">+973</option><option value="+966">+966</option><option value="+965">+965</option><option value="+974">+974</option><option value="+971">+971</option></select></div>'
                   '<div class="fld"><label>{ph}</label><input id="nf_phone" inputmode="tel"></div>'
                   '<button class="btn pri big" onclick="submitNotify()">{btn}</button>'
                   ).format(sub=d["notif_sub"], cl=d["country_label"], ph=d["phone_label"], btn=d["notify_btn"])

    drop_body = ('<p class="mnote">{sub}</p><div class="fld"><label>{ph}</label><input id="dr_phone" inputmode="tel"></div>'
                 '<button class="btn pri big" onclick="submitDropRemind()">{btn}</button>'
                 ).format(sub=d["drop_remind"], ph=d["drop_input"], btn=d["drop_remind"])

    req_vers = "".join('<button class="radio" data-g="ver" data-v="%s" onclick="pickReqVer(\'%s\')">%s</button>' % (v, v, d["ver_" + v]) for v in ("home", "away", "third", "player", "fan"))
    req_body = ('<p class="mnote">{sub}</p>'
                '<div class="fld"><label>{club}</label><input id="req_club"></div>'
                '<div class="fld"><label>{type}</label><div class="radios">'
                '<button class="radio on" data-g="rty" data-v="jersey" onclick="pickReqType(\'jersey\')">{tj}</button>'
                '<button class="radio" data-g="rty" data-v="mug" onclick="pickReqType(\'mug\')">{tm}</button>'
                '<button class="radio" data-g="rty" data-v="other" onclick="pickReqType(\'other\')">{to}</button></div></div>'
                '<div class="fld" id="reqverfld"><label>{ver}</label><div class="radios">{vers}</div></div>'
                '<div class="frow"><div class="fld"><label>{size}</label><input id="req_size" placeholder="S / M / L / XL"></div>'
                '<div class="fld"><label>{qty}</label><div class="qty"><button onclick="var q=$(\'req_qty\');var v=parseInt(q.textContent,10)-1;if(v<1)v=1;q.textContent=v">−</button><span class="qn" id="req_qty">1</span><button onclick="var q=$(\'req_qty\');var v=parseInt(q.textContent,10)+1;if(v>99)v=99;q.textContent=v">+</button></div></div></div>'
                '<div class="fld"><label>{notes}</label><textarea id="req_notes"></textarea></div>'
                '<img id="req_photo" style="display:none;max-height:140px;border-radius:12px;margin-bottom:10px" alt="">'
                '<button class="btn wa big" onclick="submitRequest()">{send}</button>'
                ).format(sub=d["req_sub"], club=d["req_club"], type=d["req_type"],
                         tj=d["type_jersey"], tm=d["type_mug"], to=d["type_other"],
                         ver=d["req_version"], vers=req_vers, size=d["req_size"],
                         qty=d["req_qty"], notes=d["req_notes"], send=d["req_send"])

    img_body = ('<p class="mnote">{sub}</p>'
                '<div style="display:flex;gap:10px;flex-wrap:wrap">'
                '<label class="btn pri" style="flex:1;justify-content:center">{cam}<input type="file" accept="image/*" capture="environment" onchange="isHandleFile(this,true)" style="display:none"></label>'
                '<label class="btn ghost" style="flex:1;justify-content:center">{up}<input type="file" accept="image/*" onchange="isHandleFile(this,false)" style="display:none"></label></div>'
                '<div class="fld" style="margin-top:12px"><label>{desc}</label><input id="is_desc" placeholder="{ph}"></div>'
                '<p id="is_analyzing" class="mnote" style="margin-top:10px;font-weight:800;display:none">{an}</p>'
                '<div id="is_resultsBox"></div>'
                ).format(sub=d["is_sub"], cam=d["is_camera"], up=d["is_upload"],
                         desc=d["is_desc"], ph=d["is_desc_ph"], an=d["is_analyzing"])

    points_body = '<div id="ptsBox"></div>'

    tryit_body = ('<p class="mnote">{sub}</p>'
                  '<div style="display:flex;gap:10px;flex-wrap:wrap">'
                  '<label class="btn pri" style="flex:1;justify-content:center">{cam}<input id="tryfile" type="file" accept="image/*" capture="environment" onchange="tryHandle(this,true)" style="display:none"></label>'
                  '<label class="btn ghost" style="flex:1;justify-content:center">{up}<input type="file" accept="image/*" onchange="tryHandle(this,false)" style="display:none"></label></div>'
                  '<p class="img-search-tip">{hint}</p>'
                  '<div id="tryCanvasWrap" style="display:none;margin-top:10px">'
                  '<div class="try-stage"><canvas id="tryCanvas"></canvas><span class="try-ai">{ai}</span></div>'
                  '<div class="mwarning">⚠️ {dis}</div>'
                  '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:12px">'
                  '<button class="btn pri" style="flex:1" onclick="tryAdd()">{add}</button>'
                  '<button class="btn ghost" style="flex:1" onclick="tryShare()">{sh}</button>'
                  '<button class="btn ghost" style="flex:1" onclick="tryReset()">{ag}</button></div>'
                  '<p class="img-search-tip">{priv}</p></div>'
                  ).format(sub=d["try_sub"], cam=d["try_cam"], up=d["try_up"], hint=d["try_hint"],
                           ai=d["try_ai"], dis=d["try_dis"], add=d["try_add"], sh=d["try_share"],
                           ag=d["try_again"], priv=d["try_priv"])

    pricedrop_body = ('<p class="mnote">{sub}</p>'
                      '<input type="hidden" id="pd_prod">'
                      '<div class="fld"><label>{ph}</label><input id="pd_phone" inputmode="tel" placeholder="+973 ________"></div>'
                      '<button class="btn pri big" onclick="submitPriceDrop()">{btn}</button>'
                      ).format(sub=d["pd_sub"], ph=d["pd_phone"], btn=d["pd_btn"])

    login_body = auth_box_html()

    reorder_body = '<div id="ro_body"></div>'

    return (modal("m-sizes", d["szt_head"], size_body, True)
            + modal("m-wash", d["wash_title"], wash_body, True)
            + modal("m-ret", d["ret_title"], ret_body, True)
            + modal("m-how", d["how_title"], how_body)
            + modal("m-contact", d["contact_title"], contact_body)
            + modal("m-settings", d["set_title"], settings_body)
            + modal("m-checkout", d["co_title"], checkout_body)
            + modal("m-notify", d["notif_title"], notify_body)
            + modal("m-drop", d["drop_title"], drop_body)
            + modal("m-request", d["req_title"], req_body, True)
            + modal("m-imgsearch", d["is_title"], img_body)
            + modal("m-points", d["pts_title"], points_body)
            + modal("m-tryit", d["try_title"], tryit_body, True)
            + modal("m-pricedrop", d["pd_title"], pricedrop_body)
            + modal("m-login", d["auth_title"], login_body)
            + modal("m-reorder", d["ro_title"], reorder_body))


# ============================== PAGES ==============================
def filters_panel_html():
    en = lang() == "en"
    d = cfg.L[lang()]
    dots = ""
    for i, (_, label, hexc) in enumerate(COLOR_FILTERS):
        cls = " hide" if i >= 6 else ""
        dots += ('<button class="col-dot%s" data-col="%s" title="%s" onclick="setColorFilter(this)" '
                 'style="background:%s"></button>' % (cls, hexc, label, hexc))
    if len(COLOR_FILTERS) > 6:
        dots += '<button class="col-more" id="colMore" onclick="moreColors()">%s</button>' % d["fp_more"]
    cats = "".join(
        '<label class="cat-opt"><input type="radio" name="fpcat" value="%s" '
        'onchange="filters.cat=this.value;applyFilters()"> %s</label>'
        % (k, d["cat_" + k]) for k in ("best", "new", "offer"))
    clubs = "".join(
        '<button class="club-opt" data-v="%s" onclick="setFilter(\'club\',this.getAttribute(\'data-v\'),this)">%s %s</button>'
        % (cid, c.get("emoji", "⚽"), c.get(en and "en" or "ar")) for cid, c in cfg.CLUBS.items())
    sizes = "".join(
        '<button class="sz-btn" onclick="setFilter(\'size\',\'%s\',this)">%s</button>' % (s, s)
        for s in cfg.SIZE_ORDER[:5])
    return ('<aside class="filters-panel" id="filtersBar">'
            '<div class="fp-title">⚙️ {t}</div>'
            '<div class="fp-sec"><div class="fp-lbl">🎨 {cols}</div><div class="fp-colors">{dots}</div></div>'
            '<div class="fp-sec"><div class="fp-lbl">🔥 {cat}</div><div class="fp-cats">{cats}</div></div>'
            '<details class="fp-acc"><summary>🛡️ {club}</summary>'
            '<div class="fp-clubs" style="margin-top:8px">{clubs}</div></details>'
            '<div class="fp-sec" style="margin-top:14px"><div class="fp-lbl">📏 {size}</div>'
            '<div class="fp-sizes">{sizes}</div></div>'
            '<button class="btn dark block fp-apply" onclick="applyFilters();toggleFilters(false)">{res}</button>'
            '</aside>').format(t=d["fp_title"], cols=d["fp_colors"], dots=dots, cat=d["fp_cat"], cats=cats,
                               club=d["fp_club"], clubs=clubs, size=d["fp_size"], sizes=sizes, res=d["show_results"])


def sort_bar_html():
    d = cfg.L[lang()]
    return ('<div class="sort-bar">'
            '<span class="sort-lbl">{lbl}</span>'
            '<select class="sel sort" id="sortSel" onchange="applySort()">'
            '<option value="best" selected>{sb}</option><option value="new">{sn}</option>'
            '<option value="lo">{lo}</option><option value="hi">{hi}</option></select>'
            '<button class="btn ghost sm fbtn" onclick="toggleFilters()">⚙️ {fb}</button>'
            '<button class="btn ghost sm" onclick="clearFilters()">{clr}</button>'
            '</div>').format(lbl=d["sort_label"], sb=d["sort_best"], sn=d["sort_new"],
                             lo=d["sort_lo"], hi=d["sort_hi"], fb=d["filters_btn"], clr=d["clear_filters"])


def shop_section_html(grid, grid_id):
    d = cfg.L[lang()]
    return ('<div class="shop-wrap">'
            + filters_panel_html()
            + '<div class="shop-main">'
            + sort_bar_html()
            + '<div class="grid" id="{gid}">{grid}</div>'
            + '<div class="search-none" id="searchNone" style="display:none"><div class="sn-ic">🔍</div>'
            '<p class="mnote">{sn}</p><button class="btn pri" onclick="clearFilters()">{show}</button></div>'
            + '</div></div>').format(gid=grid_id, grid=grid, sn=d["search_none"], show=d["show_all"])


def features_html():
    d = cfg.L[lang()]
    rows = ""
    for i in range(1, 5):
        rows += ('<div class="feat"><span class="fic">{ic}</span>'
                 '<div><b>{t}</b><span>{x}</span></div></div>').format(
            ic=("🚚", "💳", "🏆", "🔄")[i - 1], t=d["feat_%d_t" % i], x=d["feat_%d_d" % i])
    return '<div class="feat-bar">{rows}</div>'.format(rows=rows)


def home_body():
    en = lang() == "en"
    d = cfg.L[lang()]

    prods = [p for p in cfg.PRODUCTS if not p.get("hidden")]
    jgrid = "".join(product_card(p) for p in prods if p["kind"] == "jersey")
    mgrid = "".join(product_card(p) for p in prods if p["kind"] == "mug")

    best_html = "".join(product_card(p) for p in prods if "best" in p.get("badges", []))
    new_html = "".join(product_card(p) for p in prods if "new" in p.get("badges", []))

    clubs_html = ""
    loy_btns = ""
    for cid, c in cfg.CLUBS.items():
        th = club_themes().get(cid, {})
        ac = th.get("ac", "#E11D48"); ac2 = th.get("ac2", "#F97316")
        cnt = sum(1 for p in prods if p.get("club_id") == cid)
        nm = c.get(en and "en" or "ar", "")
        em = c.get("emoji", "⚽")
        clubs_html += ('<a class="clubcard" href="/club/{cid}" style="--cc:{ac};--cc2:{ac2}">'
                       '<span class="cc-logo"><span class="em">{em}</span></span>'
                       '<b>{nm}</b><span class="cc-count">{cnt} {prod}</span>'
                       '<span class="cc-go">{go} ←</span></a>'
                       ).format(cid=cid, ac=ac, ac2=ac2, em=em, nm=nm,
                                cnt=cnt, prod=d["club_items_label"], go=d["club_view_lineup"])
        loy_btns += ('<button class="loy-btn" data-cid="{cid}" style="--cc:{ac}" onclick="pickLoyal(\'{cid}\',this)">'
                     '<span class="lb-em">{em}</span><span class="lb-t">{nm}</span></button>'
                     ).format(cid=cid, ac=ac, em=em, nm=nm)

    steps = "".join(
        ('<div class="step-card rv"><span class="step-num">{n}</span>'
         '<div class="step-ic">{ic}</div><h3>{t}</h3><p>{x}</p></div>')
        .format(n=i + 1, ic=("🛒", "📏", "💬", "🚚")[i],
                t=d["step_%d_t" % (i + 1)], x=d["step_%d_d" % (i + 1)])
        for i in range(4))

    hero = ('<div class="hero">'
            '<span class="hero-tag"><span class="pulse"></span>{tag}</span>'
            '<h1>{t1}<br><span class="g">{t2}</span></h1><p>{sub}</p>'
            '<div class="hero-btns"><a class="btn pri" href="/products">{cj}</a>'
            '<a class="btn ghost" href="#clubs">{ct}</a></div>'
            '<div class="hero-ball"><span class="ring"></span>⚽</div></div>'
            ).format(tag=d["home_section_hero_tag"], t1=d["home_hero_t1"], t2=d["home_hero_t2"],
                     sub=d["home_hero_sub"], cj=d["home_cta_shop"], ct=d["home_cta_team"])

    clubs_sec = ('<div class="sec rv" id="clubs"><div class="sec-head"><h2><span class="bar"></span>{t}</h2>'
                 '<span class="sec-sub">{s}</span></div>'
                 '<div class="clubs">{cards}</div></div>'
                 ).format(t=d["clubs_pick_title"], s=d["clubs_pick_sub"], cards=clubs_html)

    loyal_sec = ('<div class="sec rv"><div class="sec-head"><h2><span class="bar"></span>{t}</h2></div>'
                 '<div class="loyal">'
                 '<div style="font-size:42px">⚽</div>'
                 '<h3 class="loyal-q">{q}</h3>'
                 '<p class="loyal-sub" id="loyMsg">{pick}</p>'
                 '<div class="loyal-pick">{btns}</div>'
                 '<div class="loyal-out" id="loyOut"><span class="great">{great}</span>'
                 '<div><a class="btn pri loyal-go" id="loyGo" href="#">{go} ←</a></div></div>'
                 '</div></div>'
                 ).format(t=d["loyal_title"], q=d["loyal_q"], pick=d["loyal_pick_plz"],
                          btns=loy_btns, great=d["loyal_great"], go=d["loyal_go"])

    size_sec = ('<div class="sec rv"><div class="szsec-banner">'
                '<span class="big-ic">📏</span>'
                '<div><h2>{t}</h2><p>{s}</p></div>'
                '<a class="btn btn-light" href="/size-guide">{b} ←</a></div></div>'
                ).format(t=d["szsec_title"], s=d["szsec_sub"], b=d["szsec_btn"])

    steps_sec = ('<div class="sec rv"><div class="sec-head"><h2><span class="bar"></span>{t}</h2></div>'
                 '<div class="steps-grid">{steps}</div></div>'
                 ).format(t=d["steps_title"], steps=steps)

    pitch_sec = ('<div class="sec rv"><div class="pitch-sec">'
                 '<span class="pitch-lines"></span><span class="pitch-half"></span><span class="pitch-mid"></span>'
                 '<span class="pitch-ball">⚽</span>'
                 '<h2>{t1}<br>{t2}</h2>'
                 '<a class="btn pri" href="/products">{b}</a>'
                 '</div></div>'
                 ).format(t1=d["pitch_title"], t2=d["pitch_title2"], b=d["pitch_btn"])

    match_html = ""
    mi = match_info()
    if mi:
        mhome = cfg.CLUBS.get(mi["home"], {}); maway = cfg.CLUBS.get(mi["away"], {})
        match_html = ('<div class="sec"><div class="match-card">'
                      '<div class="sec-head"><h2><span class="bar"></span>{t}</h2><span class="sec-sub">{sub}</span></div>'
                      '<div class="mc-teams"><span class="mc-team">{hem} <b>{ha}</b></span>'
                      '<span class="mc-vs">VS</span>'
                      '<span class="mc-team"><b>{ae}</b> {aa}</span></div>'
                      '<div class="mc-count">{starts}</div>'
                      '<div class="mc-count msout" data-ms="{iso}">--:--:--</div>'
                      '<div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:16px">'
                      '<a class="btn pri" href="/club/{hid}">{hs}</a>'
                      '<a class="btn ghost" href="/club/{aid}">{asb}</a></div></div></div>'
                      ).format(t=d["next_match"], sub=d["next_match_sub"],
                               hem=mhome.get("emoji", ""), ha=mhome.get(en and "en" or "ar", ""),
                               ae=maway.get("emoji", ""), aa=maway.get(en and "en" or "ar", ""),
                               starts=d["md_starts"], iso=mi["kickoff_iso"],
                               hid=mi["home"], aid=mi["away"], hs=d["md_shop"], asb=d["md_shop"])
    poll_html = ""
    pol = gx_data()["poll"]
    if pol:
        data = pol["data"]
        q = data.get("q_" + lang()) or data.get("q_ar", "")
        options = data.get("options", [])
        total = pol["total"]
        winner = data.get("winner")
        if pol["status"] == "closed" or pol["ended"]:
            poll_html += '<div class="sec"><div class="poll poll-win"><div class="big">' + d["poll_winner"] + '</div>'
            if winner:
                w = next((o for o in options if str(o.get("id")) == str(winner)), None)
                poll_html += '<div style="font-size:1.8rem;font-weight:900;color:var(--ac);margin-top:8px">' + esc(w.get("label_" + lang(), w.get("label_ar"))) + '</div>' if w else ''
            poll_html += '<p class="mnote">' + d["poll_thanks"] + '</p></div></div>'
        else:
            poll_html += ('<div class="sec"><div class="poll"><div class="sec-head"><h2><span class="bar"></span>' + d["poll_title"] + '</h2></div>'
                          '<p class="mnote" style="font-weight:800">' + esc(q) + '</p>')
            for o in options:
                votes = pol["votes"].get(o.get("id") or o.get("key"), 0)
                pct = int(round(votes / total * 100)) if total else 0
                label = o.get("label_" + lang(), o.get("label_ar"))
                color = o.get("color", "var(--ac)")
                poll_html += ('<div class="poll-opt" onclick="votePoll(\'{key}\')">'
                              '<div class="pbar" style="width:{pct}%"></div>'
                              '<div class="pf" style="background:{c}22;border:1px solid {c}55">{ic}</div>'
                              '<div class="pt">{label}</div>'
                              '<div class="pv">{votes} {vs} · {pct}%</div></div>').format(
                    key=o.get("id") or o.get("key"), pct=pct, c=color, ic=o.get("icon", "⚽"),
                    label=esc(label), votes=votes, vs=d["poll_votes"])
            poll_html += '</div></div>'

    quick = ('<div class="qcard rv" onclick="location.href=\'/size-guide\'"><div class="qic">📏</div>'
             '<h3>{a}</h3><p>{b}</p><span class="qview">{c} ←</span></div>'
             '<div class="qcard rv" onclick="location.href=\'/care\'"><div class="qic">🧺</div>'
             '<h3>{d}</h3><p>{e}</p><span class="qview">{c} ←</span></div>'
             '<div class="qcard rv" onclick="location.href=\'/return-policy\'"><div class="qic">🔄</div>'
             '<h3>{f}</h3><p>{g}</p><span class="qview">{c} ←</span></div>'
             '<div class="qcard rv" onclick="openModal(\'m-request\')"><div class="qic">📝</div>'
             '<h3>{h}</h3><p>{i}</p><span class="qview">{c} ←</span></div>'
             ).format(a=d["quick_size_t"], b=d["quick_size_d"], c=d["view_details"],
                      d=d["quick_wash_t"], e=d["quick_wash_d"], f=d["quick_ret_t"], g=d["quick_ret_d"],
                      h=d["req_title"], i=d["req_sub"])

    best_sec = ('<div class="sec rv" id="best"><div class="sec-head"><h2><span class="bar"></span>{t}</h2>'
                '<span class="sec-sub">{s}</span><a class="sec-more" href="/products">{all} ←</a></div>'
                '<div class="scroll-row">{cards}</div></div>'
                ).format(t=d["best_title"], s=d["best_sub"], all=d["view_all"], cards=best_html or "") if best_html else ""
    new_sec = ('<div class="sec rv" id="new"><div class="sec-head"><h2><span class="bar"></span>{t}</h2>'
               '<span class="sec-sub">{s}</span><a class="sec-more" href="/products">{all} ←</a></div>'
               '<div class="scroll-row">{cards}</div></div>'
               ).format(t=d["new_title"], s=d["new_sub"], all=d["view_all"], cards=new_html or "") if new_html else ""

    return (atmos_html("full")
            + '<div class="wrap">'
            + hero
            + features_html()
            + '<div class="sec rv" id="jerseys"><div class="sec-head"><h2><span class="bar"></span>{sj}</h2><span class="sec-sub">{sj_sub}</span></div>'
            + shop_section_html(jgrid, "gridJ")
            + best_sec
            + new_sec
            + clubs_sec
            + loyal_sec
            + '<div class="sec rv" id="mugs"><div class="sec-head"><h2><span class="bar"></span>{sm}</h2><span class="sec-sub">{sm_sub}</span></div>'
            + '<div class="grid" id="gridM">{mgrid}</div></div>'
            + size_sec
            + steps_sec
            + pitch_sec
            + match_html
            + poll_html
            + '<div class="sec rv" id="info"><div class="sec-head"><h2><span class="bar"></span>{qt}</h2></div>'
            + '<div class="quick">{quick}</div></div>'
            + '</div>'
            ).format(sj=d["sec_jerseys"], sj_sub=d["sec_jerseys_sub"],
                     sm=d["sec_mugs"], sm_sub=d["sec_mugs_sub"], qt=d["quick_title"],
                     jgrid=jgrid, mgrid=mgrid, quick=quick)


def listing_page(kind):
    en = lang() == "en"
    d = cfg.L[lang()]
    if kind == "mug":
        title, sub = d["mugs_title"], d["mugs_sub"]
    else:
        title, sub = d["prod_title"], d["prod_sub"]
    prods = [p for p in cfg.PRODUCTS if not p.get("hidden") and p["kind"] == kind]
    grid = "".join(product_card(p) for p in prods)
    body = (atmos_html("light")
            + '<div class="wrap">'
            '<div class="page-head"><h1>{t}</h1><p>{s}</p></div>'
            + shop_section_html(grid, "gridL")
            + '<div style="text-align:center;margin-top:26px"><a class="back" href="/home">← {b}</a></div>'
            '</div>'
            ).format(t=title, s=sub, grid=grid, b=d["back"])
    return base_page(body, active=("mugs" if kind == "mug" else "products"))


def info_page(kind):
    en = lang() == "en"
    d = cfg.L[lang()]
    if kind == "size":
        title, sub = d["szp_title"], d["szp_sub"]
        inner = ("<p class='mnote'>{note}</p>".format(note=d["szt_note"]) + size_table_html(cfg.SIZE_CHART)
                 + "<h4 class='msec'>{m}</h4>".format(m=d["szt_measure"]) + "<div class='szill-wrap'>" + size_diagram() + "</div>"
                 + "<ol class='steps'><li>{a}</li><li>{b}</li></ol>".format(a=d["szt_measure_1"], b=d["szt_measure_2"])
                 + "<div class='mwarning'>💡 {t}<br>{x}</div>".format(t=d["szt_between"], x=d["szt_between_txt"]))
    elif kind == "care":
        title, sub = d["care_title"], d["care_sub"]
        steps = "".join("<li><b>{n}</b> {txt}</li>".format(n=i + 1, txt=d["wash_" + str(i + 1)]) for i in range(8))
        inner = "<ol class='steps'>" + steps + "</ol>" + "<div class='mwarning'>⚠️ {w}</div>".format(w=d["wash_warn"])
    elif kind == "ret":
        title, sub = d["ret_page_title"], d["ret_page_sub"]
        items = "".join("<li><b>{t}</b> — {x}</li>".format(t=d["ret_" + str(i) + "t"], x=d["ret_" + str(i) + "d"]) for i in range(1, 5))
        inner = "<ul class='ret'>" + items + "</ul>" + "<div class='mwarning'>⚠️ {w}</div>".format(w=d["ret_warn"])
    else:
        title, sub = d["how_page_title"], d["how_page_sub"]
        inner = ("<ol class='steps'>" + "".join("<li><b>{n}</b> {x}</li>".format(n=i + 1, x=d["how_" + str(i + 1)]) for i in range(4)) + "</ol>")
    body = ('<div class="wrap"><div class="page-head"><h1>{t}</h1><p>{s}</p></div>'
            '<div class="content-card">{inner}</div>'
            '<div style="text-align:center;margin-top:26px"><a class="back" href="/home">← {b}</a></div>'
            '</div>').format(t=title, s=sub, inner=inner, b=d["back"])
    return base_page(body, active=("sizes" if kind == "size" else ""))


def cart_page():
    d = cfg.L[lang()]
    body = ('<div class="wrap"><div class="page-head"><h1>{t}</h1><p>{s}</p></div>'
            '<div id="cartPage"></div>'
            '<div style="text-align:center;margin-top:26px"><a class="back" href="/home">← {b}</a></div>'
            '</div>').format(t=d["cart_page_title"], s=d["cart_page_sub"], b=d["back"])
    js = "<script>document.addEventListener('DOMContentLoaded',function(){ renderCartPage(); });</script>"
    return base_page(body, page_js=js, active="")


def fav_page():
    en = lang() == "en"
    d = cfg.L[lang()]
    me = current_user()
    body = ('<div class="wrap"><div class="page-head"><h1>{t}</h1><p>{s}</p></div>'
            '<div class="grid" id="favPage">').format(t=d["fav_page_title"], s=d["fav_page_sub"])
    if me:
        favs = db.user_favs(me["id"])
        cards = "".join(product_card(p) for p in cfg.PRODUCTS if p["id"] in favs and not p.get("hidden"))
        body += cards or '<p class="mnote">' + d["fav_empty"] + '</p>'
    else:
        body += '<p class="mnote">' + d["acc_guest"] + '</p>'
    body += ('</div>'
             '<div style="text-align:center;margin-top:26px"><a class="back" href="/home">← {b}</a></div>'
             '</div>').format(b=d["back"])
    if not me:
        js = "<script>document.addEventListener('DOMContentLoaded',function(){ renderFavPageGuest(); });</script>"
        return base_page(body, page_js=js)
    return base_page(body)


def club_page(cid):
    en = lang() == "en"
    d = cfg.L[lang()]
    c = cfg.CLUBS.get(cid)
    if not c:
        return base_page('<div class="wrap"><h2>404</h2></div>')
    th = club_themes().get(cid, {})
    ac = th.get("ac", "#E11D48"); ac2 = th.get("ac2", "#F97316")
    prods = [p for p in cfg.PRODUCTS if not p.get("hidden") and p.get("club_id") == cid]
    grid = "".join(product_card(p) for p in prods)
    name = c.get(en and "en" or "ar", "")
    body = (atmos_html("full")
            + '<div class="bs-wrap" aria-hidden="true"><span class="bs-ball">⚽</span></div>'
            + '<div class="wrap club-in">'
            + '<div class="club-banner" style="background:linear-gradient(135deg,{ac},{ac2})">'
            '<span class="cb-emoji">{em}</span><h1>{name}</h1>'
            '<p>{shop}</p><a class="btn lightbtn" href="/home#jerseys">← {b}</a></div>'
            + '<div class="sec"><div class="sec-head"><h2><span class="bar"></span>{pt}</h2>'
            '<span class="sec-sub">{n} {p}</span></div>'
            '<div class="grid">{grid}</div></div>'
            + '</div>').format(ac=ac, ac2=ac2, em=c.get("emoji", "⚽"), name=name,
                               shop=d["club_shop"], b=d["back"], pt=d["club_products"],
                               n=len(prods), p=d["club_items_label"], grid=grid)
    return base_page(body, extra_club=cid)


def blocked_page():
    en = lang() == "en"
    d = cfg.L[lang()]
    body = ('<div class="wrap"><div class="ok-card" style="max-width:480px;margin:0 auto;text-align:center;padding:44px 24px">'
            '<div style="font-size:56px">🚫</div><h2 style="margin-top:12px">{t}</h2>'
            '<p class="mnote" style="margin-top:12px">{m}</p>'
            '<div style="margin-top:22px"><a class="btn pri" href="/home">← {b}</a></div>'
            '</div></div>').format(t=d["admin_blocked_title"], m=d["admin_blocked_msg"], b=d["admin_blocked_back"])
    return Response(base_page(body), status=403)


def product_card(p):
    en = lang() == "en"
    d = cfg.L[lang()]
    name = p.get("name_en") if en else p.get("name_ar")
    cat = d["cat_mug"] if p["kind"] == "mug" else d["cat_jersey"]
    pr = fmt_cur(eff_price(p))
    stock = eff_stock(p)
    avail_total = sum(stock.values())
    badges_html = ""
    for b in p.get("badges", []):
        if b in ("new", "best", "offer"):
            badges_html += "<span class='badge %s'>%s</span>" % (b, d["b_" + b])
    if avail_total <= 0:
        badges_html += "<span class='badge soldout'>%s</span>" % d["b_soldout"]
    fav = gx_fav_marker(p["id"])
    low = ""
    if 0 < avail_total <= 2:
        low = "<span class='tbadge warn'>%s</span>" % d["stock_left"].format(n=avail_total)
    stock_csv = ",".join([k for k, v in stock.items() if v > 0])
    club = cfg.club_of(p)
    club_id = club and p["club_id"] or ""
    clubn = (club and club.get(en and "en" or "ar")) or ""
    th = club_themes().get(club_id, {}) if club_id else {}
    pc = th.get("ac", "#E11D48"); pc2 = th.get("ac2", "#F97316")
    first = p["imgs"][0]
    order = next((i for i, x in enumerate(cfg.PRODUCTS) if x["id"] == p["id"]), 0)
    b_csv = ",".join(p.get("badges", []))
    ncol = nearest_color(p["colors"][0])
    if p["kind"] == "mug":
        sizes_row = ""
    else:
        pills = "".join(
            ('<span class="sz-pill%s">%s</span>' % (" oos" if stock.get(sz, 0) <= 0 else "", sz))
            for sz in cfg.SIZE_ORDER[:5])
        sizes_row = '<div class="sizes-row">{pills}</div>'.format(pills=pills)
    pdots = "".join('<span class="pdot" style="background:%s"></span>' % c for c in p["colors"])
    return (
        '<div class="pcard" data-id="{id}" data-kind="{kind}" data-club="{cid}" data-clubn="{cn}" data-stock="{csv}" data-price="{price}" data-name="{name}" data-order="{order}" data-badge="{bcsv}" data-col="{ncol}" style="--pc:{pc};--pc2:{pc2}">'
        '<div class="badges">{badges}</div>'
        '<button class="heart {on}" onclick="toggleFav(\'{id}\',this)">{h}</button>'
        '<a href="/product/{id}"><div class="pimg" style="background:linear-gradient(135deg,{c1},{c2})">'
        '<img src="/img/{first}" alt="{name}" loading="lazy"></div></a>'
        '<div class="pover"><a class="pover-btn" href="/product/{id}">{view} ←</a></div>'
        '<div class="pbody"><span class="pcat">{cat}</span><h3>{name}</h3>'
        '{low}'
        '{sizes_row}'
        '<div class="pcols">{pdots}</div>'
        '<div class="pfoot"><b>{pr}</b><a class="pview" href="/product/{id}">{view} ←</a></div></div></div>'
    ).format(id=p["id"], kind=p["kind"], cid=club_id, cn=clubn.replace('"', "&quot;"), csv=stock_csv,
             price=eff_price(p), name=name.replace('"', "&quot;"), badges=badges_html, on="on" if fav else "", h="❤" if fav else "🤍",
             c1=p["colors"][0], c2=p["colors"][1], first=first, cat=cat, pr=pr, view=d["view"], low=low,
             order=order, bcsv=b_csv, ncol=ncol, sizes_row=sizes_row, pdots=pdots,
             pc=pc, pc2=pc2)


def gx_fav_marker(pid):
    u = current_user()
    if u:
        return pid in db.user_favs(u["id"])
    return False


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def product_body(pid):
    en = lang() == "en"
    d = cfg.L[lang()]
    p = next((x for x in cfg.PRODUCTS if x["id"] == pid), None)
    if not p:
        return '<div class="wrap"><h2>404</h2></div>'
    name = p.get("name_en") if en else p.get("name_ar")
    is_mug = p["kind"] == "mug"
    cat = d["cat_mug"] if is_mug else d["cat_jersey"]
    pr = fmt_cur(eff_price(p))
    club = cfg.club_of(p)
    club_id = (p.get("club_id") or "")
    stock = eff_stock(p)
    avail_total = sum(stock.values())

    arr = json_d(p["imgs"])
    gthumbs = "".join("<img src='/img/{s}' class='{c}' onclick='setGal({i},GARR)' alt=''>".format(
        s=p["imgs"][i], c="on" if i == 0 else "", i=i) for i in range(len(p["imgs"])))

    sizes = ""
    my_sz = ""
    prev_note = ""
    if not is_mug:
        u = current_user()
        if u:
            my_sz = db.user_sizes(u["id"]).get(p["id"], "")
            for o in db.orders_by_user(u["id"]):
                hit = next((it for it in o["data"].get("items", []) if it.get("id") == p["id"]), None)
                if hit:
                    prev_note = d["last_order"].format(sz=hit.get("size", "—"), q=hit.get("qty", 1))
                    if not my_sz and hit.get("size"):
                        my_sz = hit.get("size")
                    break
        chips = ""
        for sz in cfg.SIZE_ORDER:
            q = stock.get(sz, 0)
            oos = q <= 0
            on = " on" if (not oos and sz == my_sz) else ""
            chips += ("<button class='size-chip{s}{o}' data-sz='{sz}' onclick='selectSize(this)'>{sz}"
                      "{x}</button>").format(s=(" oos" if oos else ""), o=on, sz=sz,
                                             x="<span class='xs'>×</span>" if oos else "")
        sizes = ('<div class="szsec"><div class="lbl"><span>{sl}</span>'
                 '<span class="szlink" onclick="openModal(\'m-sizes\')">📏 {sg}</span></div>'
                 '<div class="sizes">{chips}</div>{note}</div>').format(
            sl=d["size_label"], sg=d["size_guide"], chips=chips,
            note=('<p class="mnote sz-note">' + (prev_note or d["saved_size"].format(sz=my_sz)) + '</p>') if (prev_note or my_sz) else "")

    trust = ""
    if avail_total <= 0:
        trust = "<span class='tbadge warn'>× " + d["b_soldout"] + "</span>"
    elif avail_total <= 2:
        trust = "<span class='tbadge warn'>" + d["stock_left"].format(n=avail_total) + "</span>"
    else:
        trust = "<span class='tbadge'>" + d["in_stock"] + "</span>"
    if p.get("badges"):
        for b in p["badges"]:
            trust += "<span class='tbadge'>" + d["b_" + b] + "</span>"
    trust = '<div class="trust">{t}</div>'.format(t=trust)

    trust_info = ('<div class="trust" style="margin-top:8px">'
                  '<span class="tbadge">{a}</span><span class="tbadge">{b}</span>'
                  '<span class="tbadge">{c}</span><span class="tbadge">{d}</span></div>'
                  ).format(a=d["trust_i1"], b=d["trust_i2"], c=d["trust_i3"], d=d["trust_i4"])

    notify = ""
    if avail_total <= 0 or (not is_mug and any(q <= 0 for q in stock.values())):
        first_oos = next((sz for sz in cfg.SIZE_ORDER if stock.get(sz, 0) <= 0), "")
        notify = ('<div class="notifybox"><p class="mnote" style="margin-bottom:10px">'
                  '<button class="nb-btn" onclick="notifyModal(\'{id}\',\'{sz}\')">{btn}</button></p></div>'
                  ).format(id=p["id"], sz=first_oos, btn=d["notify_me"])

    ratings = ""
    dim_rows = "".join(
        ('<div class="rv2-row"><span class="rv2-lbl">{lbl}</span><div class="stars-in" data-dim="{dm}">'
         '<span onclick="setDim(\'{dm}\',1)">★</span><span onclick="setDim(\'{dm}\',2)">★</span>'
         '<span onclick="setDim(\'{dm}\',3)">★</span><span onclick="setDim(\'{dm}\',4)">★</span>'
         '<span onclick="setDim(\'{dm}\',5)">★</span></div></div>').format(
            lbl=d["rv2_" + dm], dm=dm)
        for dm in ("design", "fabric", "quality", "fit"))
    fit_radios = ('<div class="radios">'
                  '<button class="radio" data-g="rvfit" data-v="small" onclick="setRevFit(\'small\')">{s}</button>'
                  '<button class="radio" data-g="rvfit" data-v="fits" onclick="setRevFit(\'fits\')">{o}</button>'
                  '<button class="radio" data-g="rvfit" data-v="wide" onclick="setRevFit(\'wide\')">{w}</button></div>'
                  ).format(s=d["rv2_fit_s"], o=d["rv2_fit_o"], w=d["rv2_fit_w"])
    ratings = ('<div class="rat-sec"><div class="sec-head"><h2><span class="bar"></span>{t}</h2>'
               '<button class="btn ghost sm" onclick="toggleRatForm()">{w}</button></div>'
               '<div class="rat-head"><div><span class="rat-avg" id="ratAvg">0.0</span> <span class="rat-stars" id="ratStars">☆☆☆☆☆</span>'
               '<div class="rat-note" id="ratNote"></div></div>'
               '<div class="rat-dims" id="ratDims"></div></div>'
               '<div id="ratList"></div>'
               '<div class="rat-form" id="ratForm" style="display:none">'
               '<div class="fld"><label>{n}</label><input id="rat_name"></div>'
               + dim_rows +
               '<div class="fld"><label>{fq}</label>' + fit_radios + '</div>'
               '<div class="fld"><label>{c}</label><textarea id="rat_txt" placeholder="{exp}"></textarea></div>'
               '<div class="fld"><label>{ph}</label><input id="rat_photo" type="file" accept="image/*"></div>'
               '<label style="display:flex;gap:8px;align-items:flex-start;font-size:.82rem;color:var(--mut);margin-bottom:12px">'
               '<input id="rat_consent" type="checkbox" style="margin-top:3px"> {consent}</label>'
               '<button class="btn pri" onclick="submitReview(\'{id}\')">{btn}</button></div>'
               '<div class="photos-sec"><div class="sec-head"><h2><span class="bar"></span>{p}</h2></div>'
               '<div id="custPhotos"></div></div></div>'
               ).format(t=d["rat_title"], w=d["rat_write"], n=d["rat_name"], fq=d["rv2_fit_q"],
                        c=d["rat_comment"], exp=d["rv2_exp"], ph=d["rat_photo"], consent=d["rv2_photo_ok"],
                        btn=d["rat_submit"], p=d["customers_photos"], id=p["id"])

    yml = ""
    others = [x for x in cfg.PRODUCTS if x["id"] != p["id"]]
    if club:
        same = [x for x in others if x.get("club_id") == p["club_id"]]
        others = same + [x for x in others if x.get("club_id") != p["club_id"]]
    yml = ('<div class="youlike"><div class="sec-head"><h2><span class="bar"></span>{t}</h2></div>'
           '<div class="grid">{cards}</div></div>').format(t=d["you_may_like"],
           cards="".join(product_card(x) for x in others[:4]))

    page_js = ('<script>var GARR=' + arr + ';' + ('selSize=' + json_d(my_sz) + ';' if my_sz else '') +
               'document.addEventListener("DOMContentLoaded",function(){ setGal(0,GARR); buildReviews("%s"); });</script>') % p["id"]

    trybtn = ""
    if not is_mug:
        trybtn = '<button class="btn ghost orderbtn" style="margin-top:10px" onclick="tryOpen(\'{id}\')">📸 {tr}</button>'.format(id=p["id"], tr=d["try_title"])

    one = len(p["imgs"]) <= 1
    gal_nav = "" if one else (
        '<span class="gcount" id="gcount">1 {of} {n}</span>'
        '<button class="gar r" id="garr" onclick="event.stopPropagation();movGal(1)">‹</button>'
        '<button class="gar l" id="garr2" onclick="event.stopPropagation();movGal(-1)">›</button>'
    ).format(of=d["img_of"], n=len(p["imgs"]))
    thumbs_block = "" if one else '<div class="gthumb" id="gthumbs">{gthumbs}</div>'

    body = (
        atmos_html("light")
        + '<div class="wrap">'
        '<input type="hidden" id="prod_id" value="{id}">'
        '<a class="back" href="/home">← {back}</a>'
        '<div class="pg">'
        '<div class="gal"><div class="gmain" onclick="openLB(document.getElementById(\'gmain\').src)">'
        '<img id="gmain" src="/img/{first}" alt="{name}">'
        '{gal_nav}</div>'
        '{thumbs_block}'
        '<p class="zoom-hint">🔍 {zh}</p></div>'
        '<div class="pinfo"><h1>{name}</h1><p class="pcatline">{cat}</p>'
        '<div class="pprice">{pr}</div>{trust}{trust_info}'
        '{sizes}'
        '<div class="qtysec"><div class="lbl">{ql}</div>'
        '<div class="qty"><button onclick="chgQ(-1)">−</button><span class="qn" id="qty">1</span><button onclick="chgQ(1)">+</button></div></div>'
        '<button class="btn pri orderbtn" onclick="var q=parseInt(document.getElementById(\'qty\').textContent,10);addCart(\'{id}\',selSize||\'\',q)">🛒 {add}</button>'
        '<button class="btn wa orderbtn" style="margin-top:10px" onclick="orderDirect(\'{id}\')">💬 {ow}</button>'
        '<button class="btn tg orderbtn" style="margin-top:10px" onclick="orderTG(\'{id}\')">✈️ {ot}</button>'
        '{trybtn}'
        '<button class="btn ghost orderbtn" style="margin-top:10px" onclick="openPriceDrop(\'{id}\')">🔔 {pd}</button>'
        '{notify}'
        '<div class="links3">'
        '<div class="link3" onclick="openModal(\'m-sizes\')"><span class="ic">📏</span>{a}</div>'
        '<div class="link3" onclick="openModal(\'m-wash\')"><span class="ic">🧺</span>{b}</div>'
        '<div class="link3" onclick="openModal(\'m-ret\')"><span class="ic">🔄</span>{c}</div></div>'
        '</div></div>'
        '{ratings}{yml}'
        '</div>'
    ).format(back=d["back"], first=p["imgs"][0], name=name, gal_nav=gal_nav, thumbs_block=thumbs_block,
             gthumbs=gthumbs, zh=d["zoom_hint"], cat=cat, pr=pr, trust=trust, trust_info=trust_info,
             sizes=sizes, ql=d["qty_label"], id=p["id"], add=d["add"], ow=d["order_wa"], ot=d["order_tg"],
             trybtn=trybtn, pd=d["pd_title"],
             notify=notify, a=d["prod_links_sz"], b=d["prod_links_wash"], c=d["prod_links_ret"],
             ratings=ratings, yml=yml)

    extra_club = club_id or None
    return body, page_js, extra_club


def order_direct_js():
    return """<script>
function orderDirect(pid){
  var p=GX.products.find(function(x){return x.id===pid;});
  var q=parseInt(document.getElementById('qty').textContent,10);
  var chip=document.querySelector('.size-chip.on'); var sz=chip?chip.getAttribute('data-sz'):null;
  if(p.kind!=='mug' && !sz){ toast(gxT('size_required')); return; }
  var cart=[{id:pid, size:sz||'OS', qty:q}];
  var tot=(p.price*q)+GX.delivery;
  var items=[{id:pid,size:sz||'OS',qty:q,name:p[GX.lang==='ar'?'name_ar':'name_en'],price:p.price,emoji:p.emoji,kind:p.kind}];
  fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    items:items,name:'',phone:'',area:'',address:'',notes:'',delivery:GX.delivery,discount:0,total:tot,reward:0,fast:1,
    device:gxDev()})})
  .then(function(r){return r.json();}).then(function(dd){
    if(dd.code){
      var msg=gxT('hello').trim()+':\\n'+items[0].emoji+' '+items[0].name;
      if(sz) msg+='\\n'+gxT('size_w')+sz;
      msg+='\\n'+gxT('qty_w')+q+' · '+pmoney(p.price*q)+' '+GX.cur+'\\n\\n'+gxT('code_w')+dd.code;
      window.open('https://wa.me/'+GX.wa+'?text='+encodeURIComponent(msg),'_blank');
      location.href='/order/success?code='+dd.code;
    }
  });
}
</script>"""


PASSPORT_DEFAULT = {0: {"d": 0, "p": 0}, 1: {"d": 2, "p": 10}, 2: {"d": 5, "p": 30}, 3: {"d": 10, "p": 100}}


def passport_rewards():
    r = db.settings_get("passport_rewards")
    if r and isinstance(r, dict):
        return r
    return PASSPORT_DEFAULT


def passport_level(n):
    return 3 if n >= 10 else (2 if n >= 5 else (1 if n >= 2 else 0))


def user_clubs(user):
    clubs = set()
    for o in db.orders_by_user(user["id"]):
        for it in o["data"].get("items", []):
            p = next((x for x in cfg.PRODUCTS if x["id"] == it.get("id")), None)
            if p and p.get("club_id"):
                clubs.add(p["club_id"])
    return sorted(clubs)


def login_page():
    d = cfg.L[lang()]
    body = ('<div class="wrap" style="max-width:500px;margin:0 auto;padding-top:46px">'
            '<div class="page-head" style="text-align:center"><h1>👤 {t}</h1><p>{g}</p></div>'
            + auth_box_html() +
            '<p style="text-align:center;margin-top:20px"><a class="back" href="/home">← {b}</a></p>'
            '</div>'
            ).format(t=d["auth_title"], g=d["acc_guest"], b=d["back"])
    return base_page(body)


def account_page():
    en = lang() == "en"
    d = cfg.L[lang()]
    u = current_user()
    if not u:
        return login_page()
    orders = db.orders_by_user(u["id"])
    spent = sum(o["data"].get("total", 0) for o in orders if o["status"] != "cancelled")
    clubs = user_clubs(u)
    lvl = passport_level(len(clubs))
    rw = passport_rewards()
    need = [1, 2, 5, 10]

    ord_html = ""
    if not orders:
        ord_html = '<p class="mnote">' + d["acc_empty_orders"] + '</p>'
    else:
        for o in orders:
            dta = o["data"]
            items = "".join(
                '<div style="font-size:.82rem;color:var(--mut)">• {e} {n} × {q}</div>'.format(
                    e=esc(it.get("emoji", "⚽")), n=esc(it.get("name", "")), q=it.get("qty", 1))
                for it in dta.get("items", [])[:4])
            ord_html += (
                '<div class="acc-card"><div class="acc-ord">'
                '<div class="ao"><b>#{c}</b><span>{dt} · {sl} · {pl}</span>{items}</div>'
                '<div class="ao" style="min-width:90px;text-align:end"><b>{t} {cu}</b></div>'
                '<div style="display:flex;gap:6px;flex-wrap:wrap">'
                '<a class="hbtn" href="/ticket?code={c}">{tk}</a>'
                '<a class="hbtn" href="/track?code={c}">{tr}</a>'
                '<button class="hbtn" onclick="openReorder(\'{c}\')">{ro}</button>'
                '</div></div></div>'
            ).format(c=o["code"], dt=dta.get("date", ""), sl=d.get("st_" + o["status"], o["status"]),
                     pl=d.get("pay_" + o["payment"], o["payment"]), items=items,
                     t=fmt_cur(dta.get("total", 0)), cu=cur(),
                     tk=d["acc_view"], tr=d["tr_title"], ro=d["acc_reorder"])

    pp_stamps = "".join('<div class="pp-stamp%s" title="%s">%s</div>' % (
        "" if cid in clubs else " lock", esc(c.get(en and "en" or "ar", "")), c.get("emoji", "⚽"))
        for cid, c in cfg.CLUBS.items())
    nxt = lvl + 1 if lvl < 3 else None
    prog_pct = int(len(clubs) / need[nxt] * 100) if nxt else 100
    pp_meta = (d["pp_next"] + ": " + str(need[nxt] - len(clubs))) if nxt else "MAX"
    pp_html = ('<div class="pp-card"><div class="pp-id">GOLAZOX • {ppid}</div>'
               '<div class="pp-level">{lvlname}</div>'
               '<div style="opacity:.85;font-size:.82rem">{n} {stamps}</div>'
               '<div class="pp-stamps">{stamps_el}</div>'
               '<div class="pp-prog"><i style="width:{pct}%"></i></div>'
               '<div style="opacity:.85;font-size:.78rem;margin-top:8px">{meta}</div></div>'
               ).format(ppid="GX-FAN-" + str(u["id"]), lvlname=d["lv_" + str(lvl)],
                        n=len(clubs), stamps=d["pp_stamps"], stamps_el=pp_stamps,
                        pct=prog_pct, meta=pp_meta)
    rw_html = '<div class="dna-grid">'
    for l in range(4):
        r = rw.get(str(l), rw.get(l, {"d": 0, "p": 0}))
        rw_html += ('<div class="dna-cell{cur}"><b>{name}</b><span>{rw}</span></div>').format(
            cur=" on" if l == lvl else "", name=d["lv_" + str(l)],
            rw=((str(r.get("d", 0)) + "% · +" + str(r.get("p", 0))) if (r.get("d") or r.get("p")) else "—"))
    rw_html += '</div>'

    data_html = ('<div class="fld"><label>{n}</label><input id="pd_name" value="{name}"></div>'
                 '<div class="frow"><div class="fld"><label>{a}</label><input id="pd_area" value="{area}"></div>'
                 '<div class="fld"><label>{ad}</label><input id="pd_addr" value="{addr}"></div></div>'
                 '<button class="btn pri big" onclick="saveAccountData()">{sv}</button>'
                 ).format(n=d["co_name"], name=esc(u.get("name", "") or ""), a=d["co_area"],
                          area=esc(u.get("area", "") or ""), ad=d["co_address"],
                          addr=esc(u.get("address", "") or ""), sv=d["ok_saved"])

    set_html = ('<p class="mnote">{sub}</p><div style="display:flex;gap:10px;flex-wrap:wrap">'
                '<button class="hbtn" onclick="openModal(\'m-settings\')">{st}</button>'
                '<button class="hbtn" onclick="saveAccountData()">{sv}</button></div>'
                ).format(sub=d["auth_sub"], st=d["set_title"], sv=d["ok_saved"])

    saved_sizes = db.user_sizes(u["id"])
    sz_prods = [p for p in cfg.PRODUCTS if p["id"] in saved_sizes and not p.get("hidden")]
    if sz_prods:
        sz_html = ""
        for p in sz_prods:
            sz_html += ('<div class="acc-szrow">'
                        '<a href="/product/{id}"><b>{e} {n}</b></a>'
                        '<span class="pill">{sw} {s}</span></div>').format(
                id=p["id"], e=p.get("emoji", "⚽"), n=esc(p.get("name_ar") if not en else p.get("name_en")),
                sw=d["size_w"], s=esc(saved_sizes[p["id"]]))
        sizes_html = '<div class="acc-szlist">' + sz_html + '</div>'
    else:
        sizes_html = '<p class="mnote">' + d["acc_sizes_empty"] + '</p>'

    tabs = [("acc-orders", d["acc_orders"]), ("acc-favs", d["acc_favs"]),
            ("acc-sizes", d["acc_sizes"]), ("acc-alerts", d["acc_alerts"]),
            ("acc-points", d["acc_points"]), ("acc-passport", d["acc_passport"]),
            ("acc-dna", d["acc_dna"]), ("acc-data", d["acc_data"]),
            ("acc-settings", d["acc_settings"])]
    nav = "".join('<button class="acc-btn%s" data-tab="%s" onclick="accTab(\'%s\')">%s</button>' % (
        " on" if i == 0 else "", sid, sid, lbl) for i, (sid, lbl) in enumerate(tabs))

    body = (
        '<div class="wrap"><div class="acc-box">'
        '<div class="acc-hero"><h2>{w} {n} 👋</h2><p>{since}: {d} · {sp}: <b>{s} {c}</b></p>'
        '<button class="hbtn" style="position:absolute;top:16px;inset-inline-end:16px;background:rgba(255,255,255,.18);border-color:rgba(255,255,255,.4)" onclick="authOut()">{out}</button></div>'
        '<div class="acc-nav">{nav}</div>'
        '<div class="acc-sec on" id="acc-orders">{orders}</div>'
        '<div class="acc-sec" id="acc-favs"><div id="favsBox"></div></div>'
        '<div class="acc-sec" id="acc-sizes">{sizes}</div>'
        '<div class="acc-sec" id="acc-alerts"><div id="alertsBox"></div></div>'
        '<div class="acc-sec" id="acc-points"><div id="pointsBox"></div></div>'
        '<div class="acc-sec" id="acc-passport">{pp}{rw}</div>'
        '<div class="acc-sec" id="acc-dna"><div id="dnaBox"></div><div id="dnaRec"></div></div>'
        '<div class="acc-sec" id="acc-data">{data}</div>'
        '<div class="acc-sec" id="acc-settings">{set}</div>'
        '</div></div>'
    ).format(w=d["acc_welcome"], n=esc(u.get("name", "") or "👤"), since=d["acc_member_since"],
             d=u.get("created", ""), sp=d["acc_spent"], s=fmt_cur(spent), c=cur(), out=d["ac_logout"],
             nav=nav, orders=ord_html, sizes=sizes_html, pp=pp_html, rw=rw_html, data=data_html, set=set_html)
    return base_page(body)


def enter_page():
    en = lang() == "en"
    d = cfg.L[lang()]
    return """<!DOCTYPE html>
<html lang="LANG" dir="DIR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>golazox</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚽</text></svg>">
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Poppins:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'FONT','Segoe UI',sans-serif;background:#05070D;color:#fff;min-height:100vh;overflow:hidden}
.st{position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:30px 20px;
  background:radial-gradient(700px 420px at 50% 12%,#14532d 0%,#07170f 45%,#05070D 75%);overflow:hidden}
.grass{position:absolute;left:0;right:0;bottom:0;height:34%;background:repeating-linear-gradient(0deg,transparent 0 44px,rgba(255,255,255,.05) 44px 88px),linear-gradient(180deg,#0a2e1a,#082517)}
.lights{position:absolute;top:-90px;left:6%;width:70px;height:210px;background:linear-gradient(180deg,rgba(255,255,255,.85),transparent);border-radius:0 0 30px 30px;filter:blur(3px);opacity:.45;animation:glow 3s infinite}
.lights.right{left:auto;right:6%;animation-delay:1.4s}
@keyframes glow{0%,100%{opacity:.25}50%{opacity:.6}}
.ball{font-size:110px;animation:pop .7s cubic-bezier(.2,.9,.3,1.2), spin 3s linear infinite}
@keyframes pop{0%{transform:scale(0) rotate(-180deg)}70%{transform:scale(1.12)}100%{transform:scale(1)}}
@keyframes spin{0%{transform:rotate(0)}100%{transform:rotate(360deg)}}
h1{font-size:2rem;font-weight:900;margin-top:22px;letter-spacing:1px}
.tag{margin-top:12px;color:#9fb3a5;font-size:.85rem;letter-spacing:3px;font-weight:800}
.btns{display:flex;gap:14px;margin-top:34px;flex-wrap:wrap;justify-content:center;position:relative;z-index:2}
.btns a{padding:15px 34px;border-radius:16px;font-weight:900;font-size:1rem;text-decoration:none;min-width:230px;opacity:0;animation:fadeup .6s ease forwards}
.btns a:first-child{background:linear-gradient(90deg,#E11D48,#F97316);color:#fff;box-shadow:0 14px 40px rgba(225,29,72,.4)}
.btns a:nth-child(2){background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.3);color:#fff;animation-delay:.18s}
@keyframes fadeup{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
.brand{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);color:#4a5d51;font-size:.8rem;font-weight:900;letter-spacing:4px;z-index:3}
@media (max-width:560px){ h1{font-size:1.5rem} .btns a{min-width:200px;padding:13px 22px} }
</style></head>
<body>
<div class="st"><div class="grass"></div><div class="lights"></div><div class="lights right"></div>
<div class="ball">⚽</div>
<h1>__WELC__</h1><p class="tag">__TAG__</p>
<div class="btns"><a href="/account">__ENT__</a><a href="/home">__SKIP__</a></div>
<div class="brand">GOLAZOX</div>
</div></body></html>""".replace("LANG", "en" if en else "ar") \
        .replace("DIR", "ltr" if en else "rtl") \
        .replace("FONT", "Poppins" if en else "Cairo") \
        .replace("__WELC__", d["ent_welc"]).replace("__TAG__", d["ent_tag"]) \
        .replace("__ENT__", d["ent_enter"]).replace("__SKIP__", d["ent_skip"])


PEN_ZONES = {"tl": (-110, 92), "tc": (0, 92), "tr": (110, 92), "bl": (-110, 172), "br": (110, 172)}


def penalty_page(code):
    en = lang() == "en"
    d = cfg.L[lang()]
    o = db.order_get(code)
    if not o:
        return base_page('<div class="wrap"><h2>404</h2></div>')
    zones = "".join(
        ("<button class='pen-zone' data-z='{z}' style='left:calc(50% {dx});top:{dy}px' onclick='penShoot(this)'>{lb}</button>"
         ).format(z=z, dx=("+ 110px" if x > 0 else ("- 110px" if x < 0 else "")), dy=y, lb=d["pen_" + z])
        for z, (x, y) in PEN_ZONES.items())
    body = (
        '<div class="wrap pen-std">'
        '<div class="pen-head"><span class="pen-code">⚽ PENALTY — {code}</span>'
        '<a class="hbtn" href="/ticket?code={code}">{tk}</a></div>'
        '<div class="pen-pitch">'
        '<div class="pen-stripes"></div><div class="pen-crowd"></div>'
        '<div class="pen-lights"></div><div class="pen-lights right"></div>'
        '<div class="pen-goal"></div>{zones}'
        '<div class="pen-keeper" id="penKeeper"><div class="kd l"></div><div class="kd r"></div><div class="kh"></div><div class="kb"></div></div>'
        '<div class="pen-ball" id="penBall">⚽</div>'
        '<div class="pen-result" id="penRes"></div>'
        '</div>'
        '<p class="pen-note">{once}</p></div>'
    ).format(code=code, tk=d["ok_ticket"], zones=zones, once=d["pen_once"])
    page_js = """<script>
var PEN_CODE={code};
var ZP={{tl:['calc(50% - 110px)','92px'],tc:['50%','92px'],tr:['calc(50% + 110px)','92px'],bl:['calc(50% - 110px)','172px'],br:['calc(50% + 110px)','172px']}};
var PEN_DONE=(localStorage.getItem('pen_'+PEN_CODE)=='1');
function penShow(goal,once){{
  var t=goal?gxT('pen_goal'):gxT('pen_saved');
  var sub=goal?('+10 '+gxT('pen_pts')):(once?gxT('pen_once'):gxT('pen_saved_t'));
  var res=$('penRes');
  res.innerHTML='<span class="big">'+t+'</span><span class="pts">'+sub+'</span>'
    +'<div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:6px">'
    +'<a class="btn" style="background:#25D366;color:#fff" href="/track?code='+PEN_CODE+'">'+gxT('pen_track')+'</a>'
    +'<a class="btn" style="background:#fff;color:#0F172A" href="/home">'+gxT('pen_back')+'</a></div>';
  res.classList.add('show');
  if(goal&&!once) confetti(50);
}}
function penShoot(btn){{
  if(PEN_DONE) return;
  var z=btn.getAttribute('data-z');
  fetch('/api/penalty/play',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{code:PEN_CODE,shot:z,device:gxDev()}})}})
  .then(function(r){{return r.json();}}).then(function(dd){{
    if(dd.error==='notfound'){{ toast('404'); return; }}
    PEN_DONE=true; localStorage.setItem('pen_'+PEN_CODE,'1');
    var ball=$('penBall'), keep=$('penKeeper');
    if(dd.fresh){{
      ball.style.left=ZP[z][0]; ball.style.top=ZP[z][1];
      if(dd.keeper&&ZP[dd.keeper]){{ keep.style.left=ZP[dd.keeper][0]; keep.style.top=ZP[dd.keeper][1]; }}
      penShow(dd.goal,false);
    }} else {{ penShow(dd.goal,true); }}
  }});
}}
document.addEventListener('DOMContentLoaded',function(){{
  if(PEN_DONE){{
    fetch('/api/penalty/status?code='+PEN_CODE).then(function(r){{return r.json();}}).then(function(dd){{
      if(dd.done) penShow(dd.goal,true);
    }});
  }}
}});
</script>""".format(code=code)
    return base_page(body, page_js=page_js)


def success_page(code):
    en = lang() == "en"
    d = cfg.L[lang()]
    o = db.order_get(code)
    if not o:
        return base_page('<div class="wrap"><h2>404</h2></div>')
    banner = ""
    u = current_user()
    if u:
        clubs = user_clubs(u)
        order_clubs = set()
        for it in o["data"].get("items", []):
            p = next((x for x in cfg.PRODUCTS if x["id"] == it.get("id")), None)
            if p and p.get("club_id"):
                order_clubs.add(p["club_id"])
        if order_clubs:
            lvl = passport_level(len(clubs))
            stamps = "".join('<div class="pp-stamp">%s</div>' % cfg.CLUBS[c]["emoji"]
                             for c in order_clubs if c in cfg.CLUBS)
            banner = ('<div class="ok-card" style="margin-top:14px;padding:22px">'
                      '<div style="font-weight:900;font-size:1.05rem">' + d["pp_title"] + '</div>'
                      '<div style="display:flex;gap:10px;justify-content:center;margin-top:12px;flex-wrap:wrap">'
                      + stamps + '</div>'
                      '<p style="opacity:.85;font-size:.85rem;margin-top:12px">' + d["pp_unlocked"] + ' · ' + d["lv_" + str(lvl)] + '</p>'
                      '<a class="btn ghost" style="margin-top:12px" href="/account">' + d["acc_passport"] + '</a>'
                      '</div>')
    body = (
        '<div class="wrap okpage">'
        '<div class="ok-card"><div class="ok-anim">🎉</div>'
        '<h1>{t}</h1><p class="mnote" style="margin-top:8px">{w}</p>'
        '<div class="ok-code">{c}</div>'
        '<div class="ok-btns">'
        '<a class="btn pri" href="/ticket?code={c}">{tk}</a>'
        '<a class="btn ghost" href="/track?code={c}">{tr}</a>'
        '<a class="btn ghost" href="/home">{b}</a></div></div>'
        + banner +
        '<div class="ok-card" style="margin-top:14px;padding:22px">'
        '<div style="font-weight:900;font-size:1.05rem">' + d["pen_title"] + '</div>'
        '<p class="mnote" style="margin-top:6px">{ps}</p>'
        '<a class="btn pri" style="margin-top:14px" href="/penalty?code={c}">' + d["pen_go"] + '</a></div>'
        '</div>'
    ).format(t=d["ok_title"], w=d["ok_wa"], c=code, tk=d["ok_ticket"], tr=d["tr_title"],
             b=d["back"], ps=d["pen_sub"])
    return base_page(body)


def my_alerts_page():
    en = lang() == "en"
    d = cfg.L[lang()]
    body = ('<div class="wrap"><div class="al-box">'
            '<h2 style="margin-bottom:14px">{t}</h2><div id="alertsBox"></div>'
            '<div style="text-align:center;margin-top:16px"><a class="back" href="/account">← {b}</a></div>'
            '</div></div>').format(t=d["acc_alerts"], b=d["back"])
    return base_page(body, page_js="<script>document.addEventListener('DOMContentLoaded',loadAlerts);</script>")


def admin_order_page(code):
    o = db.order_get(code)
    if not o:
        return admin_page("<div class='msg'>طلب غير موجود</div>")
    dta = o["data"]
    st_opts = "".join('<option value="%s"%s>%s</option>' % (v, " selected" if o["status"] == v else "", lb)
                      for v, lb in [("pending", "جديد"), ("confirmed", "مؤكد"), ("preparing", "قيد التجهيز"),
                                    ("delivering", "تم الشحن"), ("delivered", "مكتمل"), ("cancelled", "ملغي")])
    pay_opts = "".join('<option value="%s"%s>%s</option>' % (v, " selected" if o["payment"] == v else "", lb)
                       for v, lb in [("pending", "بانتظار الدفع"), ("paid", "تم الدفع"), ("not", "لم يتم الدفع")])
    item_rows = ""
    for i, it in enumerate(dta.get("items", [])):
        sz_sel = it.get("size", "OS")
        if it.get("kind") == "mug":
            size_ctl = '<input type="hidden" name="it_sz_%d" value="%s">OS' % (i, esc(sz_sel))
        else:
            sz_opts = "".join('<option value="%s"%s>%s</option>' % (s, " selected" if s == sz_sel else "", s)
                              for s in cfg.SIZE_ORDER)
            size_ctl = '<select name="it_sz_%d">%s</select>' % (i, sz_opts)
        item_rows += ('<tr><td>{e} {n}</td><td>{sz}</td>'
                      '<td><input type="number" name="it_q_{i}" value="{q}" min="0" style="width:70px"></td>'
                      '<td>{pr} {cu}</td></tr>').format(
            e=it.get("emoji", "⚽"), n=esc(it.get("name", "")), sz=size_ctl, i=i,
            q=it.get("qty", 1), pr=fmt_cur(it.get("price", 0)), cu=cur())
    body = ('<div class="adm">'
            '<div class="hd-in" style="justify-content:space-between;padding:14px 0"><b style="font-size:1.2rem">📦 #{c}</b>'
            '<a href="/admin" class="hbtn">← لوحة التحكم</a></div>'
            '<form method="post"><input type="hidden" name="act" value="order_save">'
            '<input type="hidden" name="code" value="{c}">'
            '<div class="adm-card"><h3>👤 بيانات العميل</h3><div style="display:grid;gap:8px;max-width:520px">'
            '<label>الاسم</label><input class="sel" name="name" value="{n}">'
            '<label>الهاتف</label><input class="sel" name="phone" value="{p}" dir="ltr">'
            '<label>المنطقة</label><input class="sel" name="area" value="{a}">'
            '<label>العنوان</label><input class="sel" name="address" value="{ad}">'
            '<label>ملاحظات</label><textarea class="sel" name="notes" rows="2">{no}</textarea></div></div>'
            '<div class="adm-card"><h3>📦 المنتجات (تعديل المقاس/الكمية)</h3>'
            '<table><tr><th>المنتج</th><th>المقاس</th><th>الكمية</th><th>السعر</th></tr>{items}</table>'
            '<p style="margin-top:10px;font-weight:900">الإجمالي: {tot} {cu}</p></div>'
            '<div class="adm-card"><h3>⚙️ الحالة</h3><div style="display:grid;gap:10px;max-width:420px">'
            '<label>الحالة</label><select class="sel" name="status">{st}</select>'
            '<label>الدفع</label><select class="sel" name="payment">{pay}</select>'
            '<button class="btn pri">💾 حفظ الطلب</button></div></div>'
            '</form></div>').format(c=code, n=esc(dta.get("name", "—")), p=esc(dta.get("phone", "—")),
                                    a=esc(dta.get("area", "—")), ad=esc(dta.get("address", "—")),
                                    no=esc(dta.get("notes", "")), items=item_rows, tot=fmt_cur(dta.get("total", 0)),
                                    cu=cur(), st=st_opts, pay=pay_opts)
    return admin_template(body)


def welcome_page():
    en = lang() == "en"
    d = cfg.L[lang()]
    return """<!DOCTYPE html>
<html lang="LANG" dir="DIR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>golazox</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚽</text></svg>">
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Poppins:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'FONT','Segoe UI',Tahoma,sans-serif;background:#F3F6FB;color:#0F172A;min-height:100vh}
.welc{min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:30px 20px;position:relative;overflow:hidden;
background:radial-gradient(900px 500px at 50% -20%,#FFF1E6 0%,#F3F6FB 60%)}
.welc .ball{font-size:72px}
.welc h1{font-size:2rem;font-weight:900;margin-top:16px;line-height:1.5}
.welc p{color:#5B6782;margin-top:12px;font-size:1rem;line-height:1.9}
.wlang{display:flex;gap:14px;justify-content:center;margin-top:28px;flex-wrap:wrap}
.wlang a{padding:14px 32px;border-radius:16px;font-weight:900;font-size:1rem;border:1.5px solid #E2E8F0;background:#fff;color:#0F172A}
.wlang a:hover{border-color:#E11D48;transform:translateY(-2px)}
.wlang a:first-child{background:linear-gradient(90deg,#E11D48,#F97316);border-color:transparent;color:#fff}
.brand{margin-top:24px;color:#94A3B8;font-size:.8rem;font-weight:800;letter-spacing:2px}
</style></head>
<body>
<div class="welc"><div class="welc-in">
<div class="ball">⚽</div>
<h1>__WT__</h1><p>__WS__</p>
<div class="wlang"><a href="/enter/ar">__WAR__</a><a href="/enter/en">__WEN__</a></div>
<div class="brand">GOLAZOX</div>
</div></div>
</body></html>""".replace("LANG", "en" if en else "ar") \
        .replace("DIR", "ltr" if en else "rtl") \
        .replace("FONT", "Poppins" if en else "Cairo") \
        .replace("__WT__", d["welcome_t"]).replace("__WS__", d["welcome_s"]) \
        .replace("__WAR__", d["welcome_ar"]).replace("__WEN__", d["welcome_en"])


def ticket_page(code):
    en = lang() == "en"
    d = cfg.L[lang()]
    o = db.order_get(code)
    if not o:
        return base_page('<div class="wrap"><h2>404</h2></div>')
    data = o["data"]
    items = data.get("items", [])
    status = o["status"]
    status_label = d.get("st_" + status, status)
    total = data.get("total", 0)
    def item_html(it):
        return ('<div class="tk-item"><span>{e} {n}{s}</span>'
                '<span>{q} × {pr} {c}</span></div>').format(
            e=it.get("emoji", "⚽"), n=esc(it.get("name", "")),
            s=(" · " + d["size_w"] + it["size"]) if it.get("size") and it.get("kind") != "mug" else "",
            q=it.get("qty", 1), pr=fmt_cur(it.get("price", 0)), c=cur())
    items_html = "".join(item_html(i) for i in items)
    qr = "https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=" + url_for("track", code=code, _external=True)
    cust = "".join("" for _ in [])
    wa_msg = d["tk_msg"].format(code=code)
    idx = ORDER_FLOW.index(status) if status in ORDER_FLOW else -1
    tj = ""
    if status != "cancelled":
        tj_steps = [("tstage_ok", "✓"), ("tstage_pay", "💳"), ("tstage_prep", "🧵"),
                    ("tstage_way", "🚚"), ("tstage_done", "⚽")]
        tj_inner = "".join(
            '<div class="tj-step {cls}"><div class="tj-dot">{ic}</div><b>{lbl}</b></div>'.format(
                cls="done" if i <= idx else ("cur" if i == idx else ""), ic=ic, lbl=d[k])
            for i, (k, ic) in enumerate(tj_steps))
        tj = '<div class="tj">{inner}</div>'.format(inner=tj_inner)
    body = (
        '<div class="wrap ticket">'
        '<div class="tk"><div class="tk-top"><span class="tlogo">⚽ GOLAZOX</span><span>{store}</span></div>'
        '<div class="tk-stub"><div class="tk-code">{code}</div>'
        '<div class="tk-row"><span>{date}: <b>{dt}</b></span><span>{time}: <b>{tm}</b></span></div>'
        '<div class="tk-row"><span>{cust}: <b>{cname}</b></span></div></div>'
        '<div class="tk-items">{items}</div>'
        '<div class="tk-total"><span>{total}</span><span style="color:var(--ac)">{t}</span></div>'
        '<div class="tk-status"><span>{st}:</span><span class="pill">{sl}</span></div>'
        '{journey}'
        '<div class="tk-qr"><img src="{qr}" alt="QR" width="150"></div>'
        '<div class="tk-btns">'
        '<button class="btn ghost" onclick="shareTk()">{sh}</button>'
        '<button class="btn ghost" onclick="window.print()">{sv}</button>'
        '<button class="btn ghost" onclick="location.href=\'/track?code={code}\'">{tr}</button>'
        '<a class="btn wa" target="_blank" rel="noopener" href="https://wa.me/{wa}?text={wm}">{cw}</a>'
        '</div><div class="tk-foot">© 2026 golazox</div></div>'
        '<div style="text-align:center;margin-top:18px"><a class="back" href="/home">← {b}</a></div>'
        '</div>'
    ).format(store=d["tk_store"], code=code, date=d["tk_date"], dt=data.get("date", ""),
             time=d["tk_time"], tm=data.get("time", ""), cust=d["tk_customer"], cname=esc(data.get("name", "—")),
             items=items_html, total=d["tk_total"], t=fmt_cur(total), st=d["tk_status"],
             sl=status_label, journey=tj, qr=qr, sh=d["tk_share"], sv=d["tk_save"], tr=d["tk_track"],
             wa=cfg.WHATSAPP, wm=esc(wa_msg), cw=d["tk_wa"], b=d["back"])
    page_js = """<script>
function shareTk(){ var url=location.href;
  if(navigator.share){ navigator.share({title:'golazox',url:url}); } else { navigator.clipboard.writeText(url); toast(url); } }
</script>"""
    return base_page(body, page_js=page_js)


def track_page(code=""):
    en = lang() == "en"
    d = cfg.L[lang()]
    o = db.order_get(code) if code else None
    if not o:
        body = ('<div class="wrap"><div style="max-width:520px;margin:0 auto;text-align:center;padding-top:40px">'
                '<h2>🚚 ' + d["tr_title"] + '</h2><p class="mnote" style="margin-top:14px">' + d["tr_code"] + '</p>'
                '<form method="get" action="/track" style="display:flex;gap:10px;margin-top:12px">'
                '<input class="sel" style="flex:1" name="code" placeholder="' + d["tr_code_ph"] + '">'
                '<button class="btn pri">' + d["tr_submit"] + '</button></form></div></div>')
        return base_page(body)
    data = o["data"]
    status = o["status"]
    order = ["pending", "confirmed", "preparing", "delivering", "delivered"]
    seq = {s: i for i, s in enumerate(order)}
    idx = seq.get(status, -1)
    cancelled = status == "cancelled"
    tl = ""
    if cancelled:
        tl = '<div class="tl"><div class="dot"></div><div><div class="lt">' + d["st_cancelled"] + '</div></div></div>'
    else:
        for i, st in enumerate(order):
            done = i <= idx if idx >= 0 else False
            cur = i == idx
            cls = "done" if done else ("cur" if cur else "")
            tl += ('<div class="tl {cls}"><div class="dot"></div>'
                   '<div><div class="lt">{lbl}</div></div></div>').format(cls=cls, lbl=d["st_" + st])
    pay = d.get("pay_" + o["payment"], o["payment"])
    idx2 = idx if idx >= 0 else 0
    cancelled = status == "cancelled"
    station_on = 0 if cancelled else min(4, idx2 + 1)
    pct = 0 if cancelled else {0: 0, 1: 12, 2: 40, 3: 68, 4: 100}.get(idx, 0)
    stgs = [("os_placed", "1️⃣"), ("os_prep", "🧵"), ("os_way", "🚚"), ("os_arr", "🏠")]
    os_html = ""
    for i, (k, ic) in enumerate(stgs):
        cls = "on" if i < station_on else ""
        os_html += '<div class="os-station {cls}"><span class="ic">{ic}</span><b>{lbl}</b></div>'.format(cls=cls, ic=ic, lbl=d[k])
        if i < 3:
            scls = "on" if i < station_on - 1 else ""
            os_html += '<div class="os-seg {scls}"></div>'.format(scls=scls)
    first_item = data.get("items", [{}])[0].get("id", "j1")
    os_msg = d["os_placed_s"]
    if cancelled:
        os_msg = d["st_cancelled"]
    elif idx == 1:
        os_msg = d["os_prep_s"]
    elif idx == 2:
        os_msg = d["os_way_s"]
    elif idx >= 3:
        os_msg = d["os_arr_s"]
    os_block = ('<div class="os-card"><div class="os-title">' + d["os_title"] + '</div>'
                '<div class="os-path">' + os_html + '<div class="os-ball" id="osBall" style="left:{pct}%">⚽</div></div>'
                '<div class="os-msg">{msg}</div>'
                '<div class="os-goal" id="osGoal">' + d["os_goal"] + '</div>'
                '<div class="os-rate" id="osRate"><a class="btn pri" href="/product/{pid}">' + d["os_rate"] + '</a></div>'
                '</div>').format(pct=pct, msg=os_msg, pid=first_item)
    body = (
        '<div class="wrap"><div style="max-width:520px;margin:0 auto">'
        '<div class="tk" style="margin-bottom:20px"><div class="tk-stub"><div class="tk-code">{code}</div>'
        '<div class="tk-row"><span>{date}: <b>{dt}</b></span></div>'
        '<div class="tk-row"><span>{pay}: <b>{pl}</b></span></div></div></div>'
        '{os}'
        '<div class="timeline">{tl}</div>'
        '<div style="text-align:center;margin-top:20px"><a class="back" href="/home">← {b}</a></div>'
        '</div></div>'
    ).format(code=code, date=d["tk_date"], dt=data.get("date", ""), pay=d["tr_pay"], pl=pay,
             os=os_block, tl=tl, b=d["back"])
    page_js = ""
    if status == "delivered":
        page_js = ("<script>document.addEventListener('DOMContentLoaded',function(){"
                   "var g=document.getElementById('osGoal');var r=document.getElementById('osRate');"
                   "if(g)g.style.display='block';if(r)r.style.display='block';confetti(40);});</script>")
    return base_page(body, page_js=page_js)


# ============================== ROUTES ==============================
@app.route("/")
def index():
    if not has_lang():
        return welcome_page()
    return redirect("/home")


@app.route("/home")
def home():
    if not has_lang():
        return redirect("/")
    return base_page(home_body(), active="home")


@app.route("/products")
def products_page():
    if not has_lang():
        return redirect("/")
    return listing_page("jersey")


@app.route("/mugs")
def mugs_page():
    if not has_lang():
        return redirect("/")
    return listing_page("mug")


@app.route("/size-guide")
def size_guide_page():
    if not has_lang():
        return redirect("/")
    return info_page("size")


@app.route("/care")
def care_page():
    if not has_lang():
        return redirect("/")
    return info_page("care")


@app.route("/returns")
def returns_page():
    if not has_lang():
        return redirect("/")
    return info_page("ret")


@app.route("/return-policy")
def return_policy_page():
    if not has_lang():
        return redirect("/")
    return info_page("ret")


@app.route("/how-to-order")
def how_page():
    if not has_lang():
        return redirect("/")
    return info_page("how")


@app.route("/cart")
def cart_route():
    if not has_lang():
        return redirect("/")
    return cart_page()


@app.route("/favorites")
def favorites_route():
    if not has_lang():
        return redirect("/")
    return fav_page()


@app.route("/club/<cid>")
def club_route(cid):
    if not has_lang():
        return redirect("/")
    if cid not in cfg.CLUBS:
        return redirect("/home")
    return club_page(cid)


@app.route("/product/<pid>")
def product(pid):
    if not has_lang():
        return redirect("/")
    p = next((x for x in cfg.PRODUCTS if x["id"] == pid), None)
    if not p:
        return redirect("/home")
    body, page_js, club = product_body(pid)
    return base_page(body, page_js=page_js + order_direct_js(), extra_club=club)


@app.route("/ticket")
def ticket():
    if not has_lang():
        return redirect("/")
    return ticket_page(request.args.get("code", ""))


@app.route("/track")
def track():
    if not has_lang():
        return redirect("/")
    return track_page(request.args.get("code", ""))


@app.route("/lang/<l>")
def setlang(l):
    r = redirect("/home" if request.cookies.get("lang") else "/")
    r.set_cookie("lang", l, max_age=31536000)
    return r


@app.route("/enter/<l>")
def enter(l):
    if l not in ("ar", "en"):
        return redirect("/")
    r = make_enter()
    r.set_cookie("lang", l, max_age=31536000)
    return r


def make_enter():
    return Response(enter_page(), content_type="text/html")


@app.route("/order/success")
def order_success():
    if not has_lang():
        return redirect("/")
    return success_page(request.args.get("code", ""))


@app.route("/penalty")
def penalty():
    if not has_lang():
        return redirect("/")
    return penalty_page(request.args.get("code", ""))


@app.route("/my/alerts")
def my_alerts():
    if not has_lang():
        return redirect("/")
    return my_alerts_page()


@app.route("/account")
def account():
    if not has_lang():
        return redirect("/")
    return account_page()


@app.route("/login")
def login_route():
    if not has_lang():
        return redirect("/")
    if current_user():
        return redirect("/account")
    return login_page()


@app.route("/admin/order/<code>")
def admin_order(code):
    if not admin_auth():
        if current_user():
            return blocked_page()
        return redirect("/admin/login")
    return admin_order_page(code)


@app.route("/health")
def health():
    return "ok"


# ---------- APIs ----------
@app.route("/api/order", methods=["POST"])
def api_order():
    data = request.get_json(force=True)
    now = datetime.datetime.now()
    data["date"] = now.strftime("%Y-%m-%d")
    data["time"] = now.strftime("%H:%M")
    u = current_user()
    if u:
        data["user_id"] = u["id"]
    code = db.order_create(data)
    return json_d({"code": code})


@app.route("/api/notify", methods=["POST"])
def api_notify():
    data = request.get_json(force=True)
    db.notify_add(data.get("product", ""), data.get("size", ""), data.get("phone", ""), data.get("country", "+973"))
    return json_d({"ok": True})


@app.route("/api/request", methods=["POST"])
def api_request():
    data = request.get_json(force=True)
    ref = db.request_add(data)
    return json_d({"ref": ref})


@app.route("/api/vote", methods=["POST"])
def api_vote():
    data = request.get_json(force=True)
    ok = db.vote_add(int(data.get("poll", 0)), str(data.get("option", "")), str(data.get("device", "")))
    return json_d({"ok": ok})


# ---------- SMS ----------
import time as _t
import urllib.request as _ur
import urllib.parse as _up
import base64 as _b64


def sms_log(msg):
    import sys
    try:
        sys.stderr.write("[SMS] %s\n" % msg)
        sys.stderr.flush()
    except Exception:
        pass


def send_sms(phone, text):
    provider = (os.environ.get("SMS_PROVIDER", "") or "").strip().lower()
    if provider == "taqnyat":
        return sms_taqnyat(phone, text)
    if provider == "twilio":
        return sms_twilio(phone, text)
    sms_log("SMS_PROVIDER not set or unknown (%r) - no real SMS sent" % provider)
    return (False, "notcfg")


def sms_taqnyat(phone, text):
    token = (os.environ.get("TAQNYAT_TOKEN", "") or "").strip()
    sender = (os.environ.get("TAQNYAT_SENDER", "") or "GOLAZOX").strip()
    if not token:
        sms_log("TAQNYAT_TOKEN missing")
        return (False, "config")
    try:
        payload = json.dumps({"recipients": [phone], "body": text, "sender": sender}).encode("utf-8")
        req = _ur.Request("https://api.taqnyat.sa/v1/messages", data=payload,
                          headers={"Authorization": "Bearer " + token,
                                   "Content-Type": "application/json"})
        with _ur.urlopen(req, timeout=25) as r:
            raw = r.read().decode("utf-8", "replace")
        sms_log("taqnyat ok phone=%s -> %s" % (phone, raw[:200]))
        return (True, raw)
    except Exception as e:
        sms_log("taqnyat error phone=%s: %r" % (phone, e))
        return (False, "provider")


def sms_twilio(phone, text):
    sid = (os.environ.get("TWILIO_SID", "") or "").strip()
    tok = (os.environ.get("TWILIO_AUTH_TOKEN", "") or "").strip()
    frm = (os.environ.get("TWILIO_FROM", "") or "").strip()
    if not (sid and tok and frm):
        sms_log("TWILIO_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM missing")
        return (False, "config")
    try:
        data = _up.urlencode({"To": phone, "From": frm, "Body": text}).encode("utf-8")
        url = "https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json" % sid
        auth = _b64.b64encode(("%s:%s" % (sid, tok)).encode()).decode("ascii")
        req = _ur.Request(url, data=data,
                          headers={"Authorization": "Basic " + auth,
                                   "Content-Type": "application/x-www-form-urlencoded"})
        with _ur.urlopen(req, timeout=25) as r:
            raw = r.read().decode("utf-8", "replace")
        sms_log("twilio ok phone=%s -> %s" % (phone, raw[:200]))
        return (True, raw)
    except Exception as e:
        sms_log("twilio error phone=%s: %r" % (phone, e))
        return (False, "provider")


def otp_sms_text(code):
    tpl = (os.environ.get("OTP_SMS_TEXT", "") or "").strip()
    if not tpl:
        tpl = "GOLAZOX: رمزك {code}"
    return tpl.replace("{code}", code)


def otp_email_subject():
    return "GOLAZOX - رمز التحقق / Verification code"


def otp_email_text(code):
    tpl = (os.environ.get("OTP_EMAIL_TEXT", "") or "").strip()
    if not tpl:
        tpl = ("GOLAZOX\nرمز التحقق الخاص بك: {code} (صالح لمدة 10 دقائق)\n"
               "Your verification code: {code} (valid 10 minutes)")
    return tpl.replace("{code}", code)


def send_email(to, subject, text):
    host = (os.environ.get("SMTP_HOST", "") or "").strip()
    port_s = (os.environ.get("SMTP_PORT", "") or "").strip()
    port = int(port_s) if port_s.isdigit() else 587
    user = (os.environ.get("SMTP_USER", "") or "").strip()
    pwd = os.environ.get("SMTP_PASS", "") or ""
    frm = (os.environ.get("EMAIL_FROM", "") or user).strip()
    if not (host and user):
        sms_log("SMTP not configured (SMTP_HOST/SMTP_USER missing)")
        return (False, "notcfg")
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart()
        msg["From"] = frm
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(text, "plain", "utf-8"))
        s = smtplib.SMTP(host, port, timeout=25)
        s.ehlo()
        if port in (587, 465):
            s.starttls()
        s.login(user, pwd)
        s.sendmail(frm, [to], msg.as_string())
        s.quit()
        sms_log("email ok -> %s" % to)
        return (True, "sent")
    except Exception as e:
        sms_log("email error: %r" % e)
        return (False, "provider")


def auth_contact(data):
    em = (data.get("email") or "").strip().lower()
    if em:
        parts = em.split("@")
        if len(parts) != 2 or not parts[0] or len(parts[1]) < 3 or "." not in parts[1]:
            return (None, "bad")
        return (em, "email")
    ph = fix_phone(data.get("phone", ""))
    digits = "".join(ch for ch in ph if ch.isdigit())
    if not (ph.startswith("+") and 8 <= len(digits) <= 15):
        return (None, "bad")
    return (ph, "phone")


# ---------- auth ----------
RATE_SEND_MAX = 5
RATE_SEND_WINDOW = 600
RATE_SEND_GAP = 30
RATE_VERIFY_MAX = 5
RATE_BLOCK = 600
_otp_rate = {}


def otp_rate_blocked(phone):
    r = _otp_rate.get(phone)
    if r and r.get("block_until") and _t.time() < r["block_until"]:
        return r["block_until"]
    return None


def otp_rate_allow_send(phone):
    now = _t.time()
    r = _otp_rate.setdefault(phone, {"sends": [], "fails": []})
    r["sends"] = [t for t in r["sends"] if now - t < RATE_SEND_WINDOW]
    if len(r["sends"]) >= RATE_SEND_MAX:
        return False
    if r["sends"] and now - r["sends"][-1] < RATE_SEND_GAP:
        return "gap"
    r["sends"].append(now)
    return True


def otp_rate_fail(phone):
    now = _t.time()
    r = _otp_rate.setdefault(phone, {"sends": [], "fails": []})
    r["fails"] = [t for t in r["fails"] if now - t < RATE_VERIFY_MAX * 60]
    r["fails"].append(now)
    if len(r["fails"]) >= RATE_VERIFY_MAX:
        r["block_until"] = now + RATE_BLOCK
        return True
    return False


def otp_rate_reset(phone):
    _otp_rate.pop(phone, None)


@app.route("/api/auth/otp", methods=["POST"])
def api_auth_otp():
    data = request.get_json(force=True)
    contact, mode = auth_contact(data)
    if not contact:
        return json_d({"ok": False, "error": "bad"})
    if otp_rate_blocked(contact):
        return json_d({"ok": False, "error": "rate_limit"})
    allow = otp_rate_allow_send(contact)
    if allow is False:
        return json_d({"ok": False, "error": "rate_limit"})
    if allow == "gap":
        return json_d({"ok": False, "error": "rate_gap"})
    code = db.otp_new(contact)
    registered = db.user_by_phone(contact) is not None
    demo = os.environ.get("DEMO_OTP", "0") == "1"
    if mode == "email":
        if not (os.environ.get("SMTP_HOST", "") or "").strip():
            if demo:
                return json_d({"ok": True, "demo": True, "otp": code, "registered": registered})
            sms_log("email OTP blocked: SMTP_HOST not set on the server (set DEMO_OTP=1 only for local dev)")
            return json_d({"ok": False, "error": "sms_notcfg", "registered": registered})
        ok, detail = send_email(contact, otp_email_subject(), otp_email_text(code))
        if not ok:
            return json_d({"ok": False, "error": "sms_fail", "registered": registered})
        return json_d({"ok": True, "demo": False, "registered": registered})
    provider = (os.environ.get("SMS_PROVIDER", "") or "").strip().lower()
    if not provider:
        if demo:
            return json_d({"ok": True, "demo": True, "otp": code, "registered": registered})
        sms_log("OTP blocked: SMS_PROVIDER not set on the server (set DEMO_OTP=1 only for local dev)")
        return json_d({"ok": False, "error": "sms_notcfg", "registered": registered})
    ok, detail = send_sms(contact, otp_sms_text(code))
    if not ok:
        return json_d({"ok": False, "error": "sms_fail", "registered": registered})
    return json_d({"ok": True, "demo": False, "registered": registered})


@app.route("/api/auth/verify", methods=["POST"])
def api_auth_verify():
    data = request.get_json(force=True)
    contact, mode = auth_contact(data)
    if not contact:
        return json_d({"ok": False, "reason": "code"})
    code = str(data.get("code", "")).strip()
    if otp_rate_blocked(contact):
        return json_d({"ok": False, "reason": "rate"})
    state, oid = db.otp_state(contact, code)
    if state != "ok":
        if otp_rate_fail(contact):
            return json_d({"ok": False, "reason": "rate"})
        reason = "expired" if state == "expired" else "code"
        return json_d({"ok": False, "reason": reason})
    db.otp_consume(oid)
    u = db.user_by_phone(contact)
    if not u:
        uid = db.user_create(contact, str(data.get("name", "") or "").strip(), "customer", lang())
        u = db.user_by_id(uid)
    if not u or u["status"] != "active":
        return json_d({"ok": False, "reason": "blocked"})
    pw = str(data.get("password", "") or "").strip()
    if pw:
        db.user_update(u["id"], password=pw)
    session["user_id"] = u["id"]
    session.permanent = True
    db.user_touch(u["id"])
    otp_rate_reset(contact)
    return json_d({"ok": True, "role": u["role"]})


@app.route("/api/auth/password", methods=["POST"])
def api_auth_password():
    data = request.get_json(force=True)
    contact, mode = auth_contact(data)
    pw = str(data.get("password", "") or "")
    u = db.user_by_phone(contact) if contact else None
    if not u or u.get("status") != "active" or not u.get("password") or u["password"] != pw:
        return json_d({"ok": False})
    session["user_id"] = u["id"]
    session.permanent = True
    db.user_touch(u["id"])
    return json_d({"ok": True, "role": u["role"]})


@app.route("/api/auth/logout")
def api_auth_logout():
    session.pop("user_id", None)
    return json_d({"ok": True})


@app.route("/api/me")
def api_me():
    u = current_user()
    if not u:
        return json_d({"ok": False})
    return json_d({"ok": True, "id": u["id"], "name": u["name"], "phone": u["phone"],
                   "role": u["role"], "favs": db.user_favs(u["id"])})


@app.route("/api/diag")
def api_diag():
    return json_d({
        "smtp_host": bool((os.environ.get("SMTP_HOST") or "").strip()),
        "smtp_user": bool((os.environ.get("SMTP_USER") or "").strip()),
        "smtp_pass": bool(os.environ.get("SMTP_PASS") or ""),
        "smtp_port": (os.environ.get("SMTP_PORT") or "").strip(),
        "email_from": bool((os.environ.get("EMAIL_FROM") or "").strip()),
        "sms_provider": (os.environ.get("SMS_PROVIDER") or "").strip(),
        "demo_otp": (os.environ.get("DEMO_OTP") or "").strip(),
    })


@app.route("/api/favs", methods=["POST"])
def api_favs():
    u = current_user()
    if not u:
        return json_d({"ok": False})
    data = request.get_json(force=True)
    favs = data.get("favs", [])
    valid = [f for f in favs if any(x["id"] == f for x in cfg.PRODUCTS)]
    db.user_favs_set(u["id"], valid)
    return json_d({"ok": True})


@app.route("/api/size/save", methods=["POST"])
def api_size_save():
    u = current_user()
    if not u:
        return json_d({"ok": False})
    data = request.get_json(force=True)
    pid = str(data.get("product", ""))
    sz = str(data.get("size", "") or "")
    if not any(x["id"] == pid for x in cfg.PRODUCTS):
        return json_d({"ok": False})
    db.user_size_set(u["id"], pid, sz)
    return json_d({"ok": True})


# ---------- account ----------
@app.route("/api/account/save", methods=["POST"])
def api_account_save():
    u = current_user()
    if not u:
        return json_d({"ok": False})
    data = request.get_json(force=True)
    db.user_update(u["id"],
                   name=str(data.get("name", "") or "").strip(),
                   area=str(data.get("area", "") or "").strip(),
                   address=str(data.get("address", "") or "").strip(),
                   theme=str(data.get("theme", "light")),
                   font=str(data.get("font", "b")))
    return json_d({"ok": True})


@app.route("/api/points")
def api_points():
    device = str(request.args.get("device", ""))
    return json_d({"total": db.points_get(device)})


@app.route("/api/dna")
def api_dna():
    u = current_user()
    orders = db.orders_by_user(u["id"]) if u else []
    oitems = []
    cc = {}
    for o in orders:
        for it in o["data"].get("items", []):
            p = next((x for x in cfg.PRODUCTS if x["id"] == it.get("id")), None)
            cid = p.get("club_id") if p else None
            oitems.append({"kind": p["kind"] if p else "jersey", "club": cid, "size": it.get("size") or ""})
            if cid:
                cc[cid] = cc.get(cid, 0) + 1
    lvl = passport_level(len(set(x["club"] for x in oitems if x["club"])))
    top_club = max(cc, key=cc.get) if cc else None
    rec = [p["id"] for p in cfg.PRODUCTS if p.get("club_id") == top_club]
    for p in cfg.PRODUCTS:
        if p["id"] not in rec:
            rec.append(p["id"])
    return json_d({"orders": oitems, "level": lvl, "rec": rec[:6]})


# ---------- reorder ----------
@app.route("/api/reorder")
def api_reorder_get():
    code = request.args.get("code", "")
    o = db.order_get(code)
    if not o:
        return json_d({"items": []})
    out = []
    for it in o["data"].get("items", []):
        p = next((x for x in cfg.PRODUCTS if x["id"] == it.get("id")), None)
        if not p:
            continue
        st = eff_stock(p)
        sizes = [sz for sz in cfg.SIZE_ORDER if st.get(sz, 0) > 0]
        out.append({"id": it["id"], "name": it.get("name", ""),
                    "name_ar": p.get("name_ar", ""), "name_en": p.get("name_en", ""),
                    "emoji": p.get("emoji", "⚽"),
                    "size": it.get("size", "OS"), "qty": it.get("qty", 1),
                    "sizes": sizes if p["kind"] != "mug" else []})
    return json_d({"items": out})


@app.route("/api/reorder", methods=["POST"])
def api_reorder_post():
    data = request.get_json(force=True)
    o = db.order_get(data.get("code", ""))
    if not o:
        return json_d({"ok": False})
    cart = []
    for it in o["data"].get("items", []):
        p = next((x for x in cfg.PRODUCTS if x["id"] == it.get("id")), None)
        if not p:
            continue
        st = eff_stock(p)
        sz = (data.get("sizes") or {}).get(it["id"], it.get("size", "OS"))
        if sz not in st or st[sz] <= 0:
            continue
        cart.append({"id": it["id"], "size": sz, "qty": it.get("qty", 1)})
    if not cart:
        return json_d({"ok": False})
    return json_d({"ok": True, "cart": cart})


# ---------- reviews v2 ----------
@app.route("/api/reviews/<pid>")
def api_reviews(pid):
    rows = db.reviews_list(pid, "approved")
    device = request.args.get("device", "")
    g = {"design": 0, "fabric": 0, "quality": 0, "fit": 0}
    cnt = len(rows)
    for r in rows:
        for k in g:
            v = r.get(k) or 0
            g[k] += v
    avg = round(sum(g.values()) / (cnt * 4), 2) if cnt else 0.0
    dims = {k: round(v / cnt, 1) if cnt else 0.0 for k, v in g.items()}
    list_ = []
    for r in rows:
        overall = round((r["design"] + r["fabric"] + r["quality"] + r["fit"]) / 4.0, 1)
        list_.append({"id": r["id"], "name": r["name"], "overall": overall,
                      "verified": bool(r["verified"]), "pending": r["status"] != "approved",
                      "design": r["design"], "fabric": r["fabric"], "quality": r["quality"],
                      "fit_dim": r["fit"], "text": r["text"], "photo": r["photo"],
                      "created": r["created"], "mine": r["device"] == device})
    photos = [r["photo"] for r in rows if r.get("photo")]
    my = next(({"design": r["design"], "fabric": r["fabric"], "quality": r["quality"],
                "fit": r["fit"], "text": r["text"], "status": r["status"]}
               for r in db.reviews_list(pid) if r["device"] == device), None)
    return json_d({"n": cnt, "avg": avg, "dims": dims, "list": list_, "photos": photos, "my": my})


@app.route("/api/review", methods=["POST"])
def api_review():
    data = request.get_json(force=True)
    pid = str(data.get("product", ""))
    device = str(data.get("device", ""))
    name = str(data.get("name", "—") or "—")
    try:
        design = int(data.get("design", 0)); fabric = int(data.get("fabric", 0))
        quality = int(data.get("quality", 0)); fit = int(data.get("size_rating", 0))
    except Exception:
        design = fabric = quality = fit = 0
    db.review_add(pid, device, name[:40], design, fabric, quality, fit,
                  str(data.get("fit", "") or "")[:20], str(data.get("text", "") or "")[:500],
                  data.get("photo") or None, db.review_verified(pid, device))
    return json_d({"ok": True})


@app.route("/api/review/report", methods=["POST"])
def api_review_report():
    data = request.get_json(force=True)
    db.review_report(int(data.get("id", 0)))
    return json_d({"ok": True})


# ---------- penalty ----------
@app.route("/api/penalty/play", methods=["POST"])
def api_penalty_play():
    data = request.get_json(force=True)
    shot = str(data.get("shot", ""))
    if shot not in PEN_ZONES:
        return json_d({"error": "shot"})
    r = db.penalty_play(str(data.get("code", "")), str(data.get("device", "")), shot)
    return json_d(r)


@app.route("/api/penalty/status")
def api_penalty_status():
    return json_d(db.penalty_status(str(request.args.get("code", ""))))


# ---------- price-drop alerts ----------
@app.route("/api/alerts", methods=["GET", "POST"])
def api_alerts():
    if request.method == "POST":
        data = request.get_json(force=True)
        pid = str(data.get("product", ""))
        ph = normal_phone(data.get("phone", ""))
        device = str(data.get("device", ""))
        p = next((x for x in cfg.PRODUCTS if x["id"] == pid), None)
        if not p:
            return json_d({"ok": False})
        db.alert_add(pid, ph, device, eff_price(p))
        return json_d({"ok": True})
    device = str(request.args.get("device", ""))
    return json_d({"alerts": db.alerts_for(device)})


@app.route("/api/alerts/cancel", methods=["POST"])
def api_alerts_cancel():
    data = request.get_json(force=True)
    db.alert_cancel(int(data.get("id", 0)), str(data.get("device", "")))
    return json_d({"ok": True})


# ---------- ADMIN ----------
def admin_auth():
    if session.get("admin_ok"):
        return True
    u = current_user()
    return bool(u and u.get("role") in ("admin", "super_admin"))


def admin_login_page(msg=""):
    body = (
        '<div class="wrap"><div style="max-width:400px;margin:60px auto;text-align:center">'
        '<div style="font-size:3rem">🔐</div><h2 style="margin-top:8px">لوحة تحكم golazox</h2>'
        '<p class="mnote">أدخل كلمة المرور للمتابعة</p>'
        + msg +
        '<form method="post" action="/admin/login" style="display:grid;gap:10px;margin-top:18px">'
        '<input class="sel" type="password" name="pw" placeholder="كلمة المرور" autofocus>'
        '<button class="btn pri">دخول</button></form>'
        '<p style="margin-top:16px"><a class="back" href="/home">← العودة للموقع</a></p>'
        '</div></div>')
    return base_page(body)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pw = request.form.get("pw", "")
        if pw == cfg.ADMIN_PASS:
            session["admin_ok"] = True
            return redirect("/admin")
        return admin_login_page("<div class='msg err'>كلمة المرور غير صحيحة</div>")
    if admin_auth():
        return redirect("/admin")
    return admin_login_page("")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_ok", None)
    return redirect("/")


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not admin_auth():
        if request.method == "POST":
            return json_d({"error": "unauthorized"}), 401
        if current_user():
            return blocked_page()
        return redirect("/admin/login")
    if request.method == "POST":
        act = request.form.get("act", "")
        if act == "order":
            db.order_update(request.form.get("code", ""), status=request.form.get("status", "pending"),
                            payment=request.form.get("payment", "pending"))
            return admin_page("<div class='msg'>تم الحفظ</div>")
        if act == "order_save":
            code = request.form.get("code", "")
            o = db.order_get(code)
            if o:
                dta = dict(o["data"])
                dta["name"] = request.form.get("name", dta.get("name", ""))
                dta["phone"] = request.form.get("phone", dta.get("phone", ""))
                dta["area"] = request.form.get("area", dta.get("area", ""))
                dta["address"] = request.form.get("address", dta.get("address", ""))
                dta["notes"] = request.form.get("notes", dta.get("notes", ""))
                items = []
                total = 0
                for i, it in enumerate(dta.get("items", [])):
                    sz = request.form.get("it_sz_" + str(i), it.get("size", "OS"))
                    try:
                        q = max(0, int(request.form.get("it_q_" + str(i), it.get("qty", 1))))
                    except Exception:
                        q = it.get("qty", 1)
                    if q <= 0:
                        continue
                    it = dict(it)
                    it["size"] = sz
                    it["qty"] = q
                    total += it.get("price", 0) * q
                    items.append(it)
                dta["items"] = items
                dta["total"] = total
                db.order_update(code, data=dta, status=request.form.get("status", o["status"]),
                                payment=request.form.get("payment", o["payment"]))
            return admin_page("<div class='msg'>💾 تم حفظ الطلب</div>")
        if act == "stock":
            pid = request.form.get("pid", "")
            stock = eff_stock(next((x for x in cfg.PRODUCTS if x["id"] == pid), cfg.PRODUCTS[0]))
            for sz in stock.keys():
                v = request.form.get("s_" + sz, "")
                if v != "":
                    db.set_stock(pid, sz, max(0, int(v)))
                    if int(v) > 0:
                        db.notify_mark_ready(pid, sz)
            reload_stock()
            return admin_page("<div class='msg'>تم تحديث المخزون</div>")
        if act == "req":
            db.request_status(int(request.form.get("rid", 0)), request.form.get("status", "new"))
            return admin_page("<div class='msg'>تم الحفظ</div>")
        if act == "poll_new":
            db.poll_save({
                "q_ar": request.form.get("q_ar", ""), "q_en": request.form.get("q_en", ""),
                "options": json.loads(request.form.get("opts", "[]")),
                "hide": bool(request.form.get("hide")), "winner": request.form.get("winner", ""),
                "status": request.form.get("status", "open")}, )
            return admin_page("<div class='msg'>تم إنشاء التصويت</div>")
        if act == "poll_upd":
            p = db.poll_get(int(request.form.get("pid", 0)))
            if p:
                p["data"]["status"] = request.form.get("status", "open")
                p["data"]["winner"] = request.form.get("winner", "")
                p["data"]["hide"] = bool(request.form.get("hide"))
                db.poll_update(p["id"], p["data"])
            return admin_page("<div class='msg'>تم الحفظ</div>")
        if act == "match":
            db.settings_set("match", {
                "home": request.form.get("home", ""), "away": request.form.get("away", ""),
                "kickoff": request.form.get("kickoff", "").replace("T", " "), "result": request.form.get("result", "") or None})
            return admin_page("<div class='msg'>تم الحفظ</div>")
        if act == "match_clear":
            db.settings_set("match", None)
            return admin_page("<div class='msg'>تم المسح</div>")
        if act == "drop":
            db.settings_set("drop", {
                "ar": request.form.get("drop_ar", ""), "en": request.form.get("drop_en", ""),
                "target": request.form.get("target", "").replace("T", " "),
                "img": request.form.get("img", ""),
                "product_ids": [x.strip() for x in request.form.get("pids", "").split(",") if x.strip()]})
            return admin_page("<div class='msg'>تم الحفظ</div>")
        if act == "drop_clear":
            db.settings_set("drop", None)
            return admin_page("<div class='msg'>تم المسح</div>")
        if act == "club_theme":
            for cid in cfg.CLUBS:
                if request.form.get("reset_" + cid):
                    db.club_theme_set(cid, {})
                    continue
                ac = request.form.get("ac_" + cid, "").strip()
                ac2 = request.form.get("ac2_" + cid, "").strip()
                glow = request.form.get("glow_" + cid, "").strip()
                tint = request.form.get("tint_" + cid, "").strip()
                t = {k: v for k, v in (("ac", ac), ("ac2", ac2), ("glow", glow), ("tint", tint)) if v}
                if t:
                    db.club_theme_set(cid, t)
            return admin_page("<div class='msg'>تم حفظ الثيمات</div>")
        if act == "price":
            pid = request.form.get("pid", "")
            v = request.form.get("price", "")
            p = next((x for x in cfg.PRODUCTS if x["id"] == pid), None)
            if p and v != "":
                db.set_price(pid, float(v))
            return admin_page("<div class='msg'>تم تحديث السعر</div>")
        if act == "price_reset":
            pid = request.form.get("pid", "")
            db.settings_set("price_" + pid, None)
            return admin_page("<div class='msg'>تمت إعادة السعر الافتراضي</div>")
        if act == "product_save":
            overrides = db.products_overrides()
            pid = str(request.form.get("pid", "")).strip()
            base = next((x for x in cfg.PRODUCTS if x["id"] == pid), None)
            is_new = base is None
            rec = dict(base) if base else {
                "id": pid, "kind": "jersey", "price": cfg.PRICE_JERSEY,
                "name_ar": "", "name_en": "", "desc_ar": "", "desc_en": "",
                "colors": ["#E11D48", "#F97316"], "emoji": "👕", "imgs": [pid + "_1"], "badges": [],
                "stock": {}}
            rec["id"] = pid
            kind = request.form.get("kind", "")
            if kind in ("jersey", "mug"):
                rec["kind"] = kind
            club = request.form.get("club", "")
            if club:
                rec["club_id"] = club
            else:
                rec.pop("club_id", None)
            na = request.form.get("name_ar", "").strip()
            ne = request.form.get("name_en", "").strip()
            if na:
                rec["name_ar"] = na
            if ne:
                rec["name_en"] = ne
            pr = request.form.get("price", "").strip()
            if pr != "":
                try:
                    rec["price"] = float(pr)
                except Exception:
                    pass
            em = request.form.get("emoji", "").strip()
            if em:
                rec["emoji"] = em
            cols = request.form.get("colors", "").strip()
            if cols:
                arr = [c.strip() for c in cols.split(",") if c.strip()][:2]
                rec["colors"] = [arr[0], arr[0]] if len(arr) == 1 else arr
            bad = request.form.get("badges", "").strip()
            badges = [b.strip() for b in bad.split(",") if b.strip()] if bad else []
            for key, tag in (("b_new", "new"), ("b_best", "best")):
                if request.form.get(key) and tag not in badges:
                    badges.append(tag)
                elif not request.form.get(key) and tag in badges:
                    badges.remove(tag)
            rec["badges"] = badges
            imgs = request.form.get("imgs", "").strip()
            if imgs:
                rec["imgs"] = [x.strip() for x in imgs.split(",") if x.strip()]
            stock_txt = request.form.get("stock", "").strip()
            if stock_txt:
                new_stock = {}
                for part in stock_txt.split():
                    if ":" not in part:
                        continue
                    sz, q = part.rsplit(":", 1)
                    try:
                        new_stock[sz.strip()] = max(0, int(q))
                    except Exception:
                        pass
                if new_stock:
                    rec["stock"] = new_stock
                    for sz, q in new_stock.items():
                        db.set_stock(pid, sz, q)
                        if q > 0:
                            db.notify_mark_ready(pid, sz)
            rec.pop("is_new", None)
            if is_new:
                rec["is_new"] = True
                for sz, q in rec.get("stock", {}).items():
                    db.set_stock(pid, sz, q)
            rec["hidden"] = bool(request.form.get("hidden"))
            rec.pop("remove", None)
            overrides = [o for o in overrides if o.get("id") != pid]
            overrides.append(rec)
            db.save_products_overrides(overrides)
            reload_products()
            reload_stock()
            return admin_page("<div class='msg'>✅ تم حفظ المنتج</div>")
        if act == "product_del":
            pid = str(request.form.get("pid", "")).strip()
            overrides = [o for o in db.products_overrides() if o.get("id") != pid]
            overrides.append({"id": pid, "remove": True})
            db.save_products_overrides(overrides)
            reload_products()
            return admin_page("<div class='msg'>🗑 تم حذف المنتج</div>")
        if act == "review":
            db.review_set_status(int(request.form.get("rid", 0)), request.form.get("status", "approved"))
            return admin_page("<div class='msg'>تم الحفظ</div>")
        if act == "alert_clear":
            db.settings_set("price_" + request.form.get("pid", ""), None)
            db.alert_trigger(request.form.get("pid", ""))
            return admin_page("<div class='msg'>تم إرسال التنبيهات</div>")
        if act == "alert_trigger":
            db.alert_trigger(request.form.get("pid", ""))
            return admin_page("<div class='msg'>تم إرسال التنبيهات</div>")
        if act == "cust":
            db.user_update(int(request.form.get("uid", 0)), status=request.form.get("status", "active"))
            return admin_page("<div class='msg'>تم الحفظ</div>")
        if act == "pp_rewards":
            rw = {}
            for l in range(4):
                try:
                    dsc = float(request.form.get("pp_d_" + str(l), 0) or 0)
                    pts = int(float(request.form.get("pp_p_" + str(l), 0) or 0))
                except Exception:
                    dsc = pts = 0
                rw[str(l)] = {"d": dsc, "p": pts}
            db.settings_set("passport_rewards", rw)
            return admin_page("<div class='msg'>تم حفظ مكافآت الجواز</div>")
        if act == "admins":
            ph = normal_phone(request.form.get("phone", ""))
            nm = request.form.get("name", "").strip()
            if ph and nm:
                u = db.user_by_phone(ph)
                if u:
                    db.user_update(u["id"], role="admin", name=nm, status="active")
                else:
                    db.user_create(ph, nm, "admin")
            return admin_page("<div class='msg'>تمت إضافة المدير</div>")
        if act == "admins_toggle":
            db.user_update(int(request.form.get("uid", 0)), role=request.form.get("role", "customer"))
            return admin_page("<div class='msg'>تم الحفظ</div>")
    return admin_page("")


def reload_stock():
    global STOCK
    STOCK = db.get_stock()


def admin_page(msg=""):
    dl = cfg.L.get("ar", cfg.L.get("en", {}))
    orders = db.orders_list()
    stock = STOCK
    requests = db.requests_list()
    polls = db.polls_list()
    notifs = db.notify_list()
    ready = db.notify_list(ready_only=True)
    m = db.settings_get("match")
    dr = db.settings_get("drop")
    club_opts = "".join('<option value="%s">%s</option>' % (k, v["ar"]) for k, v in cfg.CLUBS.items())
    sel = lambda cur, opts: "".join('<option value="%s"%s>%s</option>' % (v, " selected" if v == cur else "", lb) for v, lb in opts)
    st_opts = [("pending", "جديد"), ("confirmed", "مؤكد"), ("preparing", "قيد التجهيز"),
               ("delivering", "خرج للتوصيل"), ("delivered", "تم التسليم"), ("cancelled", "ملغي")]
    pay_opts = [("pending", "بانتظار الدفع"), ("paid", "تم الدفع"), ("not", "لم يتم الدفع")]

    rows = ""
    for o in orders[:30]:
        d = o["data"]
        items = ", ".join(i.get("name", "") for i in d.get("items", [])[:2])
        rows += ("<tr><td><b>{c}</b></td><td>{n}</td><td>{i}</td><td>{t} {cu}</td>"
                 "<td>{s}</td><td>{p}</td><td><a href='/admin/order/{c}'>فتح</a></td></tr>").format(
            c=o["code"], n=esc(d.get("name", "—")), i=esc(items),
            t=fmt_cur(d.get("total", 0)), cu=cur(),
            s=o["status"], p=o["payment"])

    stock_rows = ""
    for p in cfg.PRODUCTS:
        st = stock.get(p["id"], p.get("stock", {}))
        ins = ""
        for sz, q in st.items():
            ins += '<span style="white-space:nowrap">%s <input class="mini" name="s_%s" type="number" value="%d"></span> ' % (sz, sz, q)
        stock_rows += ("<form method='post' style='display:contents'><input type='hidden' name='act' value='stock'>"
                       "<tr><td><input type='hidden' name='pid' value='{id}'>{id} {name}</td><td>{ins}</td>"
                       "<td><button class='hbtn'>حفظ</button></td></tr></form>").format(
            id=p["id"], name=p.get("name_ar", ""), ins=ins)

    req_rows = ""
    for r in requests[:30]:
        d = r["data"]
        req_rows += ("<form method='post' style='display:contents'><input type='hidden' name='act' value='req'>"
                     "<input type='hidden' name='rid' value='{rid}'>"
                     "<tr><td>#{rid}</td><td>{club}</td><td>{type} {ver}</td><td>{size} × {qty}</td>"
                     "<td>{notes}</td><td><select name='status'>{opts}</select>"
                     "<button class='hbtn'>حفظ</button></td></tr></form>").format(
            rid=r["id"], club=esc(d.get("club", "")), type=esc(d.get("type", "")),
            ver=esc(d.get("version", "")), size=esc(d.get("size", "")), qty=esc(d.get("qty", "")),
            notes=esc(d.get("notes", "")),
            opts="".join('<option value="%s"%s>%s</option>' % (s, " selected" if s == r["status"] else "", lbl)
                         for s, lbl in [("new", "جديد"), ("reviewed", "تمت المراجعة"), ("available", "متوفر"),
                                        ("unavailable", "غير متوفر"), ("contacted", "تم التواصل")]))

    notif_rows = ""
    for n in notifs[:30]:
        wa = "https://wa.me/" + n["phone"].replace("+", "")
        notif_rows += ("<tr><td>{p} {sz}</td><td>{ph}</td><td>{c}</td>"
                       "<td>{st}</td><td><a href='{wa}' target='_blank'>واتساب</a></td></tr>").format(
            p=n["product"], sz=n["size"], ph=n["phone"], c=n["created"],
            st="جاهز" if n["notified"] else "بانتظار", wa=wa)

    poll_rows = ""
    for pl in polls:
        q = pl["data"].get("q_ar", "")
        poll_rows += ("<form method='post' style='display:contents'><input type='hidden' name='act' value='poll_upd'>"
                      "<input type='hidden' name='pid' value='{pid}'>"
                      "<tr><td>#{pid} {q}</td><td>{opts}</td><td>{hide}</td><td>{win}</td><td><button class='hbtn'>حفظ</button></td></tr></form>").format(
            pid=pl["id"], q=esc(q),
            opts="".join('<option value="%s"%s>%s</option>' % (s, " selected" if s == pl["data"].get("status", "open") else "", lbl)
                         for s, lbl in [("open", "مفتوح"), ("closed", "مغلق")]),
            hide="<input type='checkbox' name='hide' " + ("checked" if pl["data"].get("hide") else "") + ">",
            win="<input name='winner' value='" + esc(pl["data"].get("winner", "")) + "' placeholder='الخيار الفائز'>")

    n_orders = len([o for o in orders if o["status"] == "pending"])
    rev = sum(o["data"].get("total", 0) for o in orders if o["status"] not in ("cancelled",))
    n_ready = len(ready)

    today = datetime.date.today().strftime("%Y-%m-%d")
    ym = today[:7]
    rev_today = sum(o["data"].get("total", 0) for o in orders
                    if o["status"] != "cancelled" and o["data"].get("date") == today)
    rev_month = sum(o["data"].get("total", 0) for o in orders
                    if o["status"] != "cancelled" and str(o["data"].get("date", "")).startswith(ym))
    cnt = {}
    cntq = {}
    for o in orders:
        for it in o["data"].get("items", []):
            pid = it.get("id", "")
            if not pid:
                continue
            cnt[pid] = cnt.get(pid, 0) + 1
            cntq[pid] = cntq.get(pid, 0) + it.get("qty", 1)
    ranked = sorted(cntq.items(), key=lambda kv: -kv[1])
    top = "—"
    if ranked:
        tp = next((x for x in cfg.PRODUCTS if x["id"] == ranked[0][0]), None)
        top = (tp.get("name_ar", "") if tp else ranked[0][0]) or ranked[0][0]
    top_rows = ""
    for pid, q in ranked[:10]:
        tp = next((x for x in cfg.PRODUCTS if x["id"] == pid), None)
        if not tp:
            continue
        top_rows += ("<tr><td>{rank}</td><td>{e} {n}</td>"
                     "<td>{t} {cu}</td><td>{q} قطع</td></tr>").format(
            rank=ranked.index((pid, q)) + 1, e=tp.get("emoji", "⚽"), n=esc(tp.get("name_ar", pid)),
            t=fmt_cur(eff_price(tp)), cu=cur(), q=q)
    top_card = ('<div class="adm-card"><h3>🏆 المنتجات الأكثر طلبًا</h3>'
                '<table><tr><th>#</th><th>المنتج</th><th>السعر</th><th>الكمية المطلوبة</th></tr>{top_rows}</table></div>').format(top_rows=top_rows) if top_rows else ""
    n_cust = len(db.users_list())

    price_rows = ""
    for p in cfg.PRODUCTS:
        curp = eff_price(p)
        price_rows += ("<tr><td>{id} {name}</td><td>{cp} {cu}</td><td>"
                       "<form method='post' style='display:inline'><input type='hidden' name='act' value='price'>"
                       "<input type='hidden' name='pid' value='{id}'><input class='mini' name='price' value='{cp}'>"
                       "<button class='hbtn'>حفظ</button></form> "
                       "<form method='post' style='display:inline'><input type='hidden' name='act' value='price_reset'>"
                       "<input type='hidden' name='pid' value='{id}'><button class='hbtn'>افتراضي</button></form></td></tr>"
                       ).format(id=p["id"], name=p.get("name_ar", ""), cp=fmt_cur(curp), cu=cur())

    prod_add_form = ('<div class="adm-card"><h3>➕ إضافة منتج</h3>'
                     '<form method="post" style="display:grid;gap:8px;max-width:620px">'
                     '<input type="hidden" name="act" value="product_save">'
                     '<div style="display:flex;gap:8px;flex-wrap:wrap"><input name="pid" placeholder="المعرّف (مثال: j7)" required>'
                     '<select name="kind"><option value="jersey">تيشيرت</option><option value="mug">مق</option></select>'
                     '<select name="club"><option value="">بدون نادي</option>' + club_opts + '</select></div>'
                     '<div style="display:flex;gap:8px;flex-wrap:wrap"><input name="name_ar" placeholder="الاسم (عربي)" required>'
                     '<input name="name_en" placeholder="الاسم (إنجليزي)"></div>'
                     '<div style="display:flex;gap:8px;flex-wrap:wrap"><input class="mini" name="price" type="number" step="0.5" value="7">'
                     '<input class="mini" name="emoji" value="👕"><input class="mini" name="colors" value="#E11D48,#F97316">'
                     '<input class="mini" name="badges" placeholder="badges إضافية (offer)"></div>'
                     '<div style="display:flex;gap:14px;align-items:center">'
                     '<label style="font-size:.82rem">⭐ جديد<input type="checkbox" name="b_new" value="1"></label>'
                     '<label style="font-size:.82rem">🔥 الأكثر مبيعًا<input type="checkbox" name="b_best" value="1"></label></div>'
                     '<input name="imgs" placeholder="الصور مفصولة بفاصلة (مثال: j7_1,j7_2)">'
                     '<input name="stock" placeholder="المخزون: S:3,M:5,L:8,XL:4,2XL:2,3XL:0">'
                     '<button class="hbtn">💾 حفظ المنتج</button></form></div>')

    prod_rows = ""
    for p in cfg.PRODUCTS:
        st = eff_stock(p)
        st_txt = " ".join("%s:%d" % (k, v) for k, v in st.items())
        bad = ",".join(p.get("badges", []))
        prod_rows += ('<tr><td><b>{id}</b> {name}<br><small style="color:#64748b">{kind} · {price} {cu}{hid}</small></td>'
                      '<td><form method="post" style="display:grid;gap:6px;max-width:540px">'
                      '<input type="hidden" name="act" value="product_save"><input type="hidden" name="pid" value="{id}">'
                      '<div style="display:flex;gap:6px;flex-wrap:wrap"><input name="name_ar" value="{na}" placeholder="عربي">'
                      '<input name="name_en" value="{ne}" placeholder="EN"></div>'
                      '<div style="display:flex;gap:6px;flex-wrap:wrap"><input class="mini" name="price" value="{pr}">'
                      '<input class="mini" name="emoji" value="{em}">'
                      '<input class="mini" name="badges" value="{bad}" placeholder="badges">'
                      '<input class="mini" name="stock" value="{st_txt}" placeholder="مخزون"></div>'
                      '<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">'
                      '<label style="font-size:.78rem">⭐ جديد<input type="checkbox" name="b_new" value="1"{bnew}></label>'
                      '<label style="font-size:.78rem">🔥 الأكثر مبيعًا<input type="checkbox" name="b_best" value="1"{bbest}></label>'
                      '<label style="font-size:.78rem">إخفاء<input type="checkbox" name="hidden"{hc}></label>'
                      '<button class="hbtn">حفظ</button></form></div></td>'
                      '<td><form method="post" onsubmit="return confirm(\'هل تريد حذف المنتج؟\')">'
                      '<input type="hidden" name="act" value="product_del"><input type="hidden" name="pid" value="{id}">'
                      '<button class="hbtn" style="background:#dc2626">حذف</button></form></td></tr>'
                      ).format(id=p["id"], name=p.get("name_ar", ""), kind=d.get("type_jersey") if p["kind"] == "jersey" else d.get("type_mug", ""),
                               price=fmt_cur(eff_price(p)), cu=cur(), hid=" · مخفي" if p.get("hidden") else "",
                               na=p.get("name_ar", ""), ne=p.get("name_en", ""), pr=eff_price(p),
                               em=p.get("emoji", "👕"), bad=bad, st_txt=st_txt, hc=" checked" if p.get("hidden") else "",
                               bnew=" checked" if "new" in p.get("badges", []) else "",
                               bbest=" checked" if "best" in p.get("badges", []) else "")
    prod_card = prod_add_form + '<div class="adm-card"><h3>📋 المنتجات (إضافة / تعديل / حذف)</h3><table>' + prod_rows + '</table></div>'

    rev_rows = ""
    for r in db.reviews_list()[:30]:
        rev_rows += ("<form method='post' style='display:contents'><input type='hidden' name='act' value='review'>"
                     "<input type='hidden' name='rid' value='{rid}'>"
                     "<tr><td>{pid}</td><td>{name}</td><td>{dims}</td><td>{txt}</td>"
                     "<td>{ver}</td><td><select name='status'>{opts}</select>"
                     "<button class='hbtn'>حفظ</button></td></tr></form>").format(
            rid=r["id"], pid=r["product"], name=esc(r["name"] or "—"),
            dims="%s★ %s★ %s★ %s★" % (r["design"], r["fabric"], r["quality"], r["fit"]),
            txt=esc(r["text"] or "")[:80], ver="✓" if r["verified"] else "—",
            opts="".join('<option value="%s"%s>%s</option>' % (s, " selected" if s == r["status"] else "", lb)
                         for s, lb in [("pending", "بانتظار"), ("approved", "مقبول"), ("rejected", "مرفوض")]))

    al_rows = ""
    for a in db.alerts_list()[:30]:
        al_rows += ("<tr><td>{p}</td><td>{ph}</td><td>{pr} {cu}</td><td>{st}</td></tr>").format(
            p=a["product"], ph=a["phone"], pr=fmt_cur(a["price"]), cu=cur(),
            st="أُرسل ✓" if a["triggered"] else ("ملغي" if not a["active"] else "بانتظار"))

    cust_rows = ""
    for u in db.users_list():
        uo = db.orders_by_user(u["id"])
        us = sum(x["data"].get("total", 0) for x in uo if x["status"] != "cancelled")
        cust_rows += ("<form method='post' style='display:contents'><input type='hidden' name='act' value='cust'>"
                      "<input type='hidden' name='uid' value='{uid}'>"
                      "<tr><td>{name}</td><td>{phone}</td><td>{role}</td><td>{ord} طلبات · {sp} {cu}</td>"
                      "<td><select name='status'>{opts}</select>"
                      "<button class='hbtn'>حفظ</button></td></tr></form>").format(
            uid=u["id"], name=esc(u["name"] or "—"), phone=esc(u["phone"]), role=u["role"],
            ord=len(uo), sp=fmt_cur(us), cu=cur(),
            opts="".join('<option value="%s"%s>%s</option>' % (s, " selected" if s == u["status"] else "", lb)
                         for s, lb in [("active", "نشط"), ("disabled", "موقوف")]))

    super_role = admin_role() == "super_admin"
    adm_rows = ""
    for u in db.users_list():
        if u["role"] not in ("admin", "super_admin"):
            continue
        togg = ""
        if super_role and u["role"] == "admin":
            togg = ("<form method='post' style='display:inline'><input type='hidden' name='act' value='admins_toggle'>"
                    "<input type='hidden' name='uid' value='{uid}'><input type='hidden' name='role' value='customer'>"
                    "<button class='hbtn'>إلغاء الصلاحية</button></form>").format(uid=u["id"])
        adm_rows += "<tr><td>{name}</td><td>{phone}</td><td>{role}</td><td>{t}</td></tr>".format(
            name=esc(u["name"] or "—"), phone=esc(u["phone"]), role=u["role"], t=togg)

    pp_rw = passport_rewards()
    pp_form = ""
    for l in range(4):
        r = pp_rw.get(str(l), pp_rw.get(l, {"d": 0, "p": 0}))
        pp_form += ("<div style='display:flex;gap:8px;align-items:center'><b style='width:110px'>{name}</b>"
                    "<input class='mini' name='pp_d_{l}' type='number' step='0.5' value='{d}' placeholder='خصم %'>"
                    "<input class='mini' name='pp_p_{l}' type='number' value='{p}' placeholder='نقاط'></div>"
                    ).format(name=dl["lv_" + str(l)], l=l, d=r.get("d", 0), p=r.get("p", 0))
    pp_card = ('<div class="adm-card"><h3>🎫 مكافآت جواز كرة القدم</h3>'
               '<form method="post" style="display:grid;gap:8px;max-width:560px"><input type="hidden" name="act" value="pp_rewards">'
               + pp_form + '<button class="hbtn">حفظ المكافآت</button></form></div>')

    theme_rows = ""
    for cid, c in cfg.CLUBS.items():
        t = club_themes().get(cid, {})
        theme_rows += ('<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px">'
                       '<b style="min-width:150px">%s %s</b>'
                       '<label>أساسي<input class="mini" type="color" name="ac_%s" value="%s"></label>'
                       '<label>ثانوي<input class="mini" type="color" name="ac2_%s" value="%s"></label>'
                       '<label>توهج<input class="mini" type="color" name="glow_%s" value="%s"></label>'
                       '<label>لون الصفحة<input class="mini" type="color" name="tint_%s" value="%s"></label>'
                       '<label style="font-size:.78rem;color:#64748b">استعادة الافتراضي<input type="checkbox" name="reset_%s"></label>'
                       '</div>') % (c.get("emoji", ""), c.get("ar", cid),
                                    cid, t.get("ac", "#E11D48"),
                                    cid, t.get("ac2", "#F97316"),
                                    cid, t.get("glow", "#E11D48"),
                                    cid, t.get("tint", "#E11D48"),
                                    cid)
    theme_card = ('<div class="adm-card"><h3>🎨 ثيمات الأندية (الثيم الديناميكي)</h3>'
                  '<form method="post" style="max-width:820px"><input type="hidden" name="act" value="club_theme">'
                  + theme_rows +
                  '<button class="hbtn">حفظ الثيمات</button>'
                  '<p style="font-size:.78rem;color:#64748b;margin-top:6px">كل نادي يغيّر ألوان الموقع بالكامل عند دخول صفحة المنتج أو عند اختياره من إعدادات المستخدم.</p>'
                  '</form></div>')
    adm_card = ""
    if super_role:
        adm_card = ('<div class="adm-card"><h3>👥 إدارة المديرين</h3>'
                    '<form method="post" style="display:grid;gap:8px;max-width:420px;margin-bottom:12px">'
                    '<input type="hidden" name="act" value="admins">'
                    '<input name="name" placeholder="اسم المدير">'
                    '<input name="phone" placeholder="رقم الهاتف (بينات أو دولي)">'
                    '<button class="hbtn">إضافة مدير</button></form>'
                    '<table><tr><th>الاسم</th><th>الهاتف</th><th>الدور</th><th></th></tr>{adm_rows}</table></div>').format(adm_rows=adm_rows)

    body = ('<div class="adm">'
            '<div class="hd-in" style="justify-content:space-between;padding:14px 0"><b style="font-size:1.2rem">⚙️ لوحة تحكم golazox</b>'
            '<span><a href="/home" class="hbtn">الموقع</a> <a href="/admin/logout" class="hbtn">خروج</a></span></div>'
            + msg +
            '<div class="stat-cards">'
            '<div class="stat"><b>{n1}</b><span>طلبات جديدة</span></div>'
            '<div class="stat"><b>{n2}</b><span>إجمالي الطلبات</span></div>'
            '<div class="stat"><b>{rev}</b><span>الإيراد الكلي ({cu})</span></div>'
            '<div class="stat"><b>{rt}</b><span>إيراد اليوم</span></div>'
            '<div class="stat"><b>{rm}</b><span>إيراد الشهر</span></div>'
            '<div class="stat"><b>{top}</b><span>الأكثر مبيعًا</span></div>'
            '<div class="stat"><b>{nc}</b><span>العملاء</span></div>'
            '<div class="stat"><b>{n3}</b><span>تنبيهات جاهزة</span></div></div>'
            '<div class="adm-card"><h3>📦 الطلبات</h3><table><tr><th>الرقم</th><th>العميل</th><th>المنتجات</th><th>الإجمالي</th><th>الحالة</th><th>الدفع</th><th></th></tr>{rows}</table></div>'
            + top_card +
            '<div class="adm-card"><h3>💰 الأسعار</h3><table><tr><th>المنتج</th><th>السعر الحالي</th><th>تعديل</th></tr>{price_rows}</table></div>'
            '<div class="adm-card"><h3>📦 المخزون</h3><table><tr><th>المنتج</th><th>المقاسات (الكمية)</th><th></th></tr>{stock_rows}</table></div>'
            + prod_card +
            '<div class="adm-card"><h3>⭐ مراجعات العملاء</h3><table><tr><th>المنتج</th><th>الاسم</th><th>التقييم</th><th>النص</th><th>موثق</th><th>الحالة</th></tr>{rev_rows}</table></div>'
            '<div class="adm-card"><h3>🔔 تنبيهات انخفاض السعر</h3><table><tr><th>المنتج</th><th>الهاتف</th><th>السعر المحفوظ</th><th>الحالة</th></tr>{al_rows}</table>'
            '<h4 style="margin-top:12px">إرسال التنبيهات الآن</h4>'
            '<form method="post" style="display:flex;gap:8px;max-width:420px"><input type="hidden" name="act" value="alert_trigger">'
            '<select name="pid">' + "".join('<option value="%s">%s</option>' % (p["id"], p.get("name_ar", "")) for p in cfg.PRODUCTS) + '</select>'
            '<button class="hbtn">إرسال</button></form></div>'
            '<div class="adm-card"><h3>👥 العملاء</h3><table><tr><th>الاسم</th><th>الهاتف</th><th>الدور</th><th>النشاط</th><th>الحالة</th></tr>{cust_rows}</table></div>'
            + adm_card + pp_card + theme_card +
            '<div class="adm-card"><h3>📝 طلبات المنتجات الخاصة</h3><table><tr><th>#</th><th>النادي</th><th>النوع</th><th>مقاس × كمية</th><th>ملاحظات</th><th>الحالة</th></tr>{req_rows}</table></div>'
            '<div class="adm-card"><h3>🔔 طلبات الإشعار عند التوفر</h3><table><tr><th>المنتج</th><th>الهاتف</th><th>التاريخ</th><th>الحالة</th><th></th></tr>{notif_rows}</table></div>'
            '<div class="adm-card"><h3>🗳️ التصويتات</h3><table><tr><th>السؤال</th><th>الحالة</th><th>إخفاء النتائج</th><th>الفائز</th><th></th></tr>{poll_rows}</table>'
            '<h4 style="margin-top:12px">تصويت جديد</h4>'
            '<form method="post" style="display:grid;gap:8px;max-width:560px">'
            '<input type="hidden" name="act" value="poll_new">'
            '<input name="q_ar" placeholder="السؤال (عربي)">'
            '<input name="q_en" placeholder="Question (EN)">'
            '<input name="opts" placeholder="الخيارات JSON، مثال: [{{\"id\":\"real\",\"label_ar\":\"ريال\",\"label_en\":\"Real\",\"color\":\"#C9A24B\",\"icon\":\"🤍\"}}]">'
            '<div style="display:flex;gap:10px"><input name="start" type="datetime-local" placeholder="بداية"><input name="end" type="datetime-local" placeholder="نهاية"></div>'
            '<label><input type="checkbox" name="hide"> إخفاء النتائج</label>'
            '<button class="hbtn">إنشاء التصويت</button></form></div>'
            '<div class="adm-card"><h3>⚡ MATCHDAY</h3>'
            '<form method="post" style="display:grid;gap:8px;max-width:560px"><input type="hidden" name="act" value="match">'
            '<div style="display:flex;gap:10px">' + club_opts + club_opts.replace("name=\"home\"", "name=\"away\"") + '</div>'
            '<input name="kickoff" type="datetime-local" value="{mk}">'
            '<input name="result" placeholder="النتيجة (اختياري)، مثال: 2-1" value="{mr}">'
            '<div style="display:flex;gap:10px"><button class="hbtn">حفظ</button>'
            '<button class="hbtn" formaction="/admin" name="act" value="match_clear">مسح</button></div></form></div>'
            '<div class="adm-card"><h3>🔥 NEW DROP</h3>'
            '<form method="post" style="display:grid;gap:8px;max-width:560px"><input type="hidden" name="act" value="drop">'
            '<div style="display:flex;gap:10px"><input name="drop_ar" placeholder="اسم الإصدار (عربي)" value="{dar}"><input name="drop_en" placeholder="Drop name (EN)" value="{den}"></div>'
            '<input name="target" type="datetime-local" value="{dtg}">'
            '<input name="img" placeholder="صورة (مثال: j1_1)" value="{dimg}">'
            '<input name="pids" placeholder="منتجات الإصدار (مفصولة بفواصل) مثال: j1,j2" value="{dids}">'
            '<div style="display:flex;gap:10px"><button class="hbtn">حفظ</button>'
            '<button class="hbtn" formaction="/admin" name="act" value="drop_clear">مسح</button></div></form></div>'
            '</div>').format(
        n1=n_orders, n2=len(orders), rev=fmt_cur(rev), cu=cur(), n3=n_ready,
        rt=fmt_cur(rev_today), rm=fmt_cur(rev_month), top=esc(top), nc=n_cust,
        rows=rows, price_rows=price_rows, stock_rows=stock_rows, rev_rows=rev_rows, al_rows=al_rows,
        cust_rows=cust_rows, req_rows=req_rows, notif_rows=notif_rows, poll_rows=poll_rows,
        mk=(m["kickoff"].replace(" ", "T") if m and m.get("kickoff") else ""),
        mr=(m["result"] if m and m.get("result") else ""),
        dar=(dr["ar"] if dr else ""), den=(dr["en"] if dr else ""),
        dtg=(dr["target"].replace(" ", "T") if dr else ""), dimg=(dr["img"] if dr else ""),
        dids=",".join(dr["product_ids"]) if dr else "")
    return admin_template(body)


def admin_template(body):
    return """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>golazox Admin</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Cairo','Segoe UI',sans-serif;background:#F3F6FB;color:#0F172A;font-size:15px}
a{text-decoration:none;color:inherit}
.hd-in{max-width:1120px;margin:0 auto;display:flex;align-items:center;gap:12px}
.hbtn{background:#fff;border:1px solid #E2E8F0;border-radius:999px;padding:8px 16px;font-weight:700;cursor:pointer;font-family:inherit;color:#0F172A}
.adm{max-width:1120px;margin:0 auto;padding:20px 18px 60px}
.adm-card{background:#fff;border:1px solid #E2E8F0;border-radius:16px;padding:18px;margin-bottom:16px;overflow-x:auto}
.adm-card h3{font-size:1.05rem;font-weight:900;margin-bottom:12px}
.adm table{width:100%;border-collapse:collapse;font-size:.88rem}
.adm th{text-align:start;padding:8px;color:#64748B;border-bottom:1px solid #E2E8F0}
.adm td{padding:8px;border-bottom:1px dashed #E2E8F0;vertical-align:top}
.adm input,.adm select{background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;padding:8px 10px;font-size:.88rem;font-family:inherit;color:#0F172A;max-width:100%}
.adm .mini{width:64px}
.stat-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:18px}
.stat{background:#fff;border:1px solid #E2E8F0;border-radius:16px;padding:16px}
.stat b{font-size:1.5rem;display:block;color:#E11D48}
.stat span{color:#64748B;font-size:.8rem}
.msg{background:#ECFDF5;border:1px solid #A7F3D0;color:#065F46;border-radius:12px;padding:10px 14px;margin-bottom:14px}
</style></head>
<body><div class="wrap2">BODY</div></body></html>""".replace("BODY", body)


if __name__ == "__main__":
    seed_super_admin()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
