# -*- coding: utf-8 -*-
"""
golazox — Premium Football Club Store (Flask)
Dark Night-Stadium theme by default (optional light mode), font sizes, full cart+checkout via WhatsApp, order ticket &
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


# ============================== LOGIN WALL ==============================
# Every page requires a logged-in user except: language selection/entry,
# the login page itself, auth APIs, image files, health check, static files,
# and the /admin* routes (they already enforce their own separate admin auth).
LOGIN_EXEMPT_ENDPOINTS = {
    "index", "enter", "setlang", "login_route", "img", "health", "static",
    "home", "products_page", "mugs_page", "club_route", "product",
    "size_guide_page", "care_page", "returns_page", "return_policy_page",
    "how_page", "ticket", "track", "order_success", "penalty",
    "api_auth_otp", "api_auth_verify", "api_auth_admin_verify",
    "api_auth_password", "api_auth_logout", "api_me", "api_diag",
    "api_order", "api_notify", "api_request", "api_vote",
    "api_reviews", "api_review", "api_review_report",
    "api_penalty_play", "api_penalty_status",
    "api_favs", "api_alerts", "api_alerts_cancel",
}


@app.before_request
def require_login_everywhere():
    ep = request.endpoint
    if ep is None:
        return None  # let Flask handle 404s normally
    if ep in LOGIN_EXEMPT_ENDPOINTS or ep.startswith("admin"):
        return None
    if not has_lang():
        return None  # allow the language-selection flow to run first
    if current_user():
        return None
    return redirect("/login")


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
    v = float(v or 0)
    text = str(int(v)) if v.is_integer() else ("%.3f" % v).rstrip("0").rstrip(".")
    return "%s %s" % (text, cur())


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
    phone = fix_phone(os.environ.get("SUPER_ADMIN_PHONE") or os.environ.get("ADMIN_PHONE") or cfg.TELEGRAM)
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


# ============================== AUDIO ASSET ==============================




# ============================== PAGE TEMPLATES ==============================
CSS = """<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { overflow-x: hidden; max-width: 100vw; }
:root {
  --golazox-black:#050607; --golazox-stadium:#0A0D0C; --golazox-green:#0B1712;
  --golazox-pitch:#10251A; --golazox-pitch-2:#163523;
  --golazox-white:#F5F7F5; --golazox-silver:#B8BFBC; --golazox-muted:#78817D;
  --bg:#050607; --bg2:#0A0D0C; --bg3:#0B1712; --bg4:#10251A; --bg5:#163523;
  --card:rgba(255,255,255,.045); --card2:rgba(255,255,255,.03); --card3:#10251A;
  --line:rgba(255,255,255,.10); --txt:#F5F7F5; --mut:#78817D; --dim:#6F8F7A;
  --brand1:#18E875; --brand2:#0B9F50; --green:#18E875; --gold:#D8B45A; --ok:#18E875; --err:#DC2626;
  --ac:var(--brand1); --ac2:var(--brand2); --warm:var(--gold);
  --team-primary:var(--brand1); --team-secondary:var(--brand2); --team-glow:rgba(24,232,117,.12);
  --sh:0 8px 32px rgba(0,0,0,.55); --sh2:0 20px 50px rgba(0,0,0,.65); --sh3:0 2px 8px rgba(0,0,0,.4);
  --fs:16px;
  --glass:rgba(5,6,7,.78); --glass2:rgba(5,6,7,.55); --glass-border:rgba(255,255,255,.08);
  --stadium-dark:#050607; --stadium-green:#0B1712;
  --glow-g:0 0 30px rgba(24,232,117,.12); --glow-w:0 0 24px rgba(216,180,90,.10);
  --grad-brand:linear-gradient(135deg,#18E875 0%,#0B9F50 100%);
  --grad-gold:linear-gradient(135deg,#D8B45A 0%,#C4992F 100%);
  --scene-shadow:0 40px 80px rgba(0,0,0,.7),0 0 60px rgba(24,232,117,.04);
  --card-radius:18px; --hero-radius:28px;
}
html[data-font="a"] { --fs:14px; }
html[data-font="c"] { --fs:18px; }
html[data-font="a"] { --fs:14px; }
html[data-font="c"] { --fs:18px; }
html { font-size: var(--fs); }
body { font-family:'FONT','Segoe UI',Tahoma,sans-serif; background:var(--bg); color:var(--txt);
  min-height:100vh; transition:background .4s ease, color .4s ease;
  padding-bottom:env(safe-area-inset-bottom);
  background-image:
    radial-gradient(ellipse 140% 50% at 50% -15%, rgba(16,37,26,.15), transparent 55%),
    radial-gradient(ellipse 50% 35% at 85% 85%, rgba(216,180,90,.015), transparent 40%),
    radial-gradient(ellipse 70% 40% at 8% 75%, rgba(16,37,26,.08), transparent 40%),
    repeating-linear-gradient(0deg, transparent 0 120px, rgba(24,232,117,.003) 120px 121px),
    repeating-linear-gradient(90deg, transparent 0 120px, rgba(24,232,117,.003) 120px 121px),
    linear-gradient(180deg, #0A0D0C 0%, #050607 45%, #050607 100%);
  background-attachment:fixed; }
html[data-theme="light"] body { background:#F3F6FB; background-image:
  radial-gradient(ellipse 140% 50% at 50% -15%, rgba(24,232,117,.03), transparent 55%),
  radial-gradient(ellipse 80% 50% at 20% 80%, rgba(216,180,90,.01), transparent 40%),
  linear-gradient(180deg, #EDF1F8 0%, #F3F6FB 100%); background-attachment:fixed;
  --card:#FFFFFF; --card2:#EDF1F8; --card3:#F8FAFF; --line:#E2E8F0; --txt:#0F172A; --mut:#5B6782; --dim:#94A3B8;
  --brand1:#18E875; --brand2:#0B9F50; --green:#18E875; --ok:#16A34A; --err:#DC2626;
  --ac:var(--brand1); --ac2:var(--brand2);
  --sh:0 8px 28px rgba(15,23,42,.07); --sh2:0 18px 44px rgba(15,23,42,.12); --sh3:0 2px 8px rgba(15,23,42,.04);
  --glass:#FFFFFF; --glass2:rgba(255,255,255,.85); --glass-border:rgba(0,0,0,.06);
  --bg:#F3F6FB; --bg2:#EDF1F8; --bg3:#E8EDF5; --bg4:#F8FAFF; --bg5:#FFFFFF;
  --scene-shadow:0 20px 50px rgba(15,23,42,.08),0 0 40px rgba(24,232,117,.03); }
a { text-decoration:none; color:inherit; } img { display:block; }
button { font-family:inherit; cursor:pointer; }
html[data-club] .hd { border-bottom:1px solid var(--line); }
html[data-club] .hd::after { content:''; display:block; height:3px;
  background:linear-gradient(90deg, var(--ac), var(--ac2)); }
.wrap { max-width:1120px; margin:0 auto; padding:22px 18px 100px; }
html[data-theme="light"] .wrap { padding-bottom:80px; }
.hd { position:sticky; top:0; z-index:95; background:rgba(5,6,7,.78); backdrop-filter:blur(22px) saturate(1.8);
  -webkit-backdrop-filter:blur(22px) saturate(1.8); border-bottom:1px solid rgba(255,255,255,.08);
  box-shadow:0 4px 30px rgba(0,0,0,.4);
  transition:background .3s ease, border-color .3s ease, box-shadow .3s ease; }
html[data-theme="light"] .hd { background:rgba(255,255,255,.92); backdrop-filter:blur(16px) saturate(1.5);
  -webkit-backdrop-filter:blur(16px) saturate(1.5); box-shadow:0 2px 14px rgba(15,23,42,.04); border-bottom-color:rgba(0,0,0,.06); }
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
/* ============================== MATCHDAY TICKER ============================== */
.md-ticker { overflow:hidden; background:#07140F; border-top:1px solid rgba(0,230,118,.20);
  border-bottom:1px solid rgba(0,230,118,.20); height:44px; display:flex; align-items:center; margin:0 0 24px; }
.md-ticker-track { display:flex; gap:40px; white-space:nowrap; animation:mdTick 24s linear infinite; }
.md-ticker span { color:#F4F7F5; font-weight:800; font-size:.82rem; letter-spacing:1.5px; flex:none; }
.md-ticker span b { color:#00E676; text-shadow:0 0 12px rgba(0,230,118,.35); }
@keyframes mdTick { from { transform:translateX(0); } to { transform:translateX(-50%); } }
@media (max-width:640px) { .md-ticker { height:38px; margin-bottom:18px; } .md-ticker span { font-size:.74rem; letter-spacing:1px; } }
@media (prefers-reduced-motion:reduce) { .md-ticker-track { animation:none; } }
/* ============================== PENALTY CHALLENGE (home teaser) ============================== */
.pc-sec { position:relative; border-radius:26px; overflow:hidden; padding:48px 24px; text-align:center;
  min-height:0; background:
    radial-gradient(ellipse at 20% 0%, rgba(255,255,255,.07), transparent 30%),
    radial-gradient(ellipse at 80% 0%, rgba(255,255,255,.06), transparent 30%),
    radial-gradient(circle at 50% 0%, rgba(0,230,118,.08), transparent 35%),
    linear-gradient(180deg, #030605 0%, #07140F 50%, #030605 100%);
  border:1px solid rgba(255,255,255,.08); animation:pcLights 8s ease-in-out infinite; }
@keyframes pcLights { 0%,100% { filter:brightness(1); } 50% { filter:brightness(1.06); } }
.pc-fog { position:absolute; inset:-20% -10%; background:radial-gradient(ellipse at 50% 100%, rgba(255,255,255,.05), transparent 60%);
  filter:blur(20px); opacity:.6; pointer-events:none; animation:pcFog 16s linear infinite; }
@keyframes pcFog { from { transform:translateX(-4%); } to { transform:translateX(4%); } }
.pc-crowd { position:absolute; top:0; left:0; right:0; height:26px; opacity:.5;
  background:repeating-linear-gradient(90deg,#0b3d23 0 24px,#123f2b 24px 48px); }
.pc-goal-wrap { position:relative; height:150px; margin:20px auto 8px; max-width:340px; }
.pc-goal { position:absolute; left:50%; top:0; transform:translateX(-50%); width:220px; height:96px;
  border:4px solid rgba(244,247,245,.85); border-top:none; border-radius:0 0 8px 8px;
  background:repeating-linear-gradient(90deg,rgba(255,255,255,.22) 0 14px,transparent 14px 28px),
    repeating-linear-gradient(0deg,rgba(255,255,255,.22) 0 14px,transparent 14px 28px);
  box-shadow:0 0 40px rgba(0,230,118,.10); }
.pc-keeper { position:absolute; left:50%; bottom:10px; transform:translateX(-50%); width:44px; height:70px;
  animation:pcBreathe 2.6s ease-in-out infinite; }
.pc-keeper .kb { position:absolute; bottom:0; width:44px; height:56px; border-radius:14px 14px 6px 6px; background:linear-gradient(180deg,#0F172A,#1E293B); }
.pc-keeper .kh { position:absolute; top:0; left:50%; transform:translateX(-50%); width:22px; height:20px; border-radius:50%; background:#1E293B; }
@keyframes pcBreathe { 0%,100% { transform:translateX(-50%) translateY(0); } 50% { transform:translateX(-50%) translateY(-2px); } }
.pc-ball { position:absolute; left:50%; bottom:2px; transform:translateX(-50%); font-size:26px; filter:drop-shadow(0 6px 6px rgba(0,0,0,.4));
  transition:transform .3s ease; }
.pc-sec:hover .pc-ball { transform:translateX(-50%) translateY(-3px); }
.pc-title { font-size:1.6rem; font-weight:900; color:#F4F7F5; margin-top:4px; }
.pc-sub { color:#AEB8B3; font-size:.95rem; margin-top:6px; }
.pc-cta { display:inline-flex; align-items:center; gap:8px; margin-top:20px; background:#00E676; color:#031008;
  border-radius:14px; padding:14px 30px; font-weight:800; font-size:.95rem; text-decoration:none;
  box-shadow:0 8px 30px rgba(0,230,118,.18); transition:transform .2s ease, box-shadow .2s ease; }
.pc-cta:hover { transform:translateY(-2px); box-shadow:0 12px 35px rgba(0,230,118,.28); }
.pc-cta:active { transform:scale(.98); }
@media (max-width:640px) { .pc-sec { padding:32px 16px; } .pc-goal-wrap { height:120px; max-width:260px; } .pc-goal { width:170px; height:76px; }
  .pc-title { font-size:1.25rem; } .pc-cta { width:100%; justify-content:center; } }
/* hero */
.hero { position:relative; overflow:hidden; border:1px solid rgba(255,255,255,.06); border-radius:26px;
  background:
  radial-gradient(130% 110% at 12% 0%, rgba(16,37,26,.25), transparent 58%),
  radial-gradient(110% 100% at 92% 100%, rgba(216,180,90,.02), transparent 60%),
  linear-gradient(120deg, rgba(11,23,18,.6) 0%, rgba(5,6,7,.92) 60%);
  padding:46px 34px; margin-bottom:26px; transition:background .45s ease;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.04); }
html[data-theme="light"] .hero { background:linear-gradient(120deg, var(--card) 0%, #F8FAFF 60%); border-color:var(--line);
  box-shadow: var(--sh); }
html[data-club] .hero { background: radial-gradient(130% 110% at 12% 0%, color-mix(in srgb, var(--ac) 12%, transparent), transparent 58%), linear-gradient(120deg, rgba(11,23,18,.5) 0%, rgba(5,6,7,.88) 60%); }
html[data-theme="light"] .hero { background:linear-gradient(120deg, var(--card) 0%, #F8FAFF 55%); }
html[data-theme="light"][data-club] .hero { background:linear-gradient(120deg, var(--tint, rgba(225,29,72,.06)) 0%, transparent 68%), linear-gradient(120deg, var(--card) 0%, #F8FAFF 55%); }
.hero h1 { font-size:2.4rem; line-height:1.15; font-weight:900; color:var(--golazox-white); }
.hero h1 .g { background:linear-gradient(90deg, var(--ac), var(--ac2)); -webkit-background-clip:text; background-clip:text; color:transparent; }
.hero p { margin-top:12px; color:var(--golazox-silver); font-size:1rem; line-height:1.9; max-width:640px; }
.hero-btns { margin-top:22px; display:flex; gap:12px; flex-wrap:wrap; }
.btn { display:inline-flex; align-items:center; gap:8px; font-weight:800; font-size:.95rem; padding:12px 24px;
  border-radius:999px; border:none; transition:transform .16s ease, box-shadow .2s ease; }
.btn:active { transform:scale(.96)!important; }
.btn.pri { background:var(--golazox-white); color:var(--golazox-black);
  box-shadow:0 8px 28px rgba(245,247,245,.15);
  transition:transform .16s ease, box-shadow .3s ease, background .3s ease; }
.btn.pri:hover { transform:translateY(-2px); background:var(--golazox-green); color:var(--golazox-white); box-shadow:0 12px 36px rgba(24,232,117,.25); }
.btn.ghost { background:transparent; border:1.5px solid rgba(255,255,255,.12); color:var(--golazox-white); backdrop-filter:blur(8px); }
html[data-theme="light"] .btn.ghost { background:var(--card); border-color:var(--line); color:var(--txt); backdrop-filter:none; }
.btn.ghost:hover { border-color:var(--ac); color:var(--ac); }
.btn.wa2 { background:var(--green); color:#fff; box-shadow:0 8px 28px rgba(24,232,117,.3); }
.btn.wa2:hover { transform:translateY(-2px); box-shadow:0 12px 36px rgba(24,232,117,.4); }
.btn.big { width:100%; justify-content:center; padding:14px; font-size:1rem; }
.btn.sm { padding:8px 16px; font-size:.85rem; }
.btn.block { width:100%; justify-content:center; }
.sec { margin-bottom:34px; }
.sec-head { display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:16px; }
.sec-head h2 { font-size:1.4rem; font-weight:900; display:flex; align-items:center; gap:10px; }
.sec-head h2 .bar { width:6px; height:1.4rem; border-radius:4px; background:linear-gradient(180deg, var(--ac), var(--ac2)); transition:background .45s ease; }
.sec-sub { color:var(--mut); font-size:.86rem; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:24px; }
/* ── 3D Product Scene Card ── */
.pcard { position:relative; perspective:900px; cursor:pointer; }
.pcard-inner {
  position:relative; border-radius:var(--card-radius); overflow:visible;
  background:var(--card); border:1px solid var(--glass-border);
  transition:transform .35s cubic-bezier(.22,1,.36,1), box-shadow .35s ease, border-color .35s ease;
  transform-style:preserve-3d; will-change:transform;
  box-shadow:var(--sh3);
}
html[data-theme="light"] .pcard-inner { background:var(--card); border-color:var(--line); }
.pcard:hover .pcard-inner, .pcard:active .pcard-inner {
  border-color:color-mix(in srgb, var(--pc, var(--ac)) 40%, var(--glass-border));
  box-shadow:var(--sh), 0 0 30px color-mix(in srgb, var(--pc, var(--ac)) 15%, transparent);
}
.pcard:hover .pcard-inner{transform:translateY(-4px) perspective(600px) rotateY(1deg) rotateX(-1deg)}
.pcard-inner::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:var(--card-radius) var(--card-radius) 0 0;
  background:linear-gradient(90deg,var(--pc,var(--ac)),var(--pc2,var(--ac2)));opacity:.6;z-index:5;transition:opacity .3s}
.pcard:hover .pcard-inner::before{opacity:1}
/* Stadium glow behind product */
.pcard-glow {
  position:absolute; top:15%; left:10%; right:10%; bottom:10%;
  border-radius:50%; filter:blur(40px); opacity:0;
  background:radial-gradient(circle, color-mix(in srgb, var(--pc, var(--ac)) 18%, transparent), transparent 70%);
  transition:opacity .4s ease; pointer-events:none; z-index:0;
}
.pcard:hover .pcard-glow { opacity:1; }
html[data-theme="light"] .pcard:hover .pcard-glow { opacity:.6; }
.pcard-edition{font-size:.55rem;font-weight:900;letter-spacing:2px;text-transform:uppercase;
  color:var(--pc,var(--ac));opacity:.5;margin-top:2px;margin-bottom:4px}
/* Product image scene */
.pimg {
  position:relative; height:260px; display:flex; align-items:center; justify-content:center;
  overflow:hidden; background:linear-gradient(180deg, var(--bg3) 0%, var(--card) 100%);
  border-radius:var(--card-radius) var(--card-radius) 0 0; z-index:1;
}
.pimg img {
  width:85%; height:88%; object-fit:contain;
  transition:transform .4s cubic-bezier(.22,1,.36,1);
  filter:drop-shadow(0 12px 24px rgba(0,0,0,.35));
  position:relative; z-index:2;
  max-width:100%; display:block;
}
.pcard:hover .pimg img {
  transform:translateZ(20px) scale(1.04);
  filter:drop-shadow(0 20px 40px rgba(0,0,0,.45)) drop-shadow(0 0 20px rgba(24,232,117,.12));
}
/* Ground shadow under product */
.pimg::after {
  content:''; position:absolute; bottom:8%; left:15%; right:15%; height:14px;
  background:radial-gradient(ellipse, rgba(0,0,0,.35) 0%, transparent 70%);
  border-radius:50%; z-index:1; transition:all .4s ease;
}
.pcard:hover .pimg::after {
  bottom:5%; left:10%; right:10%; height:18px;
  background:radial-gradient(ellipse, rgba(0,0,0,.45) 0%, rgba(24,232,117,.06) 60%, transparent 80%);
}
/* Soft reflection */
.pimg::before {
  content:''; position:absolute; top:0; left:0; right:0; height:50%;
  background:linear-gradient(180deg, rgba(255,255,255,.03) 0%, transparent 100%);
  z-index:3; pointer-events:none;
}
html[data-theme="light"] .pimg::before { background:linear-gradient(180deg, rgba(255,255,255,.4) 0%, transparent 100%); }
.pimg-fallback { display:flex; align-items:center; justify-content:center; width:100%; height:100%; font-size:3rem; color:var(--mut); opacity:.4; background:var(--bg3); }
.pimg img { background:var(--bg3); }
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
.sbox { flex:1; min-width:220px; display:flex; background:rgba(11,23,18,.6); border:1.5px solid var(--glass-border); border-radius:14px;
  align-items:center; padding:0 6px 0 14px; backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px); }
html[data-theme="light"] .sbox { background:var(--card); border-color:var(--line); backdrop-filter:none; }
.sbox input { flex:1; border:none; outline:none; background:none; color:var(--txt); font-family:inherit; font-size:.95rem; padding:12px 4px; }
.sbox button { background:var(--ac); color:var(--bg); border:none; border-radius:10px; padding:9px 14px; font-weight:800; font-size:.85rem; }
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
  font-size:.82rem; font-weight:700; font-family:inherit; color-scheme:dark; }
html[data-theme="light"] .sel { color-scheme:light; }
.sel option { background:#0B1712; color:#F4F7F5; }
html[data-theme="light"] .sel option { background:#fff; color:#0F172A; }
/* ============================== GOLAZOX FIT CHECK + CLUB COLOR ============================== */
.gx-fit-card{background:linear-gradient(145deg,rgba(24,232,117,.07),rgba(255,255,255,.025));border:1px solid rgba(24,232,117,.14);border-radius:22px;padding:20px;margin:20px 0;box-shadow:0 18px 40px rgba(0,0,0,.16)}
.gx-fit-card .gx-fit-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.gx-fit-card h3{font-size:1.05rem;font-weight:900}.gx-fit-card p{margin-top:4px;color:var(--mut);font-size:.78rem}.fit-check-btn{background:linear-gradient(135deg,var(--ac),var(--ac2));color:#07110c;border:none;border-radius:14px;padding:11px 16px;font-weight:900;box-shadow:0 10px 26px color-mix(in srgb,var(--ac) 18%,transparent)}
.gx-fit-result{display:none;margin-top:14px;border-radius:16px;padding:14px 16px;background:rgba(24,232,117,.06);border:1px solid rgba(24,232,117,.18);text-align:center}.gx-fit-result.show{display:block;animation:fadeUp .35s ease both}.gx-fit-size{font-size:2.2rem;font-weight:1000;color:var(--ac);letter-spacing:1px}.gx-fit-sub{font-size:.78rem;color:var(--mut);margin-top:4px}
.gx-club-color{position:relative;overflow:hidden;border-radius:24px;padding:22px;background:linear-gradient(135deg,var(--club-a,#18E875),var(--club-b,#0B9F50));color:#fff;box-shadow:0 22px 50px color-mix(in srgb,var(--club-a,#18E875) 20%,transparent)}.gx-club-color:before{content:"";position:absolute;inset:0;background:radial-gradient(circle at 80% 20%,rgba(255,255,255,.18),transparent 28%),linear-gradient(135deg,transparent 55%,rgba(255,255,255,.06));pointer-events:none}.gx-club-color-inner{position:relative;z-index:1}.gx-club-color-top{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}.gx-club-color h3{font-size:1.35rem;font-weight:1000}.gx-club-color small{opacity:.85;font-weight:800}.gx-club-swatches{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.gx-club-swatch{border:1px solid rgba(255,255,255,.22);background:rgba(0,0,0,.18);color:#fff;border-radius:999px;padding:8px 12px;font:inherit;font-size:.74rem;font-weight:900;cursor:pointer;backdrop-filter:blur(8px)}.gx-club-swatch.on{background:#fff;color:#0b1712;border-color:#fff;box-shadow:0 6px 16px rgba(0,0,0,.18)}.gx-club-color-cta{display:inline-flex;margin-top:14px;padding:10px 14px;border-radius:12px;background:rgba(255,255,255,.14);font-size:.76rem;font-weight:900;border:1px solid rgba(255,255,255,.18)}
@media(max-width:640px){.gx-fit-card{padding:16px}.gx-fit-size{font-size:1.9rem}.gx-club-color{padding:18px;border-radius:20px}}


/* ============================== GOLAZOX JERSEY MAP ============================== */
.gx-jmap-preview{position:relative;overflow:hidden;border:1px solid rgba(24,232,117,.14);border-radius:28px;
margin:8px 0 28px;padding:22px;background:radial-gradient(65% 80% at 18% 20%,rgba(59,130,246,.16),transparent 62%),radial-gradient(55% 70% at 78% 25%,rgba(24,232,117,.11),transparent 60%),linear-gradient(180deg,#040809 0%,#07130f 100%);
box-shadow:0 24px 70px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.04)}
.gx-jmap-preview::before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(rgba(255,255,255,.022) 1px,transparent 1px);background-size:42px 42px;pointer-events:none;opacity:.45}
.gx-jmap-grid{position:relative;z-index:1;display:grid;grid-template-columns:1.2fr .8fr;gap:18px;align-items:stretch}
.gx-jmap-stage{min-height:390px;position:relative;border-radius:22px;border:1px solid rgba(255,255,255,.08);overflow:hidden;background:radial-gradient(circle at 34% 46%,rgba(24,232,117,.14),transparent 14%),radial-gradient(circle at 67% 32%,rgba(59,130,246,.12),transparent 17%),radial-gradient(circle at 72% 68%,rgba(245,158,11,.08),transparent 16%),linear-gradient(180deg,#07111a,#030607)}
.gx-jmap-stage::after{content:"";position:absolute;inset:10% 7%;border:1px solid rgba(255,255,255,.055);border-radius:50%;box-shadow:0 0 0 24px rgba(255,255,255,.012),0 0 0 48px rgba(255,255,255,.008)}
.gx-jmap-stars{position:absolute;inset:0;background-image:radial-gradient(circle at 14% 25%,rgba(255,255,255,.8) 0 1px,transparent 1.5px),radial-gradient(circle at 30% 70%,rgba(24,232,117,.8) 0 1px,transparent 1.5px),radial-gradient(circle at 58% 18%,rgba(255,255,255,.65) 0 1px,transparent 1.5px),radial-gradient(circle at 77% 52%,rgba(59,130,246,.8) 0 1px,transparent 1.5px),radial-gradient(circle at 86% 26%,rgba(216,180,90,.7) 0 1px,transparent 1.5px);opacity:.6}
.gx-jmap-orbit{position:absolute;left:50%;top:50%;width:min(70vw,430px);height:min(70vw,430px);transform:translate(-50%,-50%);border:1px solid rgba(24,232,117,.12);border-radius:50%;box-shadow:0 0 50px rgba(24,232,117,.04)}
.gx-jmap-orbit::before,.gx-jmap-orbit::after{content:"";position:absolute;inset:13%;border:1px solid rgba(255,255,255,.045);border-radius:50%}
.gx-jmap-orbit::after{inset:31%}
.gx-jmap-lines{position:absolute;inset:0;background:linear-gradient(14deg,transparent 49.8%,rgba(255,255,255,.05) 49.9%,rgba(255,255,255,.05) 50.1%,transparent 50.2%),linear-gradient(-22deg,transparent 49.8%,rgba(255,255,255,.035) 49.9%,rgba(255,255,255,.035) 50.1%,transparent 50.2%);opacity:.9}
.gx-jmap-title{position:absolute;z-index:5;top:18px;left:18px;right:18px;display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.gx-jmap-title h3{font-size:1.45rem;font-weight:1000;letter-spacing:.5px}
.gx-jmap-title p{margin-top:4px;color:rgba(255,255,255,.52);font-size:.72rem}
.gx-jmap-tag{padding:7px 10px;border-radius:999px;border:1px solid rgba(24,232,117,.18);color:#18E875;background:rgba(24,232,117,.06);font-size:.66rem;font-weight:900}
.gx-jpin{position:absolute;z-index:4;transform:translate(-50%,-50%);padding:7px 9px;border:1px solid rgba(255,255,255,.14);background:rgba(3,7,8,.74);color:#fff;border-radius:14px;backdrop-filter:blur(10px);font-size:.68rem;font-weight:900;cursor:pointer;display:flex;align-items:center;gap:6px;box-shadow:0 10px 24px rgba(0,0,0,.22);transition:.22s}
.gx-jpin:hover,.gx-jpin.active{border-color:var(--pin,#18E875);box-shadow:0 0 28px color-mix(in srgb,var(--pin,#18E875) 24%,transparent);transform:translate(-50%,-52%) scale(1.03)}
.gx-jpin .dot{width:8px;height:8px;border-radius:50%;background:var(--pin,#18E875);box-shadow:0 0 14px var(--pin,#18E875)}
.gx-jmap-showcase{position:relative;border:1px solid rgba(255,255,255,.08);border-radius:22px;background:rgba(0,0,0,.26);overflow:hidden;min-height:390px}
.gx-jmap-showcase::before{content:"";position:absolute;inset:0;background:radial-gradient(circle at 50% 35%,var(--show-a,rgba(24,232,117,.18)),transparent 38%)}
.gx-jmap-show-inner{position:relative;z-index:2;height:100%;display:flex;flex-direction:column;padding:18px}
.gx-jmap-show-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
.gx-jmap-club{font-size:1rem;font-weight:1000}.gx-jmap-country{font-size:.65rem;color:var(--mut);margin-top:3px}
.gx-jmap-product-scene{flex:1;display:flex;align-items:center;justify-content:center;min-height:220px}
.gx-jmap-product-scene img{width:min(88%,320px);height:240px;object-fit:contain;filter:drop-shadow(0 24px 40px rgba(0,0,0,.5));transition:transform .35s}
.gx-jmap-showcase:hover .gx-jmap-product-scene img{transform:translateY(-5px) scale(1.03)}
.gx-jmap-price{font-size:1.25rem;font-weight:1000;color:var(--ac);margin-top:4px}.gx-jmap-sub{font-size:.72rem;color:var(--mut);margin-top:3px}
.gx-jmap-cta{margin-top:12px;display:flex;gap:8px}.gx-jmap-cta a{flex:1;justify-content:center}
.gx-jmap-label{font-size:.72rem;font-weight:900;color:var(--mut);margin-top:12px}
.gx-jmap-countries{display:flex;gap:9px;overflow-x:auto;padding:12px 2px 4px;scroll-snap-type:x proximity;scrollbar-width:none}
.gx-jmap-countries::-webkit-scrollbar{display:none}
.gx-jcountry{flex:0 0 104px;scroll-snap-align:start;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:10px 8px;background:rgba(255,255,255,.025);color:#fff;cursor:pointer;text-align:center;transition:.2s}
.gx-jcountry:hover,.gx-jcountry.active{border-color:var(--jc,#18E875);background:color-mix(in srgb,var(--jc,#18E875) 8%,transparent);box-shadow:0 8px 24px color-mix(in srgb,var(--jc,#18E875) 14%,transparent)}
.gx-jcountry .flag{font-size:1.4rem;display:block}.gx-jcountry b{display:block;font-size:.72rem;margin-top:5px}.gx-jcountry small{display:block;color:rgba(255,255,255,.42);font-size:.56rem;margin-top:2px}
.gx-jmap-clubs{display:flex;gap:9px;overflow-x:auto;padding:8px 2px 0;scrollbar-width:none}.gx-jmap-clubs::-webkit-scrollbar{display:none}
.gx-jclub{flex:0 0 128px;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:10px;background:rgba(255,255,255,.025);cursor:pointer;transition:.2s}
.gx-jclub:hover,.gx-jclub.active{border-color:var(--ca,#18E875);box-shadow:0 10px 28px color-mix(in srgb,var(--ca,#18E875) 13%,transparent);transform:translateY(-2px)}
.gx-jclub-top{display:flex;justify-content:space-between;gap:6px;align-items:center}.gx-jclub em{font-style:normal;font-size:1.2rem}.gx-jclub b{font-size:.7rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.gx-jclub span{display:block;margin-top:8px;color:rgba(255,255,255,.42);font-size:.56rem}
.gx-jmap-foot{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:12px;flex-wrap:wrap}.gx-jmap-count{font-size:.7rem;color:rgba(255,255,255,.48)}
.gx-jmap-open{border:1px solid rgba(24,232,117,.24);color:#18E875;background:rgba(24,232,117,.055);border-radius:999px;padding:8px 12px;font-size:.68rem;font-weight:900}
.gx-jmap-page{padding-bottom:110px}.gx-jmap-page .gx-jmap-grid{grid-template-columns:1.25fr .75fr}.gx-jmap-page .gx-jmap-stage,.gx-jmap-page .gx-jmap-showcase{min-height:500px}.gx-jmap-page .gx-jmap-product-scene img{height:315px}
@media(max-width:900px){.gx-jmap-grid,.gx-jmap-page .gx-jmap-grid{grid-template-columns:1fr}.gx-jmap-stage,.gx-jmap-page .gx-jmap-stage{min-height:360px}.gx-jmap-showcase,.gx-jmap-page .gx-jmap-showcase{min-height:430px}}
@media(max-width:640px){.gx-jmap-preview{padding:12px;border-radius:20px}.gx-jmap-stage{min-height:330px}.gx-jmap-title h3{font-size:1.05rem}.gx-jmap-title p{font-size:.62rem}.gx-jpin{font-size:.6rem;padding:6px 8px}.gx-jmap-showcase{min-height:360px}.gx-jmap-product-scene{min-height:190px}.gx-jmap-product-scene img{height:200px}.gx-jcountry{flex-basis:90px}.gx-jclub{flex-basis:118px}}

.gx-jmap-fallback{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;padding:20px 22px;border-radius:20px;border:1px solid rgba(24,232,117,.12);background:linear-gradient(135deg,rgba(24,232,117,.07),rgba(255,255,255,.02));box-shadow:0 18px 38px rgba(0,0,0,.18)}.gx-jmap-fallback>div{display:flex;flex-direction:column;gap:5px}.gx-jmap-fallback b{font-size:1.05rem}.gx-jmap-fallback span{color:var(--mut);font-size:.82rem}@media(max-width:640px){.gx-jmap-fallback{padding:16px}.gx-jmap-fallback .btn{width:100%;justify-content:center}}
/* ============================== JERSEY MAP — GLOWING WORLD EXPERIENCE ============================== */
.gx-jersey-map{position:relative;overflow:hidden;border-radius:34px;padding:22px;background:
 radial-gradient(70% 80% at 72% 28%,rgba(24,232,117,.09),transparent 55%),
 radial-gradient(60% 60% at 25% 70%,rgba(216,180,90,.06),transparent 58%),
 linear-gradient(180deg,#030807 0%,#06110c 100%);border:1px solid rgba(24,232,117,.16);
 box-shadow:0 34px 100px rgba(0,0,0,.42),inset 0 1px 0 rgba(255,255,255,.04)}
.gx-jm-shell{position:relative;z-index:2}
.gx-jm-top{display:flex;justify-content:space-between;align-items:flex-end;gap:18px;margin-bottom:18px}.gx-jm-kicker{display:block;color:#18e875;font-size:.62rem;font-weight:1000;letter-spacing:4px}.gx-jm-top h2{font-size:clamp(1.45rem,3vw,2.35rem);font-weight:1000;line-height:1.05;margin-top:6px}.gx-jm-top p{margin-top:7px;color:rgba(255,255,255,.55);font-size:.82rem}.gx-jm-top-right{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.gx-jm-pill{padding:8px 11px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.025);border-radius:999px;color:#fff;font-size:.62rem;font-weight:900}.gx-jm-pill.live{border-color:rgba(24,232,117,.2);color:#9cf3bf}.gx-jm-pill.live i{display:inline-block;width:6px;height:6px;border-radius:50%;background:#18e875;box-shadow:0 0 12px #18e875;margin-inline-end:5px}
.gx-jm-globe-wrap{position:relative;min-height:560px;border-radius:30px;overflow:hidden;border:1px solid rgba(255,255,255,.07);background:
 radial-gradient(circle at 58% 42%,rgba(255,255,255,.035),transparent 35%),
 radial-gradient(circle at 50% 50%,rgba(24,232,117,.055),transparent 50%),
 linear-gradient(180deg,#020605,#04100b 68%,#020605)}
.gx-jm-stars{position:absolute;inset:0;opacity:.55;background-image:radial-gradient(circle at 8% 18%,rgba(255,255,255,.85) 0 1px,transparent 1.5px),radial-gradient(circle at 22% 61%,rgba(24,232,117,.7) 0 1px,transparent 1.5px),radial-gradient(circle at 42% 22%,rgba(255,255,255,.65) 0 1px,transparent 1.5px),radial-gradient(circle at 68% 18%,rgba(216,180,90,.7) 0 1px,transparent 1.5px),radial-gradient(circle at 88% 45%,rgba(255,255,255,.8) 0 1px,transparent 1.5px),radial-gradient(circle at 76% 78%,rgba(24,232,117,.5) 0 1px,transparent 1.5px)}
.gx-jm-globe{position:absolute;left:52%;top:49%;width:min(76vw,620px);aspect-ratio:1;transform:translate(-50%,-50%);border-radius:50%;background:
 radial-gradient(circle at 34% 28%,rgba(255,255,255,.18),transparent 7%),
 radial-gradient(circle at 45% 38%,rgba(24,232,117,.22),transparent 32%),
 radial-gradient(circle at 50% 48%,rgba(4,21,14,.15),rgba(2,7,5,.92) 70%),
 linear-gradient(145deg,#06130e,#010504 70%);box-shadow:inset -28px -24px 80px rgba(0,0,0,.8),inset 16px 12px 60px rgba(255,255,255,.06),0 0 110px rgba(24,232,117,.12);border:1px solid rgba(255,255,255,.08);overflow:hidden}
.gx-jm-globe:before{content:"";position:absolute;inset:7%;border-radius:50%;background:repeating-linear-gradient(0deg,transparent 0 15px,rgba(255,255,255,.035) 16px 17px),repeating-linear-gradient(90deg,transparent 0 22px,rgba(24,232,117,.035) 23px 24px);transform:rotate(-8deg) scale(1.08);opacity:.7}
.gx-jm-globe:after{content:"";position:absolute;inset:-8%;border-radius:50%;border:1px solid rgba(24,232,117,.14);box-shadow:0 0 0 18px rgba(24,232,117,.025),0 0 0 40px rgba(216,180,90,.015);}
.gx-jm-continent{position:absolute;opacity:.92;filter:drop-shadow(0 0 12px rgba(24,232,117,.12))}
.gx-jm-continent.eu{left:34%;top:27%;width:28%;height:25%;background:linear-gradient(135deg,#163e2b,#0b2317);clip-path:polygon(10% 55%,22% 32%,38% 28%,47% 16%,61% 20%,69% 35%,87% 37%,92% 58%,82% 68%,72% 64%,64% 78%,48% 70%,36% 84%,25% 70%,13% 75%)}
.gx-jm-continent.uk{left:31%;top:23%;width:8%;height:10%;background:linear-gradient(135deg,#1d5a3e,#0b2519);clip-path:polygon(22% 8%,58% 0,85% 27%,70% 63%,47% 92%,16% 69%,4% 32%)}
.gx-jm-continent.sa{left:57%;top:48%;width:18%;height:18%;background:linear-gradient(135deg,#1f6b45,#0b2619);clip-path:polygon(12% 35%,29% 10%,56% 19%,86% 24%,92% 48%,72% 69%,57% 87%,32% 78%,16% 58%)}
.gx-jm-continent.as{left:57%;top:24%;width:30%;height:30%;background:linear-gradient(145deg,#11422b,#061b12);clip-path:polygon(7% 38%,15% 22%,31% 19%,42% 7%,61% 15%,71% 6%,87% 18%,94% 41%,82% 55%,74% 47%,63% 65%,50% 57%,39% 71%,23% 60%,13% 73%)}
.gx-jm-continent.na{left:6%;top:27%;width:24%;height:28%;background:linear-gradient(145deg,#0c2b1d,#05150e);clip-path:polygon(8% 18%,26% 5%,50% 12%,67% 29%,86% 35%,80% 52%,66% 49%,58% 66%,39% 61%,31% 82%,15% 73%,18% 52%,4% 44%)}
.gx-jm-continent.saam{left:24%;top:50%;width:15%;height:35%;background:linear-gradient(145deg,#0a2d1d,#04140d);clip-path:polygon(40% 4%,63% 14%,71% 32%,62% 49%,70% 68%,57% 90%,39% 98%,32% 76%,15% 59%,20% 38%,7% 20%)}
.gx-jm-arc{position:absolute;left:50%;top:48%;width:42%;height:22%;border:1px solid rgba(24,232,117,.25);border-left-color:transparent;border-bottom-color:transparent;border-radius:50%;transform:translate(-10%,-40%) rotate(18deg);box-shadow:0 0 25px rgba(24,232,117,.05);opacity:.8}
.gx-jm-arc.two{width:55%;height:31%;transform:translate(-18%,-45%) rotate(-12deg);border-color:rgba(216,180,90,.18);border-left-color:transparent;border-bottom-color:transparent}
.gx-jm-pulse{position:absolute;width:9px;height:9px;border-radius:50%;background:var(--pc,#18e875);box-shadow:0 0 0 0 color-mix(in srgb,var(--pc,#18e875) 50%,transparent);animation:gxJmPulse 2.4s infinite}.gx-jm-pulse::after{content:"";position:absolute;inset:-6px;border:1px solid color-mix(in srgb,var(--pc,#18e875) 40%,transparent);border-radius:50%;animation:gxJmPulseRing 2.4s infinite}@keyframes gxJmPulse{70%{box-shadow:0 0 0 16px transparent}}@keyframes gxJmPulseRing{100%{transform:scale(1.6);opacity:0}}
.gx-jm-marker{position:absolute;z-index:8;transform:translate(-50%,-50%);display:flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid rgba(255,255,255,.09);background:rgba(3,9,7,.72);backdrop-filter:blur(12px);border-radius:14px;color:#fff;font-size:.68rem;font-weight:1000;cursor:pointer;box-shadow:0 14px 30px rgba(0,0,0,.34);transition:.24s}.gx-jm-marker span{font-size:1.1rem}.gx-jm-marker small{display:block;color:rgba(255,255,255,.48);font-size:.52rem;font-weight:800;margin-top:1px}.gx-jm-marker:hover,.gx-jm-marker.is-active{transform:translate(-50%,-55%) scale(1.06);border-color:var(--mc,#18e875);box-shadow:0 0 30px color-mix(in srgb,var(--mc,#18e875) 22%,transparent)}
.gx-jm-hero-copy{position:absolute;left:20px;top:22px;z-index:9;max-width:270px}.gx-jm-hero-copy .ey{font-size:.6rem;letter-spacing:3px;color:#18e875;font-weight:1000}.gx-jm-hero-copy h3{font-size:1.7rem;font-weight:1000;line-height:1.05;margin-top:7px}.gx-jm-hero-copy p{font-size:.68rem;color:rgba(255,255,255,.5);margin-top:8px;line-height:1.6}.gx-jm-hero-copy .btn{margin-top:11px}
.gx-jm-stats{position:absolute;right:20px;top:22px;z-index:9;width:150px;padding:13px;border:1px solid rgba(255,255,255,.08);border-radius:18px;background:rgba(3,8,6,.58);backdrop-filter:blur(12px)}.gx-jm-stat{padding:8px 0;border-bottom:1px solid rgba(255,255,255,.06)}.gx-jm-stat:last-child{border-bottom:0}.gx-jm-stat b{display:block;font-size:1.45rem;line-height:1;color:#18e875}.gx-jm-stat span{font-size:.55rem;color:rgba(255,255,255,.46)}
.gx-jm-instruction{position:absolute;left:50%;bottom:18px;transform:translateX(-50%);z-index:9;font-size:.62rem;color:rgba(255,255,255,.52);white-space:nowrap}.gx-jm-instruction b{color:#d8b45a}
.gx-jm-journey{display:grid;grid-template-columns:1.05fr .95fr 1.1fr .72fr 1.15fr;gap:10px;margin-top:12px}.gx-jm-step{position:relative;min-height:170px;border:1px solid rgba(255,255,255,.08);border-radius:20px;background:linear-gradient(180deg,rgba(255,255,255,.035),rgba(255,255,255,.015));padding:13px;overflow:hidden}.gx-jm-step::after{content:"";position:absolute;inset:auto 12px 9px;height:1px;background:linear-gradient(90deg,transparent,rgba(216,180,90,.26),transparent)}.gx-jm-stepnum{display:inline-flex;width:24px;height:24px;align-items:center;justify-content:center;border-radius:50%;background:#101812;color:#d8b45a;font-size:.6rem;font-weight:1000;border:1px solid rgba(216,180,90,.25)}.gx-jm-step h4{font-size:.76rem;margin-top:8px;letter-spacing:.5px}.gx-jm-step .muted{font-size:.55rem;color:rgba(255,255,255,.42);margin-top:3px}.gx-jm-country-card{margin-top:13px;border-radius:14px;padding:12px;background:rgba(0,0,0,.22);min-height:95px;display:flex;flex-direction:column;justify-content:center;align-items:center}.gx-jm-country-card .flag{font-size:2rem}.gx-jm-country-card b{font-size:.72rem;margin-top:5px}.gx-jm-country-card span{font-size:.52rem;color:rgba(255,255,255,.4);margin-top:2px}
.gx-jm-club-row{display:flex;gap:7px;margin-top:12px;overflow:auto;scrollbar-width:none}.gx-jm-club-row::-webkit-scrollbar{display:none}.gx-jm-club-btn{flex:0 0 82px;padding:8px;border-radius:12px;border:1px solid rgba(255,255,255,.08);background:rgba(0,0,0,.2);color:#fff;cursor:pointer;font:inherit;text-align:center}.gx-jm-club-btn.on{background:linear-gradient(135deg,var(--ca),var(--cb));color:#041008;border-color:transparent}.gx-jm-club-btn span{display:block;font-size:1.25rem}.gx-jm-club-btn b{display:block;font-size:.52rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}
.gx-jm-jersey{margin-top:10px;min-height:113px;border-radius:14px;padding:7px;display:flex;align-items:center;justify-content:center;background:radial-gradient(circle at 50% 35%,rgba(255,255,255,.08),transparent 60%),rgba(0,0,0,.22)}.gx-jm-jersey img{width:100%;height:112px;object-fit:contain;filter:drop-shadow(0 12px 20px rgba(0,0,0,.55))}.gx-jm-size-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:7px;margin-top:13px}.gx-jm-size-grid button{padding:8px 6px;border-radius:11px;border:1px solid rgba(255,255,255,.08);background:rgba(0,0,0,.2);color:#fff;font:inherit;font-size:.58rem;font-weight:900}.gx-jm-size-grid button.active{border-color:#d8b45a;background:rgba(216,180,90,.11);color:#fff}.gx-jm-buy{display:flex;flex-direction:column;justify-content:center;height:100%}.gx-jm-buy .price{font-size:1.9rem;font-weight:1000;color:#d8b45a}.gx-jm-buy .small{font-size:.57rem;color:rgba(255,255,255,.45);margin-top:4px}.gx-jm-buy .ok{font-size:.6rem;color:#18e875;margin-top:12px;display:grid;gap:7px}.gx-jm-buy .ok span{display:flex;gap:5px;align-items:center}.gx-jm-buy .cta{margin-top:14px;width:100%;justify-content:center;background:linear-gradient(135deg,#d8b45a,#f0d889);color:#081009;border:0}.gx-jm-country-strip{display:flex;gap:8px;overflow:auto;margin-top:11px;padding-bottom:2px;scrollbar-width:none}.gx-jm-country-strip::-webkit-scrollbar{display:none}.gx-jm-country-tab{flex:0 0 auto;padding:8px 11px;border-radius:999px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.025);color:#fff;font:inherit;font-size:.6rem;font-weight:900;cursor:pointer}.gx-jm-country-tab.on{background:linear-gradient(135deg,#18e875,#0b9f50);color:#041008;border-color:transparent}
@media(max-width:1050px){.gx-jm-journey{grid-template-columns:repeat(2,1fr)}.gx-jm-journey .gx-jm-step:last-child{grid-column:1/-1}.gx-jm-stats{width:130px}.gx-jm-hero-copy{max-width:220px}}
@media(max-width:720px){.gx-jersey-map{padding:13px;border-radius:24px}.gx-jm-top{align-items:flex-start;flex-direction:column}.gx-jm-top-right{justify-content:flex-start}.gx-jm-globe-wrap{min-height:470px}.gx-jm-globe{width:min(94vw,470px);left:58%;top:52%}.gx-jm-hero-copy{left:15px;top:15px;max-width:185px}.gx-jm-hero-copy h3{font-size:1.2rem}.gx-jm-hero-copy p{font-size:.58rem}.gx-jm-stats{right:12px;top:13px;width:112px;padding:8px}.gx-jm-stat b{font-size:1.05rem}.gx-jm-marker{font-size:.54rem;padding:6px 7px}.gx-jm-marker span{font-size:.9rem}.gx-jm-instruction{font-size:.52rem;bottom:12px}.gx-jm-journey{grid-template-columns:1fr}.gx-jm-journey .gx-jm-step:last-child{grid-column:auto}.gx-jm-step{min-height:150px}.gx-jm-jersey,.gx-jm-jersey img{height:135px}.gx-jm-size-grid{grid-template-columns:repeat(3,1fr)}}
/* info cards */
.quick { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:18px; }
.qcard { background:rgba(10,13,12,.80); border:1px solid rgba(24,232,117,.06); border-radius:20px; padding:22px; cursor:pointer;
  transition:transform .16s ease, border-color .16s ease; backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px); }
html[data-theme="light"] .qcard { background:var(--card); border-color:var(--line); backdrop-filter:none; }
.qcard:hover { transform:translateY(-4px); border-color:var(--ac); }
.qic { width:52px; height:52px; border-radius:14px; display:flex; align-items:center; justify-content:center; font-size:24px;
  background:rgba(24,232,117,.06); margin-bottom:14px; }
html[data-theme="light"] .qic { background:var(--card2); }
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
/* ── Team Atmosphere ── */
.tm-atmos { position:fixed; inset:0; pointer-events:none; z-index:0; overflow:hidden; }
.tm-pitch {
  position:absolute; inset:0; opacity:.03;
  background:
    radial-gradient(circle at 50% 50%, transparent 29.5%, rgba(255,255,255,.5) 30%, rgba(255,255,255,.5) 30.5%, transparent 31%),
    linear-gradient(0deg, transparent 49.5%, rgba(255,255,255,.4) 49.5%, rgba(255,255,255,.4) 50.5%, transparent 50.5%),
    linear-gradient(90deg, transparent 49.5%, rgba(255,255,255,.4) 49.5%, rgba(255,255,255,.4) 50.5%, transparent 50.5%);
}
.tm-particles { position:absolute; inset:0; }
.tm-particles i {
  position:absolute; width:3px; height:3px; border-radius:50%; background:rgba(255,255,255,.15);
  animation:tmFloat 12s ease-in-out infinite;
}
.tm-particles i:nth-child(1){ left:15%; top:20%; animation-delay:0s; }
.tm-particles i:nth-child(2){ left:75%; top:35%; animation-delay:-3s; width:2px; height:2px; }
.tm-particles i:nth-child(3){ left:40%; top:70%; animation-delay:-6s; }
.tm-particles i:nth-child(4){ left:85%; top:60%; animation-delay:-9s; width:2px; height:2px; }
.tm-particles i:nth-child(5){ left:25%; top:85%; animation-delay:-4s; }
@keyframes tmFloat {
  0%,100%{ transform:translateY(0) translateX(0); opacity:.15; }
  25%{ transform:translateY(-15px) translateX(5px); opacity:.25; }
  50%{ transform:translateY(-8px) translateX(-3px); opacity:.1; }
  75%{ transform:translateY(-20px) translateX(8px); opacity:.2; }
}
.tm-ball {
  position:fixed; bottom:15%; right:5%; font-size:28px; opacity:.08;
  animation:tmBallFloat 8s ease-in-out infinite; pointer-events:none; z-index:0;
}
@keyframes tmBallFloat {
  0%,100%{ transform:translateY(0) rotate(0deg); }
  50%{ transform:translateY(-12px) rotate(15deg); }
}
.pg { display:grid; grid-template-columns:1fr 1fr; gap:30px; align-items:start; }
.gal { position:sticky; top:86px; perspective:1200px; }
.gmain {
  position:relative; border:1px solid var(--glass-border); border-radius:var(--hero-radius); overflow:visible;
  cursor:zoom-in; background:linear-gradient(180deg, var(--bg3) 0%, var(--card) 100%);
  box-shadow:var(--scene-shadow); transition:transform .5s cubic-bezier(.22,1,.36,1), box-shadow .5s ease;
  transform-style:preserve-3d;
}
html[data-theme="light"] .gmain { background:linear-gradient(180deg, #F0F4F8 0%, #FFFFFF 100%); border-color:var(--line); box-shadow:var(--sh2); }
/* Stadium glow behind main image */
.gmain::before {
  content:''; position:absolute; top:10%; left:5%; right:5%; bottom:15%;
  border-radius:50%; filter:blur(60px); z-index:0;
  background:radial-gradient(circle, color-mix(in srgb, var(--ac) 12%, transparent), transparent 70%);
  pointer-events:none; opacity:.7;
}
/* Ground shadow */
.gmain::after {
  content:''; position:absolute; bottom:-12px; left:10%; right:10%; height:24px;
  background:radial-gradient(ellipse, rgba(0,0,0,.4) 0%, transparent 70%);
  border-radius:50%; z-index:-1; pointer-events:none;
}
html[data-theme="light"] .gmain::after { background:radial-gradient(ellipse, rgba(15,23,42,.08) 0%, transparent 70%); }
.gmain:hover {
  transform:translateY(-4px);
  box-shadow:var(--sh2), 0 0 50px color-mix(in srgb, var(--ac) 10%, transparent);
}
.gmain img { width:100%; height:500px; object-fit:cover; position:relative; z-index:1;
  transition:transform .5s cubic-bezier(.22,1,.36,1);
  filter:drop-shadow(0 16px 32px rgba(0,0,0,.3));
  max-width:100%; display:block;
}
.gmain:hover img { transform:scale(1.03) translateZ(10px); }
/* Light reflection overlay */
.gmain .gmain-ref {
  position:absolute; top:0; left:0; right:0; height:50%;
  background:linear-gradient(180deg, rgba(255,255,255,.025) 0%, transparent 100%);
  border-radius:var(--hero-radius) var(--hero-radius) 0 0; z-index:2; pointer-events:none;
}
html[data-theme="light"] .gmain .gmain-ref { background:linear-gradient(180deg, rgba(255,255,255,.35) 0%, transparent 100%); }
.gar { position:absolute; top:50%; transform:translateY(-50%); width:42px; height:42px; border-radius:50%;
  background:rgba(5,6,7,.6); color:#fff; border:none; font-size:18px; z-index:2; transition:background .2s ease; }
.gar:hover { background:var(--ac); }
.gar.r { inset-inline-end:12px; } .gar.l { inset-inline-start:12px; }
.gthumb { display:flex; gap:10px; margin-top:12px; overflow-x:auto; -webkit-overflow-scrolling:touch; scrollbar-width:thin; padding-bottom:2px; }
.gthumb img { width:72px; height:72px; min-width:72px; object-fit:cover; border-radius:12px; border:2px solid var(--line); cursor:pointer; opacity:.75; }
.gthumb img.on { border-color:var(--ac); opacity:1; }
.gcount { position:absolute; bottom:10px; inset-inline-start:10px; background:rgba(5,6,7,.75); color:#fff; font-size:.72rem;
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
.mback { position:fixed; inset:0; background:rgba(5,6,7,.7); backdrop-filter:blur(6px); z-index:400;
  display:none; align-items:center; justify-content:center; padding:18px; }
html[data-theme="light"] .mback { background:rgba(15,23,42,.6); backdrop-filter:blur(4px); }
.mback.open { display:flex; }
.mbox { background:rgba(5,6,7,.95); border:1px solid rgba(24,232,117,.08); border-radius:22px; width:100%; max-width:560px;
  max-height:88vh; display:flex; flex-direction:column; animation:pop .18s ease; box-shadow:0 24px 60px rgba(0,0,0,.55);
  backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px); }
html[data-theme="light"] .mbox { background:var(--card); border-color:var(--line); backdrop-filter:none; box-shadow:var(--sh2); }
.mbox.wide { max-width:720px; }
@keyframes pop { from { transform:scale(.96); opacity:0; } to { transform:scale(1); opacity:1; } }
.mhead { display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid var(--glass-border); }
html[data-theme="light"] .mhead { border-bottom-color:var(--line); }
.mhead h3 { font-size:1.05rem; font-weight:900; }
.mx { width:32px; height:32px; border-radius:50%; background:rgba(24,232,117,.1); border:1px solid var(--glass-border); color:var(--txt); }
html[data-theme="light"] .mx { background:var(--card2); border-color:var(--line); }
.mbody { padding:20px; overflow-y:auto; }
.mnote { color:var(--mut); font-size:.88rem; line-height:1.8; margin-bottom:12px; }
.mwarning { background:rgba(216,180,90,.08); border:1px solid rgba(216,180,90,.25); color:var(--warm); border-radius:14px; padding:12px 15px;
  font-size:.84rem; line-height:1.8; margin-top:14px; }
html[data-theme="light"] .mwarning { background:#FFF7ED; border-color:#FDBA74; color:#C2410C; }
.mtip { background:rgba(24,232,117,.08); border:1px solid rgba(24,232,117,.25); color:var(--ac); border-radius:14px;
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
.fld input, .fld select, .fld textarea { width:100%; background:rgba(11,23,18,.6); border:1px solid var(--glass-border); border-radius:12px;
  padding:12px 14px; color:var(--txt); font-family:inherit; font-size:.92rem; }
html[data-theme="light"] .fld input, html[data-theme="light"] .fld select, html[data-theme="light"] .fld textarea { background:var(--card2); border-color:var(--line); }
.fld textarea { min-height:70px; resize:vertical; }
.frow { display:flex; gap:10px; }
.frow .fld { flex:1; }
.radios { display:flex; gap:8px; flex-wrap:wrap; }
.radio { background:rgba(11,23,18,.5); border:1.5px solid var(--glass-border); border-radius:999px; padding:8px 14px; font-size:.82rem;
  font-weight:700; color:var(--mut); cursor:pointer; }
html[data-theme="light"] .radio { background:var(--card); border-color:var(--line); }
.radio.on { background:var(--ac); border-color:transparent; color:var(--bg); }
/* cart */
.co { position:fixed; inset:0; background:rgba(5,10,7,.6); backdrop-filter:blur(4px); z-index:350; display:none; }
html[data-theme="light"] .co { background:rgba(15,23,42,.5); backdrop-filter:none; }
.co.open { display:block; }
.cd { position:fixed; top:0; bottom:0; inset-inline-end:0; width:400px; max-width:94vw; background:rgba(5,6,7,.96); z-index:351;
  display:none; flex-direction:column; box-shadow:-12px 0 40px rgba(0,0,0,.45); backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
  border-left:1px solid rgba(24,232,117,.08); }
html[data-theme="light"] .cd { background:var(--card); border-left-color:var(--line); box-shadow:-12px 0 40px rgba(0,0,0,.18); backdrop-filter:none; }
.cd.open { display:flex; }
.cd-head { display:flex; align-items:center; justify-content:space-between; padding:14px 18px; border-bottom:1px solid var(--glass-border); }
html[data-theme="light"] .cd-head { border-bottom-color:var(--line); }
.cd-head b { font-size:1.05rem; }
.cd-body { flex:1; overflow-y:auto; padding:12px 18px; }
.cd-empty { text-align:center; color:var(--mut); padding:40px 10px; font-size:.9rem; }
.ci { display:flex; align-items:center; gap:12px; padding:12px 0; border-bottom:1px dashed var(--glass-border); }
html[data-theme="light"] .ci { border-bottom-color:var(--line); }
.ci-emoji { font-size:1.6rem; }
.ci-tx { flex:1; min-width:0; }
.ci-tx b { display:block; font-size:.88rem; }
.ci-tx span { font-size:.8rem; color:var(--mut); }
.qty2 { display:flex; align-items:center; gap:8px; }
.qty2 button { width:26px; height:26px; border-radius:50%; border:1px solid rgba(24,232,117,.06); background:rgba(11,23,18,.5); color:var(--txt); font-size:.95rem; font-weight:800; }
html[data-theme="light"] .qty2 button { border-color:var(--line); background:var(--card); }
.qty2 .qn { min-width:18px; text-align:center; font-weight:800; }
.cd-foot { padding:14px 18px; border-top:1px solid rgba(24,232,117,.06); background:rgba(11,23,18,.8); backdrop-filter:blur(10px); }
html[data-theme="light"] .cd-foot { border-top-color:var(--line); background:var(--card2); backdrop-filter:none; }
.row-t { display:flex; justify-content:space-between; font-size:.88rem; margin-bottom:8px; color:var(--mut); }
.row-t b { color:var(--txt); }
.row-t.total { font-size:1.05rem; font-weight:900; color:var(--txt); margin-top:6px; }
.pts-row { background:rgba(24,232,117,.08); border:1px dashed rgba(24,232,117,.3); border-radius:10px; padding:8px 12px;
  font-size:.8rem; margin-bottom:10px; color:var(--ac); }
html[data-theme="light"] .pts-row { background:rgba(201,162,75,.1); border-color:rgba(201,162,75,.5); color:var(--gold); }
.pts-row select { background:rgba(11,23,18,.5); border:1px solid var(--glass-border); border-radius:8px; color:var(--txt); padding:4px 6px; font-size:.78rem; margin-top:6px; }
html[data-theme="light"] .pts-row select { background:var(--card); border-color:var(--line); }
/* fab - WhatsApp floating button */
.fab { position:fixed; bottom:80px; inset-inline-end:16px; z-index:300; width:54px; height:54px; border-radius:50%;
  background:#25D366; border:none; font-size:22px; box-shadow:0 8px 28px rgba(37,211,102,.4); display:flex;
  align-items:center; justify-content:center; transition:transform .2s ease; text-decoration:none;
  animation:waPulse 3s ease-in-out infinite; }
.fab:hover { transform:scale(1.08); box-shadow:0 12px 36px rgba(37,211,102,.5); }
@keyframes waPulse { 0%,100%{box-shadow:0 8px 28px rgba(37,211,102,.4)} 50%{box-shadow:0 8px 28px rgba(37,211,102,.4),0 0 0 8px rgba(37,211,102,.12)} }
@media (min-width:769px) { .fab { bottom:24px; width:58px; height:58px; font-size:26px; } }
/* matchday */
.md-banner { background:linear-gradient(120deg,var(--ac) 0%, var(--ac2) 100%); color:var(--bg); border-radius:22px; padding:26px 28px;
  margin-bottom:26px; display:flex; align-items:center; gap:20px; flex-wrap:wrap; justify-content:space-between; }
.md-teams { display:flex; align-items:center; gap:16px; font-weight:900; font-size:1.2rem; }
.md-teams .md-vs { color:rgba(5,6,7,.7); font-size:.9rem; }
.md-count { font-size:1.1rem; font-weight:900; letter-spacing:2px; font-variant-numeric:tabular-nums; }
.md-bar { background:var(--ac); color:var(--bg); text-align:center; padding:7px 12px; font-size:.82rem; font-weight:800;
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
.poll { background:var(--glass); border:1px solid var(--glass-border); border-radius:20px; padding:24px;
  backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); }
html[data-theme="light"] .poll { background:var(--card); border-color:var(--line); backdrop-filter:none; }
.poll-opt { display:flex; align-items:center; gap:12px; background:rgba(11,23,18,.5); border:1.5px solid rgba(24,232,117,.06);
  border-radius:14px; padding:13px 16px; margin-bottom:10px; cursor:pointer; position:relative; overflow:hidden; }
html[data-theme="light"] .poll-opt { background:var(--card2); border-color:var(--line); }
.poll-opt:hover { border-color:var(--ac); }
.poll-opt .pf { width:40px; height:40px; border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:1.1rem; }
.poll-opt .pt { flex:1; font-weight:800; font-size:.92rem; }
.poll-opt .pv { font-weight:800; font-size:.8rem; color:var(--mut); }
.poll-opt .pbar { position:absolute; inset-block:0; inset-inline-start:0; width:0; background:color-mix(in srgb, var(--ac) 18%, transparent); transition:width .5s ease; z-index:0; }
.poll-opt > * { position:relative; z-index:1; }
.poll-win { text-align:center; padding:20px; }
.poll-win .big { font-size:2rem; font-weight:900; }
/* lightbox */
.lb { position:fixed; inset:0; background:rgba(5,6,7,.94); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
  z-index:500; display:none; align-items:center; justify-content:center; overflow:hidden; touch-action:none; }
.lb.open { display:flex; }
.lb-stage { position:relative; width:100%; height:100%; display:flex; align-items:center; justify-content:center; overflow:hidden; }
.lb img { max-width:92vw; max-height:80vh; border-radius:10px; user-select:none; -webkit-user-select:none;
  touch-action:none; transition:transform .15s ease; cursor:grab; will-change:transform; }
.lb img.dragging { transition:none; cursor:grabbing; }
.lb-btn { background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.14); color:#fff; width:42px; height:42px;
  border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:1.1rem; cursor:pointer;
  backdrop-filter:blur(10px); transition:background .2s ease, border-color .2s ease, transform .2s ease; }
.lb-btn:hover { background:rgba(24,232,117,.18); border-color:rgba(24,232,117,.45); transform:translateY(-1px); }
.lb-close { position:absolute; top:16px; inset-inline-end:16px; z-index:3; }
.lb-nav { position:absolute; top:50%; transform:translateY(-50%); z-index:3; }
.lb-prev { inset-inline-start:16px; }
.lb-next { inset-inline-end:16px; }
.lb-zoombar { position:absolute; bottom:20px; left:50%; transform:translateX(-50%); z-index:3; display:flex;
  align-items:center; gap:6px; background:rgba(5,6,7,.7); border:1px solid rgba(255,255,255,.1); border-radius:999px;
  padding:6px 8px; backdrop-filter:blur(10px); }
.lb-zoombar .lb-btn { width:34px; height:34px; font-size:.95rem; }
.lb-zoompct { color:#F5F7F5; font-size:.8rem; font-weight:800; min-width:46px; text-align:center; }
.lb-count { position:absolute; top:18px; inset-inline-start:18px; z-index:3; color:#F5F7F5; font-size:.78rem;
  font-weight:800; background:rgba(5,6,7,.6); border:1px solid rgba(255,255,255,.1); border-radius:999px; padding:5px 12px; }
@media (max-width:640px) {
  .lb-btn { width:36px; height:36px; font-size:1rem; }
  .lb-nav { top:auto; bottom:76px; transform:none; }
  .lb-prev { inset-inline-start:12px; } .lb-next { inset-inline-end:12px; }
  .lb-close { top:12px; inset-inline-end:12px; }
  .lb-zoombar { bottom:14px; }
  .lb img { max-height:70vh; }
}
/* welcome */
.welc { min-height:100vh; min-height:100dvh; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center;
  padding:30px 20px; position:relative; overflow:hidden; background:var(--bg);
  background-image:
    radial-gradient(ellipse 120% 60% at 50% -10%, rgba(24,232,117,.10), transparent 50%),
    radial-gradient(ellipse 60% 40% at 80% 90%, rgba(216,180,90,.03), transparent 40%),
    linear-gradient(180deg, var(--bg2) 0%, #0A0D0C 100%); }
.welc .ball { font-size:72px; filter:drop-shadow(0 12px 28px rgba(24,232,117,.35)); }
.welc h1 { font-size:2rem; font-weight:900; margin-top:16px; line-height:1.5; color:#F5F7F6; }
.welc p { color:#A0ADA8; margin-top:12px; font-size:1rem; line-height:1.9; }
.wlang { display:flex; gap:14px; justify-content:center; margin-top:28px; flex-wrap:wrap; }
.wlang a { padding:14px 32px; border-radius:16px; font-weight:900; font-size:1rem; border:1.5px solid rgba(24,232,117,.15);
  background:rgba(5,6,7,.65); color:#F5F7F6; backdrop-filter:blur(8px); }
.wlang a:hover { border-color:var(--ac); transform:translateY(-2px); }
.wlang a:first-child { background:var(--gradient-brand); border-color:transparent; color:#fff; }
.brand { margin-top:24px; color:#6B7A73; font-size:.8rem; font-weight:800; letter-spacing:2px; }
/* ticket & track */
.ticket { max-width:640px; margin:0 auto; }
.tk { background:var(--glass); border:1.5px solid var(--glass-border); border-radius:24px; overflow:hidden; box-shadow:0 18px 44px rgba(0,0,0,.4);
  backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px); }
html[data-theme="light"] .tk { background:var(--card); border-color:var(--line); box-shadow:var(--sh2); backdrop-filter:none; }
.tk-top { padding:20px 24px; display:flex; align-items:center; justify-content:space-between; gap:10px; }
.tk-top .tlogo { font-weight:900; font-size:1.2rem; }
.tk-stub { position:relative; border-top:2px dashed var(--glass-border); border-bottom:2px dashed var(--glass-border); padding:18px 24px; }
html[data-theme="light"] .tk-stub { border-top-color:var(--line); border-bottom-color:var(--line); }
.tk-stub:before, .tk-stub:after { content:''; position:absolute; width:22px; height:22px; border-radius:50%; background:var(--stadium-dark); top:50%; }
html[data-theme="light"] .tk-stub:before, html[data-theme="light"] .tk-stub:after { background:var(--bg-primary); }
.tk-stub:before { inset-inline-start:-12px; transform:translateY(-50%); }
.tk-stub:after { inset-inline-end:-12px; transform:translateY(-50%); }
.tk-code { font-size:1.7rem; font-weight:900; text-align:center; color:var(--ac); }
.tk-row { display:flex; justify-content:space-between; gap:10px; font-size:.85rem; margin-top:6px; color:var(--mut); }
.tk-row b { color:var(--txt); }
.tk-items { padding:16px 24px; }
.tk-item { display:flex; justify-content:space-between; gap:10px; font-size:.88rem; padding:6px 0; border-bottom:1px dashed var(--glass-border); }
html[data-theme="light"] .tk-item { border-bottom-color:var(--line); }
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
.set-row { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px 0; border-bottom:1px solid var(--glass-border); }
html[data-theme="light"] .set-row { border-bottom-color:var(--line); }
.set-row .st { font-weight:800; font-size:.92rem; }
.set-row .st small { display:block; color:var(--mut); font-weight:600; font-size:.76rem; }
.seg { display:flex; gap:6px; flex-wrap:wrap; }
.seg button { background:rgba(11,23,18,.5); border:1.5px solid rgba(24,232,117,.06); border-radius:999px; padding:8px 14px; font-size:.8rem;
  font-weight:800; color:var(--mut); }
html[data-theme="light"] .seg button { background:var(--card); border-color:var(--line); }
.seg button.on { background:var(--ac); border-color:transparent; color:var(--bg); }
/* admin */
.adm { max-width:1080px; margin:0 auto; padding:24px 18px 60px; }
.adm-card { background:var(--glass); border:1px solid var(--glass-border); border-radius:18px; padding:18px; margin-bottom:16px;
  backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); }
html[data-theme="light"] .adm-card { background:var(--card); border-color:var(--line); backdrop-filter:none; }
.adm-card h3 { font-size:1.05rem; font-weight:900; margin-bottom:12px; }
.adm table { width:100%; border-collapse:collapse; font-size:.85rem; }
.adm th { text-align:start; padding:8px; color:var(--mut); border-bottom:1px solid var(--glass-border); }
html[data-theme="light"] .adm th { border-bottom-color:var(--line); }
.adm td { padding:8px; border-bottom:1px dashed var(--glass-border); }
html[data-theme="light"] .adm td { border-bottom-color:var(--line); }
.adm input, .adm select { background:rgba(11,23,18,.6); border:1px solid rgba(24,232,117,.06); border-radius:8px; color:var(--txt);
  padding:7px 10px; font-size:.85rem; font-family:inherit; }
html[data-theme="light"] .adm input, html[data-theme="light"] .adm select { background:var(--card2); border-color:var(--line); }
.adm .mini { width:70px; }
.stat-cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-bottom:18px; }
.stat { background:var(--glass); border:1px solid var(--glass-border); border-radius:16px; padding:16px;
  backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); }
html[data-theme="light"] .stat { background:var(--card); border-color:var(--line); backdrop-filter:none; }
.stat b { font-size:1.5rem; display:block; color:var(--ac); }
.stat span { color:var(--mut); font-size:.8rem; }
.msg { background:rgba(24,232,117,.1); border:1px solid rgba(24,232,117,.3); color:var(--ac); border-radius:12px; padding:10px 14px; margin-bottom:14px; font-size:.88rem; }
/* toast */
.toast { position:fixed; bottom:80px; inset-inline-start:50%; transform:translateX(-50%) translateY(80px); background:var(--ac);
  color:var(--bg); padding:12px 20px; border-radius:12px; font-weight:800; font-size:.9rem; z-index:600; opacity:0;
  transition:transform .25s ease, opacity .25s ease; max-width:90vw; text-align:center;
  box-shadow:0 8px 28px rgba(24,232,117,.35); }
.toast.show { transform:translateX(-50%) translateY(0); opacity:1; }
@media (min-width:769px) { .toast { bottom:24px; } }
.img-search-tip { color:var(--mut); font-size:.78rem; margin-top:8px; }
.res-card { display:flex; align-items:center; gap:12px; background:var(--glass); border:1px solid var(--glass-border);
  border-radius:14px; padding:10px 14px; margin-bottom:10px; backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); }
html[data-theme="light"] .res-card { background:var(--card); border-color:var(--line); backdrop-filter:none; }
.res-card img { width:64px; height:64px; object-fit:cover; border-radius:10px; }
.res-card .rc-t { flex:1; }
.res-card .rc-t b { display:block; font-size:.92rem; }
.res-card .rc-t span { font-size:.8rem; color:var(--mut); }
.res-card .rc-p { font-weight:900; color:var(--ac); }
.res-card .rc-s { font-size:.72rem; color:var(--ok); font-weight:800; }
@media (max-width:900px) {
  .pg { grid-template-columns:1fr; }
  .gal { position:static; }
  .gmain img { height:340px; max-height:50vh; object-fit:contain; }
  .hero h1 { font-size:1.8rem; }
  .nav { order:3; width:100%; justify-content:center; }
  .gmain { overflow:hidden; }
}
/* success page */
.okpage { max-width:620px; margin:0 auto; }
.ok-card { background:var(--glass); border:1px solid var(--glass-border); border-radius:24px; padding:44px 24px; text-align:center;
  box-shadow:0 18px 44px rgba(0,0,0,.4); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); }
html[data-theme="light"] .ok-card { background:var(--card); border-color:var(--line); box-shadow:var(--sh2); backdrop-filter:none; }
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
  background:linear-gradient(180deg,#10251A,#166534 55%,#15803d); box-shadow:var(--sh); user-select:none; }
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
.os-card { background:rgba(10,13,12,.80); border:1px solid rgba(24,232,117,.06); border-radius:20px; padding:22px 16px; margin-bottom:20px;
  backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); }
html[data-theme="light"] .os-card { background:var(--card); border-color:var(--line); backdrop-filter:none; }
.os-title { text-align:center; font-weight:900; font-size:1.05rem; letter-spacing:1px; }
.os-path { display:flex; align-items:center; justify-content:space-between; margin-top:28px; position:relative; }
.os-station { display:flex; flex-direction:column; align-items:center; gap:6px; font-size:.7rem; font-weight:800; color:var(--mut); text-align:center; width:76px; z-index:2; }
.os-station .ic { width:46px; height:46px; border-radius:50%; background:rgba(11,23,18,.5); border:2px solid rgba(24,232,117,.06); display:flex; align-items:center; justify-content:center; font-size:1.3rem; }
html[data-theme="light"] .os-station .ic { background:var(--card2); border-color:var(--line); }
.os-station.on .ic { background:linear-gradient(90deg,var(--ac),var(--ac2)); border-color:transparent; box-shadow:0 6px 16px rgba(24,232,117,.35); }
.os-station.on { color:var(--txt); }
.os-seg { flex:1; height:6px; background:rgba(24,232,117,.12); border-radius:99px; position:relative; margin:0 4px; }
html[data-theme="light"] .os-seg { background:var(--line); }
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
.acc-n { position:relative; display:flex; gap:12px; align-items:flex-start; background:var(--card); border:1px solid var(--line); border-radius:14px; padding:12px 16px; margin-bottom:10px; }
.acc-ndot { flex:0 0 8px; width:8px; height:8px; border-radius:50%; background:var(--ac); margin-top:8px; }
.acc-ndt { font-size:.72rem; color:var(--mut); white-space:nowrap; margin-inline-start:auto; }
.acc-box { max-width:740px; margin:0 auto; }
.acc-card { background:var(--card); border:1px solid var(--line); border-radius:18px; padding:16px; margin-bottom:12px; }
.acc-ord { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
.acc-ord .ao { flex:1; min-width:200px; }
.acc-ord .ao b { display:block; }
.acc-ord .ao span { font-size:.78rem; color:var(--mut); }
.acc-hero { background:linear-gradient(120deg,var(--ac),var(--ac2)); color:#fff; border-radius:22px; padding:22px; margin-bottom:18px; position:relative; overflow:hidden; }
.acc-hero h2 { font-size:1.5rem; font-weight:900; }
.acc-hero p { opacity:.92; font-size:.85rem; margin-top:6px; }
.acc-ordhead { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:12px; }
.acc-ordhead .ao b { font-size:1rem; }
.acc-ordhead .ao span { font-size:.78rem; color:var(--mut); }
.acc-oit { display:flex; align-items:center; gap:12px; padding:8px 0; border-bottom:1px dashed var(--line); }
.acc-oit:last-of-type { border-bottom:none; }
.acc-oit img { width:52px; height:52px; border-radius:12px; object-fit:cover; flex:none; border:1px solid var(--line); }
.acc-oem { width:52px; height:52px; border-radius:12px; background:var(--card2); display:flex; align-items:center; justify-content:center; font-size:1.4rem; flex:none; }
.acc-oit .aoit { flex:1; min-width:0; }
.acc-oit .aoit b { font-size:.9rem; }
.acc-oit .aoit span { font-size:.76rem; color:var(--mut); }
.acc-tlbtn { width:100%; justify-content:center; margin-top:10px; }
.acc-badge { background:var(--ac); color:#fff; border-radius:999px; font-size:.68rem; font-weight:900; padding:2px 8px; margin-inline-start:6px; vertical-align:middle; }
.ro-out b { color:var(--err); }
.ro-out span { color:var(--err); font-weight:800; }
/* passport */
.pp-card { background:linear-gradient(135deg,var(--card2),var(--bg2)); color:#fff; border-radius:20px; padding:22px; position:relative; overflow:hidden; }
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
.phone-row .cc-sel { flex:0 0 112px; border:1.5px solid var(--line); border-radius:12px; padding:0 10px; font-size:.9rem; font-weight:800; background:var(--card2); color:var(--txt); font-family:inherit; color-scheme:dark; }
html[data-theme="light"] .phone-row .cc-sel { color-scheme:light; }
.phone-row .cc-sel option { background:#0B1712; color:#F4F7F5; }
html[data-theme="light"] .phone-row .cc-sel option { background:#fff; color:#0F172A; }
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
@keyframes pulse { 0%,100%{box-shadow:0 0 0 0 rgba(24,232,117,.4)} 50%{box-shadow:0 0 0 8px rgba(24,232,117,0)} }
@media (max-width:560px) {
  .grid { grid-template-columns:repeat(2,1fr); gap:10px; }
  .pcard-inner { transform:none!important; }
  .pcard-glow { display:none; }
  .pimg { height:150px; background:var(--bg3); }
  .pimg img { width:90%; height:90%; object-fit:contain; filter:drop-shadow(0 6px 12px rgba(0,0,0,.25)); }
  .hero { padding:20px 14px; border-radius:16px; margin-bottom:14px; }
  .links3 { grid-template-columns:1fr; }
  .gmain { perspective:none; transform:none!important; }
  .gmain img { height:auto; max-height:280px; filter:drop-shadow(0 8px 16px rgba(0,0,0,.2)); background:var(--bg3); }
  .gmain::before { filter:blur(30px); opacity:.4; }
  .gmain::after { height:12px; bottom:-6px; }
  .pg { grid-template-columns:1fr; gap:14px; }
  .gal { position:static; perspective:none; }
  .tm-ball { display:none; }
  .tm-particles i { animation-duration:16s; }
  .tm-label { font-size:.6rem; padding:3px 10px; }
  .tk-btns { grid-template-columns:1fr; }
  #filtersBar { position:fixed; left:0; right:0; bottom:0; z-index:80; flex-direction:column; align-items:stretch;
    background:var(--card,#fff); border-top:1.5px solid var(--line,#e5e7eb); padding:18px 16px calc(18px + env(safe-area-inset-bottom));
    border-radius:20px 20px 0 0; box-shadow:0 -14px 40px rgba(2,6,23,.18);
    transform:translateY(110%); transition:transform .28s ease; }
  #filtersBar.open { transform:translateY(0); }
  .pinfo h1 { font-size:1.1rem; }
  .orderbtn { margin-top:16px; }
  .frow { flex-direction:column; gap:0; }
}
/* ============================== FOOTBALL STADIUM ATMOSPHERE ============================== */
body { overflow-x:hidden; }
.wrap { position:relative; z-index:1; }
.stadium-bg { position:fixed; inset:0; z-index:0; overflow:hidden; pointer-events:none; }
.stadium-bg .atm-lines { position:absolute; inset:0; opacity:.3;
  background:
    repeating-linear-gradient(0deg, transparent 0 68px, rgba(24,232,117,.02) 68px 69px),
    repeating-linear-gradient(90deg, transparent 0 68px, rgba(24,232,117,.02) 68px 69px); }
html[data-theme="light"] .stadium-bg .atm-lines { opacity:.55;
  background: repeating-linear-gradient(0deg, transparent 0 68px, rgba(15,23,42,.03) 68px 69px),
    repeating-linear-gradient(90deg, transparent 0 68px, rgba(15,23,42,.03) 68px 69px); }
.stadium-bg .atm-circle { position:absolute; left:50%; top:56%; width:560px; height:560px; margin:-280px 0 0 -280px;
  border:3px dashed rgba(24,232,117,.06); border-radius:50%; }
.stadium-bg .atm-glow { position:absolute; border-radius:50%; filter:blur(80px); animation:atmGlow 16s ease-in-out infinite; }
.stadium-bg .atm-glow.g1 { width:430px; height:430px; left:-130px; top:-130px;
  background:radial-gradient(circle, rgba(24,232,117,.14), transparent 70%); }
.stadium-bg .atm-glow.g2 { width:390px; height:390px; right:-110px; top:26%;
  background:radial-gradient(circle, rgba(216,180,90,.08), transparent 70%); animation-delay:-5s; }
.stadium-bg .atm-glow.g3 { width:480px; height:480px; left:32%; bottom:-230px;
  background:radial-gradient(circle, rgba(24,232,117,.07), transparent 70%); animation-delay:-9s; }
html[data-theme="light"] .stadium-bg .atm-glow.g1 { background:radial-gradient(circle, var(--glow2, rgba(225,29,72,.16)), transparent 70%); }
html[data-theme="light"] .stadium-bg .atm-glow.g2 { background:radial-gradient(circle, var(--glow3, rgba(56,130,246,.13)), transparent 70%); }
html[data-theme="light"] .stadium-bg .atm-glow.g3 { background:radial-gradient(circle, rgba(37,211,102,.09), transparent 70%); }
@keyframes atmGlow { 0%,100% { transform:translate(0,0) scale(1); } 50% { transform:translate(46px,-34px) scale(1.1); } }
.stadium-bg .atm-ball { position:absolute; opacity:.1; filter:blur(.4px); animation:atmFloat linear infinite; }
@keyframes atmFloat {
  0% { transform:translate(0,0) rotate(0deg); }
  25% { transform:translate(28px,-42px) rotate(16deg); }
  50% { transform:translate(-18px,-84px) rotate(30deg); }
  75% { transform:translate(-34px,-42px) rotate(16deg); }
  100% { transform:translate(0,0) rotate(0deg); }
}
.stadium-bg .atm-dot { position:absolute; width:4px; height:4px; border-radius:50%; background:var(--ac);
  opacity:.12; animation:atmDot linear infinite; }
@keyframes atmDot { 0% { transform:translateY(0) scale(1); opacity:.1; } 50% { transform:translateY(-76px) scale(1.5); opacity:.25; } 100% { transform:translateY(0) scale(1); opacity:.1; } }
.stadium-bg .atm-light { position:absolute; width:2px; background:linear-gradient(to bottom, transparent, rgba(24,232,117,.4));
  filter:blur(1px); transform-origin:top center; opacity:.35; animation:atmLight 7s ease-in-out infinite; }
@keyframes atmLight { 0%,100% { opacity:.25; transform:rotate(-3deg) scaleY(1); } 50% { opacity:.5; transform:rotate(3deg) scaleY(1.12); } }
html[data-theme="light"] .stadium-bg .atm-light { background:linear-gradient(to bottom, transparent, rgba(148,163,184,.7)); }
.stadium-bg .atm-pitch { position:absolute; left:-4%; right:-4%; bottom:-3%; height:26%;
  background:
    repeating-linear-gradient(90deg, transparent 0 96px, rgba(24,232,117,.03) 96px 98px);
  border-radius:50% 50% 0 0/ 26% 26% 0 0; opacity:.4; }
html[data-theme="light"] .stadium-bg .atm-pitch { background:repeating-linear-gradient(90deg, transparent 0 96px, rgba(15,23,42,.045) 96px 98px); opacity:.6; }
html[data-club] .stadium-bg .atm-dot { background:var(--ac); }
html[data-club] .stadium-bg .atm-circle { border-color:color-mix(in srgb, var(--ac) 22%, transparent); }
html[data-club] .stadium-bg .atm-glow.g1 { background:radial-gradient(circle, var(--glow, rgba(24,232,117,.2)), transparent 70%); }
html[data-club] .stadium-bg .atm-glow.g2 { background:radial-gradient(circle, color-mix(in srgb, var(--ac2) 26%, transparent), transparent 70%); }
@media (prefers-reduced-motion: reduce) {
  .stadium-bg .atm-ball, .stadium-bg .atm-dot, .stadium-bg .atm-glow, .stadium-bg .atm-circle, .stadium-bg .atm-lines { animation:none !important; }
  .pcard-inner, .gmain, .gmain img { transform:none!important; transition:none!important; }
  .pg .gmain, .pg .pinfo { animation:none!important; opacity:1!important; }
  *, *::before, *::after { transition-duration:.01ms !important; animation-duration:.01ms !important; animation-iteration-count:1 !important; }
}
/* ============================== STICKY GLASS NAVBAR ============================== */
.hd { transition:background .3s ease, box-shadow .3s ease, border-color .3s ease; }
.hd.scrolled { background:rgba(5,6,7,.92); backdrop-filter:blur(20px) saturate(1.6);
  -webkit-backdrop-filter:blur(20px) saturate(1.6); box-shadow:0 6px 28px rgba(0,0,0,.4); border-bottom-color:transparent; }
html[data-theme="light"] .hd.scrolled { background:rgba(255,255,255,.92); box-shadow:0 6px 28px rgba(15,23,42,.08); }
/* ============================== HERO ============================== */
.hero { background:
  radial-gradient(130% 110% at 12% 0%, rgba(24,232,117,.15), transparent 58%),
  radial-gradient(110% 100% at 92% 100%, rgba(216,180,90,.06), transparent 60%),
  linear-gradient(120deg, rgba(11,23,18,.75) 0%, rgba(5,6,7,.92) 60%);
  border-color:var(--glass-border); }
html[data-theme="light"] .hero { background:
  radial-gradient(130% 110% at 12% 0%, color-mix(in srgb, var(--ac) 15%, transparent), transparent 58%),
  radial-gradient(110% 100% at 92% 100%, rgba(37,211,102,.07), transparent 60%),
  linear-gradient(120deg, var(--card) 0%, #F8FAFF 60%),
  repeating-linear-gradient(0deg, transparent 0 32px, rgba(15,23,42,.022) 32px 33px); border-color:var(--line); }
.hero-tag { display:inline-flex; align-items:center; gap:9px; background:var(--glass); border:1px solid var(--glass-border);
  color:var(--ac); font-size:.72rem; font-weight:900; letter-spacing:2px; padding:7px 15px; border-radius:999px;
  margin-bottom:18px; box-shadow:var(--sh); backdrop-filter:blur(8px); }
html[data-theme="light"] .hero-tag { background:var(--card); border-color:var(--line); backdrop-filter:none; }
.hero-tag .pulse { width:8px; height:8px; border-radius:50%; background:var(--ok); animation:pulse 2s infinite; }
.hero-brand { font-family:'Poppins','Cairo',sans-serif; font-weight:900; letter-spacing:6px; font-size:2.6rem;
  line-height:1; color:transparent; background:linear-gradient(90deg, var(--ac), var(--ac2) 55%, var(--warm));
  -webkit-background-clip:text; background-clip:text; margin-bottom:6px; opacity:.95;
  filter:drop-shadow(0 6px 24px rgba(24,232,117,.3)); }
.hero-price { display:inline-flex; gap:10px; flex-wrap:wrap; margin-top:16px; }
.hero-price span, .hero-price { font-weight:900; color:var(--ac); }
.hero-price::before { content:'⚡'; }
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
.scroll-row { display:flex; gap:18px; overflow-x:auto; padding-bottom:12px; scroll-snap-type:x proximity; scrollbar-width:thin;
  scrollbar-color:rgba(24,232,117,.2) transparent; }
.scroll-row .pcard { flex:0 0 260px; scroll-snap-align:start; }
.pcard { transition:transform .18s ease, box-shadow .24s ease, border-color .24s ease; }
.pcard:hover { transform:translateY(-6px);
  box-shadow:0 22px 48px rgba(0,0,0,.35);
  border-color:color-mix(in srgb, var(--pc, var(--ac)) 45%, var(--glass-border)); }
.pover { position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
  background:rgba(5,6,7,.4); opacity:0; transition:opacity .22s ease; z-index:2; }
html[data-theme="light"] .pover { background:rgba(2,6,23,.34); }
.pover .pover-btn { background:var(--ac); color:var(--bg); font-weight:900; font-size:.86rem; padding:11px 22px; border-radius:999px;
  box-shadow:0 12px 28px rgba(0,0,0,.32); transform:translateY(8px); transition:transform .22s ease; }
.pcard:hover .pover { opacity:1; }
.pcard:hover .pover .pover-btn { transform:none; }
/* ============================== PRODUCT PAGE ENTRANCE ============================== */
.pg .gmain { animation:prodIn .5s cubic-bezier(.22,1,.36,1) .1s both; }
.pg .pinfo { animation:prodIn .5s cubic-bezier(.22,1,.36,1) .25s both; }
@keyframes prodIn { from { opacity:0; transform:translateY(24px) scale(.97); } to { opacity:1; transform:none; } }
/* ============================== LOYALTY TEST ============================== */
.loyal { background:var(--glass); border:1px solid var(--glass-border);
  border-radius:26px; padding:32px 20px; text-align:center; position:relative; overflow:hidden;
  backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); }
html[data-theme="light"] .loyal { background:linear-gradient(135deg, var(--card), var(--card2)); border-color:var(--line); backdrop-filter:none; }
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
  border-radius:24px; padding:26px 26px; color:var(--bg); box-shadow:0 20px 44px rgba(24,232,117,.25);
  position:relative; overflow:hidden; }
.szsec-banner::after { content:'👕'; position:absolute; font-size:7rem; opacity:.1; inset-inline-end:6%; top:-18px; }
.szsec-banner .big-ic { font-size:46px; }
.szsec-banner h2 { font-size:1.35rem; font-weight:900; }
.szsec-banner p { opacity:.92; font-size:.88rem; margin-top:4px; }
.szsec-banner .btn-light { margin-inline-start:auto; background:var(--bg); color:var(--ac); border:none; }
/* ============================== HOW TO ORDER STEPS ============================== */
.steps-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:16px; }
.step-card { position:relative; background:rgba(10,13,12,.80); border:1px solid rgba(24,232,117,.06); border-radius:20px;
  padding:24px 18px 20px; overflow:hidden; transition:transform .18s ease, box-shadow .22s ease, border-color .22s ease;
  backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); }
html[data-theme="light"] .step-card { background:var(--card); border-color:var(--line); backdrop-filter:none; }
.step-card:hover { transform:translateY(-4px); border-color:color-mix(in srgb, var(--ac) 45%, var(--glass-border)); box-shadow:0 16px 40px rgba(0,0,0,.3); }
.step-card .step-num { position:absolute; top:-16px; inset-inline-end:-6px; font-size:5rem; font-weight:900;
  color:var(--ac); opacity:.06; line-height:1; }
.step-card .step-ic { width:50px; height:50px; border-radius:15px; display:flex; align-items:center; justify-content:center;
  font-size:25px; background:linear-gradient(135deg, var(--ac), var(--ac2)); box-shadow:0 8px 20px rgba(24,232,117,.3); }
.step-card h3 { font-size:1rem; font-weight:900; margin-top:13px; }
.step-card p { color:var(--mut); font-size:.82rem; line-height:1.7; margin-top:6px; }
/* ============================== DARK PITCH CTA ============================== */
.pitch-sec { position:relative; border-radius:28px; overflow:hidden; color:#F5F7F6; padding:60px 24px; text-align:center;
  background:radial-gradient(130% 150% at 50% 0%, var(--card2) 0%, var(--bg2) 55%, #0A0D0C 100%); }
.pitch-sec .pitch-lines { position:absolute; inset:0;
  background:repeating-linear-gradient(0deg, transparent 0 52px, rgba(24,232,117,.06) 52px 53px),
  repeating-linear-gradient(90deg, transparent 0 52px, rgba(24,232,117,.06) 52px 53px); }
.pitch-sec .pitch-mid { position:absolute; left:50%; top:50%; width:400px; height:400px; transform:translate(-50%,-50%);
  border:2px solid rgba(24,232,117,.12); border-radius:50%; }
.pitch-sec .pitch-half { position:absolute; left:50%; top:0; bottom:0; width:400px; transform:translateX(-50%);
  border-left:2px solid rgba(24,232,117,.08); border-right:2px solid rgba(24,232,117,.08); }
.pitch-sec .pitch-ball { position:absolute; bottom:16px; inset-inline-end:24px; font-size:54px; opacity:.25; animation:atmFloat 12s linear infinite; }
.pitch-sec h2 { font-size:1.95rem; font-weight:900; position:relative; z-index:1; line-height:1.35; }
.pitch-sec .btn { position:relative; z-index:1; margin-top:22px; }
html[data-theme="light"] .pitch-sec { background:radial-gradient(130% 150% at 50% 0%, #16340f 0%, #0b2410 55%, #07170d 100%); }
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
.rv { opacity:1; transform:none; }
html.js .rv { opacity:0; transform:translateY(22px); transition:opacity .6s ease, transform .6s ease; }
html.js .rv.in { opacity:1; transform:none; }
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
/* ============================== LUXURY THEME (DARK LUXE SPORTS) ============================== */
:root {
  --bg:#050607; --card:rgba(10,13,12,.85); --card2:rgba(11,23,18,.75); --line:rgba(24,232,117,.08); --txt:#FFFFFF; --mut:#A7B0AC;
  --brand1:#18E875; --brand2:#0B9F50; --green:#18E875; --gold:#D8B45A; --ok:#18E875; --err:#DC2626;
  --ac:#18E875; --ac2:#0B9F50; --dark:#050607;
  --sh:0 8px 32px rgba(0,0,0,.5); --sh2:0 20px 50px rgba(0,0,0,.6);
  --glow:rgba(24,232,117,.30);
}
html[data-theme="dark"] { --bg:#050607; --card:rgba(10,13,12,.85); --card2:rgba(11,23,18,.75); --line:rgba(24,232,117,.08); --txt:#FFFFFF; --mut:#A7B0AC; }
/* header */
.hd { background:#050607; border-bottom:1px solid rgba(24,232,117,.08); box-shadow:0 2px 18px rgba(0,0,0,.3); }
html[data-club] .hd::after { background:linear-gradient(90deg,var(--ac,#18E875),var(--ac2,#0B9F50)); }
.logo { color:#fff; }
.logo .ball { filter:drop-shadow(0 0 6px rgba(24,232,117,.5)); }
.nv { color:#A7B0AC; }
.nv:hover { color:#fff; background:rgba(255,255,255,.08); }
.nv.on { background:linear-gradient(90deg,#18E875,#0B9F50); color:#050607; }
.hbtn { background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.12); color:#E9E9EC; }
.hbtn:hover { border-color:#18E875; color:#fff; }
.hcount { background:#18E875; color:#050607; }
.hd-search { width:100%; display:flex; justify-content:center; margin-top:8px; }
.hd-sbox { max-width:560px; width:100%; background:rgba(255,255,255,.06); border:1.5px solid rgba(255,255,255,.12); }
.hd-sbox input { color:#fff; }
.hd-sbox input::placeholder { color:#6B7A73; }
.hd-sbox button { background:linear-gradient(90deg,#18E875,#0B9F50); color:#050607; border-radius:10px; }
/* buttons */
.btn.pri { background:linear-gradient(90deg,#18E875,#0B9F50); color:#050607; box-shadow:0 12px 30px rgba(24,232,117,.30); transition:box-shadow .3s ease, transform .3s ease; }
.btn.pri:hover { transform:translateY(-2px); box-shadow:0 16px 40px rgba(24,232,117,.40); }
.btn.dark { background:#050607; color:#fff; border:1px solid rgba(255,255,255,.12); box-shadow:0 12px 28px rgba(0,0,0,.3); }
.btn.dark:hover { transform:translateY(-2px); background:#0B1712; }
.btn.ghost { background:rgba(255,255,255,.04); border:1.5px solid rgba(255,255,255,.12); color:#fff; }
.btn.ghost:hover { border-color:#18E875; color:#18E875; }
/* hero: night stadium */
.hero { border:1px solid rgba(24,232,117,.08); border-radius:26px; position:relative; overflow:hidden;
  background:radial-gradient(1100px 520px at 78% -20%, rgba(24,232,117,.12), transparent 60%),
             radial-gradient(900px 500px at 8% 120%, rgba(24,232,117,.06), transparent 55%),
             linear-gradient(120deg,#050607 0%, #0A0D0C 58%, #0B1712 100%);
  color:#F5F5F4; padding:54px 44px; margin-bottom:26px; }
.hero::before { content:''; position:absolute; inset:0; pointer-events:none; opacity:.5;
  background:repeating-linear-gradient(0deg, transparent 0 34px, rgba(255,255,255,.02) 34px 36px),
             radial-gradient(circle at 50% 125%, rgba(24,232,117,.15), transparent 55%);
  animation:luxGlow 12s ease-in-out infinite; }
@keyframes luxGlow { 0%,100% { opacity:.3; } 50% { opacity:.55; } }
.hero h1 { color:#F5F5F4; font-size:2.5rem; position:relative; z-index:1; }
.hero h1 .g { background:linear-gradient(90deg,#18E875,#0B9F50); -webkit-background-clip:text; background-clip:text; color:transparent; }
.hero p { color:#A7B0AC; position:relative; z-index:1; }
.hero-tag { color:#18E875; position:relative; z-index:1; }
.hero .btn.ghost { background:rgba(255,255,255,.06); border-color:rgba(255,255,255,.15); color:#F5F5F4; }
.hero .btn.ghost:hover { border-color:#18E875; color:#18E875; }
.hero-btns { position:relative; z-index:1; }
.hero-ball { opacity:.2; position:absolute; inset-inline-end:6%; top:50%; transform:translateY(-50%); }
/* features strip */
.feat-bar { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; background:rgba(10,13,12,.85); border:1px solid rgba(24,232,117,.08);
  border-radius:20px; padding:20px 18px; margin-bottom:30px; box-shadow:var(--sh); }
.feat { display:flex; align-items:center; gap:12px; }
.feat .fic { width:46px; height:46px; border-radius:14px; background:rgba(24,232,117,.08); color:#18E875; font-size:21px;
  display:flex; align-items:center; justify-content:center; flex:none; }
.feat b { font-size:.92rem; font-weight:800; display:block; }
.feat span { font-size:.78rem; color:var(--mut); }
@media (max-width:720px){ .feat-bar { grid-template-columns:1fr 1fr; gap:14px 10px; } .feat .fic{ width:40px; height:40px; font-size:18px; } }
/* shop layout */
.shop-wrap { display:grid; grid-template-columns:268px 1fr; gap:26px; align-items:start; }
.shop-main { min-width:0; }
@media (max-width:900px){ .shop-wrap { grid-template-columns:1fr; } }
/* filter panel */
.filters-panel { background:rgba(10,13,12,.85); border:1px solid rgba(24,232,117,.08); border-radius:20px; padding:18px 16px; box-shadow:var(--sh); }
.fp-title { font-weight:900; font-size:1.02rem; display:flex; align-items:center; gap:8px;
  padding-bottom:12px; border-bottom:2px solid rgba(24,232,117,.12); margin-bottom:14px; }
.fp-sec { margin-bottom:16px; }
.fp-lbl { font-size:.84rem; font-weight:800; margin-bottom:10px; display:flex; align-items:center; gap:6px; color:var(--txt); }
.fp-colors { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.col-dot { width:26px; height:26px; border-radius:50%; border:2px solid #fff; box-shadow:0 0 0 1.5px var(--line);
  cursor:pointer; transition:transform .15s ease, box-shadow .15s ease; }
.col-dot:hover { transform:scale(1.15); }
.col-dot.on { box-shadow:0 0 0 2.5px #0B0B0C; transform:scale(1.1); }
.col-dot.hide { display:none; }
.col-more { background:none; border:none; color:#18E875; font-weight:800; font-size:.78rem; cursor:pointer; padding:4px 2px; }
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
  background:var(--card2); font-weight:800; font-size:.8rem; cursor:pointer; color:var(--txt); }
.sz-btn:hover { border-color:#18E875; }
.sz-btn.on { background:#050607; border-color:#18E875; color:#18E875; }
details.fp-acc { border-top:1px solid var(--line); padding-top:12px; }
details.fp-acc summary { list-style:none; cursor:pointer; font-size:.84rem; font-weight:800;
  display:flex; justify-content:space-between; align-items:center; }
details.fp-acc summary::-webkit-details-marker { display:none; }
details.fp-acc summary::after { content:'+'; color:#A8852E; font-weight:900; }
details.fp-acc[open] summary::after { content:'−'; }
.fp-colors.show .col-dot.hide { display:inline-flex; }
.btn.dark { background:linear-gradient(90deg,#050607,#0B1712); color:#18E875; border:1.5px solid rgba(24,232,117,.2); }
.btn.dark:hover { transform:translateY(-2px); box-shadow:0 12px 26px rgba(0,0,0,.3); }
.fp-apply { width:100%; justify-content:center; margin-top:8px; font-size:.92rem; }
@media (min-width:561px) { .fbtn { display:none !important; } }
/* sort bar */
.sort-bar { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:16px; }
.sort-bar .sort-lbl { font-size:.9rem; font-weight:800; color:var(--txt); }
select.sort { border:1.5px solid var(--line); border-radius:12px; padding:9px 14px; font-size:.85rem;
  font-weight:800; background:rgba(10,13,12,.85); color:var(--txt); font-family:inherit; }
/* listing page search hero */
.list-search { border:1px solid rgba(24,232,117,.06); border-radius:24px; padding:26px 22px; margin-bottom:22px;
  background:
    radial-gradient(120% 140% at 8% 0%, color-mix(in srgb, var(--ac) 10%, transparent), transparent 55%),
    linear-gradient(120deg, rgba(10,13,12,.85), rgba(11,23,18,.75)); box-shadow:var(--sh); }
.list-search .ls-head { display:flex; align-items:center; gap:14px; margin-bottom:16px; }
.list-search .ls-ic { font-size:2.2rem; filter:drop-shadow(0 8px 14px var(--glow, rgba(225,29,72,.25))); }
.list-search h1 { font-size:1.5rem; font-weight:900; color:var(--txt); }
.list-search p { color:var(--mut); font-size:.9rem; margin-top:4px; }
.list-search .ls-box { display:flex; gap:10px; flex-wrap:wrap; }
.list-search .ls-box input { flex:1; min-width:220px; border:1.5px solid rgba(24,232,117,.08); border-radius:14px;
  padding:13px 16px; font-size:.95rem; background:rgba(11,23,18,.6); color:var(--txt); font-family:inherit; }
html[data-theme="dark"] .list-search .ls-box input { background:var(--card2); }
.list-search .ls-box .btn { font-weight:800; }
@media (max-width:560px) { .list-search { padding:20px 16px; } .list-search .ls-ic { font-size:1.7rem; } }
/* how-to-order timeline */
.hw-timeline { position:relative; display:grid; grid-template-columns:1fr 1fr; gap:18px; margin-bottom:30px; }
.hw-step { position:relative; display:flex; align-items:flex-start; gap:14px; background:rgba(10,13,12,.80);
  border:1px solid rgba(24,232,117,.06); border-radius:20px; padding:18px 16px; box-shadow:var(--sh); }
.hw-step .hw-dot { flex:0 0 auto; width:36px; height:36px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-weight:900; color:#fff;   background:linear-gradient(135deg,var(--ac),var(--ac2));
  box-shadow:0 8px 18px var(--glow, rgba(24,232,117,.25)); font-size:.95rem; }
.hw-step .hw-line { display:none; }
.hw-step .hw-ic { flex:0 0 auto; font-size:1.8rem; line-height:1.4; filter:drop-shadow(0 6px 10px var(--glow, rgba(24,232,117,.2))); }
.hw-step .hw-txt b { display:block; font-size:.95rem; font-weight:900; color:var(--txt); }
.hw-step .hw-txt span { display:block; font-size:.82rem; color:var(--mut); line-height:1.7; margin-top:4px; }
@media (max-width:700px) { .hw-timeline { grid-template-columns:1fr; } }
.hw-prices { background:rgba(10,13,12,.80); border:1px solid rgba(24,232,117,.06); border-radius:24px; padding:24px 20px; margin-bottom:26px; box-shadow:var(--sh); }
.hw-prices h2 { font-size:1.3rem; font-weight:900; color:var(--txt); display:flex; align-items:center; gap:10px; }
.hw-sub { color:var(--mut); font-size:.9rem; margin-top:6px; margin-bottom:16px; }
.hw-price-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; }
.hw-price-card { border:1.5px solid var(--line); border-radius:18px; padding:18px 16px; text-align:center;
  background:linear-gradient(150deg, color-mix(in srgb, var(--hwc,var(--ac)) 12%, transparent), transparent 60%);
  transition:transform .2s ease, box-shadow .25s ease; }
.hw-price-card:hover { transform:translateY(-4px); box-shadow:0 16px 34px color-mix(in srgb, var(--hwc,var(--ac)) 25%, transparent); }
.hw-price-card .hwp-ic { font-size:1.7rem; }
.hw-price-card .hwp-t { font-weight:900; font-size:.92rem; color:var(--txt); margin-top:6px; }
.hw-price-card .hwp-price { font-size:1.5rem; font-weight:900; color:var(--hwc,var(--ac)); margin-top:6px; }
.hw-price-card .hwp-d { font-size:.78rem; color:var(--mut); margin-top:4px; }
.hw-ctas { display:flex; gap:12px; flex-wrap:wrap; justify-content:center; margin-bottom:8px; }
.hw-ctas .btn { font-weight:800; }
/* product card */
.pcard { background:rgba(255,255,255,.045); border:1px solid rgba(255,255,255,.10); border-radius:18px; overflow:hidden;
  box-shadow:0 8px 28px rgba(0,0,0,.3); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); transition:transform .3s ease, box-shadow .3s ease, border-color .3s ease; }
html[data-theme="light"] .pcard { background:#fff; box-shadow:var(--sh); backdrop-filter:none; }
.pcard:hover { transform:translateY(-4px); box-shadow:0 18px 44px rgba(0,0,0,.45), 0 0 30px color-mix(in srgb, var(--ac) 15%, transparent); border-color:color-mix(in srgb, var(--ac) 30%, rgba(255,255,255,.10)); }
.pimg { height:210px; background:rgba(255,255,255,.03); }
html[data-theme="light"] .pimg { background:#FBFBFA; }
.badge.best { background:linear-gradient(90deg, var(--ac), var(--ac2)); color:#050607; }
.badge.new { background:linear-gradient(90deg, var(--warm), #D8B45A); color:#050607; }
.badge.offer { background:linear-gradient(90deg,#1F7A4D,#2E9B63); color:#fff; }
.badge.soldout { background:rgba(100,100,100,.7); }
.heart { background:rgba(5,6,7,.6); backdrop-filter:blur(8px); border:1px solid rgba(255,255,255,.08); box-shadow:0 4px 12px rgba(0,0,0,.3); }
html[data-theme="light"] .heart { background:rgba(255,255,255,.94); border-color:transparent; box-shadow:0 4px 12px rgba(12,12,13,.14); }
.heart.on { color:#E11D48; }
.pbody { padding:13px 14px 14px; }
.pcat { color:var(--ac); }
.pbody h3 { font-size:1rem; }
.pfoot b { font-size:1rem; color:var(--ac); }
.pview { color:var(--mut); }
.pcard:hover .pview { color:var(--ac); }
.sizes-row { display:flex; gap:6px; flex-wrap:wrap; margin-top:9px; }
.sz-pill { min-width:30px; text-align:center; font-size:.68rem; font-weight:800; padding:4px 5px;
  border-radius:7px; border:1px solid rgba(24,232,117,.06); color:var(--mut); background:rgba(11,23,18,.5); }
html[data-theme="light"] .sz-pill { border-color:var(--line); background:#fff; }
.sz-pill.oos { opacity:.35; text-decoration:line-through; }
.pcols { display:flex; gap:6px; margin-top:9px; align-items:center; }
.pdot { width:14px; height:14px; border-radius:50%; border:1px solid rgba(255,255,255,.15); }
html[data-theme="light"] .pdot { border-color:rgba(0,0,0,.14); }
.sel { background:rgba(11,23,18,.5); border:1.5px solid rgba(24,232,117,.06); color:var(--txt); }
html[data-theme="light"] .sel { background:#fff; border-color:var(--line); }
.chip { background:rgba(11,23,18,.5); border:1.5px solid rgba(24,232,117,.06); color:var(--mut); }
html[data-theme="light"] .chip { background:#fff; border-color:var(--line); }
.chip.on { background:var(--ac); border-color:transparent; color:var(--bg); }
.sec-head h2 .bar { background:linear-gradient(180deg, var(--ac), var(--ac2)); }
/* footer */
.ft { background:rgba(5,6,7,.96); border-top:1px solid rgba(24,232,117,.06); color:#A7B0AC;
  backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px); }
html[data-theme="light"] .ft { background:var(--card); border-top-color:var(--line); color:var(--txt); }
.ft-brand { color:#F5F7F6; }
.ft-copy, .ft-col a, .ft-col span.lk, .ft-title, .ft-desc, .ft-links a { color:#AEB8B4; }
html[data-theme="light"] .ft-copy, html[data-theme="light"] .ft-col a, html[data-theme="light"] .ft-col span.lk,
html[data-theme="light"] .ft-title, html[data-theme="light"] .ft-desc, html[data-theme="light"] .ft-links a { color:#5B6782; }
.ft-col a:hover, .ft-col span.lk:hover, .ft-links a:hover { color:var(--ac); }
.ft-social a { background:rgba(24,232,117,.06); border:1px solid rgba(24,232,117,.12); }
html[data-theme="light"] .ft-social a { background:var(--card2); border-color:var(--line); }
.ft-copy { border-top:1px solid rgba(24,232,117,.06); }
html[data-theme="light"] .ft-copy { border-top-color:var(--line); }
/* ============================== MOBILE MENU (HAMBURGER) ============================== */
.hmenu { display:none; }
.nv-close { display:none; }
@media (max-width:900px) {
  .hmenu { display:inline-flex; align-items:center; justify-content:center; font-size:1.05rem; }
  .hd-in { gap:6px; }
  .hd-in .hbtn { padding:6px 9px; font-size:.78rem; }
  .logo { font-size:1.12rem; }
  .nav { display:none; order:4; flex:1 0 100%; flex-direction:column; width:100%; gap:2px;
    justify-content:flex-start; padding:10px 0 2px; }
  .nav.open { display:flex; }
  .nav .nv { width:100%; text-align:start; padding:12px 14px; border-radius:10px;
    white-space:normal; font-size:.9rem; }
  .nv-close { display:inline-flex; align-self:flex-end; margin-bottom:4px;
    background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.18); color:#E9E9EC;
    width:34px; height:34px; align-items:center; justify-content:center; font-size:.85rem;
    border-radius:10px; }
  .hd-search { order:5; }
}
@media (max-width:480px) {
  .hd-in { padding:6px 8px; gap:4px; }
  .hd-in .hbtn { padding:4px 6px; font-size:.7rem; }
  .logo { font-size:1rem; }
  .hd-search { margin-top:4px; }
  .btn.big { padding:11px; font-size:.88rem; }
}
/* ============================== CINEMATIC INTRO ============================== */
.gx-intro { position:fixed; inset:0; z-index:9999; background:var(--bg); display:flex; align-items:center; justify-content:center;
  transition:opacity .6s ease, visibility .6s ease; }
.gx-intro.done { opacity:0; visibility:hidden; pointer-events:none; }
.gx-intro .intro-inner { text-align:center; }
.gx-intro .intro-pitch { position:absolute; inset:0; opacity:0; transition:opacity .8s ease .2s; }
.gx-intro.show .intro-pitch { opacity:1; background:repeating-linear-gradient(90deg, transparent 0 96px, rgba(24,232,117,.03) 96px 98px);
  border-radius:50% 50% 0 0/ 20% 20% 0 0; bottom:0; top:auto; height:40%; }
.gx-intro .intro-light { position:absolute; width:3px; height:0; background:linear-gradient(to bottom, rgba(24,232,117,.6), transparent);
  filter:blur(2px); top:0; opacity:0; transition:height .5s ease, opacity .5s ease; }
.gx-intro.show .intro-light { opacity:1; height:180px; }
.gx-intro .intro-light:nth-child(2) { left:20%; transition-delay:.3s; }
.gx-intro .intro-light:nth-child(3) { left:50%; transition-delay:.5s; }
.gx-intro .intro-light:nth-child(4) { left:80%; transition-delay:.4s; }
.gx-intro .intro-ball { position:relative; font-size:0; z-index:2; opacity:0; transform:scale(.3) translateY(40px);
  transition:opacity .4s ease .6s, transform .5s cubic-bezier(.34,1.56,.64,1) .6s; }
.gx-intro.show .intro-ball { opacity:1; transform:scale(1) translateY(0); font-size:72px; filter:drop-shadow(0 12px 28px rgba(24,232,117,.30)); }
.gx-intro .intro-logo { position:relative; z-index:2; font-size:1.8rem; font-weight:900; letter-spacing:8px;
  color:transparent; background:linear-gradient(90deg, #0B9F50, #18E875 55%, #4DFFA8);
  -webkit-background-clip:text; background-clip:text; margin-top:16px; opacity:0; transform:translateY(10px);
  transition:opacity .4s ease .9s, transform .4s ease .9s; }
.gx-intro.show .intro-logo { opacity:1; transform:none; }
@media (prefers-reduced-motion: reduce) { .gx-intro { display:none!important; } }
/* ============================== BOTTOM NAVIGATION ============================== */
.gx-bnav { position:fixed; bottom:0; left:0; right:0; z-index:90; display:none;
  background:rgba(5,6,7,.94); backdrop-filter:blur(20px) saturate(1.6);
  -webkit-backdrop-filter:blur(20px) saturate(1.6); border-top:1px solid rgba(24,232,117,.08);
  padding-bottom:env(safe-area-inset-bottom); }
html[data-theme="light"] .gx-bnav { background:rgba(255,255,255,.92); border-top-color:var(--line); }
@media (max-width:768px) { .gx-bnav { display:flex; justify-content:space-around; align-items:center; padding:6px 0 4px; } .wrap { padding-bottom:110px!important; } }
.gx-bnav a { display:flex; flex-direction:column; align-items:center; gap:2px; padding:6px 10px; font-size:.62rem;
  font-weight:700; color:var(--mut); text-decoration:none; transition:color .2s ease; position:relative; }
.gx-bnav a.on { color:var(--ac); }
.gx-bnav a.on::before { content:''; position:absolute; top:-6px; left:50%; transform:translateX(-50%); width:20px; height:3px;
  border-radius:2px; background:var(--ac); box-shadow:0 0 8px rgba(24,232,117,.4); }
.gx-bnav .bnav-icon { font-size:1.2rem; }
.gx-bnav .bnav-badge { position:absolute; top:2px; right:6px; background:var(--ac); color:var(--bg); font-size:.55rem;
  font-weight:900; min-width:16px; height:16px; border-radius:999px; display:flex; align-items:center; justify-content:center; padding:0 3px; }
/* ============================== FOOTBALL SCROLL ============================== */
.gx-football { position:fixed; z-index:5; pointer-events:none; font-size:28px; filter:drop-shadow(0 6px 12px rgba(0,0,0,.4));
  will-change:transform; transition:none; opacity:0; }
@media (max-width:768px) { .gx-football { font-size:22px; } }
@media (prefers-reduced-motion: reduce) { .gx-football { display:none!important; } }
/* ============================== SECTION BACKGROUNDS ============================== */
.sec-stadium { position:relative; }
.sec-stadium::before { content:''; position:absolute; inset:0; border-radius:26px; opacity:.6;
  background:radial-gradient(ellipse 100% 80% at 50% 0%, rgba(24,232,117,.06), transparent 70%); pointer-events:none; }
html[data-theme="light"] .sec-stadium::before { background:radial-gradient(ellipse 100% 80% at 50% 0%, rgba(225,29,72,.04), transparent 70%); }
/* ============================== MICRO INTERACTIONS ============================== */
.gx-press { transition:transform .12s ease!important; }
.gx-press:active { transform:scale(.96)!important; }
.heart { transition:transform .2s ease, color .2s ease, box-shadow .2s ease; }
.heart:active { transform:scale(.85)!important; }
.heart.pop { animation:heartPop .4s ease; }
@keyframes heartPop { 0%{transform:scale(1)} 30%{transform:scale(1.3)} 60%{transform:scale(.9)} 100%{transform:scale(1)} }
.gx-shake { animation:gxShake .4s ease; }
@keyframes gxShake { 0%,100%{transform:translateX(0)} 20%{transform:translateX(-6px)} 40%{transform:translateX(6px)} 60%{transform:translateX(-4px)} 80%{transform:translateX(4px)} }
/* ============================== DELIVERED CELEBRATION ============================== */
.gx-goal-fx { position:fixed; inset:0; z-index:9998; display:flex; align-items:center; justify-content:center;
  background:rgba(5,6,7,.85); opacity:0; visibility:hidden; transition:opacity .3s ease, visibility .3s ease; }
.gx-goal-fx.show { opacity:1; visibility:visible; }
.gx-goal-fx .goal-txt { font-size:3rem; font-weight:900; color:var(--warm); text-shadow:0 0 30px rgba(216,180,90,.4);
  animation:goalPulse 1s ease infinite; }
@keyframes goalPulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.05)} }
@media (prefers-reduced-motion: reduce) { .gx-goal-fx .goal-txt { animation:none; } }
/* ============================== MATCHDAY MODE ============================== */
.mkmode-toggle{position:fixed;top:14px;inset-inline-end:14px;z-index:88;display:flex;align-items:center;gap:8px;
  background:rgba(5,6,7,.8);border:1px solid rgba(24,232,117,.15);border-radius:999px;padding:6px 14px 6px 10px;
  cursor:pointer;transition:all .3s;backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px)}
.mkmode-toggle:hover{border-color:rgba(24,232,117,.35);box-shadow:0 0 20px rgba(24,232,117,.1)}
.mkmode-toggle .mkmode-ic{font-size:1rem}
.mkmode-toggle .mkmode-lbl{font-size:.7rem;font-weight:800;color:rgba(255,255,255,.6);letter-spacing:1px}
.mkmode-toggle.active{background:rgba(24,232,117,.12);border-color:rgba(24,232,117,.3)}
.mkmode-toggle.active .mkmode-lbl{color:#18E875}
html.mkmode{--bg:#050607;--bg2:#050907;--card:rgba(5,6,7,.85);--card2:rgba(11,23,18,.6);
  --txt:#F5F7F6;--mut:#6B7A73;--line:rgba(24,232,117,.08);--ac:#18E875;--ac2:#0B9F50;
  --glass:rgba(5,6,7,.7);--glass-border:rgba(24,232,117,.08)}
html.mkmode::before{content:'';position:fixed;inset:0;z-index:-2;
  background:radial-gradient(900px 500px at 50% 0%,rgba(24,232,117,.06),transparent 50%),
  radial-gradient(600px 300px at 20% 100%,rgba(24,232,117,.03),transparent 50%),
  radial-gradient(600px 300px at 80% 100%,rgba(24,232,117,.03),transparent 50%),
  linear-gradient(180deg,#050607 0%,#050D09 40%,#07100C 100%);pointer-events:none}
html.mkmode::after{content:'';position:fixed;top:0;left:0;right:0;height:200px;z-index:-1;
  background:linear-gradient(180deg,rgba(24,232,117,.04),transparent);pointer-events:none;
  animation:mkFlicker 6s ease-in-out infinite}
@keyframes mkFlicker{0%,100%{opacity:.4}50%{opacity:.7}}
.mkmode-pitch{display:none;position:fixed;bottom:0;left:0;right:0;height:120px;z-index:-1;pointer-events:none;
  background:repeating-linear-gradient(0deg,transparent 0 8px,rgba(24,232,117,.015) 8px 16px),
  linear-gradient(180deg,transparent,rgba(27,94,58,.08))}
html.mkmode .mkmode-pitch{display:block}
.mkmode-lights{display:none;position:fixed;top:0;left:0;right:0;height:300px;z-index:-1;pointer-events:none}
html.mkmode .mkmode-lights{display:block}
.mkmode-lights .mkl{position:absolute;width:2px;height:80px;top:0;background:linear-gradient(180deg,rgba(255,255,255,.3),transparent);border-radius:0 0 2px 2px;animation:mklPulse 4s ease-in-out infinite}
.mkmode-lights .mkl:nth-child(1){left:10%;animation-delay:0s}
.mkmode-lights .mkl:nth-child(2){left:30%;animation-delay:1s;height:60px}
.mkmode-lights .mkl:nth-child(3){right:30%;animation-delay:2s;height:70px}
.mkmode-lights .mkl:nth-child(4){right:10%;animation-delay:3s}
@keyframes mklPulse{0%,100%{opacity:.15}50%{opacity:.4}}
@media (max-width:768px){.mkmode-toggle{top:auto;bottom:60px;inset-inline-end:10px;padding:5px 10px 5px 8px}.mkmode-toggle .mkmode-lbl{font-size:.6rem}}
/* ============================== PAGE TRANSITIONS ============================== */
.gx-page-in { animation:gxPageIn .35s ease both; }
@keyframes gxPageIn { from { opacity:0; transform:translateY(12px); } to { opacity:1; transform:none; } }
@media (prefers-reduced-motion: reduce) { .gx-page-in { animation:none; } }
/* ============================== ADMIN LOGIN ============================== */
.adm-login-card {
  background: var(--glass); border: 1px solid var(--glass-border); border-radius: 28px;
  padding: 44px 32px 36px; backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
  box-shadow: 0 28px 60px rgba(0,0,0,.45);
  background-image: radial-gradient(ellipse 120% 100% at 50% 0%, rgba(24,232,117,.08), transparent 55%);
}
html[data-theme="light"] .adm-login-card {
  background: var(--card); border-color: var(--line); backdrop-filter: none;
  box-shadow: var(--sh2); background-image: none;
}
.adm-login-icon {
  font-size: 3.4rem; margin-bottom: 8px; filter: drop-shadow(0 8px 20px rgba(24,232,117,.35));
  animation: admIconFloat 4s ease-in-out infinite;
}
@keyframes admIconFloat { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-8px)} }
.adm-login-brand {
  font-family: 'Poppins','Cairo',sans-serif; font-size: 1.8rem; font-weight: 900; letter-spacing: 5px;
  background: linear-gradient(90deg, var(--ac), var(--ac2)); -webkit-background-clip: text;
  background-clip: text; color: transparent; filter: drop-shadow(0 4px 14px rgba(24,232,117,.28));
}
.adm-login-title { font-size: 1.15rem; font-weight: 900; margin-top: 10px; }
.adm-login-sub { color: var(--mut); font-size: .86rem; margin-top: 6px; }
.adm-field { text-align: right; }
html[dir="ltr"] .adm-field { text-align: left; }
.adm-label { display: block; font-size: .78rem; font-weight: 800; color: var(--mut); margin-bottom: 6px; letter-spacing: .5px; }
.adm-input {
  width: 100%; padding: 13px 16px; border-radius: 14px; border: 1.5px solid var(--glass-border);
  background: rgba(11,23,18,.6); color: var(--txt); font-size: .92rem; font-family: inherit;
  transition: border-color .2s ease, box-shadow .2s ease;
}
html[data-theme="light"] .adm-input { background: var(--card2); border-color: var(--line); }
.adm-input:focus { outline: none; border-color: var(--ac); box-shadow: 0 0 0 3px rgba(24,232,117,.15); }
.adm-msg { border-radius: 12px; padding: 11px 14px; margin-bottom: 14px; font-size: .88rem; font-weight: 700; }
.adm-msg.err { background: rgba(220,38,38,.12); border: 1px solid rgba(220,38,38,.3); color: #FCA5A5; }
html[data-theme="light"] .adm-msg.err { color: #DC2626; }
/* ============================== CART GOAL ANIMATION ============================== */
.gx-ball-fly {
  position: fixed; font-size: 32px; z-index: 500; pointer-events: none;
  transition: all .7s cubic-bezier(.25,.7,.25,1); filter: drop-shadow(0 6px 14px rgba(0,0,0,.35));
}
.gx-ball-fly.go { opacity: 0; transform: scale(.4); }
.gx-goal-fx {
  position: fixed; inset: 0; display: none; align-items: center; justify-content: center;
  z-index: 600; background: rgba(2,6,23,.6); pointer-events: none;
}
.gx-goal-fx.show { display: flex; }
.gx-goal-fx .goal-txt {
  font-size: 3.4rem; font-weight: 900; color: var(--ac);
  text-shadow: 0 8px 40px rgba(24,232,117,.45);
  animation: goalPulse .6s ease;
}
@keyframes goalPulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.08)} }
/* ============================== PLAYER CARD ============================== */
.pcard-id {
  background: linear-gradient(135deg, var(--card2) 0%, var(--bg2) 50%, var(--card2) 100%);
  color: #fff; border-radius: 22px; padding: 28px 24px; position: relative; overflow: hidden;
  box-shadow: 0 22px 50px rgba(0,0,0,.35); margin-bottom: 18px;
}
.pcard-id::after { content: '⚽'; position: absolute; font-size: 8rem; opacity: .06; inset-inline-end: 14px; bottom: -18px; }
.pcard-id .pid-logo { font-size: 1.6rem; font-weight: 900; letter-spacing: 3px; color: #F7D033; }
.pcard-id .pid-name { font-size: 1.5rem; font-weight: 900; margin-top: 8px; }
.pcard-id .pid-meta { font-size: .82rem; color: rgba(255,255,255,.7); margin-top: 6px; }
.pcard-id .pid-level {
  display: inline-block; background: linear-gradient(90deg, var(--ac), var(--ac2));
  color: #0A0D0C; border-radius: 999px; padding: 5px 16px; font-size: .78rem; font-weight: 900; margin-top: 12px;
}
.pcard-id .pid-emoji { font-size: 3.8rem; position: absolute; top: 16px; inset-inline-end: 20px; opacity: .2; }
/* ============================== MATCH TICKET EXPERIENCE ============================== */
.mk-hero{position:relative;min-height:420px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:60px 20px 40px;overflow:hidden}
.mk-hero::before{content:'';position:absolute;inset:0;background:radial-gradient(800px 500px at 50% 0%,var(--mk-glow1,rgba(24,232,117,.10)),transparent 60%),radial-gradient(600px 300px at 50% 100%,var(--mk-glow2,rgba(24,232,117,.04)),transparent 60%);z-index:0;transition:background .6s ease}
.mk-hero>*{position:relative;z-index:1}
.mk-grass{position:absolute;bottom:0;left:0;right:0;height:80px;background:repeating-linear-gradient(0deg,transparent 0 12px,rgba(255,255,255,.03) 12px 24px),linear-gradient(180deg,rgba(27,122,61,.08),rgba(27,122,61,.15));z-index:0}
.mk-lights{position:absolute;top:-60px;width:3px;height:120px;background:linear-gradient(180deg,rgba(255,255,255,.5),transparent);border-radius:0 0 4px 4px;opacity:.25;animation:mkpulse 4s ease-in-out infinite}
.mk-lights:nth-child(2){left:12%;animation-delay:.8s}
.mk-lights:nth-child(3){right:12%;animation-delay:1.6s}
.mk-lights:nth-child(4){left:28%;animation-delay:2.4s;height:90px;top:-40px}
.mk-lights:nth-child(5){right:28%;animation-delay:3.2s;height:90px;top:-40px}
@keyframes mkpulse{0%,100%{opacity:.15}50%{opacity:.35}}
.mk-subtitle{font-size:.85rem;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:var(--mk-ac,rgba(24,232,117,.8));margin-bottom:8px}
.mk-title{font-size:2rem;font-weight:900;color:#fff;margin-bottom:6px;line-height:1.2}
.mk-empty{font-size:1.1rem;color:rgba(255,255,255,.6);margin-bottom:24px}
.mk-explore{display:inline-flex;align-items:center;gap:8px;padding:14px 32px;border-radius:14px;background:var(--mk-ac,#18E875);color:#050607;font-weight:900;font-size:1rem;border:none;cursor:pointer;text-decoration:none;transition:transform .2s,box-shadow .2s}
.mk-explore:hover{transform:scale(1.04);box-shadow:0 0 30px var(--mk-glow,rgba(24,232,117,.3))}
/* --- Main Ticket --- */
.mk-ticket{width:100%;max-width:600px;margin:0 auto;border-radius:20px;overflow:hidden;position:relative;background:linear-gradient(160deg,rgba(10,13,12,.95),rgba(5,6,7,.98));border:1px solid var(--mk-border,rgba(24,232,117,.15));box-shadow:0 20px 60px rgba(0,0,0,.5),0 0 40px var(--mk-glow,rgba(24,232,117,.08));animation:ticketIn .6s ease-out}
@keyframes ticketIn{from{opacity:0;transform:translateY(30px) scale(.96)}to{opacity:1;transform:translateY(0) scale(1)}}
.mk-ticket-top{padding:24px 24px 16px;border-bottom:2px dashed var(--mk-border,rgba(24,232,117,.12));position:relative}
.mk-ticket-top::after{content:'';position:absolute;bottom:-12px;inset-inline-start:-12px;width:24px;height:24px;background:var(--bg);border-radius:50%}
.mk-ticket-top::before{content:'';position:absolute;bottom:-12px;inset-inline-end:-12px;width:24px;height:24px;background:var(--bg);border-radius:50%}
.mk-ticket-brand{text-align:center;margin-bottom:14px}
.mk-ticket-brand h3{font-size:.72rem;font-weight:800;letter-spacing:4px;text-transform:uppercase;color:var(--mk-ac,rgba(24,232,117,.8));margin-bottom:2px}
.mk-ticket-brand .mk-ticket-sub{font-size:1.1rem;font-weight:900;color:#fff;letter-spacing:2px}
.mk-matchup{display:flex;align-items:center;justify-content:center;gap:20px;margin:16px 0}
.mk-matchup .mk-team{text-align:center;flex:1}
.mk-matchup .mk-team-name{font-weight:900;font-size:1rem;color:#fff;margin-top:6px}
.mk-matchup .mk-team-role{font-size:.7rem;color:rgba(255,255,255,.5);font-weight:700;letter-spacing:2px;text-transform:uppercase}
.mk-matchup .mk-vs{font-size:1.4rem;font-weight:900;color:var(--mk-ac,#18E875);text-shadow:0 0 20px var(--mk-glow,rgba(24,232,117,.3))}
.mk-ticket-mid{padding:20px 24px;border-bottom:2px dashed var(--mk-border,rgba(24,232,117,.12));position:relative}
.mk-ticket-mid::after{content:'';position:absolute;bottom:-12px;inset-inline-start:-12px;width:24px;height:24px;background:var(--bg);border-radius:50%}
.mk-ticket-mid::before{content:'';position:absolute;bottom:-12px;inset-inline-end:-12px;width:24px;height:24px;background:var(--bg);border-radius:50%}
.mk-detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px 20px}
.mk-detail{display:flex;flex-direction:column}
.mk-detail-label{font-size:.65rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,.4);margin-bottom:2px}
.mk-detail-value{font-size:.95rem;font-weight:800;color:#fff}
.mk-detail-value.mk-highlight{color:var(--mk-ac,#18E875);font-size:1.1rem}
.mk-ticket-bottom{padding:20px 24px;display:flex;gap:16px;align-items:flex-start}
.mk-barcode{flex:0 0 80px;display:flex;flex-direction:column;align-items:center;gap:4px}
.mk-barcode-lines{width:80px;height:50px;background:repeating-linear-gradient(90deg,rgba(255,255,255,.7) 0 2px,transparent 2px 4px,rgba(255,255,255,.4) 4 5px,transparent 5 8px,rgba(255,255,255,.6) 8 10px,transparent 10 12px);border-radius:4px;animation:brcscan 3s linear infinite}
@keyframes brcscan{0%{background-position:0 0}100%{background-position:24px 0}}
.mk-barcode-id{font-size:.6rem;color:rgba(255,255,255,.4);font-family:monospace;letter-spacing:1px}
.mk-ticket-meta{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:8px}
.mk-meta-item{text-align:center}
.mk-meta-label{font-size:.55rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:rgba(255,255,255,.35)}
.mk-meta-val{font-size:.8rem;font-weight:800;color:rgba(255,255,255,.8);font-family:monospace}
.mk-ticket-actions{display:flex;gap:8px;padding:0 24px 20px;flex-wrap:wrap}
.mk-ticket-actions .hbtn,.mk-ticket-actions a.hbtn{flex:1;min-width:0;text-align:center;font-size:.82rem;padding:10px 8px}
/* --- Status Journey --- */
.mk-journey{max-width:600px;margin:20px auto 0;padding:20px;border-radius:16px;background:rgba(10,13,12,.6);border:1px solid var(--mk-border,rgba(24,232,117,.10))}
.mk-journey-title{font-size:.75rem;font-weight:800;letter-spacing:2px;text-transform:uppercase;color:var(--mk-ac,rgba(24,232,117,.7));margin-bottom:16px;text-align:center}
.mk-journey-steps{display:flex;align-items:center;justify-content:center;gap:0;position:relative}
.mk-step{display:flex;flex-direction:column;align-items:center;position:relative;z-index:1;flex:1;max-width:120px}
.mk-step-dot{width:32px;height:32px;border-radius:50%;background:rgba(255,255,255,.06);border:2px solid rgba(255,255,255,.1);display:flex;align-items:center;justify-content:center;font-size:.7rem;margin-bottom:6px;transition:all .4s ease}
.mk-step.done .mk-step-dot{background:var(--mk-ac,#18E875);border-color:var(--mk-ac,#18E875);color:#050607;box-shadow:0 0 16px var(--mk-glow,rgba(24,232,117,.25))}
.mk-step.cur .mk-step-dot{background:transparent;border-color:var(--mk-ac,#18E875);color:var(--mk-ac,#18E875);box-shadow:0 0 20px var(--mk-glow,rgba(24,232,117,.3));animation:mkglow 2s ease-in-out infinite}
@keyframes mkglow{0%,100%{box-shadow:0 0 12px var(--mk-glow,rgba(24,232,117,.2))}50%{box-shadow:0 0 24px var(--mk-glow,rgba(24,232,117,.4))}}
.mk-step-lbl{font-size:.65rem;font-weight:700;color:rgba(255,255,255,.35);text-align:center;line-height:1.2}
.mk-step.done .mk-step-lbl,.mk-step.cur .mk-step-lbl{color:rgba(255,255,255,.8)}
.mk-step-line{position:absolute;top:16px;inset-inline-start:calc(50% + 20px);inset-inline-end:calc(-50% + 20px);height:2px;background:rgba(255,255,255,.08);z-index:0}
.mk-step.done .mk-step-line{background:var(--mk-ac,#18E875)}
.mk-step:last-child .mk-step-line{display:none}
/* --- Mini Tickets --- */
.mk-section-head{display:flex;align-items:center;gap:10px;margin:30px 0 16px;padding:0 4px}
.mk-section-head h3{font-size:1rem;font-weight:900;color:#fff}
.mk-section-head .mk-sh-line{flex:1;height:1px;background:var(--mk-border,rgba(24,232,117,.10))}
.mk-mini-tickets{display:grid;gap:12px}
.mk-mini{border-radius:14px;overflow:hidden;background:linear-gradient(145deg,rgba(10,13,12,.85),rgba(5,6,7,.9));border:1px solid var(--mk-border,rgba(24,232,117,.08));cursor:pointer;transition:transform .22s,box-shadow .22s,border-color .22s}
.mk-mini:hover{transform:translateY(-3px);box-shadow:0 12px 30px rgba(0,0,0,.4),0 0 20px var(--mk-glow,rgba(24,232,117,.06));border-color:var(--mk-ac,rgba(24,232,117,.2))}
.mk-mini-top{display:flex;align-items:center;gap:12px;padding:14px 16px;border-bottom:1px dashed var(--mk-border,rgba(24,232,117,.08))}
.mk-mini-img{width:52px;height:52px;border-radius:10px;object-fit:cover;border:1px solid var(--mk-border,rgba(24,232,117,.1));flex:none;background:var(--card)}
.mk-mini-info{flex:1;min-width:0}
.mk-mini-team{font-size:.65rem;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--mk-ac,rgba(24,232,117,.6))}
.mk-mini-name{font-size:.88rem;font-weight:800;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mk-mini-status{padding:3px 10px;border-radius:999px;font-size:.65rem;font-weight:800;white-space:nowrap}
.mk-mini-status.st-pending{background:rgba(251,191,36,.15);color:#FCD34D}
.mk-mini-status.st-confirmed{background:rgba(96,165,250,.15);color:#93C5FD}
.mk-mini-status.st-preparing{background:var(--mk-ac-soft,rgba(24,232,117,.12));color:var(--mk-ac,#18E875)}
.mk-mini-status.st-delivering{background:rgba(168,85,247,.15);color:#C4B5FD}
.mk-mini-status.st-delivered{background:rgba(52,211,153,.15);color:#6EE7B7}
.mk-mini-status.st-cancelled{background:rgba(239,68,68,.15);color:#FCA5A5}
.mk-mini-bottom{display:flex;justify-content:space-between;align-items:center;padding:12px 16px}
.mk-mini-code{font-size:.72rem;font-weight:800;color:rgba(255,255,255,.5);font-family:monospace}
.mk-mini-price{font-size:.9rem;font-weight:900;color:#fff}
.mk-mini-date{font-size:.7rem;color:rgba(255,255,255,.35)}
/* --- Fan Card --- */
.mk-fan{max-width:900px;margin:0 auto 24px;border-radius:20px;overflow:hidden;position:relative;
  display:flex; background:linear-gradient(135deg,rgba(255,255,255,.045),rgba(255,255,255,.015)),
  linear-gradient(160deg,rgba(10,13,12,.95),rgba(5,6,7,.98));
  border:1px solid rgba(255,255,255,.12); box-shadow:0 20px 60px rgba(0,0,0,.45),0 0 35px var(--mk-glow,rgba(0,230,118,.05));
  backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px); animation:ticketIn .6s ease-out}
.mk-fan-strip{flex:0 0 46px; background:linear-gradient(180deg,var(--mk-ac,#00E676),var(--mk-ac2,#16A765));
  display:flex; flex-direction:column; align-items:center; justify-content:space-between; padding:18px 0; gap:10px}
.mk-fan-strip-title{writing-mode:vertical-rl; transform:rotate(180deg); font-weight:900; letter-spacing:5px;
  font-size:.85rem; color:#030605}
.mk-fan-strip-sub{writing-mode:vertical-rl; transform:rotate(180deg); font-weight:800; letter-spacing:3px;
  font-size:.62rem; color:rgba(3,6,5,.65)}
.mk-fan-body{flex:1; padding:22px 24px; min-width:0; position:relative; border-inline-end:2px dashed rgba(255,255,255,.14)}
.mk-fan-body::after{content:'';position:absolute;bottom:-11px;inset-inline-end:-11px;width:22px;height:22px;background:var(--bg);border-radius:50%;z-index:2}
.mk-fan-body::before{content:'';position:absolute;top:-11px;inset-inline-end:-11px;width:22px;height:22px;background:var(--bg);border-radius:50%;z-index:2}
.mk-fan-brand{font-size:.68rem;font-weight:800;letter-spacing:3px;text-transform:uppercase;color:var(--mk-ac,#00E676);margin-bottom:2px}
.mk-fan-sub{font-size:.98rem;font-weight:900;color:#F4F7F5;letter-spacing:1px;margin-bottom:14px}
.mk-fan-header{display:flex;align-items:center;gap:14px;margin-bottom:16px}
.mk-fan-avatar{width:56px;height:56px;border-radius:50%;flex:none;background:rgba(255,255,255,.04);
  border:2px solid var(--mk-ac,#00E676);display:flex;align-items:center;justify-content:center;
  font-size:1.5rem;color:var(--mk-ac,#00E676);font-weight:900;overflow:hidden}
.mk-fan-avatar img{width:100%;height:100%;object-fit:cover}
.mk-fan-name{font-size:1.15rem;font-weight:900;color:#F4F7F5}
.mk-fan-id{font-size:.72rem;color:#AAB4AF;font-family:monospace;letter-spacing:.5px;margin-top:2px}
.mk-fan-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;border-top:1px dashed rgba(255,255,255,.12);padding-top:16px}
.mk-fan-stat{text-align:center}
.mk-fan-stat-val{font-size:1.05rem;font-weight:900;color:#F4F7F5;direction:ltr}
.mk-fan-stat-lbl{font-size:.6rem;font-weight:800;color:#AAB4AF;margin-top:3px;letter-spacing:1px;text-transform:uppercase}
.mk-fan-qr{flex:0 0 150px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:22px 16px}
.mk-fan-qr-lbl{font-size:.62rem;font-weight:800;letter-spacing:2px;color:#AAB4AF;text-transform:uppercase}
.mk-fan-qr-box{width:88px;height:88px;border-radius:10px;background:#F4F7F5 repeating-linear-gradient(90deg,#030605 0 6px,transparent 6px 12px),
  repeating-linear-gradient(0deg,#030605 0 6px,transparent 6px 12px); background-blend-mode:multiply; opacity:.92}
.mk-fan-qr-code{font-size:.66rem;font-weight:800;color:#F4F7F5;font-family:monospace;letter-spacing:.5px;text-align:center;direction:ltr}
@media (max-width:768px){
  .mk-fan{flex-direction:column}
  .mk-fan-strip{flex-direction:row;width:100%;padding:8px 16px;gap:14px}
  .mk-fan-strip-title,.mk-fan-strip-sub{writing-mode:horizontal-tb;transform:none}
  .mk-fan-body{border-inline-end:none;border-bottom:2px dashed rgba(255,255,255,.14)}
  .mk-fan-body::after,.mk-fan-body::before{inset-inline-end:auto;left:50%;transform:translateX(-50%);bottom:-11px;top:auto}
  .mk-fan-body::before{display:none}
  .mk-fan-grid{grid-template-columns:repeat(2,1fr);gap:12px}
  .mk-fan-qr{flex:none;padding:18px}
}
/* --- Acc tabs (simplified) --- */
.mk-tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:20px;justify-content:center}
.mk-tab{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:8px 16px;font-size:.8rem;font-weight:800;color:rgba(255,255,255,.5);cursor:pointer;transition:all .2s}
.mk-tab:hover{border-color:var(--mk-ac,rgba(24,232,117,.2));color:rgba(255,255,255,.8)}
.mk-tab.on{background:var(--mk-ac-soft,rgba(24,232,117,.1));border-color:var(--mk-ac,rgba(24,232,117,.25));color:var(--mk-ac,#18E875)}
.mk-sec{display:none}
.mk-sec.on{display:block;animation:fadeUp .3s ease}
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.mk-sec-inner{max-width:600px;margin:0 auto}
/* --- Saved sizes --- */
.mk-szrow{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-radius:10px;background:rgba(255,255,255,.03);margin-bottom:6px;border:1px solid rgba(255,255,255,.04)}
.mk-szrow a{color:var(--mk-ac,#18E875);text-decoration:none;font-weight:800;font-size:.88rem}
.mk-szrow .pill{font-size:.72rem;padding:3px 10px}
.mk-data-fld{margin-bottom:14px}
.mk-data-fld label{display:block;font-size:.72rem;font-weight:700;color:rgba(255,255,255,.5);letter-spacing:1px;text-transform:uppercase;margin-bottom:4px}
.mk-data-fld input{width:100%;padding:12px 14px;border-radius:10px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.04);color:#fff;font-size:.9rem;font-weight:600}
.mk-data-fld input:focus{outline:none;border-color:var(--mk-ac,rgba(24,232,117,.3))}
.mk-logout{display:flex;justify-content:center;margin-top:24px}
.mk-logout button{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.2);color:#FCA5A5;border-radius:12px;padding:12px 28px;font-weight:800;font-size:.88rem;cursor:pointer;transition:all .2s}
.mk-logout button:hover{background:rgba(239,68,68,.2)}
/* --- Ticket detail overlay --- */
.mk-detail-overlay{position:fixed;inset:0;z-index:9000;display:none;align-items:center;justify-content:center;background:rgba(5,6,7,.85);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);padding:20px;animation:fadeIn .25s ease}
.mk-detail-overlay.on{display:flex}
.mk-detail-close{position:fixed;top:20px;inset-inline-end:20px;width:44px;height:44px;border-radius:50%;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.15);color:#fff;font-size:1.2rem;cursor:pointer;z-index:9001;display:flex;align-items:center;justify-content:center}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
/* --- Mobile responsive --- */
@media(max-width:600px){
.mk-hero{min-height:360px;padding:50px 16px 30px}
.mk-title{font-size:1.5rem}
.mk-ticket{max-width:100%;border-radius:16px}
.mk-ticket-top,.mk-ticket-mid{padding:18px 16px 14px}
.mk-ticket-bottom{padding:16px;flex-direction:column;align-items:center}
.mk-barcode{flex:none}
.mk-detail-grid{grid-template-columns:1fr 1fr;gap:10px 14px}
.mk-journey-steps{gap:0}
.mk-step{max-width:80px}
.mk-step-dot{width:26px;height:26px;font-size:.6rem}
.mk-fan-grid{grid-template-columns:repeat(3,1fr);gap:8px}
.mk-mini-top{padding:12px}
.mk-mini-bottom{padding:10px 12px}
}
/* ============================== JERSEY OF THE DAY ============================== */
.spotlight-card {
  background: var(--glass); border: 1px solid var(--glass-border); border-radius: 24px;
  padding: 22px; display: flex; gap: 22px; align-items: center; position: relative; overflow: hidden;
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 18px 44px rgba(0,0,0,.25);
  background-image: radial-gradient(ellipse 120% 100% at 20% 0%, rgba(24,232,117,.08), transparent 50%);
  transition: transform .22s ease, box-shadow .24s ease;
}
html[data-theme="light"] .spotlight-card { background: var(--card); border-color: var(--line); backdrop-filter: none; box-shadow: var(--sh); }
.spotlight-card:hover { transform: translateY(-4px); box-shadow: 0 24px 54px rgba(0,0,0,.35); }
.spotlight-img { width: 160px; height: 160px; border-radius: 18px; object-fit: cover; flex: none;
  border: 2px solid var(--glass-border); box-shadow: 0 12px 28px rgba(0,0,0,.3); }
.spotlight-info { flex: 1; }
.spotlight-badge {
  display: inline-flex; align-items: center; gap: 6px;
  background: linear-gradient(90deg, var(--ac), var(--ac2)); color: #0A0D0C;
  border-radius: 999px; padding: 5px 14px; font-size: .7rem; font-weight: 900; letter-spacing: 1px;
}
.spotlight-info h3 { font-size: 1.2rem; font-weight: 900; margin-top: 10px; }
.spotlight-info p { color: var(--mut); font-size: .86rem; margin-top: 6px; line-height: 1.7; }
.spotlight-price { font-size: 1.4rem; font-weight: 900; color: var(--ac); margin-top: 12px; }
@media (max-width: 640px) {
  .spotlight-card { flex-direction: column; text-align: center; }
  .spotlight-img { width: 100%; height: 200px; }
  .adm-login-card { padding: 32px 20px 28px; }
}
/* ============================== SIZE GUIDE PREMIUM ============================== */
.sg-page { padding-bottom: 80px; }
.sg-hero {
  position: relative; overflow: hidden; min-height: 320px;
  background:
    radial-gradient(ellipse 120% 100% at 20% 10%, rgba(24,232,117,.12), transparent 55%),
    radial-gradient(ellipse 80% 80% at 80% 80%, rgba(216,180,90,.05), transparent 50%),
    linear-gradient(180deg, #0A0D0C 0%, var(--bg2) 40%, #0B1712 100%);
  display: flex; align-items: center; padding: 40px 24px;
}
html[data-theme="light"] .sg-hero {
  background: linear-gradient(180deg, #F3F6FB 0%, #EDF1F8 100%);
}
.sg-hero-inner { max-width: 1120px; margin: 0 auto; width: 100%; display: flex; align-items: center; gap: 40px; }
.sg-hero-visual { flex: 0 0 180px; position: relative; display: flex; align-items: center; justify-content: center; }
.sg-hero-jersey { font-size: 120px; filter: drop-shadow(0 20px 40px rgba(24,232,117,.25)); animation: sgFloat 5s ease-in-out infinite; position: relative; z-index: 1; }
@keyframes sgFloat { 0%,100%{transform:translateY(0) rotate(-3deg)} 50%{transform:translateY(-12px) rotate(3deg)} }
.sg-hero-glow { position: absolute; width: 200px; height: 200px; border-radius: 50%; background: radial-gradient(circle, rgba(24,232,117,.2), transparent 70%); filter: blur(30px); }
.sg-hero-text { flex: 1; }
.sg-hero-text h1 { font-size: 2.4rem; font-weight: 900; line-height: 1.2; color: #F5F7F6; }
html[data-theme="light"] .sg-hero-text h1 { color: #0F172A; }
.sg-green { color: #18E875; }
html[data-theme="light"] .sg-green { color: #16A34A; }
.sg-hero-text p { color: #A8B2AD; font-size: 1rem; margin-top: 10px; line-height: 1.7; }
html[data-theme="light"] .sg-hero-text p { color: #5B6782; }
.sg-wrap { max-width: 800px; margin: -40px auto 0; position: relative; z-index: 2; }
.sg-calc-card {
  background: rgba(5,6,7,.82); border: 1px solid rgba(24,232,117,.25); border-radius: 24px;
  padding: 32px 28px; backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 28px 60px rgba(0,0,0,.45), 0 0 40px rgba(24,232,117,.06);
}
html[data-theme="light"] .sg-calc-card {
  background: #FFFFFF; border-color: #E2E8F0; backdrop-filter: none;
  box-shadow: 0 28px 60px rgba(15,23,42,.08);
}
.sg-calc-header { text-align: center; margin-bottom: 24px; }
.sg-calc-header h2 { font-size: 1.5rem; font-weight: 900; color: #F5F7F6; }
html[data-theme="light"] .sg-calc-header h2 { color: #0F172A; }
.sg-calc-header p { color: #6B7A73; font-size: .88rem; margin-top: 6px; }
html[data-theme="light"] .sg-calc-header p { color: #5B6782; }
.sg-calc-inputs { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
.sg-field label { display: block; font-size: .78rem; font-weight: 800; color: #6B7A73; margin-bottom: 6px; letter-spacing: .5px; }
html[data-theme="light"] .sg-field label { color: #5B6782; }
.sg-input-wrap {
  display: flex; align-items: center; background: rgba(11,23,18,.6); border: 1.5px solid rgba(24,232,117,.15);
  border-radius: 14px; overflow: hidden; transition: border-color .2s, box-shadow .2s;
}
html[data-theme="light"] .sg-input-wrap { background: #F8FAFC; border-color: #E2E8F0; }
.sg-input-wrap:focus-within { border-color: #18E875; box-shadow: 0 0 0 3px rgba(24,232,117,.12); }
html[data-theme="light"] .sg-input-wrap:focus-within { border-color: #16A34A; box-shadow: 0 0 0 3px rgba(22,163,74,.12); }
.sg-input-wrap input {
  flex: 1; padding: 14px 16px; background: transparent; border: none; color: #F5F7F6;
  font-size: 1.1rem; font-weight: 800; font-family: inherit; outline: none; min-width: 0;
}
html[data-theme="light"] .sg-input-wrap input { color: #0F172A; }
.sg-input-wrap input::placeholder { color: #4A5A54; }
.sg-unit { padding: 0 14px; font-size: .78rem; font-weight: 800; color: #4A5A54; white-space: nowrap; }
html[data-theme="light"] .sg-unit { color: #94A3B8; }
.sg-calc-btn { margin-top: 4px; }
/* Result Card */
.sg-result {
  margin-top: 24px; text-align: center; padding: 28px 20px;
  background: rgba(11,23,18,.5); border: 1px solid rgba(24,232,117,.2); border-radius: 20px;
  animation: sgResultIn .5s ease both;
}
html[data-theme="light"] .sg-result { background: #F0FDF4; border-color: #BBF7D0; }
@keyframes sgResultIn { from { opacity:0; transform:translateY(12px) scale(.98); } to { opacity:1; transform:none; } }
.sg-result-size {
  font-size: 5rem; font-weight: 900; color: #18E875; line-height: 1;
  text-shadow: 0 8px 40px rgba(24,232,117,.3); position: relative; display: inline-block;
}
html[data-theme="light"] .sg-result-size { color: #16A34A; text-shadow: none; }
.sg-result-size::before {
  content: '⚽'; position: absolute; font-size: 3rem; top: -10px; right: -40px; opacity: .12;
  animation: sgBallSpin 8s linear infinite;
}
@keyframes sgBallSpin { to { transform: rotate(360deg); } }
.sg-result-label { font-size: .88rem; color: #6B7A73; margin-top: 6px; font-weight: 700; }
html[data-theme="light"] .sg-result-label { color: #5B6782; }
.sg-result-details { display: flex; justify-content: center; gap: 24px; margin-top: 16px; }
.sg-rdetail { display: flex; flex-direction: column; align-items: center; }
.sg-rdetail span { font-size: .72rem; color: #4A5A54; font-weight: 700; }
.sg-rdetail b { font-size: 1rem; color: #F5F7F6; margin-top: 2px; }
html[data-theme="light"] .sg-rdetail b { color: #0F172A; }
.sg-result-badge {
  display: inline-block; margin-top: 16px; background: rgba(24,232,117,.12); color: #18E875;
  border: 1px solid rgba(24,232,117,.3); border-radius: 999px; padding: 6px 18px;
  font-size: .82rem; font-weight: 800;
}
html[data-theme="light"] .sg-result-badge { background: #DCFCE7; color: #16A34A; border-color: #BBF7D0; }
.sg-pop { animation: sgPop .4s ease; }
@keyframes sgPop { 0%{transform:scale(.6);opacity:0} 60%{transform:scale(1.1)} 100%{transform:scale(1);opacity:1} }
/* Adjacent Sizes */
.sg-adjacent { margin-top: 24px; text-align: center; }
.sg-adjacent h3 { font-size: 1.1rem; font-weight: 900; color: #F5F7F6; }
html[data-theme="light"] .sg-adjacent h3 { color: #0F172A; }
.sg-adjacent p { color: #6B7A73; font-size: .86rem; margin-top: 4px; }
.sg-adj-cards { display: flex; gap: 12px; justify-content: center; margin-top: 14px; }
.sg-adj-card {
  background: rgba(11,23,18,.4); border: 1.5px solid rgba(24,232,117,.12); border-radius: 16px;
  padding: 16px 24px; text-align: center; min-width: 100px; transition: all .2s;
}
html[data-theme="light"] .sg-adj-card { background: #F8FAFC; border-color: #E2E8F0; }
.sg-adj-card.on {
  background: rgba(24,232,117,.08); border-color: rgba(24,232,117,.4);
  box-shadow: 0 8px 24px rgba(24,232,117,.12);
}
html[data-theme="light"] .sg-adj-card.on { background: #F0FDF4; border-color: #86EFAC; box-shadow: none; }
.sg-adj-sz { font-size: 1.6rem; font-weight: 900; color: #F5F7F6; }
.sg-adj-card.on .sg-adj-sz { color: #18E875; }
html[data-theme="light"] .sg-adj-sz { color: #0F172A; }
.sg-adj-lbl { font-size: .72rem; color: #6B7A73; margin-top: 4px; font-weight: 700; }
/* Size Table Section */
.sg-table-section { margin-top: 28px; }
.sg-table-section h3 { font-size: 1.05rem; font-weight: 900; color: #F5F7F6; margin-bottom: 12px; }
html[data-theme="light"] .sg-table-section h3 { color: #0F172A; }
/* Products Section */
.sg-products { max-width: 1120px; margin: 30px auto 0; padding: 0 18px; }
/* Asian Fit Note */
.sg-asian-note {
  background: rgba(24,232,117,.06); border: 1px solid rgba(24,232,117,.18);
  border-radius: 16px; padding: 18px 22px; margin-bottom: 20px;
  font-size: .85rem; line-height: 1.7; color: #B9C4BE;
  position: relative; overflow: hidden;
}
.sg-asian-note::before {
  content: '⚠️'; position: absolute; top: 16px; inset-inline-end: 16px;
  font-size: 1.4rem; opacity: .2;
}
html[data-theme="light"] .sg-asian-note { background: rgba(24,232,117,.04); border-color: rgba(24,232,117,.15); color: #4A5A54; }
.sg-disclaimer {
  margin-top: 14px; padding-top: 14px; border-top: 1px dashed rgba(24,232,117,.12);
  font-size: .78rem; color: #6B7A73; text-align: center;
}
/* Trust Bar */
.sg-trust-bar {
  max-width: 1120px; margin: 36px auto 0; padding: 0 18px;
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;
}
.sg-trust-item {
  background: rgba(5,6,7,.5); border: 1px solid rgba(24,232,117,.1); border-radius: 16px;
  padding: 18px 14px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 8px;
}
html[data-theme="light"] .sg-trust-item { background: #FFFFFF; border-color: #E2E8F0; }
.sg-trust-ic { font-size: 1.6rem; }
.sg-trust-item b { font-size: .82rem; font-weight: 800; color: #F5F7F6; }
html[data-theme="light"] .sg-trust-item b { color: #0F172A; }
.sg-trust-item span { font-size: .72rem; color: #6B7A73; line-height: 1.5; }
html[data-theme="light"] .sg-trust-item span { color: #5B6782; }
@media (max-width: 768px) {
  .sg-hero { min-height: 260px; padding: 30px 18px; }
  .sg-hero-inner { flex-direction: column; text-align: center; gap: 20px; }
  .sg-hero-visual { flex: none; }
  .sg-hero-jersey { font-size: 80px; }
  .sg-hero-text h1 { font-size: 1.8rem; }
  .sg-calc-inputs { grid-template-columns: 1fr; }
  .sg-trust-bar { grid-template-columns: 1fr 1fr; }
  .sg-result-size { font-size: 3.8rem; }
  .sg-adj-cards { flex-direction: column; align-items: center; }
}
@media (max-width: 480px) {
  .sg-trust-bar { grid-template-columns: 1fr; }
  .sg-calc-card { padding: 24px 18px; }
}
/* ============================== MATCHDAY MODE ============================== */
.matchday-btn { border-color: rgba(24,232,117,.3) !important; color: #18E875 !important; margin-top: 12px; width: 100%; justify-content: center; }
.matchday-btn.active { background: rgba(24,232,117,.1); border-color: rgba(24,232,117,.5) !important; }
html[data-theme="light"] .matchday-btn { color: #16A34A !important; border-color: #BBF7D0 !important; }
html[data-theme="light"] .matchday-btn.active { background: #F0FDF4; border-color: #86EFAC !important; }
html.matchday-mode .pg-wrap { position: relative; }
html.matchday-mode .pg-wrap::before {
  content: ''; position: fixed; inset: 0; z-index: -1; pointer-events: none;
  background:
    radial-gradient(ellipse 80% 60% at 50% 0%, rgba(24,232,117,.15), transparent 50%),
    radial-gradient(ellipse 60% 40% at 20% 80%, rgba(216,180,90,.06), transparent 40%),
    linear-gradient(180deg, #0B1712 0%, var(--bg2) 50%, #0B1712 100%);
  animation: matchdayBg 8s ease-in-out infinite;
}
@keyframes matchdayBg { 0%,100%{opacity:.8} 50%{opacity:1} }
html.matchday-mode .gmain { box-shadow: 0 0 60px rgba(24,232,117,.3), 0 26px 60px rgba(0,0,0,.4); }
.live-drop-badge {
  display: inline-flex; align-items: center; gap: 6px; background: rgba(220,38,38,.12);
  border: 1px solid rgba(220,38,38,.3); border-radius: 999px; padding: 5px 14px;
  font-size: .7rem; font-weight: 900; color: #EF4444; letter-spacing: 1px; margin-bottom: 12px;
}
.live-dot { width: 7px; height: 7px; border-radius: 50%; background: #EF4444; animation: livePulse 1.5s ease infinite; }
@keyframes livePulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(.8)} }
html[data-theme="light"] .live-drop-badge { background: #FEF2F2; border-color: #FECACA; color: #DC2626; }
html[data-theme="light"] .live-dot { background: #DC2626; }
/* ============================== JERSEY STADIUM EXPERIENCE ============================== */
.jersey-exp{margin-top:28px}
.jersey-exp .je-section{margin-bottom:28px}
.je-head h2{font-size:1rem;font-weight:900;display:flex;align-items:center;gap:8px}
.je-head .bar{width:3px;height:16px;border-radius:2px;background:var(--je-ac,#18E875);flex-shrink:0}
.je-sub{font-size:.8rem;color:var(--mut);margin-top:4px;font-weight:600}
/* Reveal */
.je-reveal{position:relative;margin-top:16px;border-radius:20px;overflow:hidden;height:320px;
  background:linear-gradient(135deg,rgba(5,6,7,.9),rgba(11,23,18,.9));
  border:1px solid rgba(24,232,117,.1);display:flex;align-items:center;justify-content:center;cursor:pointer}
.je-curtain{position:absolute;top:0;bottom:0;width:50%;background:linear-gradient(180deg,var(--je-ac,#18E875),var(--je-ac2,#0D7A46));
  z-index:3;transition:transform .8s cubic-bezier(.65,0,.35,1)}
.je-curtain.left{left:0;transform-origin:left center}
.je-curtain.right{right:0;transform-origin:right center}
.je-reveal.open .je-curtain.left{transform:translateX(-100%)}
.je-reveal.open .je-curtain.right{transform:translateX(100%)}
.je-jersey{position:relative;z-index:2;text-align:center;opacity:0;transform:scale(.8);transition:all .6s ease .5s}
.je-reveal.open .je-jersey{opacity:1;transform:scale(1)}
.je-jersey img{max-height:220px;max-width:200px;object-fit:contain;filter:drop-shadow(0 20px 40px rgba(0,0,0,.5))}
.je-spotlight{position:absolute;top:-40%;left:50%;transform:translateX(-50%);width:200%;height:100%;
  background:radial-gradient(ellipse at center,rgba(24,232,117,.06),transparent 60%);z-index:1;pointer-events:none}
.je-reveal-btn{position:absolute;bottom:20px;left:50%;transform:translateX(-50%);z-index:5;
  padding:10px 28px;border-radius:12px;background:linear-gradient(90deg,var(--je-ac,#18E875),var(--je-ac2,#0D7A46));
  color:#fff;font-weight:900;font-size:.8rem;letter-spacing:2px;border:none;cursor:pointer;
  box-shadow:0 8px 24px rgba(24,232,117,.2);transition:all .3s}
.je-reveal-btn:hover{transform:translateX(-50%) translateY(-2px);box-shadow:0 12px 32px rgba(24,232,117,.3)}
.je-reveal.open .je-reveal-btn{opacity:0;pointer-events:none;transform:translateX(-50%) translateY(10px)}
/* GOLAZOX WOW — MOBILE CLUB SWIPE / IMAGE SAFETY */
.gx-club-swipe-wrap{position:relative}
.gx-club-swipe{position:relative;height:470px;overflow:hidden;border-radius:24px;touch-action:pan-y;isolation:isolate}
.gx-club-swipe-card{position:absolute;inset:0;width:100%;height:100%;border-radius:24px;overflow:hidden;border:1px solid color-mix(in srgb,var(--sw-ac,#18E875) 28%,rgba(255,255,255,.08));background:radial-gradient(circle at 50% 18%,color-mix(in srgb,var(--sw-ac,#18E875) 14%,transparent),transparent 34%),linear-gradient(180deg,#07100c 0%,#030605 100%);box-shadow:0 24px 60px rgba(0,0,0,.38);transform-origin:center center;backface-visibility:hidden;will-change:transform,opacity}
.gx-swipe-bg{position:absolute;inset:0;pointer-events:none;background:radial-gradient(circle at 50% 56%,color-mix(in srgb,var(--sw-ac,#18E875) 22%,transparent),transparent 31%),linear-gradient(135deg,color-mix(in srgb,var(--sw-ac,#18E875) 8%,transparent),transparent 58%)}
.gx-swipe-top{position:relative;z-index:3;display:flex;justify-content:space-between;align-items:center;padding:16px 16px 0;font-weight:900;color:#fff}
.gx-swipe-top span{font-size:.82rem}
.gx-swipe-top small{font-size:.63rem;color:rgba(255,255,255,.48);letter-spacing:1px}
.gx-swipe-stage{position:relative;z-index:2;height:315px;margin-top:2px;display:flex;align-items:center;justify-content:center;overflow:hidden;padding:12px 18px 0}
.gx-swipe-stage::before{content:"";position:absolute;left:50%;bottom:24px;width:68%;height:24px;transform:translateX(-50%);border-radius:50%;background:radial-gradient(ellipse,rgba(0,0,0,.58),transparent 70%);filter:blur(8px);pointer-events:none}
.gx-swipe-stage img{display:block!important;width:auto!important;height:auto!important;max-width:min(78%,300px)!important;max-height:295px!important;min-width:0!important;min-height:0!important;object-fit:contain!important;object-position:center!important;background:transparent!important;position:relative!important;z-index:3!important;filter:drop-shadow(0 24px 34px rgba(0,0,0,.58)) drop-shadow(0 0 28px color-mix(in srgb,var(--sw-ac,#18E875) 14%,transparent));transform:translateZ(0);}
.gx-swipe-glow{position:absolute;left:50%;top:46%;width:190px;height:190px;transform:translate(-50%,-50%);border-radius:50%;background:radial-gradient(circle,color-mix(in srgb,var(--sw-ac,#18E875) 18%,transparent),transparent 68%);filter:blur(4px);pointer-events:none}
.gx-swipe-bottom{position:absolute;left:0;right:0;bottom:0;z-index:4;display:flex;align-items:flex-end;justify-content:space-between;gap:12px;padding:14px 16px 16px;background:linear-gradient(180deg,transparent,rgba(0,0,0,.78) 36%)}
.gx-swipe-bottom b{display:block;font-size:1rem;font-weight:900}
.gx-swipe-bottom span{display:block;margin-top:3px;color:rgba(255,255,255,.46);font-size:.62rem;letter-spacing:1.3px}
.gx-swipe-cta{display:inline-flex;align-items:center;justify-content:center;min-height:42px;padding:10px 14px;border-radius:12px;background:linear-gradient(135deg,var(--sw-ac,#18E875),var(--sw-ac2,#0B9F50));color:#031009;font-size:.72rem;font-weight:900;white-space:nowrap;box-shadow:0 8px 20px color-mix(in srgb,var(--sw-ac,#18E875) 16%,transparent)}
.gx-swipe-controls{display:flex;align-items:center;justify-content:center;gap:12px;margin-top:12px}
.gx-swipe-arrow{width:38px;height:38px;border-radius:50%;border:1px solid rgba(255,255,255,.1);background:var(--card);color:var(--txt);font-size:1.25rem}
.gx-swipe-arrow:active{transform:scale(.94)}
.gx-swipe-dots{display:flex;gap:6px;align-items:center;justify-content:center}
.gx-dot{width:7px;height:7px;border:0;border-radius:50%;padding:0;background:rgba(255,255,255,.2);cursor:pointer}
.gx-dot.on{width:22px;border-radius:999px;background:var(--ac,#18E875)}
.gx-swipe-note{text-align:center;margin-top:8px;font-size:.65rem;font-weight:800;color:var(--mut);letter-spacing:1.2px}
@media(max-width:640px){.gx-club-swipe{height:435px;border-radius:20px}.gx-swipe-stage{height:286px;padding-top:8px}.gx-swipe-stage img{max-width:82%!important;max-height:270px!important}.gx-swipe-bottom{padding:12px}.gx-swipe-cta{min-height:40px;padding:9px 12px;font-size:.68rem}}

/* GOLAZOX WOW — CINEMATIC JERSEY REVEAL */
.je-reveal{isolation:isolate;touch-action:pan-y}
.je-reveal::before{content:"";position:absolute;inset:0;z-index:0;pointer-events:none;background:radial-gradient(circle at 50% 48%,var(--je-glow,rgba(24,232,117,.18)),transparent 30%),radial-gradient(circle at 50% 115%,rgba(255,255,255,.08),transparent 42%),linear-gradient(180deg,rgba(255,255,255,.025),transparent 55%)}
.je-reveal::after{content:"";position:absolute;inset:0;z-index:4;pointer-events:none;opacity:0;background:linear-gradient(115deg,transparent 24%,rgba(255,255,255,.22) 45%,transparent 62%);transform:translateX(-120%)}
.je-reveal.open::after{opacity:1;animation:jeSweep 1.05s cubic-bezier(.2,.7,.2,1) .12s both}
@keyframes jeSweep{to{transform:translateX(120%)}}
.je-stadium-lines{position:absolute;inset:0;z-index:1;opacity:.16;pointer-events:none;background:linear-gradient(90deg,transparent 49.7%,rgba(255,255,255,.34) 49.9%,rgba(255,255,255,.34) 50.1%,transparent 50.3%),radial-gradient(circle at 50% 55%,transparent 0 23%,rgba(255,255,255,.15) 23.3% 23.6%,transparent 23.9%)}
.je-halo{position:absolute;left:50%;top:50%;width:190px;height:190px;z-index:1;transform:translate(-50%,-50%);border-radius:50%;background:radial-gradient(circle,rgba(255,255,255,.08),transparent 62%);box-shadow:0 0 70px var(--je-glow,rgba(24,232,117,.15));opacity:.5}
.je-reveal.open .je-halo{animation:jeHalo .9s ease-out both}
@keyframes jeHalo{0%{transform:translate(-50%,-50%) scale(.65);opacity:.08}55%{opacity:.82}100%{transform:translate(-50%,-50%) scale(1.18);opacity:.22}}
.je-jersey{z-index:2}
.je-jersey img{max-height:230px;max-width:210px;transform:translateY(20px) scale(.86) rotate(-2deg);filter:drop-shadow(0 22px 34px rgba(0,0,0,.55)) drop-shadow(0 0 24px var(--je-glow,rgba(24,232,117,.12)))}
.je-reveal.open .je-jersey img{animation:jeJerseyIn .85s cubic-bezier(.16,1,.3,1) .42s both,jeJerseyFloat 4s ease-in-out 1.28s infinite}
@keyframes jeJerseyIn{0%{opacity:0;transform:translateY(60px) scale(.72) rotate(-6deg)}60%{opacity:1;transform:translateY(-8px) scale(1.04) rotate(2deg)}100%{opacity:1;transform:translateY(0) scale(1) rotate(0)}}
@keyframes jeJerseyFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}
.je-nameplate{position:absolute;left:50%;bottom:20px;transform:translate(-50%,8px);z-index:5;opacity:0;display:flex;flex-direction:column;align-items:center;gap:2px;white-space:nowrap;padding:8px 16px;border-radius:999px;background:rgba(0,0,0,.42);border:1px solid rgba(255,255,255,.11);backdrop-filter:blur(10px)}
.je-reveal.open .je-nameplate{animation:jeNameIn .55s ease 1s both}
@keyframes jeNameIn{to{opacity:1;transform:translate(-50%,0)}}
.je-nameplate b{font-size:.8rem;letter-spacing:1.4px;color:#fff;font-weight:900}.je-nameplate span{font-size:.57rem;letter-spacing:2px;color:rgba(255,255,255,.55);font-weight:800}
@media(max-width:560px){.je-reveal{height:255px}.je-jersey img{max-height:205px;max-width:185px}.je-halo{width:155px;height:155px}}
/* Locker */
.je-locker{margin-top:16px;display:flex;gap:16px;align-items:stretch;flex-wrap:wrap}
.je-locker-slot{flex:1;min-width:180px;padding:24px;border-radius:16px;background:rgba(10,13,12,.8);
  border:1px solid rgba(24,232,117,.1);text-align:center;position:relative;overflow:hidden}
.je-locker-slot::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--je-ac,#18E875)}
.je-locker-jersey{margin:0 auto 12px;width:120px;height:120px;border-radius:12px;overflow:hidden;
  background:rgba(255,255,255,.03);display:flex;align-items:center;justify-content:center}
.je-locker-jersey img{width:100%;height:100%;object-fit:contain;padding:8px}
.je-locker-name{font-weight:900;font-size:.9rem;letter-spacing:1px}
.je-locker-num{font-size:1.8rem;font-weight:900;color:var(--je-ac,#18E875);margin-top:4px;opacity:.5}
.je-locker-shelf{flex:1;min-width:140px;display:flex;flex-direction:column;gap:10px;justify-content:center}
.je-shelf-item{display:flex;align-items:center;gap:10px;padding:12px 16px;border-radius:12px;
  background:rgba(10,13,12,.6);border:1px solid rgba(255,255,255,.05);font-size:.8rem;font-weight:700;
  color:rgba(255,255,255,.6)}
.je-shelf-item span{font-size:1.1rem}
/* Tunnel */
.je-tunnel{position:relative;margin-top:16px;height:120px;border-radius:16px;overflow:hidden;
  background:linear-gradient(90deg,rgba(5,6,7,.9),rgba(10,13,12,.9));border:1px solid rgba(255,255,255,.05);display:flex;align-items:center;justify-content:center}
.je-tunnel-wall{position:absolute;top:0;bottom:0;width:30%;z-index:1}
.je-tunnel-wall.left{left:0;background:linear-gradient(90deg,rgba(10,13,12,1),transparent)}
.je-tunnel-wall.right{right:0;background:linear-gradient(270deg,rgba(10,13,12,1),transparent)}
.je-tunnel-road{position:absolute;inset:0;
  background:repeating-linear-gradient(90deg,transparent 0 30px,rgba(255,255,255,.02) 30px 32px);
  border-top:2px solid rgba(24,232,117,.1);border-bottom:2px solid rgba(24,232,117,.1)}
.je-tunnel-light{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:120px;height:120px;
  border-radius:50%;background:radial-gradient(circle,rgba(24,232,117,.08),transparent 70%);z-index:2;
  animation:tPulse 3s ease-in-out infinite}
@keyframes tPulse{0%,100%{opacity:.4;transform:translate(-50%,-50%) scale(1)}50%{opacity:.8;transform:translate(-50%,-50%) scale(1.2)}}
.je-tunnel-end{position:relative;z-index:3;font-weight:900;font-size:.9rem;letter-spacing:3px;
  color:rgba(24,232,117,.5);text-shadow:0 0 20px rgba(24,232,117,.2)}
/* Light theme */
html[data-theme="light"] .je-reveal{background:linear-gradient(135deg,#F8FAF9,#EDF5F0);border-color:rgba(24,232,117,.15)}
html[data-theme="light"] .je-locker-slot{background:#fff;border-color:rgba(24,232,117,.12)}
html[data-theme="light"] .je-shelf-item{background:#F8FAF9;border-color:rgba(0,0,0,.06)}
html[data-theme="light"] .je-tunnel{background:linear-gradient(90deg,#F0FDF4,#fff,#F0FDF4)}
/* Responsive */
@media (max-width:560px){
  .je-reveal{height:240px}
  .je-locker{flex-direction:column}
  .je-locker-slot{min-width:100%}
}
/* ============================== MATCH TICKET ============================== */
.mtk-page { min-height:100vh; background: #0B1712; position: relative; overflow: hidden; overflow-x:hidden; }
html[data-theme="light"] .mtk-page { background: #F3F6FB; }
.mtk-lights { position: fixed; top: -60px; left: 0; right: 0; display: flex; justify-content: space-around; pointer-events: none; z-index: 0; }
.mtk-light { width: 4px; height: 160px; background: linear-gradient(180deg, rgba(255,255,255,.5), transparent); filter: blur(2px); opacity: .3; animation: mtkLight 4s ease-in-out infinite; }
.mtk-light:nth-child(2) { animation-delay: -2s; }
@keyframes mtkLight { 0%,100%{opacity:.2;transform:rotate(-2deg)} 50%{opacity:.5;transform:rotate(2deg)} }
.mtk-wrap { max-width: 480px; margin: 0 auto; padding: 30px 18px 80px; position: relative; z-index: 1; }
.mtk-ticket {
  background: linear-gradient(180deg, var(--card2) 0%, var(--bg2) 100%);
  border: 1px solid rgba(24,232,117,.18); border-radius: 24px; overflow: hidden;
  box-shadow: 0 30px 70px rgba(0,0,0,.5), 0 0 50px rgba(24,232,117,.06);
  opacity: 0; transform: translateY(30px); transition: all .6s cubic-bezier(.2,.8,.3,1);
}
.mtk-ticket.mtk-reveal { opacity: 1; transform: none; }
html[data-theme="light"] .mtk-ticket { background: #FFFFFF; border-color: #E2E8F0; box-shadow: var(--sh2); }
.mtk-header { text-align: center; padding: 28px 20px 18px; }
.mtk-brand { font-family: 'Poppins','Cairo',sans-serif; font-size: 1.4rem; font-weight: 900; letter-spacing: 4px;
  background: linear-gradient(90deg, var(--ac), var(--ac2)); -webkit-background-clip: text; background-clip: text; color: transparent; }
.mtk-matchday { font-size: .72rem; font-weight: 900; letter-spacing: 3px; color: #6B7A73; margin-top: 4px; }
html[data-theme="light"] .mtk-matchday { color: #5B6782; }
.mtk-perf { height: 1px; border-top: 2px dashed rgba(24,232,117,.15); margin: 0 20px; position: relative; }
.mtk-perf::before, .mtk-perf::after { content: ''; position: absolute; top: -8px; width: 16px; height: 16px;
  border-radius: 50%; background: #0B1712; }
.mtk-perf::before { left: -28px; }
.mtk-perf::after { right: -28px; }
html[data-theme="light"] .mtk-perf::before, html[data-theme="light"] .mtk-perf::after { background: #F3F6FB; }
.mtk-code-section { text-align: center; padding: 20px; }
.mtk-code { font-size: 2rem; font-weight: 900; color: #F5F7F6; letter-spacing: 3px; font-family: 'Poppins','Cairo',monospace; }
html[data-theme="light"] .mtk-code { color: #0F172A; }
.mtk-code-label { font-size: .66rem; color: #4A5A54; letter-spacing: 2px; margin-top: 4px; font-weight: 800; }
.mtk-items-section { padding: 16px 20px; }
.mtk-section-title { font-size: .7rem; font-weight: 900; letter-spacing: 2px; color: #6B7A73; margin-bottom: 10px; }
html[data-theme="light"] .mtk-section-title { color: #5B6782; }
.mtk-item { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px dashed rgba(24,232,117,.08); }
.mtk-item:last-child { border-bottom: none; }
.mtk-item-ic { font-size: 1.4rem; width: 36px; text-align: center; }
.mtk-item-info { flex: 1; }
.mtk-item-info b { display: block; font-size: .88rem; color: #F5F7F6; }
html[data-theme="light"] .mtk-item-info b { color: #0F172A; }
.mtk-item-info span { font-size: .74rem; color: #6B7A73; }
.mtk-status-section { padding: 16px 20px; text-align: center; }
.mtk-status-label { font-size: .66rem; font-weight: 900; letter-spacing: 2px; color: #6B7A73; }
.mtk-status-pill {
  display: inline-flex; align-items: center; gap: 6px; margin-top: 8px;
  background: rgba(24,232,117,.1); border: 1px solid rgba(24,232,117,.3);
  border-radius: 999px; padding: 8px 20px; font-size: .88rem; font-weight: 900; color: #18E875;
}
html[data-theme="light"] .mtk-status-pill { background: #F0FDF4; border-color: #BBF7D0; color: #16A34A; }
/* Match Journey */
.mtk-journey { padding: 20px; }
.mtk-jtitle { text-align: center; font-weight: 900; font-size: .82rem; letter-spacing: 1px; color: #F5F7F6; margin-bottom: 16px; }
html[data-theme="light"] .mtk-jtitle { color: #0F172A; }
.mtk-jtrack { position: relative; height: 6px; border-radius: 999px; background: rgba(24,232,117,.08); margin-bottom: 16px; }
.mtk-jfill { position: absolute; inset: 0; border-radius: 999px; background: linear-gradient(90deg, var(--ac), var(--ac2)); transition: width 1s ease; }
.mtk-jball { position: absolute; top: -11px; transform: translateX(-50%); font-size: 22px; transition: left 1s ease; filter: drop-shadow(0 4px 8px rgba(0,0,0,.3)); z-index: 2; }
.mtk-jsteps { display: flex; justify-content: space-between; }
.mtk-jstep { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1; }
.mtk-jdot { width: 30px; height: 30px; border-radius: 50%; background: rgba(24,232,117,.06); border: 2px solid rgba(24,232,117,.12);
  display: flex; align-items: center; justify-content: center; font-size: .8rem; transition: all .3s; }
html[data-theme="light"] .mtk-jdot { background: #F1F5F9; border-color: #E2E8F0; }
.mtk-jstep.done .mtk-jdot { background: var(--ac); border-color: var(--ac); }
.mtk-jstep.cur .mtk-jdot { background: var(--ac); border-color: var(--ac); animation: pulse 1.4s infinite; box-shadow: 0 0 16px rgba(24,232,117,.4); }
.mtk-jstep b { font-size: .6rem; color: #6B7A73; font-weight: 800; text-align: center; }
.mtk-jstep.done b, .mtk-jstep.cur b { color: #F5F7F6; }
html[data-theme="light"] .mtk-jstep.done b, html[data-theme="light"] .mtk-jstep.cur b { color: #0F172A; }
/* Goal Celebration */
.mtk-goal {
  display: none; text-align: center; padding: 24px 20px; font-size: 1.6rem; font-weight: 900; color: #18E875;
  text-shadow: 0 8px 30px rgba(24,232,117,.3);
}
.mtk-goal.show { display: block; animation: mtkGoalIn .6s ease; }
.mtk-goal span { display: block; font-size: .88rem; color: #6B7A73; margin-top: 6px; font-weight: 700; }
@keyframes mtkGoalIn { from { opacity:0; transform:scale(.8); } to { opacity:1; transform:none; } }
/* QR */
.mtk-qr { text-align: center; padding: 20px; }
.mtk-qr img { border-radius: 14px; border: 2px solid rgba(24,232,117,.1); }
.mtk-qr-label { font-size: .66rem; color: #4A5A54; margin-top: 6px; letter-spacing: 1px; }
/* Footer */
.mtk-footer { text-align: center; padding: 16px 20px 24px; }
.mtk-footer-brand { font-family: 'Poppins','Cairo',sans-serif; font-size: .82rem; font-weight: 900; letter-spacing: 3px; color: #4A5A54; }
.mtk-footer-date { font-size: .72rem; color: #4A5A54; margin-top: 4px; }
/* Buttons */
.mtk-btns { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; margin-top: 18px; }
.mtk-btns .btn { flex: 1; min-width: 100px; justify-content: center; }
@media (max-width: 480px) {
  .mtk-code { font-size: 1.6rem; }
  .mtk-jstep b { font-size: .52rem; }
  .mtk-jdot { width: 26px; height: 26px; font-size: .7rem; }
}
/* ============================== COMPREHENSIVE MOBILE FIXES ============================== */
@media (max-width:768px) {
  .wrap { padding:14px 12px 110px; }
  html[data-theme="light"] .wrap { padding-bottom:100px; }
  .gx-bnav { padding-bottom:env(safe-area-inset-bottom); }
  .hero { padding:24px 16px; margin-bottom:16px; border-radius:18px; }
  .hero h1 { font-size:1.5rem; line-height:1.2; }
  .hero p { font-size:.88rem; line-height:1.7; }
  .hero-btns { margin-top:14px; gap:8px; }
  .hero-btns .btn { flex:1; min-width:0; justify-content:center; padding:11px 14px; font-size:.88rem; }
  .hero-ball { display:none; }
  .hero-tag { font-size:.6rem; padding:5px 10px; margin-bottom:12px; }
  .hero-brand { font-size:1.6rem; letter-spacing:3px; }
  .sec { margin-bottom:20px; }
  .sec-head { margin-bottom:10px; }
  .sec-head h2 { font-size:1.15rem; }
  .grid { gap:12px; }
  .pg { grid-template-columns:1fr; gap:16px; }
  .gal { position:static; }
  .gmain { perspective:none; transform:none!important; border-radius:18px; }
  .gmain img { height:auto; max-height:300px; object-fit:contain; filter:drop-shadow(0 8px 16px rgba(0,0,0,.2)); }
  .gmain::before { filter:blur(20px); opacity:.3; }
  .gmain::after { height:12px; bottom:-6px; }
  .pimg { height:180px; }
  .pimg img { width:90%; height:90%; }
  .pinfo h1 { font-size:1.2rem; }
  .okpage { padding:0 12px; }
  .ok-card { padding:28px 16px; border-radius:18px; }
  .ok-anim { font-size:42px; }
  .ok-card h1 { font-size:1.25rem; }
  .ok-code { font-size:1.2rem; }
  .ok-btns { flex-direction:column; gap:8px; margin-top:16px; }
  .ok-btns .btn { min-width:0; width:100%; padding:12px; font-size:.9rem; }
  .ticket { padding:0 12px; }
  .tk { border-radius:18px; }
  .tk-top { padding:14px 16px; }
  .tk-stub { padding:14px 16px; }
  .tk-items { padding:12px 16px; }
  .tk-btns { grid-template-columns:1fr; padding:12px 16px 16px; gap:8px; }
  .tk-total { padding:10px 16px; }
  .tk-btns .btn { padding:11px; font-size:.88rem; }
  .cd { width:100%; max-width:100vw; top:auto; bottom:0; left:0; right:0; inset-inline-end:0;
    height:auto; max-height:88dvh; max-height:88vh; border-radius:20px 20px 0 0;
    border-left:none; border-top:1px solid rgba(24,232,117,.10); box-shadow:0 -12px 40px rgba(0,0,0,.5); }
  .cd-head { padding:12px 14px; }
  .cd-body { flex:0 1 auto; max-height:42vh; padding:10px 14px; }
  .cd-foot { padding:12px 14px; padding-bottom:calc(12px + env(safe-area-inset-bottom)); }
  .ci { gap:10px; padding:10px 0; }
  .ci-emoji { font-size:1.3rem; }
  .ci-tx b { font-size:.82rem; }
  .ci-tx span { font-size:.74rem; }
  .btn { padding:10px 18px; font-size:.88rem; }
  .btn.big { padding:12px; font-size:.92rem; }
  .btn.sm { padding:7px 12px; font-size:.8rem; }
  .fab { bottom:76px; width:48px; height:48px; font-size:20px; }
  .toast { bottom:80px; font-size:.82rem; padding:10px 16px; }
  .mkmode-toggle { bottom:66px; inset-inline-end:10px; padding:4px 8px; }
  .mkmode-toggle .mkmode-lbl { font-size:.55rem; }
  .pen-pitch { height:300px; }
  .pen-goal { width:240px; height:110px; }
  .pen-zone { width:56px; height:38px; font-size:.6rem; }
  .pen-keeper { width:60px; height:96px; }
  .pen-keeper .kb { width:60px; height:76px; }
  .spotlight-card { flex-direction:column; text-align:center; padding:16px; gap:14px; border-radius:18px; }
  .spotlight-img { width:100%; height:180px; border-radius:14px; }
  .spotlight-info h3 { font-size:1.05rem; }
  .spotlight-price { font-size:1.2rem; }
  .sg-hero { min-height:auto; padding:24px 14px; }
  .sg-hero-inner { flex-direction:column; text-align:center; gap:14px; }
  .sg-hero-jersey { font-size:64px; }
  .sg-hero-text h1 { font-size:1.4rem; }
  .sg-calc-card { padding:20px 14px; border-radius:18px; }
  .sg-calc-inputs { grid-template-columns:1fr; gap:10px; }
  .sg-trust-bar { grid-template-columns:1fr 1fr; gap:8px; padding:0 14px; }
  .outfit-items { gap:6px; }
  .outfit-item { min-width:68px; padding:8px 10px; }
  .outfit-plus { display:none; }
  .outfit-header { flex-direction:column; gap:8px; }
  .je-reveal { height:200px; border-radius:14px; }
  .je-locker { flex-direction:column; gap:10px; }
  .je-locker-slot { min-width:100%; padding:16px; }
  .hw-timeline { grid-template-columns:1fr; gap:12px; }
  .hw-prices { padding:18px 14px; border-radius:18px; }
  .hw-price-grid { grid-template-columns:1fr; gap:10px; }
  .hw-ctas { flex-direction:column; }
  .hw-ctas .btn { width:100%; justify-content:center; }
  .ft-grid { grid-template-columns:1fr; gap:16px; }
  .pitch-sec { padding:36px 16px; border-radius:18px; }
  .pitch-sec h2 { font-size:1.2rem; }
  .club-banner { padding:22px 14px; border-radius:18px; }
  .club-banner h1 { font-size:1.5rem; }
  .clubs { grid-template-columns:repeat(auto-fill,minmax(90px,1fr)); gap:8px; }
  .clubcard { padding:12px 6px 10px; border-radius:14px; }
  .cc-logo { width:48px; height:48px; font-size:22px; }
  .clubcard b { font-size:.82rem; }
  .szsec-banner { padding:18px 14px; border-radius:18px; gap:10px; }
  .szsec-banner h2 { font-size:1.1rem; }
  .loyal { padding:20px 14px; border-radius:18px; }
  .loyal .loyal-q { font-size:1.1rem; }
  .loy-btn { width:74px; padding:10px 4px; }
  .list-search { padding:16px 14px; border-radius:18px; }
  .list-search h1 { font-size:1.2rem; }
  .list-search .ls-box input { min-width:0; padding:11px 12px; font-size:.88rem; }
  .feat-bar { padding:14px 12px; border-radius:14px; margin-bottom:20px; }
  .feat b { font-size:.82rem; }
  .feat span { font-size:.7rem; }
  .stat-cards { grid-template-columns:repeat(2,1fr); gap:8px; }
  .stat { padding:12px; border-radius:12px; }
  .stat b { font-size:1.2rem; }
  .adm { padding:14px 12px 50px; }
  .mbox { border-radius:16px; max-width:96vw; }
  .mhead { padding:12px 14px; }
  .mbody { padding:14px; }
  .sb { gap:6px; }
  .sbox { min-width:0; }
  .links3 { grid-template-columns:1fr; gap:8px; }
  .qcard { padding:14px; border-radius:14px; }
  .poll { padding:16px; border-radius:14px; }
  .drop-banner { padding:18px 14px; border-radius:18px; }
  .drop-banner h2 { font-size:1.2rem; }
  .md-banner { padding:18px 14px; border-radius:18px; gap:12px; }
  .md-teams { font-size:1rem; }
  .acc-card { padding:12px; border-radius:14px; }
  .acc-hero { padding:16px; border-radius:16px; }
  .acc-hero h2 { font-size:1.2rem; }
  .pp-card { padding:16px; border-radius:16px; }
  .dna-grid { grid-template-columns:repeat(2,1fr); gap:8px; }
  .dna-cell { padding:10px; border-radius:12px; }
  .al-box { padding:0 12px; }
  .al-item { padding:10px 12px; border-radius:12px; }
  .os-card { padding:16px 12px; border-radius:14px; margin-bottom:14px; }
  .os-title { font-size:.92rem; }
  .os-path { margin-top:18px; }
  .os-station { width:58px; font-size:.6rem; }
  .os-station .ic { width:36px; height:36px; font-size:1rem; }
  .os-msg { font-size:.85rem; margin-top:22px; }
  .tj { gap:4px; }
  .tj .tj-step { min-width:60px; }
  .tj .tj-dot { width:22px; height:22px; font-size:.7rem; }
  .mk-hero { min-height:auto; padding:40px 14px 24px; }
  .mk-title { font-size:1.4rem; }
  .mk-ticket { max-width:100%; border-radius:14px; }
  .mk-ticket-top, .mk-ticket-mid { padding:14px 14px 12px; }
  .mk-ticket-bottom { padding:12px 14px; flex-direction:column; align-items:center; }
  .mk-detail-grid { gap:8px 12px; }
  .mk-fan { padding:16px; border-radius:14px; }
  .mtk-wrap { padding:18px 12px 80px; }
  .mtk-ticket { border-radius:16px; }
  .mtk-header { padding:18px 14px 12px; }
  .mtk-items-section, .mtk-status-section, .mtk-journey, .mtk-qr, .mtk-footer { padding-left:14px; padding-right:14px; }
}
@media (max-width:480px) {
  .wrap { padding:10px 10px 100px; }
  .hero { padding:18px 12px; }
  .hero h1 { font-size:1.3rem; }
  .hero-brand { font-size:1.3rem; letter-spacing:2px; }
  .pinfo h1 { font-size:1.1rem; }
  .gmain img { max-height:260px; }
  .ok-card { padding:22px 12px; }
  .ok-card h1 { font-size:1.1rem; }
  .grid { gap:10px; }
  .clubcard b { font-size:.76rem; }
  .cc-logo { width:42px; height:42px; font-size:20px; }
  .clubs { grid-template-columns:repeat(auto-fill,minmax(80px,1fr)); gap:6px; }
  .ft-grid { gap:14px; }
  .sg-trust-bar { grid-template-columns:1fr; }
  .outfit-item { min-width:60px; padding:8px 8px; }
  .outfit-ic { font-size:1.6rem; }
  .pen-pitch { height:260px; }
  .pen-goal { width:200px; height:90px; }
}
/* ===== GOLAXOX MOBILE EXPERIENCE UPGRADE ===== */
.gx-fan-moment{margin:18px 0;padding:14px 16px;border:1px solid rgba(24,232,117,.14);border-radius:18px;background:linear-gradient(135deg,rgba(24,232,117,.07),rgba(255,255,255,.025));display:flex;align-items:center;justify-content:center;gap:10px;text-align:center;min-height:52px}
.gx-fan-moment .fm-dot{width:8px;height:8px;border-radius:50%;background:#18E875;box-shadow:0 0 12px rgba(24,232,117,.6);animation:fmPulse 1.8s ease-in-out infinite}
.gx-fan-moment .fm-text{font-weight:800;color:var(--txt);font-size:.86rem}
.gx-fan-moment .fm-sub{font-size:.68rem;color:var(--mut);margin-right:4px}
@keyframes fmPulse{0%,100%{transform:scale(.8);opacity:.55}50%{transform:scale(1.15);opacity:1}}

.gx-recent-tunnel{position:relative;overflow:hidden;border-radius:22px;border:1px solid rgba(24,232,117,.16);background:
radial-gradient(circle at 50% 100%,rgba(24,232,117,.16),transparent 48%),
linear-gradient(180deg,#06110c,#030605);padding:18px 14px 20px}
.gx-recent-tunnel:before{content:"";position:absolute;inset:0;background:repeating-linear-gradient(90deg,transparent 0 42px,rgba(24,232,117,.035) 42px 44px);pointer-events:none}
.gx-recent-track{display:flex;gap:12px;overflow-x:auto;padding:5px 2px 8px;scroll-snap-type:x mandatory;scrollbar-width:none}
.gx-recent-track::-webkit-scrollbar{display:none}
.gx-recent-card{flex:0 0 min(180px,48vw);scroll-snap-align:center;border:1px solid rgba(255,255,255,.08);border-radius:18px;background:rgba(0,0,0,.28);padding:10px;position:relative;transition:.22s;box-shadow:0 8px 24px rgba(0,0,0,.25)}
.gx-recent-card.is-main{border-color:rgba(24,232,117,.5);box-shadow:0 0 24px rgba(24,232,117,.16)}
.gx-recent-card img{width:100%;aspect-ratio:4/5;object-fit:contain;display:block}
.gx-recent-card .rc-name{font-weight:900;font-size:.78rem;margin-top:8px}
.gx-recent-card .rc-price{color:#18E875;font-weight:900;font-size:.78rem;margin-top:4px}
.gx-recent-empty{padding:24px 14px;text-align:center;color:var(--mut);font-size:.8rem}

.gx-final-pitch{margin:22px 0;border-radius:24px;min-height:250px;position:relative;overflow:hidden;border:1px solid rgba(24,232,117,.18);background:
radial-gradient(circle at 50% 45%,rgba(24,232,117,.18),transparent 28%),
linear-gradient(180deg,#06110b 0%,#0a2216 58%,#031008 100%)}
.gx-final-pitch:before{content:"";position:absolute;inset:auto 0 0;height:58%;background:
linear-gradient(90deg,transparent 49.6%,rgba(255,255,255,.16) 49.8%,rgba(255,255,255,.16) 50.2%,transparent 50.4%),
linear-gradient(180deg,transparent,rgba(255,255,255,.035))}
.gx-final-pitch .fp-content{position:relative;z-index:2;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:250px;text-align:center;padding:24px}
.gx-final-pitch .fp-ball{font-size:3rem;filter:drop-shadow(0 0 20px rgba(255,255,255,.18));animation:fpBall 2.6s ease-in-out infinite}
.gx-final-pitch h2{margin-top:8px;font-size:clamp(1.3rem,5vw,2rem);font-weight:900}
.gx-final-pitch p{margin-top:6px;color:var(--mut);font-size:.8rem}
.gx-final-pitch .fp-actions{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:14px}
@keyframes fpBall{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}

@media(max-width:768px){
  .gx-fan-moment{margin:12px 0;padding:12px 10px;min-height:48px}
  .gx-fan-moment .fm-text{font-size:.75rem}
  .gx-fan-moment .fm-sub{font-size:.58rem}
  .gx-recent-tunnel{padding:14px 10px;border-radius:18px}
  .gx-recent-card{flex-basis:150px;border-radius:16px}
  .gx-final-pitch{min-height:220px;margin:16px 0}
  .gx-final-pitch .fp-content{min-height:220px;padding:18px}
  .gx-final-pitch .fp-actions .btn{min-height:46px;padding:10px 14px}
}
@media(prefers-reduced-motion:reduce){
  .gx-fan-moment .fm-dot,.gx-final-pitch .fp-ball{animation:none}
}

/* ============================== ULTIMATE WOW MOBILE ============================== */
.gx-wow-scan{position:relative;min-height:520px;margin:24px 0;border-radius:30px;overflow:hidden;border:1px solid rgba(255,255,255,.1);background:radial-gradient(circle at 50% 35%,rgba(24,232,117,.16),transparent 24%),linear-gradient(180deg,#020403,#07140d 56%,#020403);box-shadow:0 24px 70px rgba(0,0,0,.45)}
.gx-wow-scan:before{content:"";position:absolute;inset:0;background:repeating-linear-gradient(90deg,transparent 0 48px,rgba(255,255,255,.028) 48px 50px);pointer-events:none}
.gx-scan-light{position:absolute;left:50%;top:-18%;width:180px;height:760px;transform:translateX(-50%);background:linear-gradient(180deg,rgba(255,255,255,.18),rgba(24,232,117,.08),transparent);filter:blur(18px);animation:gxScanLight 4s ease-in-out infinite}
@keyframes gxScanLight{0%,100%{opacity:.38;transform:translateX(-50%) scaleX(.85)}50%{opacity:.8;transform:translateX(-50%) scaleX(1.15)}}
.gx-scan-head{position:relative;z-index:2;text-align:center;padding:28px 18px 8px}.gx-scan-kicker{font-size:.62rem;letter-spacing:3px;color:#18e875;font-weight:900}.gx-scan-title{font-size:clamp(1.6rem,7vw,2.5rem);font-weight:900;margin-top:7px}.gx-scan-sub{color:var(--mut);font-size:.8rem;margin-top:5px}
.gx-scan-stage{position:relative;z-index:2;height:320px;display:flex;align-items:center;justify-content:center;touch-action:none;cursor:grab}.gx-scan-stage.dragging{cursor:grabbing}.gx-scan-stage:after{content:"";position:absolute;bottom:40px;width:58%;height:18px;border-radius:50%;background:radial-gradient(ellipse,rgba(0,0,0,.55),transparent 70%);filter:blur(7px)}
.gx-scan-jersey{width:min(70vw,300px);height:300px;object-fit:contain;filter:drop-shadow(0 24px 36px rgba(0,0,0,.55)) drop-shadow(0 0 35px var(--sw-ac,#18e875));transition:transform .25s ease;user-select:none;-webkit-user-drag:none}
.gx-scan-meta{position:absolute;left:14px;right:14px;bottom:16px;z-index:3;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border-radius:16px;background:rgba(0,0,0,.34);border:1px solid rgba(255,255,255,.08);backdrop-filter:blur(12px)}.gx-scan-meta b{font-size:.9rem}.gx-scan-meta span{display:block;color:var(--mut);font-size:.68rem;margin-top:2px}.gx-scan-pill{padding:8px 11px;border-radius:999px;background:rgba(24,232,117,.11);color:#18e875;font-size:.66rem;font-weight:900;white-space:nowrap}
.gx-scan-btn{position:relative;z-index:3;display:inline-flex;align-items:center;justify-content:center;gap:8px;margin:4px auto 20px;padding:13px 18px;border-radius:14px;background:linear-gradient(135deg,#18e875,#0b9f50);color:#031009;font-weight:900;border:none;box-shadow:0 10px 30px rgba(24,232,117,.18)}
.gx-reaction{display:inline-flex;align-items:center;gap:8px;margin-top:9px;padding:6px 10px;border-radius:999px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);font-size:.66rem;color:rgba(255,255,255,.72)}.gx-reaction-dot{width:7px;height:7px;border-radius:50%;background:#18e875;box-shadow:0 0 12px rgba(24,232,117,.6);animation:gxReact 1s ease-in-out infinite}.gx-reaction.burst{animation:gxBurst .55s ease both}.gx-reaction.burst .gx-reaction-dot{background:#fff;box-shadow:0 0 18px #fff}@keyframes gxReact{50%{transform:scale(1.35);opacity:.75}}@keyframes gxBurst{0%{transform:scale(.95)}45%{transform:scale(1.05)}100%{transform:scale(1)}}
.gx-quiz{position:relative;margin:24px 0;padding:22px;border-radius:24px;border:1px solid rgba(24,232,117,.14);background:linear-gradient(135deg,rgba(24,232,117,.08),rgba(255,255,255,.025));overflow:hidden}.gx-quiz h2{font-size:1.25rem;font-weight:900}.gx-quiz p{color:var(--mut);font-size:.8rem;margin-top:5px}.gx-quiz-q{margin-top:17px;font-weight:900;font-size:1rem}.gx-quiz-opts{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}.gx-qopt{border:1px solid var(--line);background:var(--card);color:var(--txt);border-radius:14px;padding:12px 10px;font-family:inherit;font-weight:800;text-align:start;cursor:pointer}.gx-qopt.on{border-color:var(--ac);box-shadow:0 0 0 1px var(--ac),0 0 22px color-mix(in srgb,var(--ac) 15%,transparent);}.gx-quiz-result{display:none;margin-top:16px;padding:16px;border-radius:16px;background:rgba(0,0,0,.22);border:1px solid rgba(255,255,255,.08)}.gx-quiz-result.show{display:block;animation:fadeUp .35s ease}.gx-match-line{color:var(--mut);font-size:.72rem}.gx-match-name{font-size:1.35rem;font-weight:900;margin-top:4px}.gx-quiz-go{margin-top:12px}
.gx-walk{position:relative;min-height:620px;border-radius:30px;overflow:hidden;margin:28px 0;background:linear-gradient(180deg,#020403 0%,#081b10 58%,#020403 100%);border:1px solid rgba(24,232,117,.14)}.gx-walk:before{content:"";position:absolute;left:50%;bottom:-10%;width:115%;height:70%;transform:translateX(-50%) perspective(700px) rotateX(67deg);background:linear-gradient(90deg,transparent 49.7%,rgba(255,255,255,.14) 49.9%,rgba(255,255,255,.14) 50.1%,transparent 50.3%),repeating-linear-gradient(90deg,rgba(255,255,255,.02) 0 44px,transparent 44px 88px),linear-gradient(180deg,#123c24,#06130c)}.gx-walk-side{position:absolute;top:15%;bottom:12%;width:22%;background:repeating-linear-gradient(180deg,rgba(255,255,255,.07) 0 9px,transparent 9px 22px);filter:blur(.3px);opacity:.5}.gx-walk-side.l{left:3%;transform:skewY(-8deg)}.gx-walk-side.r{right:3%;transform:skewY(8deg)}.gx-walk-lights{position:absolute;inset:0;pointer-events:none;background:radial-gradient(circle at 16% 18%,rgba(255,255,255,.28),transparent 9%),radial-gradient(circle at 84% 18%,rgba(255,255,255,.28),transparent 9%),radial-gradient(circle at 50% 8%,rgba(24,232,117,.12),transparent 26%);mix-blend-mode:screen}.gx-walk-content{position:relative;z-index:3;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:620px;text-align:center;padding:28px}.gx-walk-kicker{font-size:.62rem;letter-spacing:3px;color:#18e875;font-weight:900}.gx-walk h2{font-size:clamp(1.8rem,8vw,3rem);font-weight:900;margin-top:8px}.gx-walk p{max-width:360px;color:var(--mut);font-size:.82rem;line-height:1.7;margin-top:7px}.gx-walk-jersey{width:min(68vw,290px);height:320px;object-fit:contain;filter:drop-shadow(0 22px 40px rgba(0,0,0,.65)) drop-shadow(0 0 40px rgba(24,232,117,.14));animation:gxWalkJersey 3.2s ease-in-out infinite}.gx-walk.unlocked .gx-walk-jersey{animation:gxWalkReveal .8s cubic-bezier(.22,1,.36,1) both}@keyframes gxWalkJersey{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}@keyframes gxWalkReveal{from{transform:translateY(55px) scale(.78);opacity:0;filter:blur(8px) drop-shadow(0 0 0 transparent)}to{transform:none;opacity:1;filter:drop-shadow(0 22px 40px rgba(0,0,0,.65)) drop-shadow(0 0 40px rgba(24,232,117,.18))}}.gx-walk-btn{margin-top:12px;padding:14px 22px;border-radius:15px;border:1px solid rgba(24,232,117,.36);background:rgba(0,0,0,.32);color:#fff;font-family:inherit;font-weight:900;cursor:pointer;backdrop-filter:blur(10px)}.gx-walk-btn:hover{background:rgba(24,232,117,.12)}
.gx-scan-toast{position:fixed;left:50%;bottom:104px;transform:translate(-50%,15px);opacity:0;z-index:500;padding:11px 15px;border-radius:999px;background:rgba(5,6,7,.9);color:#fff;border:1px solid rgba(24,232,117,.24);backdrop-filter:blur(10px);font-size:.76rem;font-weight:800;pointer-events:none;transition:.28s}.gx-scan-toast.show{opacity:1;transform:translate(-50%,0)}
@media(max-width:640px){.gx-wow-scan{min-height:560px;border-radius:24px}.gx-scan-stage{height:340px}.gx-scan-jersey{width:min(76vw,280px);height:310px}.gx-quiz-opts{grid-template-columns:1fr}.gx-walk{min-height:580px;border-radius:24px}.gx-walk-content{min-height:580px}.gx-walk-jersey{height:300px}}
@media(prefers-reduced-motion:reduce){.gx-scan-light,.gx-reaction-dot,.gx-walk-jersey{animation:none!important}}

</style>
"""

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
  var th=gxGet('gx_theme_v2','dark'); document.documentElement.setAttribute('data-theme',th);
  var fs=gxGet('gx_font','b'); document.documentElement.setAttribute('data-font',fs);
  var club=gxGet('gx_club',null); if(club) document.documentElement.setAttribute('data-club',club);
}
function setTheme(t){ gxSet('gx_theme_v2',t); applyPrefs(); syncPrefs(); }
function setFont(f){ gxSet('gx_font',f); applyPrefs(); syncPrefs(); }
function setMyClub(cid){ gxSet('gx_club',cid); applyPrefs(); syncPrefs(); if(cid) toast(gxT('md_choice_ok')); }
function syncPrefs(){
  var th=gxGet('gx_theme_v2','dark'), fs=gxGet('gx_font','b'), club=gxGet('gx_club',null);
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
  function showAll(){ els.forEach(function(el){ el.classList.add('in'); }); }
  if(!('IntersectionObserver' in window)){ showAll(); return; }
  try{
    var io=new IntersectionObserver(function(es){ es.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); } }); }, {threshold:.08});
    els.forEach(function(el){ io.observe(el); });
  }catch(err){ showAll(); return; }
  setTimeout(showAll, 2500);
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
function pmoney(v){ var n=Math.round(Number(v)*1000)/1000; return Number.isInteger(n)?String(n):String(n).replace(/0+$/,"").replace(/[.]$/,""); }
/* ---------- search & filters ---------- */
var filters={club:'all',type:'all',size:'all',color:'all',cat:'all',fav:false};
function gxStock(c){ try{ return JSON.parse(c.getAttribute('data-stock')||'{}'); }catch(e){ return {}; } }
function applyFilters(){
  var q=((($('sq')||{}).value)||'').trim().toLowerCase();
  var q2=((($('sq2')||{}).value)||'').trim().toLowerCase();
  if(!q) q=q2;
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
      var hay=((c.getAttribute('data-search')||'')+' '+(c.getAttribute('data-name')||'')+' '+(c.getAttribute('data-clubn')||'')).toLowerCase();
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
  var sq2=$('sq2'); if(sq2) sq2.value='';
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
      +'<button class="heart on" onclick="toggleFav(\\''+p.id+'\\',this)">❤</button>'
      +'<a href="/product/'+p.id+'"><div class="pimg" style="background:linear-gradient(135deg,'+p.colors[0]+','+p.colors[1]+')">'
      +'<img src="/img/'+p.imgs[0]+'" alt=""></div></a>'
      +'<div class="pbody"><span class="pcat">'+(p.kind==='mug'?gxT('cat_mug'):gxT('cat_jersey'))+'</span><h3>'+esc(p[GX.lang==='ar'?'name_ar':'name_en'])+'</h3>'
      +'<div class="pfoot"><b>'+pmoney(p.price)+' '+GX.cur+'</b><a class="pview" href="/product/'+p.id+'">'+gxT('view')+' ←</a></div></div></div>';
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
/* ---------- lightbox: zoom / pan / pinch / keyboard ---------- */
var lbIndex=0, lbZoomLv=1, lbPanX=0, lbPanY=0, lbDrag=null, lbPinchD=0, lbPinchZ=1;
function lbApply(){
  var img=$('lbimg'); if(!img) return;
  img.style.transform='translate('+lbPanX+'px,'+lbPanY+'px) scale('+lbZoomLv+')';
  img.style.cursor=lbZoomLv>1?'grab':'zoom-in';
  var p=$('lbPct'); if(p) p.textContent=Math.round(lbZoomLv*100)+'%';
}
function lbClampPan(){
  var max=140*(lbZoomLv-1); if(max<0) max=0;
  if(lbPanX>max) lbPanX=max; if(lbPanX<-max) lbPanX=-max;
  if(lbPanY>max) lbPanY=max; if(lbPanY<-max) lbPanY=-max;
}
function openLB(i){
  var img=$('lbimg');
  if(typeof i==='string'){
    // standalone image (e.g. review photo) — no gallery navigation
    gN=0; img.src=i; lbZoomLv=1; lbPanX=0; lbPanY=0; lbApply();
    var cnt0=$('lbCount'); if(cnt0) cnt0.style.display='none';
    var pv0=$('lbPrev'), nx0=$('lbNext'); if(pv0) pv0.style.display='none'; if(nx0) nx0.style.display='none';
    $('lb').classList.add('open'); document.body.style.overflow='hidden'; return;
  }
  var arr=(typeof GARR!=='undefined'&&GARR&&GARR.length)?GARR:[$('gmain')?$('gmain').src.split('/img/')[1]:''];
  lbIndex=(typeof i==='number')?i:(gi||0); gN=arr.length;
  img.src='/img/'+(arr[lbIndex]||arr[0]);
  lbZoomLv=1; lbPanX=0; lbPanY=0; lbApply();
  var cnt=$('lbCount'); if(cnt){ if(gN>1){ cnt.style.display=''; cnt.textContent=(lbIndex+1)+' '+gxT('img_of')+' '+gN; } else cnt.style.display='none'; }
  var pv=$('lbPrev'), nx=$('lbNext'); if(pv) pv.style.display=gN>1?'':'none'; if(nx) nx.style.display=gN>1?'':'none';
  $('lb').classList.add('open'); document.body.style.overflow='hidden';
}
function closeLB(){ $('lb').classList.remove('open'); document.body.style.overflow=''; }
function lbNav(d){
  var arr=(typeof GARR!=='undefined'&&GARR)?GARR:[]; if(!arr.length) return;
  lbIndex=(lbIndex+d+arr.length)%arr.length; $('lbimg').src='/img/'+arr[lbIndex];
  lbZoomLv=1; lbPanX=0; lbPanY=0; lbApply();
  var cnt=$('lbCount'); if(cnt) cnt.textContent=(lbIndex+1)+' '+gxT('img_of')+' '+arr.length;
}
function lbZoom(dir,step){
  step=step||.25; lbZoomLv=Math.min(3,Math.max(.5,lbZoomLv+dir*step));
  if(lbZoomLv<=1){ lbPanX=0; lbPanY=0; } lbClampPan(); lbApply();
}
function lbReset(){ lbZoomLv=1; lbPanX=0; lbPanY=0; lbApply(); }
document.addEventListener('DOMContentLoaded',function(){
  var lb=$('lb'), stage=$('lbStage'), img=$('lbimg'); if(!lb||!img) return;
  stage.addEventListener('click',function(e){ if(e.target===stage) closeLB(); });
  lb.addEventListener('wheel',function(e){ if(!lb.classList.contains('open')) return; e.preventDefault();
    lbZoom(e.deltaY<0?1:-1,.15); }, {passive:false});
  img.addEventListener('mousedown',function(e){ if(lbZoomLv<=1) return; e.preventDefault();
    lbDrag={x:e.clientX,y:e.clientY,px:lbPanX,py:lbPanY}; img.classList.add('dragging'); });
  window.addEventListener('mousemove',function(e){ if(!lbDrag) return;
    lbPanX=lbDrag.px+(e.clientX-lbDrag.x); lbPanY=lbDrag.py+(e.clientY-lbDrag.y); lbClampPan(); lbApply(); });
  window.addEventListener('mouseup',function(){ if(lbDrag){ lbDrag=null; img.classList.remove('dragging'); } });
  img.addEventListener('touchstart',function(e){
    if(e.touches.length===2){
      lbPinchD=Math.hypot(e.touches[0].clientX-e.touches[1].clientX, e.touches[0].clientY-e.touches[1].clientY);
      lbPinchZ=lbZoomLv;
    } else if(e.touches.length===1 && lbZoomLv>1){
      lbDrag={x:e.touches[0].clientX,y:e.touches[0].clientY,px:lbPanX,py:lbPanY};
    }
  }, {passive:true});
  img.addEventListener('touchmove',function(e){
    if(e.touches.length===2 && lbPinchD){ e.preventDefault();
      var d=Math.hypot(e.touches[0].clientX-e.touches[1].clientX, e.touches[0].clientY-e.touches[1].clientY);
      lbZoomLv=Math.min(3,Math.max(.5,lbPinchZ*(d/lbPinchD))); if(lbZoomLv<=1){lbPanX=0;lbPanY=0;} lbClampPan(); lbApply();
    } else if(e.touches.length===1 && lbDrag){ e.preventDefault();
      lbPanX=lbDrag.px+(e.touches[0].clientX-lbDrag.x); lbPanY=lbDrag.py+(e.touches[0].clientY-lbDrag.y);
      lbClampPan(); lbApply();
    }
  }, {passive:false});
  img.addEventListener('touchend',function(e){ if(e.touches.length<2) lbPinchD=0; if(e.touches.length<1) lbDrag=null; }, {passive:true});
  document.addEventListener('keydown',function(e){
    if(!lb.classList.contains('open')) return;
    if(e.key==='Escape') closeLB();
    else if(e.key==='ArrowLeft') lbNav(GX.lang==='ar'?1:-1);
    else if(e.key==='ArrowRight') lbNav(GX.lang==='ar'?-1:1);
    else if(e.key==='+'||e.key==='=') lbZoom(1);
    else if(e.key==='-'||e.key==='_') lbZoom(-1);
    else if(e.key==='0') lbReset();
  });
});
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
  var omSz=$('omSizeVal'); if(omSz) omSz.textContent=selSize;
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
  gxSet('gx_cart',cart); renderCart();
  /* Ball fly goal animation */
  try{
    var btn=document.querySelector('.pcard[data-id="'+id+'"] .pview, .pdetail-add');
    var cartIcon=document.querySelector('.hicon');
    if(btn && cartIcon){
      var btnR=btn.getBoundingClientRect();
      var cartR=cartIcon.getBoundingClientRect();
      var ball=document.createElement('div');
      ball.className='gx-ball-fly';
      ball.textContent='⚽';
      ball.style.left=btnR.left+btnR.width/2-16+'px';
      ball.style.top=btnR.top-10+'px';
      document.body.appendChild(ball);
      requestAnimationFrame(function(){
        requestAnimationFrame(function(){
          ball.style.left=cartR.left+cartR.width/2-16+'px';
          ball.style.top=cartR.top+'px';
          ball.classList.add('go');
        });
      });
      setTimeout(function(){ ball.remove(); },800);
      /* Show GOAL overlay */
      setTimeout(function(){
        var fx=document.getElementById('gxGoalFx');
        if(fx){ fx.classList.add('show'); setTimeout(function(){ fx.classList.remove('show'); },900); }
      },600);
    }
  }catch(e){}
  toast(gxT('add')+' ✓');
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
      +'<div class="qty2"><button onclick="changeCart(\\''+p.id+'\\',\\''+x.size+'\\',-1)">−</button><span class="qn">'+x.qty+'</span>'
      +'<button onclick="changeCart(\\''+p.id+'\\',\\''+x.size+'\\',1)">+</button></div>'
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
      +'<div class="qty2"><button onclick="changeCart(\\''+p.id+'\\',\\''+x.size+'\\',-1)">−</button><span class="qn">'+x.qty+'</span>'
      +'<button onclick="changeCart(\\''+p.id+'\\',\\''+x.size+'\\',1)">+</button></div>'
      +'<b style="color:var(--ac)">'+pmoney(p.price*x.qty)+' '+GX.cur+'</b>'
      +'<button class="ci-x" onclick="changeCart(\\''+p.id+'\\',\\''+x.size+'\\',-100)">✕</button></div>';
  });
  var tot=cartTotals();
  html+='<div class="row-t"><span>'+gxT('cart_subtotal')+'</span><b>'+pmoney(tot.sub)+' '+GX.cur+'</b></div>'
    +'<div class="row-t"><span>'+gxT('cart_delivery')+'</span><b>'+pmoney(tot.delivery)+' '+GX.cur+'</b></div>'
    +'<div class="row-t total"><span>'+gxT('cart_total')+'</span><b>'+pmoney(tot.total)+' '+GX.cur+'</b></div>'
    +'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px">'
    +'<button class="btn wa" style="flex:1" onclick="openCheckout()">'+gxT('cart_checkout')+'</button>'
    +'<button class="btn wa2" style="flex:1" onclick="orderCartTG()">💬 '+gxT('order_wa')+'</button>'
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
    +'<button class="btn wa2 block" '+(cart.length?'':'disabled style="opacity:.5"')+' onclick="orderCartTG()" style="margin-top:8px">💬 '+gxT('order_wa')+'</button>'
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
      var msg=tgOrderMsg(d.code, items, name, phone, area, addr, tot.delivery, disc, fin);
      clearCart(); closeModal('m-checkout');
      window.open('https://wa.me/message/KZFSQ7ONXMY2M1?text='+encodeURIComponent(msg),'_blank');
      location.href='/order/success?code='+d.code;
    } else { toast('Error'); }
  });
}
function tgOrderMsg(code,items,name,phone,area,addr,del,disc,total){
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
/* ---------- order via WhatsApp ---------- */
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
      var msg=gxT('hello').trim()+' 👋\\n'+gxT('wa_intro')+'\\n';
      msg+=gxT('code_w')+d.code+'\\n';
      items.forEach(function(it){
        msg+='- '+it.emoji+' '+it.name+(it.kind!=='mug'?' ('+it.size+')':'')+' × '+it.qty+'\\n';
      });
      msg+='\\n'+gxT('cart_total')+': '+pmoney(fin)+' '+GX.cur;
      window.open('https://wa.me/message/KZFSQ7ONXMY2M1?text='+encodeURIComponent(msg),'_blank');
      location.href='/order/success?code='+d.code;
    } else { toast('Error'); }
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
    window.open('https://wa.me/message/KZFSQ7ONXMY2M1?text='+encodeURIComponent(msg),'_blank');
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
    var an=$('is_analyzing'); if(an) an.style.display='block';
    var box=$('is_resultsBox'); if(box) box.innerHTML='';
    var prev=$('is_preview'); if(prev){ prev.src=dataUrl; prev.style.display='block'; }
    var cv=document.createElement('canvas'); cv.width=64; cv.height=64;
    var cx=cv.getContext('2d'); cx.drawImage(img,0,0,64,64);
    var d=cx.getImageData(0,0,64,64).data;
    var buckets={};
    for(var i=0;i<d.length;i+=4){
      var a=d[i],b=d[i+1],c2=d[i+2]; if(a+b+c2<60) continue;
      var k=Math.round(a/48)*48+','+Math.round(b/48)*48+','+Math.round(c2/48)*48;
      buckets[k]=(buckets[k]||0)+1;
    }
    var dom=Object.keys(buckets).map(function(k){ return {c:k.split(',').map(Number),n:buckets[k]}; })
      .sort(function(x,y){ return y.n-x.n; }).slice(0,5);
    if(!dom.length) dom=[{c:[200,200,200],n:1}];
    var desc=($('is_desc').value||'').trim().toLowerCase();
    var scores=GX.products.map(function(p){
      var best=0;
      p.colors.forEach(function(hex){ var rgb=hex2rgb(hex); if(!rgb) return;
        dom.forEach(function(dc){
          var dist=Math.sqrt((rgb[0]-dc.c[0])*(rgb[0]-dc.c[0])+(rgb[1]-dc.c[1])*(rgb[1]-dc.c[1])+(rgb[2]-dc.c[2])*(rgb[2]-dc.c[2]));
          var sim=Math.max(0,1-dist/441.7); if(sim>best) best=sim;
        });
      });
      var sc=best*100;
      if(desc){ var hay=((p.name_ar||'')+' '+(p.name_en||'')+' '+(p.club_ar||'')+' '+(p.club_en||'')+' '+(p.desc_ar||'')+' '+(p.desc_en||'')).toLowerCase();
        var boost = hay.indexOf(desc)>-1?12:0; sc=Math.min(99,sc*0.8+boost); }
      return {p:p, sc:Math.round(sc)};
    }).sort(function(a,b){return b.sc-a.sc;});
    if(an) an.style.display='none';
    var out=$('is_resultsBox'); var html='';
    var top=scores[0];
    if(top.sc<40){ html+='<p class="mnote">'+gxT('is_notfound')+'</p><p class="mnote">'+gxT('is_near')+'</p>'; }
    else { html+='<h4 class="msec">'+gxT('is_best')+'</h4>' + isCard(top) + '<h4 class="msec" style="margin-top:14px">'+gxT('is_similar')+'</h4>'; }
    scores.slice(1,4).forEach(function(s){ html+=isCard(s); });
    html+='<div style="text-align:center;margin-top:14px"><button class="btn pri sm" onclick="closeModal(\\'m-imgsearch\\');openRequest(\\''+dataUrl+'\\')">'+gxT('is_request')+'</button></div>';
    html+='<p class="img-search-tip">'+gxT('is_priv')+'</p>';
    html+='<p class="img-search-tip" style="color:var(--mut);font-size:.72rem">'+gxT('is_note')+'</p>';
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
    +'<div><b class="rc-p">'+pmoney(p.price)+' '+GX.cur+'</b><br><span class="rc-s">'+gxT('is_sim').replace('{p}',s.sc)+'</span></div></div>';
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
        +(r.mine?'<button class="rv-report" onclick="reportRev2(\\''+r.id+'\\')">'+gxT('rat_report')+'</button>':'')
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
function ap(P,id){ return $( (P||'') + id ); }
function authTab(P,t){
  var box=ap(P,'abox');
  if(box){
    box.querySelectorAll('.atab').forEach(function(x){ x.classList.toggle('on', x.getAttribute('data-tab')===t); });
    box.querySelectorAll('.auth-pane').forEach(function(x){ x.style.display='none'; });
  }
  var pn=ap(P,'auth_pane_'+t); if(pn) pn.style.display='block';
}
function authContact(P){ var e=ap(P,'au_email'); return ((e&&e.value)||'').trim(); }
function isEmail(v){
  var r=/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  return r.test(v);
}
function maskEmail(em){
  var at=em.indexOf('@');
  if(at<=1) return em;
  return em.charAt(0)+'***'+em.substr(at-1);
}
var auth_timer=null;
function authTimer(P,secs){
  var b=ap(P,'au_resendbtn');
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
function authSendCode(P){
  var full=authContact(P);
  if(!isEmail(full)){ toast(gxT('auth_bad_phone')); return; }
  var btn=ap(P,'au_sendbtn');
  if(btn){ btn.disabled=true; btn.textContent=gxT('auth_loading'); }
  console.log('[LOGIN] OTP request started');
  fetch('/api/auth/otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:full})})
  .then(function(r){ console.log('[LOGIN] OTP request completed status='+r.status); return r.json(); }).then(function(d){
    if(d.ok===false){
      var em = d.error==='sms_notcfg'?gxT('auth_sms_notcfg') :
               (d.error==='rate_limit'||d.error==='rate_gap')?gxT('auth_rate_limit') : gxT('auth_sms_fail');
      toast(em);
      return;
    }
    ap(P,'au_step1').style.display='none'; ap(P,'au_step2').style.display='block';
    var st=ap(P,'au_sentto'); if(st) st.textContent=maskEmail(full);
    var dm=ap(P,'au_demo'); if(dm) dm.style.display= d.demo?'block':'none';
    if(d.demo){
      ap(P,'au_democode').textContent=d.otp;
      var ac=ap(P,'au_code'); if(ac) ac.value=d.otp;
      var dl=ap(P,'au_demo_note'); if(dl) dl.style.display='block';
    }
    var nb=ap(P,'au_newbox'); if(nb) nb.style.display= d.registered?'none':'block';
    toast(gxT('auth_sent_ok'));
    authTimer(P,30);
  }).catch(function(){
    toast(gxT('auth_otp_fail'));
  }).then(function(){
    if(btn){ btn.disabled=false; btn.textContent=gxT('auth_continue'); }
  });
}
function authResend(P){ authSendCode(P); }
document.addEventListener('keydown', function(ev){
  if(ev.key!=='Enter') return;
  var t=ev.target;
  if(!t||!t.id||t.id.indexOf('au_email')<0) return;
  ev.preventDefault();
  authSendCode(t.id.replace('au_email',''));
});
function authChangePhone(P){
  var s2=ap(P,'au_step2'); if(s2){ s2.style.display='none'; }
  var s1=ap(P,'au_step1'); if(s1){ s1.style.display='block'; }
  var ac=ap(P,'au_code'); if(ac) ac.value='';
}
function authVerify(P){
  var em=authContact(P), code=(ap(P,'au_code').value||'').trim();
  var name=(ap(P,'au_name').value||'').trim();
  if(code.length<4){ toast(gxT('auth_otp_short')); return; }
  var btn=ap(P,'au_vbtn');
  if(btn){ btn.disabled=true; btn.textContent=gxT('auth_verifying'); }
  fetch('/api/auth/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em,code:code,name:name})})
  .then(function(r){return r.json();}).then(function(d){
    if(d.ok && d.admin_pending){ showAdminStep(P); return; }
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
function showAdminStep(P){
  var s2=ap(P,'au_step2'); if(s2) s2.style.display='none';
  var s3=ap(P,'au_step3'); if(s3) s3.style.display='block';
  var ans=ap(P,'au_ans'); if(ans) ans.focus();
}
function authCancelAdmin(P){
  var s3=ap(P,'au_step3'); if(s3) s3.style.display='none';
  var s2=ap(P,'au_step2'); if(s2) s2.style.display='block';
  var an=ap(P,'au_ans'); if(an) an.value='';
}
function authAdminCheck(P){
  var ans=(ap(P,'au_ans').value||'').trim();
  if(!ans){ toast(gxT('adm_q_wrong')); return; }
  var btn=ap(P,'au_abtn');
  if(btn){ btn.disabled=true; btn.textContent=gxT('adm_q_loading'); }
  fetch('/api/auth/admin_verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answer:ans})})
  .then(function(r){return r.json();}).then(function(d){
    if(btn){ btn.disabled=false; btn.textContent=gxT('adm_q_btn'); }
    if(d.ok){
      closeModal('m-login');
      location.href='/admin';
    } else {
      toast(d.reason==='noauth'?gxT('auth_blocked'):gxT('adm_q_wrong'));
      var an=ap(P,'au_ans'); if(an) an.value='';
    }
  }).catch(function(){
    if(btn){ btn.disabled=false; btn.textContent=gxT('adm_q_btn'); }
    toast(gxT('adm_q_wrong'));
  });
}
function authPwLogin(P){
  var ee=ap(P,'pw_email'), pp=ap(P,'pw_pass');
  var em=((ee&&ee.value)||'').trim(), pw=((pp&&pp.value)||'').trim();
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
/* ---------- matchday mode ---------- */
function mkModeToggle(){
  var on=document.documentElement.classList.toggle('mkmode');
  var btn=$('mkModeToggle');if(btn) btn.classList.toggle('active',on);
  try{localStorage.setItem('mkmode',on?'1':'0');}catch(e){}
}
(function(){
  try{if(localStorage.getItem('mkmode')==='1'){document.documentElement.classList.add('mkmode');var b=$('mkModeToggle');if(b) b.classList.add('active');}}catch(e){}
})();
/* ---------- reorder ---------- */
function openReorder(code){
  fetch('/api/reorder?code='+encodeURIComponent(code)).then(function(r){return r.json();}).then(function(d){
    var html='';
    d.items.forEach(function(it){
      if(!it.stock){
        html+='<div class="ro-item ro-out"><b>'+it.emoji+' '+it.name+'</b><span>'+gxT('ro_out_msg')+'</span></div>';
        return;
      }
      var alts=it.sizes||[];
      var opts=alts.slice();
      if(it.size&&opts.indexOf(it.size)===-1) opts.unshift(it.size);
      var optsHtml=opts.map(function(s){ return '<option value="'+s+'"'+(s===it.size?' selected':'')+'>'+s+'</option>'; }).join('');
      html+='<div class="ro-item"><b>'+it.emoji+' '+it.name+'</b><span>'+gxT('size_w')+it.size+'</span></div>'
        +'<div class="fld" style="margin-bottom:12px"><label>'+gxT('ro_alt')+'</label><select data-ro="'+it.id+'">'
        +optsHtml
        +'</select></div>';
    });
    var body='<div id="ro_body">'+html+'</div>'
      +'<button class="btn pri big" onclick="doReorder(\\''+code+'\\')">'+gxT('ro_add')+'</button>';
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
        +'<span>'+gxT('pd_now').replace('{p}',(p?pmoney(p.price)+' '+GX.cur:'—'))+'</span></div>'
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
    body:JSON.stringify({name:name,area:area,address:addr,theme:gxGet('gx_theme_v2','dark'),font:gxGet('gx_font','b')})})
  .then(function(r){return r.json();}).then(function(d){ if(d.ok) toast(gxT('ok_saved')); });
}
function accTab(id){
  document.querySelectorAll('.acc-sec').forEach(function(s){ s.classList.remove('on'); });
  document.querySelectorAll('.acc-btn').forEach(function(b){ b.classList.remove('on'); });
  var el=$(id); if(el) el.classList.add('on');
  var bt=document.querySelector('.acc-btn[data-tab="'+id+'"]'); if(bt) bt.classList.add('on');
  if(id==='acc-notifs'){
    var b=$('nbadge'); if(b) b.style.display='none';
    fetch('/api/account/notifs/read',{method:'POST'}).catch(function(){});
  }
}
function accTl(code){
  var el=$('tl-'+code); if(!el) return;
  el.style.display = (el.style.display==='none'||el.style.display==='') ? 'block' : 'none';
}
/* ---------- match ticket tabs ---------- */
function mkTab(id){
  document.querySelectorAll('.mk-sec').forEach(function(s){ s.classList.remove('on'); });
  document.querySelectorAll('.mk-tab').forEach(function(b){ b.classList.remove('on'); });
  var el=$(id); if(el) el.classList.add('on');
  var bt=document.querySelector('.mk-tab[data-tab="'+id+'"]'); if(bt) bt.classList.add('on');
  if(id==='mk-t-notifs'){
    fetch('/api/account/notifs/read',{method:'POST'}).catch(function(){});
  }
}
/* ---------- ticket detail overlay ---------- */
function mkDetail(code){
  fetch('/ticket?code='+encodeURIComponent(code),{headers:{'Accept':'text/html'}})
    .then(function(r){return r.text();}).then(function(html){
    var doc=new DOMParser().parseFromString(html,'text/html');
    var mkT=doc.querySelector('.mk-ticket');
    if(mkT){
      $('mkDetailBody').innerHTML='<div style="max-width:600px;width:100%">'+mkT.outerHTML+'</div>';
    } else {
      $('mkDetailBody').innerHTML='<div style="text-align:center;color:rgba(255,255,255,.6);padding:40px">Loading...</div>';
    }
    $('mkDetailOverlay').classList.add('on');
    document.body.style.overflow='hidden';
  }).catch(function(){
    location.href='/ticket?code='+encodeURIComponent(code);
  });
}
function mkDetailClose(e){
  if(e && e.target && e.target!==$('mkDetailOverlay') && !e.target.classList.contains('mk-detail-close')) return;
  $('mkDetailOverlay').classList.remove('on');
  document.body.style.overflow='';
}
/* ---------- football dna ---------- */
function trackView(pid){
  var v=gxGet('gx_views',[]); if(v.indexOf(pid)===-1){ v.push(pid); v=v.slice(-200); gxSet('gx_views',v); }
}
function dnaCard(id){
  var p=findProd(id); if(!p) return '';
  return '<a class="card" href="/product/'+p.id+'" style="text-decoration:none"><div class="pimg" style="background:linear-gradient(135deg,'+(p.colors[0]||'#E2E8F0')+','+(p.colors[1]||'#94A3B8')+')">'
    +'<img loading="lazy" src="/img/'+p.imgs[0]+'" alt=""><span class="pfav'+(gxGet('gx_favs',[]).indexOf(p.id)>-1?' on':'')+'" onclick="event.preventDefault();event.stopPropagation();toggleFav(\\''+p.id+'\\')">❤</span></div>'
    +'<div class="pbody"><b class="pname">'+p.name_ar+'</b><span class="pcat">'+gxT('cat_'+(p.kind==='mug'?'mug':'jersey'))+'</span>'
    +'<div class="pprice"><b>'+pmoney(p.price)+' '+GX.cur+'</b></div></div></a>';
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
  setTimeout(function(){
    document.querySelectorAll('.pg .gmain, .pg .pinfo, .rv, body').forEach(function(el){
      if(getComputedStyle(el).opacity < 0.5){ el.style.opacity='1'; el.style.transform='none'; el.style.animation='none'; }
    });
  }, 900);
  if($('sq')){ $('sq').addEventListener('input',applyFilters); }
  if($('sq2')){ $('sq2').addEventListener('input',applyFilters); }
  if($('prod_id')){ trackView($('prod_id').value); }
  applyFilters(); renderCart(); tickCountdown(); setInterval(tickCountdown,1000);
  if($('dnaBox')) loadDNA();
  if(location.search.indexOf('fav=1')>-1){
    filters.fav=true;
    document.querySelectorAll('.chip').forEach(function(x){ if(x.textContent.indexOf('❤')>-1) x.classList.add('on'); });
    applyFilters();
    window.scrollTo({top:0});
  }
  /* Cinematic Intro */
  try{
    if(!sessionStorage.getItem('gx_intro_done')){
      var intro=$('gxIntro');
      if(intro){
        setTimeout(function(){ intro.classList.add('show'); },50);
        setTimeout(function(){ intro.classList.add('done'); sessionStorage.setItem('gx_intro_done','1'); },1500);
      }
    } else { var intro2=$('gxIntro'); if(intro2) intro2.style.display='none'; }
  }catch(e){}
  /* Bottom nav badge */
  try{
    var bn=$('bnavBadge');
    if(bn){ var cc=cartCount(); if(cc>0){bn.textContent=cc;bn.style.display='flex';}else{bn.style.display='none';} }
  }catch(e){}
  /* Football scroll */
  try{
    var ball=$('gxFootball');
    if(ball && window.innerWidth<=1200){
      var curY=0,tgtY=0,curX=0,tgtX=0,rot=0,tgtRot=0;
      function fbUpdate(){
        tgtY=Math.max(80,Math.min(window.innerHeight-80, (window.scrollY||0)/Math.max(1,document.body.scrollHeight-window.innerHeight)*window.innerHeight));
        tgtX=Math.sin((window.scrollY||0)/600)*40;
        tgtRot=(window.scrollY||0)*0.3;
        curY+=(tgtY-curY)*0.08; curX+=(tgtX-curX)*0.08; rot+=(tgtRot-rot)*0.08;
        ball.style.transform='translate('+curX.toFixed(1)+'px,'+curY.toFixed(1)+'px) rotate('+rot.toFixed(1)+'deg)';
        ball.style.opacity='0.6';
        requestAnimationFrame(fbUpdate);
      }
      var fbRAF=null;
      function fbLoop(){ fbUpdate(); fbRAF=requestAnimationFrame(fbLoop); }
      fbLoop();
      var scrollTimer;
      window.addEventListener('scroll',function(){
        ball.style.opacity='0.7';
        clearTimeout(scrollTimer);
        scrollTimer=setTimeout(function(){ ball.style.opacity='0.4'; },800);
        /* Goal at bottom */
        var scrollPct=(window.scrollY||0)/(document.body.scrollHeight-window.innerHeight);
        if(scrollPct>0.95 && !window._goalCelebrated){
          window._goalCelebrated=true;
          var fx=document.getElementById('gxGoalFx');
          if(fx){ fx.classList.add('show'); setTimeout(function(){ fx.classList.remove('show'); },1500); }
          confetti(15);
        }
      },{passive:true});
    }
  }catch(e){}
  /* Heart micro-interaction */
  try{
    document.querySelectorAll('.heart').forEach(function(h){
      h.addEventListener('click',function(){ this.classList.remove('pop'); void this.offsetWidth; this.classList.add('pop'); });
    });
  }catch(e){}
  /* Button press effect */
  try{
    document.querySelectorAll('.btn').forEach(function(b){
      b.classList.add('gx-press');
    });
  }catch(e){}
  /* Premium 3D card tilt */
  try{
    document.querySelectorAll('.pcard').forEach(function(card){
      card.addEventListener('mousemove',function(e){
        var rect=this.getBoundingClientRect();
        var x=e.clientX-rect.left, y=e.clientY-rect.top;
        var cx=rect.width/2, cy=rect.height/2;
        var rx=(y-cy)/cy*5, ry=(cx-x)/cx*5;
        this.style.transform='perspective(600px) rotateX('+rx+'deg) rotateY('+ry+'deg) translateY(-6px)';
      });
      card.addEventListener('mouseleave',function(){
        this.style.transform='';
      });
    });
  }catch(e){}
  /* Cart Goal Animation: flying ball */
  try{
    window._gxGoalQueue=[];
    window._gxGoalRunning=false;
    window._gxRunGoal=function(){
      if(window._gxGoalRunning||!window._gxGoalQueue.length) return;
      window._gxGoalRunning=true;
      var fn=window._gxGoalQueue.shift();
      fn();
    };
  }catch(e){}
  /* 3D Product Card Tilt */
  (function(){
    var isMobile='ontouchstart'in window||navigator.maxTouchPoints>0;
    if(isMobile) return;
    document.addEventListener('mousemove',function(e){
      var cards=document.querySelectorAll('.pcard');
      cards.forEach(function(card){
        var r=card.getBoundingClientRect();
        var x=e.clientX-r.left, y=e.clientY-r.top;
        if(x<0||x>r.width||y<0||y>r.height){ card.querySelector('.pcard-inner').style.transform=''; return; }
        var cx=r.width/2, cy=r.height/2;
        var rx=(y-cy)/cy*-5, ry=(x-cx)/cx*5;
        card.querySelector('.pcard-inner').style.transform='rotateX('+rx+'deg) rotateY('+ry+'deg) scale(1.02)';
      });
    });
    document.addEventListener('mouseleave',function(){
      document.querySelectorAll('.pcard-inner').forEach(function(el){ el.style.transform=''; });
    },true);
    /* Touch: active state */
    document.querySelectorAll('.pcard').forEach(function(card){
      card.addEventListener('touchstart',function(){ card.querySelector('.pcard-inner').style.transform='scale(1.02) translateZ(8px)'; },{passive:true});
      card.addEventListener('touchend',function(){ card.querySelector('.pcard-inner').style.transform=''; },{passive:true});
    });
  })();
  /* WOW — Mobile Club Jersey Swipe */
  (function(){var wrap=document.getElementById("gxClubSwipe");if(!wrap)return;var cards=[].slice.call(wrap.querySelectorAll(".gx-club-swipe-card")),dots=document.getElementById("gxSwipeDots");if(!cards.length)return;var current=0,sx=0,sy=0;function dotsR(){if(!dots)return;dots.innerHTML=cards.map(function(_,i){return '<button class="gx-dot '+(i===current?'on':'')+'" onclick="gxClubGo('+i+')"></button>';}).join('')}function render(){cards.forEach(function(c,i){var off=i-current;c.style.transform='translateX(calc('+off*100+'% + '+off*14+'px)) scale('+(i===current?1:.92)+') rotateY('+(off*-3)+'deg)';c.style.opacity=i===current?1:(Math.abs(off)<=1?.55:0);c.style.zIndex=20-Math.abs(off)});dotsR()}window.gxClubGo=function(i){current=(i+cards.length)%cards.length;render()};window.gxClubSwipe=function(d){current=(current+d+cards.length)%cards.length;render()};wrap.addEventListener('touchstart',function(e){var t=e.touches[0];sx=t.clientX;sy=t.clientY},{passive:true});wrap.addEventListener('touchend',function(e){var t=e.changedTouches[0],dx=t.clientX-sx,dy=t.clientY-sy;if(Math.abs(dx)>48&&Math.abs(dx)>Math.abs(dy)*1.15)gxClubSwipe(dx<0?1:-1)},{passive:true});render()})();
  /* WOW — Cinematic reveal replay */
  try{var jr=document.getElementById('jeReveal');if(jr)jr.addEventListener('click',function(e){if(e.target.closest('.je-reveal-btn'))return;this.classList.remove('open');void this.offsetWidth;this.classList.add('open')})}catch(e){}
  /* Matchday Mode */
  window._matchdayOn=false;
  window.toggleMatchday=function(){
    window._matchdayOn=!window._matchdayOn;
    document.documentElement.classList.toggle('matchday-mode',window._matchdayOn);
    var btn=document.getElementById('matchdayBtn');
    if(btn){ btn.classList.toggle('active',window._matchdayOn); btn.textContent=window._matchdayOn?'⚽ EXIT MATCHDAY':'⚽ MATCHDAY'; }
  };
});

/* ---------- GOLAZOX FIT CHECK + CLUB COLOR ---------- */
window._gxFitPref='regular';window._gxFitResult=null;
function gxFitPick(el){var w=el.parentElement;if(!w)return;w.querySelectorAll('.radio').forEach(function(x){x.classList.remove('on');});el.classList.add('on');window._gxFitPref=el.getAttribute('data-v')||'regular';}
function gxParseRange(v){var s=String(v||'').replace(/[–—]/g,'-').trim();if(!s)return[0,0];var p=s.split('-').map(Number);return p.length===1?[p[0],p[0]]:[p[0],p[1]];}
function gxRangePenalty(v,lo,hi){if(v>=lo&&v<=hi)return 0;var span=Math.max(1,hi-lo);return v<lo?(lo-v)/span:(v-hi)/span;}
function gxRunFitCheck(){var w=parseFloat($('fit_weight')&&$('fit_weight').value),h=parseFloat($('fit_height')&&$('fit_height').value);if(!isFinite(w)||!isFinite(h)||w<30||w>180||h<120||h>220){toast(GX.lang==='en'?'Enter a valid weight and height.':'اكتبي وزنًا وطولًا صحيحين.');return;}var chart=GX.chart||{},keys=GX.sizes||Object.keys(chart),best=null;keys.forEach(function(sz,i){var r=chart[sz]||{},hr=gxParseRange(r.height),wr=gxParseRange(r.weight),score=gxRangePenalty(h,hr[0],hr[1])*1.35+gxRangePenalty(w,wr[0],wr[1]);var target=i+(window._gxFitPref==='loose'?0.7:(window._gxFitPref==='tight'?-0.7:0));score+=Math.abs(i-target)*0.22;if(!best||score<best.score||Math.abs(score-best.score)<.03&&((window._gxFitPref==='loose'&&i>best.index)||(window._gxFitPref==='tight'&&i<best.index)))best={size:sz,score:score,index:i};});window._gxFitResult=best;if($('fitSize'))$('fitSize').textContent=best.size;if($('fitExplain'))$('fitExplain').textContent=GX.lang==='en'?'Based on your measurements and preferred fit.':'تم اختيار المقاس بناءً على وزنك وطولك وطريقة اللبس.';if($('fitResult'))$('fitResult').classList.add('show');}
function gxUseFitSize(){var r=window._gxFitResult;if(!r)return;var c=document.querySelector('.size-chip[data-sz="'+r.size+'"]');if(c&&!c.classList.contains('oos')){selectSize(c);closeModal('m-fitcheck');toast(GX.lang==='en'?'Size '+r.size+' selected.':'تم اختيار المقاس '+r.size+'.');}else{closeModal('m-fitcheck');toast(GX.lang==='en'?'That size is currently unavailable.':'هذا المقاس غير متوفر حاليًا.');}}
function gxPickClubColor(btn){var box=$('gxClubColor');if(!box)return;document.querySelectorAll('.gx-club-swatch').forEach(function(x){x.classList.remove('on');});btn.classList.add('on');var a=btn.getAttribute('data-a')||'#18E875',b=btn.getAttribute('data-b')||'#0B9F50',cid=btn.getAttribute('data-cid')||'';box.style.setProperty('--club-a',a);box.style.setProperty('--club-b',b);var n=$('gxClubColorName');if(n)n.textContent=GX.lang==='en'?btn.getAttribute('data-name')+' • YOUR COLOR':btn.getAttribute('data-name')+' • ألوانك';var e=$('gxClubColorEmoji');if(e)e.textContent=btn.getAttribute('data-emoji')||'⚽';var l=$('gxClubColorLink');if(l)l.href='/club/'+encodeURIComponent(cid);setMyClub(cid);}

/* ---------- Ultimate WOW: Jersey Scan ---------- */
window._gxClubSwipeIndex=0;
window._gxClubSwipeData=[];
function gxInitWow(){
  var cards=[].slice.call(document.querySelectorAll('.gx-club-swipe-card'));
  window._gxClubSwipeData=cards.map(function(c){return{cid:c.getAttribute('data-cid')||'',name:(c.querySelector('.gx-swipe-bottom b')||{}).textContent||'',img:(c.querySelector('img')||{}).src||'',color:getComputedStyle(c).getPropertyValue('--sw-ac').trim()||'#18E875'};});
  var stage=document.getElementById('gxScanStage'), img=document.getElementById('gxScanJersey');
  if(stage&&img){
    var sx=0,drag=false,last=0;
    function move(x){var dx=x-sx;if(Math.abs(dx)>4){last=dx;img.style.transform='translateX('+(dx*.35)+'px) rotate('+(dx*.03)+'deg) scale('+(1+Math.min(.08,Math.abs(dx)/900))+')';}}
    function finish(){if(!drag)return;drag=false;stage.classList.remove('dragging');var d=last;img.style.transform='';if(Math.abs(d)>55){gxScanMove(d<0?1:-1);} last=0;}
    stage.addEventListener('touchstart',function(e){if(e.touches.length!==1)return;sx=e.touches[0].clientX;drag=true;stage.classList.add('dragging');},{passive:true});
    stage.addEventListener('touchmove',function(e){if(!drag||e.touches.length!==1)return;move(e.touches[0].clientX);},{passive:true});
    stage.addEventListener('touchend',finish,{passive:true});
    stage.addEventListener('pointerdown',function(e){if(e.pointerType==='mouse'){sx=e.clientX;drag=true;stage.classList.add('dragging');stage.setPointerCapture&&stage.setPointerCapture(e.pointerId);}});
    stage.addEventListener('pointermove',function(e){if(drag&&e.pointerType==='mouse')move(e.clientX);});
    stage.addEventListener('pointerup',finish);stage.addEventListener('pointercancel',finish);
  }
  gxRenderScan();

}
function gxRenderScan(){
  var c=window._gxClubSwipeData||[], i=window._gxClubSwipeIndex||0; if(!c.length)return; if(i<0)i=c.length-1;if(i>=c.length)i=0;window._gxClubSwipeIndex=i;
  var x=c[i],img=document.getElementById('gxScanJersey'),name=document.getElementById('gxScanName'),pill=document.getElementById('gxScanPill'),stage=document.getElementById('gxScanStage');
  if(img){img.style.setProperty('--sw-ac',x.color);img.src=x.img;img.alt=x.name;img.style.transform='translateX(24px) scale(.94)';setTimeout(function(){img.style.transform='';},20);} if(name)name.textContent=x.name;if(pill)pill.textContent=(GX.lang==='en'?'SWIPE':'اسحبي');if(stage)stage.closest('.gx-wow-scan').style.setProperty('--sw-ac',x.color);
  gxMaybeCrowd();
}
function gxScanMove(dir){window._gxClubSwipeIndex=(window._gxClubSwipeIndex||0)+dir;gxRenderScan();}
function gxClubSwipe(dir){gxScanMove(dir);}
function gxScanOpen(){var c=(window._gxClubSwipeData||[])[window._gxClubSwipeIndex||0];if(!c||!c.cid){location.href='/products';return;}location.href='/club/'+encodeURIComponent(c.cid);}
function gxMaybeCrowd(){var r=document.getElementById('gxCrowdReaction');if(r){r.classList.remove('burst');void r.offsetWidth;r.classList.add('burst');}if(typeof gxCrowdBurst==='function'){try{gxCrowdBurst();}catch(e){}}}
/* ---------- Crowd reaction ---------- */
window.gxCrowdBurst=function(){try{var el=document.getElementById('gxCrowdReaction');if(el){el.classList.remove('burst');void el.offsetWidth;el.classList.add('burst');}}catch(e){}};
/* ---------- Quiz ---------- */
window._gxQuiz={q1:'',q2:''};
function gxQuizPick(el){var wrap=el.parentElement,q=wrap.getAttribute('data-q');wrap.querySelectorAll('.gx-qopt').forEach(function(x){x.classList.remove('on');});el.classList.add('on');window._gxQuiz['q'+q]=el.getAttribute('data-v');if(window._gxQuiz.q1&&window._gxQuiz.q2)gxQuizResult();}
function gxQuizResult(){
  var c=window._gxClubSwipeData||[]; if(!c.length)return;
  var red=c.filter(function(x){return /red|arsenal|liverpool|united|al.nassr/i.test(x.name);});
  var pick=(window._gxQuiz.q1==='aggressive'&&red.length)?red[0]:(c[(window._gxQuiz.q2==='dark'?Math.min(2,c.length-1):0)]||c[0]);
  var res=document.getElementById('gxQuizResult'),nm=document.getElementById('gxQuizMatch'),go=document.getElementById('gxQuizGo');if(nm)nm.textContent=pick.name;if(go)go.href='/club/'+encodeURIComponent(pick.cid);if(res)res.classList.add('show');
}
/* ---------- Walk Into The Jersey ---------- */
function gxWalkEnter(){var el=document.getElementById('walkIntoJersey');if(el){el.classList.add('unlocked');el.scrollIntoView({behavior:'smooth',block:'center'});setTimeout(function(){var img=document.getElementById('gxWalkJersey');if(img)img.style.transform='scale(1.05)';},650);gxMaybeCrowd();}}
document.addEventListener('DOMContentLoaded',function(){try{var cid=gxGet('gx_club',null);if(cid){var b=document.querySelector('.gx-club-swatch[data-cid=\"'+cid+'\"]');if(b)gxPickClubColor(b);}}catch(e){}setTimeout(gxInitWow,80);});
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
        ac = t.get("ac", "#E11D48")
        ac2 = t.get("ac2", "#F97316")
        glow = hex_rgba(t.get("glow"), 0.32)
        tint = hex_rgba(t.get("tint"), 0.08)
        rules += ('html[data-club="%s"] { --ac:%s; --ac2:%s; --glow:%s; --tint:%s; '
                  '--team-primary:%s; --team-secondary:%s; '
                  '--team-glow:0 0 30px %s; --team-border:%s; --team-soft:%s; }\n'
                  % (cid, ac, ac2, glow, tint, ac, ac2, glow,
                     hex_rgba(ac, 0.15), hex_rgba(ac, 0.06)))
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
    lights = ""
    light_spec = [("12%", "-2%", "160px", "0s"), ("42%", "-6%", "190px", "-2.5s"),
                  ("72%", "-3%", "170px", "-4.5s"), ("95%", "-7%", "150px", "-1.5s")]
    if mode == "light":
        light_spec = light_spec[:2]
    for x, y, h, dl in light_spec:
        lights += ('<span class="atm-light" style="left:%s;top:%s;height:%s;animation-delay:%s"></span>'
                   % (x, y, h, dl))
    return ('<div class="stadium-bg" aria-hidden="true">'
            '<span class="atm-lines"></span><span class="atm-circle"></span>'
            '<span class="atm-glow g1"></span><span class="atm-glow g2"></span><span class="atm-glow g3"></span>'
            + lights + balls + dots + '<span class="atm-pitch"></span>' + '</div>')


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
<title>GOLAZOX — Football Universe</title>
<meta name="description" content="GOLAZOX — premium football club jerseys & sports mugs">
<meta name="theme-color" content="#0A0D0C">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚽</text></svg>">
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Poppins:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<script>(function(){try{var t=JSON.parse(localStorage.getItem('gx_theme_v2')||'"dark"');document.documentElement.setAttribute('data-theme',t);}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();</script>
<script>document.documentElement.classList.add('js');</script>
<noscript><style>.rv{opacity:1;transform:none}.hero-ball,.stadium-bg,.gx-football,.gx-intro{display:none!important}</style></noscript>
CSS
HEADEXTRA
</head>
<body>
<div class="gx-intro" id="gxIntro" aria-hidden="true"><div class="intro-pitch"></div><div class="intro-light"></div><div class="intro-light"></div><div class="intro-light"></div><div class="intro-ball">⚽</div><div class="intro-logo">GOLAZOX</div></div>
<div class="gx-football" id="gxFootball" aria-hidden="true">⚽</div>
HEADER
PRE
BODY
FOOTER
<nav class="gx-bnav" id="gxBnav" aria-label="Navigation">
<a href="/home" class="BNAV_HOME"><span class="bnav-icon">🏠</span><span>HOME</span></a>
<a href="/products" class="BNAV_SHOP"><span class="bnav-icon">👕</span><span>SHOP</span></a>
<a href="/cart" class="BNAV_CART"><span class="bnav-icon">🛒</span><span>CART</span><span class="bnav-badge" id="bnavBadge" style="display:none"></span></a>
<a href="/favorites" class="BNAV_FAV"><span class="bnav-icon">❤</span><span>WISHLIST</span></a>
<a href="/account" class="BNAV_ACC"><span class="bnav-icon">👤</span><span>ACCOUNT</span></a>
</nav>
MODALS
<div class="co" id="co" onclick="closeCart()"></div>
<div class="cd" id="cd"><div class="cd-head"><b>🛒 T_CART</b><button class="mx" onclick="closeCart()">✕</button></div>
<div class="cd-body" id="cdb"></div><div class="cd-foot" id="cdf"></div></div>
<div class="lb" id="lb">
  <div class="lb-count" id="lbCount" style="display:none"></div>
  <button class="lb-btn lb-close" onclick="closeLB()" aria-label="close">✕</button>
  <button class="lb-btn lb-nav lb-prev" id="lbPrev" onclick="lbNav(-1)" style="display:none" aria-label="prev">←</button>
  <button class="lb-btn lb-nav lb-next" id="lbNext" onclick="lbNav(1)" style="display:none" aria-label="next">→</button>
  <div class="lb-stage" id="lbStage"><img id="lbimg" alt=""></div>
  <div class="lb-zoombar">
    <button class="lb-btn" onclick="lbZoom(-1)" aria-label="zoom out">−</button>
    <span class="lb-zoompct" id="lbPct">100%</span>
    <button class="lb-btn" onclick="lbZoom(1)" aria-label="zoom in">+</button>
    <button class="lb-btn" onclick="lbReset()" aria-label="reset" title="reset">↺</button>
  </div>
</div>
<div class="gx-goal-fx" id="gxGoalFx"><div class="goal-txt">⚽ GOAL!</div></div>
<div class="mkmode-toggle" id="mkModeToggle" onclick="mkModeToggle()" title="Matchday Mode"><span class="mkmode-ic">⚽</span><span class="mkmode-lbl">MATCHDAY</span></div>
<div class="mkmode-pitch"></div>
<div class="mkmode-lights"><div class="mkl"></div><div class="mkl"></div><div class="mkl"></div><div class="mkl"></div></div>
<a class="fab" target="_blank" rel="noopener" href="https://wa.me/message/KZFSQ7ONXMY2M1" title="WhatsApp">💬</a>

<script>
(function(){
  function safeGet(key, fallback){try{return JSON.parse(localStorage.getItem(key)||JSON.stringify(fallback));}catch(e){return fallback;}}
  function safeSet(key,val){try{localStorage.setItem(key,JSON.stringify(val));}catch(e){}}


  function renderRecent(){
    var box=document.getElementById('recentTunnelTrack'); if(!box)return;
    var ids=safeGet('gx_recent_views',[]);
    if(!Array.isArray(ids)||!ids.length){
      box.innerHTML='<div class="gx-recent-empty">⚽ '+(window.GX&&GX.lang==='en'?'Browse a jersey and your recent picks will appear here.':'شاهدي تيشرتًا وسيظهر هنا آخر ما شاهدته.')+'</div>';
      return;
    }
    var seen={}; ids=ids.filter(function(id){if(seen[id])return false;seen[id]=1;return true;}).slice(0,8);
    var html='';
    ids.forEach(function(id,idx){
      var p=(window.GX&&GX.products||[]).find(function(x){return x.id===id;});
      if(!p)return;
      var name=p[GX.lang==='ar'?'name_ar':'name_en']||p.id;
      html+='<a class="gx-recent-card '+(idx===0?'is-main':'')+'" href="/product/'+encodeURIComponent(p.id)+'">'
        +'<img src="/img/'+(p.imgs&&p.imgs[0]?p.imgs[0]:'')+'" alt="">'
        +'<div class="rc-name">'+escapeHtml(name)+'</div>'
        +'<div class="rc-price">'+(typeof pmoney==='function'?pmoney(p.price):p.price)+' '+(GX.cur||'')+'</div>'
        +'</a>';
    });
    box.innerHTML=html||'<div class="gx-recent-empty">⚽</div>';
  }

  function escapeHtml(s){
    return String(s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});
  }

  function fanMoment(){
    var el=document.getElementById('fanMomentText'); if(!el)return;
    var en=!!(window.GX&&GX.lang==='en');
    var arr=en?[
      '⚡ MATCHDAY IS LIVE',
      '🔥 READY FOR YOUR NEXT JERSEY?',
      '💚 POWERED BY GOLAXOX',
      '👕 WEAR YOUR PASSION'
    ]:[
      '⚡ أجواء المباراة بدأت',
      '🔥 جاهز لتيشرتك القادم؟',
      '💚 شغفك مع GOLAXOX',
      '👕 البس شغفك'
    ];
    var i=0;
    function tick(){
      el.style.opacity='0';
      setTimeout(function(){el.textContent=arr[i++%arr.length];el.style.opacity='1';},180);
    }
    tick(); setInterval(tick,3600);
    el.style.transition='opacity .35s ease';
  }

  document.addEventListener('DOMContentLoaded',function(){
    renderRecent(); fanMoment();
  });
})();
</script>
__PAGEJS_SLOT__
__BASEJS_SLOT__
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
        .replace("MODALS", ads_html("banner") + modals_html()) \
        .replace("T_CART", d["cart_title"]) \
        .replace("BNAV_HOME", " on" if active == "home" else "") \
        .replace("BNAV_SHOP", " on" if active in ("products", "mugs", "clubs") else "") \
        .replace("BNAV_CART", " on" if active == "cart" else "") \
        .replace("BNAV_FAV", " on" if active == "favorites" else "") \
        .replace("BNAV_ACC", " on" if active in ("account", "login") else "") \
        .replace("__PAGEJS_SLOT__", page_js) \
        .replace("__BASEJS_SLOT__", js)


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
    cheer = ""
    fav_btn = '<button class="hbtn hicon" onclick="openFavs()" title="' + d["fav_filter"] + '">❤️<span class="hcount" id="favcount">0</span></button>'
    return ('<div class="hd"><div class="hd-in">'
            '<a href="/home" class="logo"><span class="ball">⚽</span>golazox</a>'
            '<nav class="nav" id="topnav">%s'
            '<button class="nv nv-close" onclick="toggleMenu()">✕</button></nav>'
            '<button class="hbtn hmenu" onclick="toggleMenu()">☰</button>'
            '%s'
            '<button class="hbtn hicon" onclick="openModal(\'m-settings\')">⚙️<span class="hcount" id="cbadge">0</span></button>'
            '<a class="hbtn hicon" href="/cart">🛒<span class="hcount" id="cbadge2">0</span></a>'
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
            '<a target="_blank" rel="noopener" href="https://wa.me/{wa}" title="{tg_title}">💬</a>'
            '<a onclick="setLang(\'{other}\')" title="{lang}">{langname}</a>'
            '</div></div>'
            '<div class="ft-col"><h4>{t1}</h4>{col_links}</div>'
            '<div class="ft-col"><h4>{t2}</h4>{club_links}</div>'
            '<div class="ft-col"><h4>{t3}</h4>{col_help}'
            '<a target="_blank" rel="noopener" href="https://wa.me/{wa}" style="margin-top:10px;font-weight:800">{tg_txt} 💬</a>'
            '</div></div>'
            '<p class="ft-copy">{copy}</p>'
            '</div></footer>').format(
        badge=d["badge"], wa=cfg.WHATSAPP, tg_title=d["ft_wa"], tg_txt=d["order_wa"],
        other="ar" if en else "en",
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


def auth_box_html(prefix=""):
    d = cfg.L[lang()]
    return ('<div class="auth-box" id="{p}abox">'
            '<p class="mnote">{sub}</p>'
            '<div class="auth-tabs">'
            '<button class="atab on" data-tab="otp" onclick="authTab(\'{p}\',\'otp\')">{t1}</button>'
            '<button class="atab" data-tab="pw" onclick="authTab(\'{p}\',\'pw\')">{t2}</button></div>'
            '<div class="auth-pane" id="{p}auth_pane_otp">'
            '<div class="auth-step1" id="{p}au_step1">'
            '<div class="fld"><label>{em}</label>'
            '<input id="{p}au_email" type="email" inputmode="email" placeholder="{emph}" autocomplete="off"></div>'
            '<button class="btn pri big" id="{p}au_sendbtn" onclick="authSendCode(\'{p}\')">{ct}</button></div>'
            '<div class="auth-step2" id="{p}au_step2">'
            '<p class="auth-sent">📨 {sent} <b id="{p}au_sentto"></b></p>'
            '<div class="fld"><label>{otp}</label><input id="{p}au_code" inputmode="numeric" maxlength="6"></div>'
            '<div class="fld" id="{p}au_newbox"><label>{nm}</label><input id="{p}au_name"></div>'
            '<div class="auth-new" id="{p}au_new">{new}</div>'
            '<div class="auth-demo" id="{p}au_demo">{demo} <b id="{p}au_democode"></b>'
            '<div id="{p}au_demo_note" style="display:none;margin-top:6px;font-weight:800">✅ {fill}</div></div>'
            '<button class="btn pri big" id="{p}au_vbtn" onclick="authVerify(\'{p}\')">{v}</button>'
            '<div class="auth-actions">'
            '<button class="hbtn" id="{p}au_resendbtn" onclick="authResend(\'{p}\')">🔄 {resend}</button>'
            '<button class="hbtn" onclick="authChangePhone(\'{p}\')">↩ {chg}</button></div></div>'
            '<div class="auth-step3" id="{p}au_step3" style="display:none">'
            '<p class="auth-sent">🔐 {aqt}</p>'
            '<p class="mnote">{aqsub}</p>'
            '<div class="fld"><label>{aqq}</label><input id="{p}au_ans" autocomplete="off"></div>'
            '<button class="btn pri big" id="{p}au_abtn" onclick="authAdminCheck(\'{p}\')">{aqb}</button>'
            '<div class="auth-actions"><button class="hbtn" onclick="authCancelAdmin(\'{p}\')">↩ {chg}</button></div></div>'
            '</div>'
            '<div class="auth-pane" id="{p}auth_pane_pw" style="display:none">'
            '<div class="fld"><label>{em}</label>'
            '<input id="{p}pw_email" type="email" inputmode="email" placeholder="{emph}" autocomplete="off"></div>'
            '<div class="fld"><label>{pw}</label><input id="{p}pw_pass" type="password"></div>'
            '<button class="btn pri big" onclick="authPwLogin(\'{p}\')">{pb}</button></div>'
            '</div>'
            ).format(p=prefix, sub=d["auth_sub"], t1=d["auth_tab_otp"], t2=d["auth_tab_pw"],
                     em=d["auth_email"], emph=d["auth_email_ph"], ct=d["auth_continue"], sent=d["auth_sent_to"],
                     otp=d["auth_otp_ph"], nm=d["auth_name_ph"], new=d["auth_new"], demo=d["auth_demo_note"],
                     fill=d["auth_demo_fill"], v=d["auth_verify"], resend=d["auth_resend"], chg=d["auth_change_num"],
                     pw=d["auth_pw_ph"], pb=d["auth_pw_btn"],
                     aqt=d["adm_q_title"], aqsub=d["adm_q_sub"], aqq=d["adm_q_q"],
                     aqb=d["adm_q_btn"])


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
                    + "<a class='btn wa2 big' target='_blank' rel='noopener' href='https://wa.me/{num}'>💬 {wa}</a>".format(num=cfg.WHATSAPP, wa=d["contact_wa"])
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
                '<img id="is_preview" style="display:none;max-height:150px;border-radius:14px;margin-top:12px" alt="">'
                '<p id="is_analyzing" class="mnote" style="margin-top:10px;font-weight:800;display:none">{an}</p>'
                '<div id="is_resultsBox"></div>'
                ).format(sub=d["is_sub"], cam=d["is_camera"], up=d["is_upload"],
                         desc=d["is_desc"], ph=d["is_desc_ph"], an=d["is_analyzing"])

    points_body = '<div id="ptsBox"></div>'

    pricedrop_body = ('<p class="mnote">{sub}</p>'
                      '<input type="hidden" id="pd_prod">'
                      '<div class="fld"><label>{ph}</label><input id="pd_phone" inputmode="tel" placeholder="+973 ________"></div>'
                      '<button class="btn pri big" onclick="submitPriceDrop()">{btn}</button>'
                      ).format(sub=d["pd_sub"], ph=d["pd_phone"], btn=d["pd_btn"])

    login_body = auth_box_html()

    reorder_body = '<div id="ro_body"></div>'

    fit_body = (
        '<div class="mnote" style="margin-bottom:14px">{intro}</div>'
        '<div class="frow"><div class="fld"><label>{weight}</label><input id="fit_weight" type="number" min="30" max="180" step="0.1" inputmode="decimal" placeholder="70"></div>'
        '<div class="fld"><label>{height}</label><input id="fit_height" type="number" min="120" max="220" step="1" inputmode="numeric" placeholder="175"></div></div>'
        '<div class="fld"><label>{fit}</label><div class="radios">'
        '<button class="radio" data-g="fitpref" data-v="tight" onclick="gxFitPick(this)">🧩 {tight}</button>'
        '<button class="radio on" data-g="fitpref" data-v="regular" onclick="gxFitPick(this)">👌 {regular}</button>'
        '<button class="radio" data-g="fitpref" data-v="loose" onclick="gxFitPick(this)">🫶 {loose}</button>'
        '</div></div>'
        '<button class="btn pri big" onclick="gxRunFitCheck()">{btn}</button>'
        '<div id="fitResult" class="gx-fit-result"><div class="gx-fit-sub">{result}</div><div id="fitSize" class="gx-fit-size">—</div><div id="fitExplain" class="gx-fit-sub"></div>'
        '<button class="btn ghost sm" style="margin-top:10px" onclick="gxUseFitSize()">{use}</button></div>'
        '<p class="mnote" style="margin-top:12px;font-size:.72rem">{note}</p>'
    ).format(
        intro=("أدخل وزنك وطولك واختر شكل اللبسة، ونقترح لك أقرب مقاس حسب جدول GOLAZOX." if not en else "Enter your weight and height, then choose your preferred fit. We’ll suggest the closest GOLAZOX size."),
        weight=("الوزن (كجم)" if not en else "Weight (kg)"), height=("الطول (سم)" if not en else "Height (cm)"),
        fit=("كيف تحب يكون التيشيرت؟" if not en else "How do you want it to fit?"),
        tight=("ضيق" if not en else "Slim"), regular=("معتدل" if not en else "Regular"), loose=("واسع" if not en else "Loose"),
        btn=("احسب مقاسي" if not en else "Find my size"), result=("المقاس المقترح" if not en else "Suggested size"),
        use=("استخدم هذا المقاس" if not en else "Use this size"), note=("المقاس تقديري وقد يختلف حسب القصة وطريقة القياس." if not en else "This is a guide estimate; fit can vary by cut and measurement method."))

    return (modal("m-fitcheck", "GOLAZOX FIT CHECK", fit_body, True)
            + modal("m-sizes", d["szt_head"], size_body, True)
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


def ads_html(place):
    """Render active announcement/ads strips for a given placement."""
    try:
        ads = db.ads_list(place=place, active_only=True)
        if not ads:
            return ""
    except Exception:
        return ""
    en = lang() == "en"
    items = ""
    for a in ads:
        txt = (a.get("text_en") if en else a.get("text_ar")) or a.get("text_ar") or a.get("text_en") or ""
        if not txt:
            continue
        link = a.get("link") or ""
        inner = '<span class="ads-txt">📢 ' + esc(txt) + '</span>'
        if link:
            items += '<a class="ads-item" href="' + esc(link) + '">' + inner + '</a>'
        else:
            items += '<div class="ads-item">' + inner + '</div>'
    if not items:
        return ""
    return '<div class="ads-strip">{items}</div>'.format(items=items)


def spotlight_html(prods):
    """Jersey of the Day / Product Spotlight section."""
    en = lang() == "en"
    d = cfg.L[lang()]
    import hashlib, datetime
    today = datetime.date.today().isoformat()
    idx = int(hashlib.md5(today.encode()).hexdigest(), 16) % len(prods) if prods else 0
    p = prods[idx] if prods else None
    if not p:
        return ""
    name = p.get("name_en") if en else p.get("name_ar")
    desc = p.get("desc_en") if en else p.get("desc_ar")
    pr = fmt_cur(eff_price(p))
    img = "/img/" + p["imgs"][0] if p.get("imgs") else ""
    club = cfg.club_of(p)
    club_name = (club.get(en and "en" or "ar", "")) if club else ""
    badge_label = d.get("spotlight_badge", "JERSEY OF THE DAY") if en else "تيشيرت اليوم"
    return (
        '<div class="sec rv"><div class="sec-head"><h2><span class="bar"></span>{t}</h2></div>'
        '<a href="/product/{pid}" class="spotlight-card">'
        '<img class="spotlight-img" src="{img}" alt="{name}" loading="lazy">'
        '<div class="spotlight-info">'
        '<span class="spotlight-badge">⚽ {badge}</span>'
        '<h3>{name}</h3>'
        '<p>{desc}</p>'
        '<div class="spotlight-price">{pr} {cur}</div>'
        '<span style="display:inline-block;margin-top:10px;font-size:.86rem;font-weight:800;color:var(--ac)">{view} ←</span>'
        '</div></a></div>'
    ).format(t=d.get("spotlight_title", "Jersey of the Day") if en else "تيشيرت اليوم",
             pid=p["id"], img=img, name=esc(name), badge=badge_label,
             desc=esc(desc or ""), pr=pr, cur=cur(), view=d["view"])



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
            '<div class="hero-brand" aria-hidden="true">GOLAZOX</div>'
            '<h1>{t1}<br><span class="g">{t2}</span></h1><p>{sub}</p>'
            '<div class="hero-btns"><a class="btn pri" href="/products">{cj}</a>'
            '<a class="btn ghost" href="#clubs">{ct}</a></div>'
            '<div class="hero-price">{pj} · {pm}</div>'
            '<div class="hero-ball"><span class="ring"></span>⚽</div></div>'
            ).format(tag=d["home_section_hero_tag"], t1=d["home_hero_t1"], t2=d["home_hero_t2"],
                     sub=("تيشيرت رياضي بجودة عالية بخامة الأبطال، يلبسك حماس الملعب من أول لحظة. اختار فريقك وعيش الأجواء ⚽🔥" if not en else "High-quality sports jerseys with a premium feel. Pick your team and live the matchday atmosphere ⚽🔥"), cj=d["home_cta_shop"], ct=d["home_cta_team"],
                     pj=fmt_cur(cfg.PRICE_JERSEY), pm=fmt_cur(cfg.PRICE_MUG))

    fit_home = ("<div class='sec rv'><div class='gx-fit-card'><div class='gx-fit-head'><div><h3>✨ {title}</h3><p>{sub}</p></div><button class='fit-check-btn' onclick=\"openModal('m-fitcheck')\">{btn}</button></div></div></div>").format(title=("اعرف مقاسك قبل الطلب" if not en else "KNOW YOUR SIZE BEFORE YOU ORDER"),sub=("وزن + طول + طريقة اللبس = مقاس أقرب لك." if not en else "Weight + height + fit preference = a closer size recommendation."),btn=("ابدأ Fit Check" if not en else "Start Fit Check"))

    club_swatches=[]
    for cid,c in cfg.CLUBS.items():
        th=club_themes().get(cid,{})
        club_swatches.append('<button class="gx-club-swatch" data-cid="%s" data-a="%s" data-b="%s" data-name="%s" data-emoji="%s" onclick="gxPickClubColor(this)">%s</button>' % (cid,th.get("ac","#18E875"),th.get("ac2","#0B9F50"),esc(c.get("en" if en else "ar",cid)),esc(c.get("emoji","⚽")),esc(c.get("en" if en else "ar",cid))))
    club_color_section=('<div class="sec rv"><div class="gx-club-color" id="gxClubColor"><div class="gx-club-color-inner"><div class="gx-club-color-top"><div><h3 id="gxClubColorName">YOUR CLUB. YOUR COLOR.</h3><small>{sub}</small></div><div id="gxClubColorEmoji" style="font-size:2rem">⚽</div></div><div class="gx-club-swatches">{swatches}</div><a id="gxClubColorLink" class="gx-club-color-cta" href="/products">{cta}</a></div></div></div>').format(sub=("اختار ناديك، وخلي ألوان GOLAZOX على مزاجك." if not en else "Pick your club and make GOLAZOX feel like your colors."),swatches="".join(club_swatches),cta=("شوف قمصان النادي" if not en else "Shop this club"))

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

    ticker_txt = "⚡ MATCHDAY" if en else "⚡ ماتش داي"
    md_ticker = ('<div class="md-ticker"><div class="md-ticker-track">' + (
        ('<span>{t} • <b>GOLAZOX</b> • FOOTBALL •</span>' * 8).format(t=ticker_txt)
    ) + '</div></div>')

    pc_sec = (
        '<div class="sec rv"><div class="pc-sec">'
        '<div class="pc-fog"></div><div class="pc-crowd"></div>'
        '<div class="pc-goal-wrap"><div class="pc-goal"></div>'
        '<div class="pc-keeper"><div class="kb"></div><div class="kh"></div></div>'
        '<div class="pc-ball">⚽</div></div>'
        '<div class="pc-title">🎯 {t}</div>'
        '<div class="pc-sub">{s}</div>'
        '<a class="pc-cta" href="/penalty">{cta}</a>'
        '</div></div>'
    ).format(
        t="PENALTY CHALLENGE",
        s=("هل تقدر تسجل ضد الحارس؟" if not en else "Can you score past the keeper?"),
        cta=d.get("pen_start", "⚡ ابدأ التحدي" if not en else "Start the Challenge ⚡"),
    )

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


    # Recently viewed tunnel: rendered from localStorage on the client.
    recent_sec = (
        '<div class="sec rv" id="recentTunnel">'
        '<div class="sec-head"><h2><span class="bar"></span>{t}</h2><span class="sec-sub">{s}</span></div>'
        '<div class="gx-recent-tunnel"><div class="gx-recent-track" id="recentTunnelTrack"></div></div>'
        '</div>'
    ).format(
        t=("LAST SEEN IN THE TUNNEL" if en else "آخر المنتجات التي شاهدتها"),
        s=("Your recent jerseys, now in the matchday tunnel" if en else "منتجاتك الأخيرة داخل نفق المباراة")
    )

    fan_moment = (
        '<div class="gx-fan-moment" id="fanMoment">'
        '<span class="fm-dot"></span><div class="fm-text" id="fanMomentText"></div>'
        '<div class="fm-sub">GOLAXOX MATCHDAY</div></div>'
    )

    final_pitch = (
        '<div class="gx-final-pitch sec rv">'
        '<div class="fp-content"><div class="fp-ball">⚽</div>'
        '<h2>{t}</h2><p>{s}</p>'
        '<div class="fp-actions"><a class="btn pri" href="/products">{shop}</a>'
        '<a class="btn ghost" href="/penalty">{play}</a></div></div></div>'
    ).format(
        t=("READY FOR KICK-OFF?" if en else "جاهز لبداية المباراة؟"),
        s=("Choose your jersey or step onto the pitch." if en else "اختر تيشرتك أو ادخل أرض الملعب."),
        shop=("SHOP YOUR JERSEY" if en else "تسوق تيشرتك"),
        play=("PLAY PENALTY" if en else "العب الركلة")
    )

    swipe_cards=[]
    for cid,c in cfg.CLUBS.items():
        th=club_themes().get(cid,{})
        club_prods=[p for p in prods if p.get("club_id")==cid and p.get("kind")=="jersey"]
        if not club_prods: continue
        fp=club_prods[0]
        swipe_cards.append((cid,th.get("ac","#E11D48"),th.get("ac2","#F97316"),c.get("en" if en else "ar",cid),c.get("emoji","⚽"),fp["imgs"][0],len(club_prods)))
    swipe_items=[]
    for i,(cid,ac,ac2,nm,em,img,count) in enumerate(swipe_cards):
        swipe_items.append(('<article class="gx-club-swipe-card" data-index="%d" style="--sw-ac:%s;--sw-ac2:%s">'
                            '<div class="gx-swipe-bg"></div><div class="gx-swipe-top"><span>%s %s</span><small>%s</small></div>'
                            '<div class="gx-swipe-stage"><div class="gx-swipe-glow"></div><img src="/img/%s" alt="%s" loading="lazy"></div>'
                            '<div class="gx-swipe-bottom"><div><b>%s</b><span>%s</span></div><a class="gx-swipe-cta" href="/club/%s">%s →</a></div></article>')
                           % (i,cid and ac,ac2,em,esc(nm),("JERSEY COLLECTION" if en else "تشكيلة قمصان النادي"),esc(img),esc(nm),esc(nm),("SWIPE TO EXPLORE" if en else "اسحبي لاكتشاف الأندية"),cid,("VIEW CLUB" if en else "شوف النادي")))
    club_swipe_sec=('<div class="sec rv gx-club-swipe-wrap" id="clubSwipeSection"><div class="sec-head"><h2><span class="bar"></span>%s</h2><span class="sec-sub">%s</span></div><div class="gx-club-swipe" id="gxClubSwipe">%s</div><div class="gx-swipe-controls"><button type="button" class="gx-swipe-arrow" onclick="gxClubSwipe(-1)">‹</button><div class="gx-swipe-dots" id="gxSwipeDots"></div><button type="button" class="gx-swipe-arrow" onclick="gxClubSwipe(1)">›</button></div><div class="gx-swipe-note" id="gxSwipeNote">%s</div></div>') % (("EXPLORE BY CLUB" if en else "اكتشفي الأندية"),("Swipe the jerseys. Pick your club." if en else "اسحبي بين الأندية وشوفي القميص مباشرة"),"".join(swipe_items),("Swipe ← →" if en else "اسحبي يمين ويسار"))

    # WOW scan and walk-through removed per request.
    quiz_sec = ('<section class="sec rv gx-quiz" id="clubQuiz">'
                '<h2>🧠 {title}</h2><p>{sub}</p>'
                '<div class="gx-quiz-q">1. {q1}</div><div class="gx-quiz-opts" data-q="1">'
                '<button class="gx-qopt" data-v="aggressive" onclick="gxQuizPick(this)">🔥 {o11}</button>'
                '<button class="gx-qopt" data-v="classic" onclick="gxQuizPick(this)">✨ {o12}</button></div>'
                '<div class="gx-quiz-q">2. {q2}</div><div class="gx-quiz-opts" data-q="2">'
                '<button class="gx-qopt" data-v="red" onclick="gxQuizPick(this)">🔴 {o21}</button>'
                '<button class="gx-qopt" data-v="dark" onclick="gxQuizPick(this)">⚫ {o22}</button></div>'
                '<div class="gx-quiz-result" id="gxQuizResult"><div class="gx-match-line">{resultLabel}</div><div class="gx-match-name" id="gxQuizMatch">—</div><a id="gxQuizGo" class="btn pri gx-quiz-go" href="#">{go}</a></div>'
                '</section>').format(title=("FIND YOUR CLUB" if en else "أي تيشيرت يناسبك؟"),sub=("Two taps. One match." if en else "اختاري بسرعة ونحدد لك القميص المناسب."),q1=("What energy are you?" if en else "وش أجواؤك؟"),o11=("Bold & loud" if en else "جريء وحماسي"),o12=("Classic & clean" if en else "كلاسيكي ومرتب"),q2=("Pick a color mood" if en else "اختاري ألوانك"),o21=("Red / fiery" if en else "أحمر وحماسي"),o22=("Dark / elite" if en else "داكن وفخم"),resultLabel=("YOUR MATCH" if en else "اختيارك"),go=("SHOP THIS JERSEY" if en else "شوفي التيشيرت"))

    # Hero first, then the world jersey experience.
    jersey_map_html = """
    <section class="sec rv gx-jersey-map" id="jerseyMap">
      <div class="gx-jm-shell">
        <div class="gx-jm-top">
          <div>
            <span class="gx-jm-kicker">GOLAZOX WORLD 🌍</span>
            <h2>WEAR YOUR PASSION. REPRESENT THE WORLD.</h2>
            <p>اختاري الدولة، ناديك، تيشيرتك ومقاسك — من خريطة واحدة.</p>
          </div>
          <div class="gx-jm-top-right">
            <span class="gx-jm-pill live"><i></i>WORLDWIDE JERSEY MAP</span>
            <span class="gx-jm-pill">ASIAN FIT</span>
            <span class="gx-jm-pill">7 د.ب</span>
          </div>
        </div>
        <div class="gx-jm-globe-wrap">
          <div class="gx-jm-stars"></div>
          <div class="gx-jm-hero-copy">
            <span class="ey">YOUR JOURNEY STARTS HERE</span>
            <h3>اختاري ناديك.<br>عيشي أجواءه.</h3>
            <p>اضغطي على الدولة أو اسحبي بين الدول، ثم اختاري القميص والمقاس.</p>
            <button class="btn pri" type="button" onclick="document.getElementById('gxJmJourney').scrollIntoView({behavior:'smooth',block:'center'})">اكتشفي الخريطة ←</button>
          </div>
          <div class="gx-jm-stats">
            <div class="gx-jm-stat"><b id="gxJmCountCountry">6</b><span>COUNTRIES</span></div>
            <div class="gx-jm-stat"><b id="gxJmCountClub">9</b><span>CLUBS IN STORE</span></div>
            <div class="gx-jm-stat"><b>7</b><span>JERSEY PRICE • BHD</span></div>
            <div class="gx-jm-stat"><span>⚡ FAST • MOBILE FIRST</span></div>
          </div>
          <div class="gx-jm-globe" aria-label="GOLAZOX interactive world globe">
            <div class="gx-jm-continent na"></div><div class="gx-jm-continent eu"></div><div class="gx-jm-continent uk"></div><div class="gx-jm-continent sa"></div><div class="gx-jm-continent as"></div><div class="gx-jm-continent saam"></div>
            <div class="gx-jm-arc"></div><div class="gx-jm-arc two"></div>
            <div class="gx-jm-pulse" style="left:49%;top:39%;--pc:#e04444"></div>
            <div class="gx-jm-pulse" style="left:57%;top:33%;--pc:#d8b45a"></div>
            <div class="gx-jm-pulse" style="left:66%;top:55%;--pc:#18e875"></div>
            <div class="gx-jm-marker is-active" data-country="spain" style="left:42%;top:40%;--mc:#e04444"><span>🇪🇸</span><div>إسبانيا<small>2 CLUBS</small></div></div>
            <div class="gx-jm-marker" data-country="england" style="left:43%;top:28%;--mc:#7dd3fc"><span>🇬🇧</span><div>إنجلترا<small>4 CLUBS</small></div></div>
            <div class="gx-jm-marker" data-country="germany" style="left:52%;top:31%;--mc:#f5c542"><span>🇩🇪</span><div>ألمانيا<small>1 CLUB</small></div></div>
            <div class="gx-jm-marker" data-country="france" style="left:45%;top:34%;--mc:#60a5fa"><span>🇫🇷</span><div>فرنسا<small>1 CLUB</small></div></div>
            <div class="gx-jm-marker" data-country="italy" style="left:57%;top:40%;--mc:#34d399"><span>🇮🇹</span><div>إيطاليا<small>1 CLUB</small></div></div>
            <div class="gx-jm-marker" data-country="saudi" style="left:67%;top:49%;--mc:#18e875"><span>🇸🇦</span><div>السعودية<small>1 CLUB</small></div></div>
          </div>
          <div class="gx-jm-instruction">🖱️ <b>اضغطي</b> على أي دولة لبدء الرحلة</div>
        </div>
        <div class="gx-jm-country-strip" id="gxJmCountryStrip"></div>
        <div class="gx-jm-journey" id="gxJmJourney">
          <article class="gx-jm-step">
            <span class="gx-jm-stepnum">1</span><h4>CHOOSE COUNTRY</h4><div class="muted">اختاري بلدك المفضل</div>
            <div class="gx-jm-country-card" id="gxJmCountryCard"><div class="flag">🇪🇸</div><b>إسبانيا</b><span>2 أندية</span></div>
          </article>
          <article class="gx-jm-step">
            <span class="gx-jm-stepnum">2</span><h4>CHOOSE CLUB</h4><div class="muted">اختاري ناديك</div>
            <div class="gx-jm-club-row" id="gxJmClubRow"></div>
          </article>
          <article class="gx-jm-step">
            <span class="gx-jm-stepnum">3</span><h4>CHOOSE JERSEY</h4><div class="muted">شاهدي القميص المختار</div>
            <div class="gx-jm-jersey" id="gxJmJersey"><span style="color:rgba(255,255,255,.4);font-size:.65rem">اختاري ناديًا</span></div>
          </article>
          <article class="gx-jm-step">
            <span class="gx-jm-stepnum">4</span><h4>CHOOSE SIZE</h4><div class="muted">Asian Fit</div>
            <div class="gx-jm-size-grid" id="gxJmSizes"><button class="active" data-size="M">M</button><button data-size="S">S</button><button data-size="L">L</button><button data-size="XL">XL</button><button data-size="2XL">2XL</button><button data-size="3XL">3XL</button></div>
          </article>
          <article class="gx-jm-step">
            <span class="gx-jm-stepnum">5</span><h4>SHOP NOW</h4><div class="muted" id="gxJmBuyClub">REAL MADRID</div>
            <div class="gx-jm-buy"><div class="price" id="gxJmBuyPrice">7 د.ب</div><div class="small">Asian Fit • جودة عالية</div><div class="ok"><span>✓ صور المنتج من المتجر</span><span>✓ اختيار المقاس</span><span>✓ طلب مباشر</span></div><a id="gxJmBuyBtn" class="btn cta" href="/products">🛒 أضف للسلة</a></div>
          </article>
        </div>
      </div>
    </section>
    """

    _jm_map = {
        "england": ("🇬🇧", "إنجلترا", ["arsenal", "liver", "united", "city"]),
        "germany": ("🇩🇪", "ألمانيا", ["bayern"]),
        "spain": ("🇪🇸", "إسبانيا", ["real", "barca"]),
        "italy": ("🇮🇹", "إيطاليا", ["juve"]),
        "france": ("🇫🇷", "فرنسا", ["psg"]),
        "saudi": ("🇸🇦", "السعودية", ["nassr"]),
    }
    _jm_data = {}
    for _country, (_flag, _label, _ids) in _jm_map.items():
        _clubs = []
        for _cid in _ids:
            _p = next((x for x in prods if x.get("club_id") == _cid and x.get("kind") == "jersey"), None)
            if not _p:
                continue
            _th = club_themes().get(_cid, {})
            _clubs.append({"id":_cid,"name":cfg.CLUBS.get(_cid,{}).get(en and "en" or "ar",_cid),"emoji":cfg.CLUBS.get(_cid,{}).get("emoji","⚽"),"img":_p.get("imgs",[""])[0],"price":eff_price(_p),"ac":_th.get("ac","#18E875"),"ac2":_th.get("ac2","#0B9F50"),"product":_p.get("id")})
        _jm_data[_country] = {"flag":_flag,"label":_label,"clubs":_clubs}

    jersey_map_js = (
        '<script>\n(function(){\n'
        'var DATA=' + json_d(_jm_data) + ';\n'
        'var root=document.getElementById("jerseyMap");if(!root)return;\n'
        'var strip=document.getElementById("gxJmCountryStrip"),clubRow=document.getElementById("gxJmClubRow"),countryCard=document.getElementById("gxJmCountryCard"),jersey=document.getElementById("gxJmJersey"),buyClub=document.getElementById("gxJmBuyClub"),buyPrice=document.getElementById("gxJmBuyPrice"),buyBtn=document.getElementById("gxJmBuyBtn"),sizes=document.getElementById("gxJmSizes"),currentCountry="spain",currentClub=null;\n'
        'function money(v){var n=Math.round((Number(v)||0)*100)/100;return Number.isInteger(n)?String(n):String(n).replace(/0+$/g,"").replace(/\\.$/g,"");}\n'
        'function selectClub(c){currentClub=c;if(jersey)jersey.innerHTML="<img src=\"/img/"+encodeURIComponent(c.img)+"\" alt=\"\" loading=\"lazy\">";if(buyClub)buyClub.textContent=(c.name||"").toUpperCase();if(buyPrice)buyPrice.textContent=money(c.price)+" د.ب";if(buyBtn)buyBtn.href="/product/"+encodeURIComponent(c.product);clubRow.querySelectorAll("button[data-club]").forEach(function(b){b.classList.toggle("on",b.dataset.club===c.id);});}\n'
        'function renderCountry(k){var d=DATA[k];if(!d)return;currentCountry=k;root.querySelectorAll(".gx-jm-marker").forEach(function(m){m.classList.toggle("is-active",m.dataset.country===k);});strip.querySelectorAll("button[data-country]").forEach(function(b){b.classList.toggle("on",b.dataset.country===k);});countryCard.innerHTML="<div class=\"flag\">"+d.flag+"</div><b>"+d.label+"</b><span>"+d.clubs.length+" أندية</span>";clubRow.innerHTML=d.clubs.map(function(c){return "<button class=\"gx-jm-club-btn\" data-club=\""+c.id+"\" style=\"--ca:"+c.ac+";--cb:"+c.ac2+"\"><span>"+c.emoji+"</span><b>"+c.name+"</b></button>";}).join("");clubRow.querySelectorAll("button[data-club]").forEach(function(b){b.addEventListener("click",function(){var c=d.clubs.find(function(x){return x.id===b.dataset.club});if(c)selectClub(c);});});if(d.clubs[0])selectClub(d.clubs[0]);}\n'
        'Object.keys(DATA).forEach(function(k){var d=DATA[k],b=document.createElement("button");b.type="button";b.className="gx-jm-country-tab";b.dataset.country=k;b.textContent=d.flag+" "+d.label;b.addEventListener("click",function(){renderCountry(k);document.getElementById("gxJmJourney").scrollIntoView({behavior:"smooth",block:"center"});});strip.appendChild(b);});\n'
        'root.querySelectorAll(".gx-jm-marker").forEach(function(m){m.addEventListener("click",function(){renderCountry(m.dataset.country);document.getElementById("gxJmJourney").scrollIntoView({behavior:"smooth",block:"center"});});});\n'
        'sizes.querySelectorAll("button[data-size]").forEach(function(b){b.addEventListener("click",function(){sizes.querySelectorAll("button").forEach(function(x){x.classList.remove("active")});b.classList.add("active");});});\n'
        'renderCountry(currentCountry);\n})();</script>'
    )

    home_html = (atmos_html("full")
            + '<div class="wrap">' 
            + hero
            + jersey_map_html
            + fit_home
            + club_color_section
            + quiz_sec
            + fan_moment
            + pc_sec
            + md_ticker
            + club_swipe_sec
            + clubs_sec
            + ads_html("home")
            + features_html()
            + spotlight_html(prods)
            + '<div class="sec rv" id="jerseys"><div class="sec-head"><h2><span class="bar"></span>{sj}</h2><span class="sec-sub">{sj_sub}</span></div>'
            + shop_section_html(jgrid, "gridJ")
            + best_sec
            + new_sec
            + recent_sec
            + loyal_sec
            + '<div class="sec rv" id="mugs"><div class="sec-head"><h2><span class="bar"></span>{sm}</h2><span class="sec-sub">{sm_sub}</span></div>'
            + '<div class="grid" id="gridM">{mgrid}</div></div>'
            + size_sec
            + steps_sec
            + pitch_sec
            + match_html
            + poll_html
            + final_pitch
            + '<div class="sec rv" id="info"><div class="sec-head"><h2><span class="bar"></span>{qt}</h2></div>'
            + '<div class="quick">{quick}</div></div>'
            + '</div>'
            ).format(sj=d["sec_jerseys"], sj_sub=d["sec_jerseys_sub"],
                     sm=d["sec_mugs"], sm_sub=d["sec_mugs_sub"], qt=d["quick_title"],
                     jgrid=jgrid, mgrid=mgrid, quick=quick)
    home_html += jersey_map_js
    return home_html


def listing_page(kind):
    en = lang() == "en"
    d = cfg.L[lang()]
    if kind == "mug":
        title, sub = d["mugs_title"], d["mugs_sub"]
        head_ic = "☕⚽"
    else:
        title, sub = d["prod_title"], d["prod_sub"]
        head_ic = "👕"
    prods = [p for p in cfg.PRODUCTS if not p.get("hidden") and p["kind"] == kind]
    grid = "".join(product_card(p) for p in prods)
    search_bar = (
        '<div class="list-search rv">'
        '<div class="ls-head"><span class="ls-ic">{ic}</span><div><h1>{t}</h1><p>{s}</p></div></div>'
        '<div class="ls-box">'
        '<input id="sq2" placeholder="{ph}" onkeydown="if(event.key===\'Enter\')applyFilters()">'
        '<button class="btn pri" onclick="applyFilters()">🔍 {go}</button>'
        '<button class="btn ghost" onclick="openModal(\'m-imgsearch\')">🖼️ {is_}</button>'
        '</div>'
        '</div>'
        ).format(ic=head_ic, t=title, s=sub, ph=d["search_ph"], go=d["search_ph"], is_=d["is_title"])
    body = (atmos_html("light")
            + '<div class="wrap">'
            + ads_html("products")
            + search_bar
            + shop_section_html(grid, "gridL")
            + '<div style="text-align:center;margin-top:26px"><a class="back" href="/home">← {b}</a></div>'
            '</div>'
            ).format(b=d["back"])
    return base_page(body, active=("mugs" if kind == "mug" else "products"))


def size_guide_premium():
    """Premium dark stadium size guide with calculator — Asian Fit."""
    en = lang() == "en"
    d = cfg.L[lang()]
    size_chart_json = json_d(cfg.SIZE_CHART)
    size_order_json = json_d(cfg.SIZE_ORDER)
    prods = [p for p in cfg.PRODUCTS if not p.get("hidden") and p["kind"] == "jersey"]
    prods_json = json_d([{"id": p["id"], "name": p.get("name_en") if en else p.get("name_ar"),
                          "price": p.get("price", 0), "emoji": p.get("emoji", "⚽"),
                          "img": p["imgs"][0] if p.get("imgs") else "",
                          "club": p.get("club_id", ""), "badges": p.get("badges", [])} for p in prods[:12]])

    trust_items = [
        ("💬", d.get("sg_trust_support_t", "دعم 24/7"), d.get("sg_trust_support_d", "خدمتك في أي وقت")),
        ("🔄", d.get("sg_trust_exchange_t", "سهولة الاستبدال"), d.get("sg_trust_exchange_d", "استبدال سهل في حال عدم المقاس")),
        ("✅", d.get("sg_trust_quality_t", "راحة وجودة"), d.get("sg_trust_quality_d", "جودة عالية وخامات مريحة")),
        ("📐", d.get("sg_trust_sizes_t", "جميع المقاسات أصلية"), d.get("sg_trust_sizes_d", "منتجات بمقاسات واضحة ومعتمدة")),
    ]
    trust_html = "".join(
        '<div class="sg-trust-item"><span class="sg-trust-ic">{ic}</span>'
        '<div><b>{t}</b><span>{x}</span></div></div>'.format(ic=ic, t=t, x=x)
        for ic, t, x in trust_items)

    asian_note_ar = ("ملاحظة: مقاسات GOLAZOX تعتمد على الـ Asian Fit، وقد تكون أصغر من المقاسات المعتادة في بعض الدول. "
                     "استخدم الجدول والحاسبة كمرجع مساعد لاختيار المقاس الأقرب لك. "
                     "وللاحتياط، إذا كنت مترددًا بين مقاسين، ننصح باختيار المقاس الأكبر، "
                     "خصوصًا إذا كنت تفضل لبسًا أكثر راحة واتساعًا.")
    asian_note_en = ("Note: GOLAZOX sizes are based on Asian Fit and may run smaller than standard sizes in some regions. "
                     "Use the chart and calculator as a guide to find your closest size. "
                     "If you're between sizes, we recommend sizing up, "
                     "especially if you prefer a more relaxed or looser fit.")
    disclaimer_ar = "⚠️ المقاس المقترح تقديری وقد يختلف حسب شكل الجسم وطريقة اللبس."
    disclaimer_en = "⚠️ The suggested size is an estimate and may vary depending on body shape and fit preference."
    between_ar = "أنت بين مقاسين. للاحتياط، ننصح باختيار المقاس الأكبر {sz}، خصوصًا إذا كنت تفضل لبسًا مريحًا أو أوسع."
    between_en = "You're between sizes. We recommend sizing up to {sz} for a more comfortable fit."

    body = (
        '<div class="sg-page">'
        '<div class="sg-hero">'
        '<div class="sg-hero-inner">'
        '<div class="sg-hero-visual"><span class="sg-hero-jersey">👕</span>'
        '<span class="sg-hero-glow"></span></div>'
        '<div class="sg-hero-text">'
        '<h1><span class="sg-green">{title_word}</span> — Asian Fit</h1>'
        '<p>{sub}</p></div></div></div>'
        '<div class="wrap sg-wrap">'
        # Asian Fit disclaimer banner
        '<div class="sg-asian-note">{asian_note}</div>'
        '<div class="sg-calc-card" id="sgCalcCard">'
        '<div class="sg-calc-header"><h2>{calc_title} 👕</h2><p>{calc_sub}</p></div>'
        '<div class="sg-calc-inputs">'
        '<div class="sg-field"><label>{height_lbl}</label>'
        '<div class="sg-input-wrap"><input type="number" id="sgHeight" placeholder="170" min="140" max="220">'
        '<span class="sg-unit">{cm}</span></div></div>'
        '<div class="sg-field"><label>{weight_lbl}</label>'
        '<div class="sg-input-wrap"><input type="number" id="sgWeight" placeholder="70" min="30" max="200">'
        '<span class="sg-unit">{kg}</span></div></div></div>'
        '<button class="btn pri big sg-calc-btn" onclick="sgCalc()">{calc_btn} ⚽</button>'
        '<div class="sg-result" id="sgResult" style="display:none">'
        '<div class="sg-result-size" id="sgResultSize">M</div>'
        '<div class="sg-result-label">{result_label}</div>'
        '<div class="sg-result-details">'
        '<div class="sg-rdetail"><span>{weight_lbl}</span><b id="sgRWeight">70 {kg}</b></div>'
        '<div class="sg-rdetail"><span>{height_lbl}</span><b id="sgRHeight">170 {cm}</b></div></div>'
        '<div class="sg-result-badge">✓ {result_badge}</div>'
        '<div class="sg-disclaimer">{disclaimer}</div></div>'
        '<div class="sg-adjacent" id="sgAdjacent" style="display:none">'
        '<h3>{adj_title}</h3><p id="sgAdjAdvice"></p>'
        '<div class="sg-adj-cards" id="sgAdjCards"></div></div>'
        '<div class="sg-table-section">'
        '<h3>{table_title}</h3>'
        '{table}</div></div>'
        '<div class="sg-products" id="sgProducts" style="display:none">'
        '<div class="sec-head"><h2><span class="bar"></span>{prod_title} <span id="sgProdSize"></span></h2></div>'
        '<div class="grid" id="sgProdGrid"></div>'
        '<div style="text-align:center;margin-top:18px"><a class="btn ghost" href="/products">{prod_all}</a></div></div>'
        '<div class="sg-trust-bar">{trust}</div>'
        '</div></div>'
    ).format(
        title_word=d.get("sg_hero_t2", "المقاسات"),
        sub=d.get("sg_hero_sub", "اعثر على المقاس المثالي لك"),
        asian_note=asian_note_ar if not en else asian_note_en,
        calc_title=d.get("sg_calc_title", "وش مقاسك؟"),
        calc_sub="أدخل طولك ووزنك، ونقترح لك المقاس الأقرب لك",
        height_lbl=d.get("sg_height", "الطول"),
        weight_lbl=d.get("sg_weight", "الوزن"),
        cm=d.get("szt_cm", "سم"), kg=d.get("szt_kg", "كجم"),
        calc_btn=d.get("sg_calc_btn", "اعرف مقاسي"),
        result_label="المقاس المقترح لك" if not en else "Suggested Size",
        result_badge="توصية تقديرية — للمساعدة فقط" if not en else "Estimate — for guidance only",
        disclaimer=disclaimer_ar if not en else disclaimer_en,
        adj_title=d.get("sg_adj_title", "بين مقاسين؟"),
        table_title="جدول المقاسات — Asian Fit" if not en else "Size Chart — Asian Fit",
        table=size_table_html(cfg.SIZE_CHART),
        prod_title=d.get("sg_prod_title", "منتجات تناسب مقاسك"),
        prod_all=d.get("view_all", "عرض الكل"),
        trust=trust_html,
    )
    page_js = '<script>\nvar SG_CHART=' + size_chart_json + ';\nvar SG_ORDER=' + size_order_json + ';\nvar SG_PRODS=' + prods_json + ';\nvar SG_CM=\'' + d.get("szt_cm", "سم") + '\';\nvar SG_KG=\'' + d.get("szt_kg", "كجم") + '\';\nvar SG_CUR=\'' + cur() + '\';\nvar SG_BETWEEN=' + json_d({"ar": between_ar, "en": between_en}) + ';\nvar SG_LANG=\'' + ("en" if en else "ar") + '\';\n' + r"""
function sgSizeFromHW(h,w){
  if(!h||!w) return null;
  var best=null,bestDist=9999,bestSz=null;
  SG_ORDER.forEach(function(sz){
    var c=SG_CHART[sz]; if(!c) return;
    var hw=c.height.split('\u2013');
    var ww=c.weight.split('\u2013');
    var hMin=parseFloat(hw[0])||0,hMax=parseFloat(hw[1])||999;
    var wMin=parseFloat(ww[0])||0,wMax=parseFloat(ww[1])||999;
    var hMid=(hMin+hMax)/2, wMid=(wMin+wMax)/2;
    var dist=Math.abs(h-hMid)*0.6+Math.abs(w-wMid)*0.4;
    if(dist<bestDist){bestDist=dist;best=sz;}
  });
  var idx=SG_ORDER.indexOf(best);
  var prev=(idx>0)?SG_ORDER[idx-1]:null;
  var prevDist=9999;
  if(prev){
    var c2=SG_CHART[prev];if(c2){
      var hw2=c2.height.split('\u2013');var ww2=c2.weight.split('\u2013');
      var hMid2=(parseFloat(hw2[0])+parseFloat(hw2[1]))/2;
      var wMid2=(parseFloat(ww2[0])+parseFloat(ww2[1]))/2;
      prevDist=Math.abs(h-hMid2)*0.6+Math.abs(w-wMid2)*0.4;
    }
  }
  var between=(prev && bestDist-prevDist<1.2 && prevDist<bestDist*1.1);
  return {size:best, between:between, lower:prev};
}
function sgCalc(){
  var h=parseFloat(($('sgHeight')||{}).value)||0;
  var w=parseFloat(($('sgWeight')||{}).value)||0;
  if(!h||!w){toast('\u0623\u062f\u062e\u0644 \u0627\u0644\u0637\u0648\u0644 \u0648\u0627\u0644\u0648\u0632\u0646');return;}
  var result=sgSizeFromHW(h,w);
  if(!result||!result.size){toast('\u062a\u062d\u0642\u0642 \u0645\u0646 \u0627\u0644\u0642\u064a\u0645');return;}
  var sz=result.size;
  var res=$('sgResult');if(res) res.style.display='block';
  var szEl=$('sgResultSize');if(szEl){szEl.textContent=sz;szEl.className='sg-result-size sg-pop';}
  var wEl=$('sgRWeight');if(wEl) wEl.textContent=w+' '+SG_KG;
  var hEl=$('sgRHeight');if(hEl) hEl.textContent=h+' '+SG_CM;
  var idx=SG_ORDER.indexOf(sz);
  var adj=[];
  if(idx>0) adj.push({sz:SG_ORDER[idx-1],label:SG_LANG==='ar'?'\u0623\u0648\u0633\u0639 \u0642\u0644\u064a\u0644\u064b\u0627':'Smaller'});
  if(idx<SG_ORDER.length-1) adj.push({sz:SG_ORDER[idx+1],label:SG_LANG==='ar'?'\u0627\u0644\u0645\u0642\u0627\u0633 \u0627\u0644\u0623\u0642\u0631\u0628':'Larger'});
  var adjBox=$('sgAdjacent');var adjCards=$('sgAdjCards');
  var adjAdvice=$('sgAdjAdvice');
  if(adjBox&&adjCards&&adj.length){
    adjBox.style.display='block';
    if(adjAdvice){
      if(result.between){
        adjAdvice.textContent=SG_BETWEEN[SG_LANG].replace('{sz}',adj[adj.length-1].sz);
      } else {
        adjAdvice.textContent=SG_LANG==='ar'?'أنت بين مقاسين، اختر الأنسب لك':'Choose the size that fits you best';
      }
    }
    adjCards.innerHTML=adj.map(function(a){
      return '<div class="sg-adj-card'+(a.label.indexOf('\u0627\u0644\u0623\u0642\u0631\u0628')>-1||a.label==='Larger'?' on':'')+'">'
        +'<div class="sg-adj-sz">'+a.sz+'</div>'
        +'<div class="sg-adj-lbl">'+a.label+'</div></div>';
    }).join('');
  }
  var prodBox=$('sgProducts');var prodGrid=$('sgProdGrid');var prodSz=$('sgProdSize');
  if(prodBox&&prodGrid){
    prodBox.style.display='block';
    if(prodSz) prodSz.textContent='('+sz+')';
    prodGrid.innerHTML=SG_PRODS.slice(0,6).map(function(p){
      return '<div class="pcard" data-id="'+p.id+'">'
        +'<a href="/product/'+p.id+'"><div class="pimg" style="background:var(--card2)">'
        +'<img src="/img/'+p.img+'" alt="'+p.name+'" loading="lazy"></div></a>'
        +'<div class="pbody"><span class="pcat">'+p.club+'</span>'
        +'<h3>'+p.name+'</h3>'
        +'<div class="pfoot"><b>'+(Number.isInteger(Number(p.price))?String(Number(p.price)):String(Number(p.price)).replace(/0+$/,'').replace(/\.$/,''))+' '+SG_CUR+'</b>'
        +'<a class="pview" href="/product/'+p.id+'">\u2190</a></div></div></div>';
    }).join('');
  }
  if(res) res.scrollIntoView({behavior:'smooth',block:'center'});
}
</script>"""
    return base_page(body, page_js=page_js, active="sizes")


def info_page(kind):
    en = lang() == "en"
    d = cfg.L[lang()]
    if kind == "size":
        return size_guide_premium()
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
        steps = "".join(
            ('<div class="hw-step rv">'
             '<div class="hw-dot">{n}</div>'
             '<div class="hw-line"></div>'
             '<div class="hw-ic">{ic}</div>'
             '<div class="hw-txt"><b>{t}</b><span>{x}</span></div>'
             '</div>')
            .format(n=i + 1, ic=("🛒", "📏", "🛍️", "💬", "📦", "⭐")[i],
                    t=d["how_%d_t" % (i + 1)], x=d["how_" + str(i + 1)])
            for i in range(6))
        price_j = fmt_cur(cfg.PRICE_JERSEY)
        price_m = fmt_cur(cfg.PRICE_MUG)
        deliv = fmt_cur(cfg.DELIVERY_FEE)
        price_cards = (
            '<div class="hw-price-card rv" style="--hwc:var(--ac);--hwc2:var(--ac2)">'
            '<div class="hwp-ic">👕</div><div class="hwp-t">{jt}</div>'
            '<div class="hwp-price">{pj}</div><div class="hwp-d">{jd}</div></div>'
            '<div class="hw-price-card rv" style="--hwc:#16A34A;--hwc2:#22C55E">'
            '<div class="hwp-ic">☕⚽</div><div class="hwp-t">{mt}</div>'
            '<div class="hwp-price">{pm}</div><div class="hwp-d">{md}</div></div>'
            '<div class="hw-price-card rv" style="--hwc:#3B82F6;--hwc2:#60A5FA">'
            '<div class="hwp-ic">🚚</div><div class="hwp-t">{dt}</div>'
            '<div class="hwp-price">{dv}</div><div class="hwp-d">{dd}</div></div>'
            ).format(jt=d["how_sec_jersey"], pj=price_j, jd=d["how_sec_jersey_d"],
                     mt=d["how_sec_mug"], pm=price_m, md=d["how_sec_mug_d"],
                     dt=d["how_delivery_t"], dv=deliv, dd=d["how_delivery_d"])
        ctas = ('<a class="btn pri" href="/products">{cj}</a>'
                '<a class="btn ghost" href="/mugs">{cm}</a>'
                '<a class="btn ghost" href="/size-guide">{cs}</a>'
                '<a class="btn wa2" target="_blank" rel="noopener" href="https://wa.me/{wa}">{cw}</a>'
                ).format(cj=d["how_cta_j"], cm=d["how_cta_m"], cs=d["how_cta_sz"],
                         cw=d["how_cta_wa"], wa=cfg.WHATSAPP)
        inner = ('<div class="hw-timeline">{steps}</div>'
                 '<div class="hw-prices"><h2><span class="bar"></span>{pt}</h2>'
                 '<p class="hw-sub">{ps}</p><div class="hw-price-grid">{cards}</div></div>'
                 '<div class="hw-ctas">{ctas}</div>'
                 ).format(steps=steps, pt=d["how_prices_t"], ps=d["how_prices_sub"],
                          cards=price_cards, ctas=ctas)
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
    team_style = (
        '<style>'
        ':root{{ --team-ac:{ac}; --team-ac2:{ac2}; }}'
        '.club-banner{{ transition: box-shadow .4s ease; }}'
        '.club-banner:hover{{ box-shadow: 0 20px 50px rgba(0,0,0,.3), 0 0 40px {ac}33; }}'
        '.club-banner h1{{ transition: color .3s ease; }}'
        '.club-banner .btn{{ transition: background .3s ease, box-shadow .3s ease; }}'
        '.sec-head .bar{{ transition: background .3s ease; }}'
        '</style>'
    ).format(ac=ac, ac2=ac2)
    team_style = team_style.replace('{', '{{').replace('}', '}}')
    body = (team_style + atmos_html("full")
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
    clubn_ar = (club and club.get("ar")) or ""
    clubn_en = (club and club.get("en")) or ""
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
    searchable = " ".join(filter(None, [
        p.get("name_ar", ""), p.get("name_en", ""),
        clubn_ar, clubn_en,
        p.get("desc_ar", ""), p.get("desc_en", ""),
        p["id"], p["kind"],
    ])).replace('"', "&quot;").lower()
    edition_html = ('<div class="pcard-edition">GOLAZOX EDITION</div>' if club_id else "")
    return (
        '<div class="pcard" data-id="{id}" data-kind="{kind}" data-club="{cid}" data-clubn="{cn}" data-search="{search}" data-stock="{csv}" data-price="{price}" data-name="{name}" data-order="{order}" data-badge="{bcsv}" data-col="{ncol}" style="--pc:{pc};--pc2:{pc2}">'
        '<div class="pcard-inner">'
        '<div class="pcard-glow"></div>'
        '<div class="badges">{badges}</div>'
        '<button class="heart {on}" onclick="toggleFav(\'{id}\',this)">{h}</button>'
        '<a href="/product/{id}"><div class="pimg">'
        '<img src="/img/{first}" alt="{name}" loading="lazy" onerror="this.onerror=null;this.style.display=\'none\';var f=document.createElement(\'div\');f.className=\'pimg-fallback\';f.textContent=\'⚽\';this.parentElement.appendChild(f)"></div></a>'
        '<div class="pover"><a class="pover-btn" href="/product/{id}">{view} ←</a></div>'
        '<div class="pbody"><span class="pcat">{cat}</span><h3>{name}</h3>'
        '{edition}'
        '{low}'
        '{sizes_row}'
        '<div class="pcols">{pdots}</div>'
        '<div class="pfoot"><b>{pr}</b><a class="pview" href="/product/{id}">{view} ←</a></div></div></div></div>'
    ).format(id=p["id"], kind=p["kind"], cid=club_id, cn=clubn.replace('"', "&quot;"), search=searchable,
             csv=stock_csv, price=eff_price(p), name=name.replace('"', "&quot;"), badges=badges_html,
             on="on" if fav else "", h="❤" if fav else "🤍",
             c1=p["colors"][0], c2=p["colors"][1], first=first, cat=cat, pr=pr, view=d["view"], low=low,
             order=order, bcsv=b_csv, ncol=ncol, sizes_row=sizes_row, pdots=pdots,
             pc=pc, pc2=pc2, edition=edition_html)


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
                 '<span style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span class="szlink" onclick="openModal(\'m-sizes\')">📏 {sg}</span><span class="szlink" onclick="openModal(\'m-fitcheck\')">✨ Fit Check</span></span></div>'
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

    # Matchday Mode toggle
    matchday_btn = ('<button class="btn ghost matchday-btn" id="matchdayBtn" onclick="toggleMatchday()">'
                    '⚽ MATCHDAY</button>')

    # Outfit Builder removed by request
    outfit_html = ""

    # Live Drop badge
    live_drop = ""
    if "new" in p.get("badges", []):
        live_drop = '<div class="live-drop-badge"><span class="live-dot"></span>LIVE DROP</div>'

    page_js = ('<script>var GARR=' + arr + ';' + ('selSize=' + json_d(my_sz) + ';' if my_sz else '') +
               'document.addEventListener("DOMContentLoaded",function(){ try{var rv=JSON.parse(localStorage.getItem("gx_recent_views")||"[]");rv=[%s].concat(rv.filter(function(x){return x!=="%s";})).slice(0,8);localStorage.setItem("gx_recent_views",JSON.stringify(rv));}catch(e){} setGal(0,GARR); buildReviews("%s");'
               'if(selSize){var om=document.getElementById("omSizeVal");if(om)om.textContent=selSize;} });'
               'function triggerReveal(){var r=document.getElementById("jeReveal");if(r)r.classList.add("open");}'
               'function initJerseyExp(){var r=document.getElementById("jeReveal");if(!r)return;'
               'var io=new IntersectionObserver(function(e){if(e[0].isIntersecting){setTimeout(function(){triggerReveal()},800);io.disconnect();}},{threshold:0.4});io.observe(r);}'
               'document.addEventListener("DOMContentLoaded",function(){initJerseyExp();});</script>') % (p["id"], p["id"], p["id"])

    one = len(p["imgs"]) <= 1
    gal_nav = "" if one else (
        '<span class="gcount" id="gcount">1 {of} {n}</span>'
        '<button class="gar r" id="garr" onclick="event.stopPropagation();movGal(1)">‹</button>'
        '<button class="gar l" id="garr2" onclick="event.stopPropagation();movGal(-1)">›</button>'
    ).format(of=d["img_of"], n=len(p["imgs"]))
    thumbs_block = "" if one else '<div class="gthumb" id="gthumbs">{gthumbs}</div>'

    # Team page theme
    team_theme = cfg.TEAM_PAGE_THEMES.get(club_id, {})
    team_style = ""
    team_atmos = ""
    team_label = ""
    if team_theme and not is_mug:
        tt = team_theme
        team_label = '<div class="tm-label" style="color:{ac}"><span class="tm-label-dot" style="background:{ac}"></span>{lbl}</div>'.format(
            ac=tt.get("accent", "#18E875"), lbl=tt.get("label", ""))
        team_style = (
            '<style>'
            ':root{{ --team-ac:{accent}; --team-ac2:{accent2}; --team-glow1:{glow1}; --team-glow2:{glow2}; }}'
            '.pg-wrap{{ background:{bg1}; }}'
            '.pg-wrap::before{{ content:""; position:fixed; inset:0; pointer-events:none; z-index:0; '
            'background: radial-gradient(ellipse 80% 50% at 50% 30%, {glow1}, transparent 60%), '
            'radial-gradient(ellipse 60% 40% at 20% 80%, {glow2}, transparent 50%), '
            'linear-gradient(180deg, {bg1} 0%, {bg2} 40%, {bg3} 100%); '
            'transition: background .5s ease; }}'
            '.pg-wrap .wrap{{ position:relative; z-index:1; }}'
            '.gmain{{ border-color: {accent}30; }}'
            '.gmain::before{{ background: radial-gradient(circle, {glow1}, transparent 70%) !important; }}'
            '.gmain:hover{{ box-shadow: 0 30px 70px rgba(0,0,0,.5), 0 0 60px {glow1}; }}'
            '.tm-label{{ display:inline-flex; align-items:center; gap:6px; padding:4px 14px; border-radius:999px; '
            'background:rgba(255,255,255,.04); border:1px solid {accent}20; font-size:.68rem; font-weight:800; '
            'letter-spacing:1.5px; text-transform:uppercase; margin-bottom:10px; transition: border-color .4s ease; }}'
            '.tm-label-dot{{ width:6px; height:6px; border-radius:50%; transition: background .4s ease; }}'
            '.pprice{{ color:{accent}; transition: color .4s ease; }}'
            '.pcatline{{ color:{accent}cc; transition: color .4s ease; }}'
            '.btn.pri{{ background:linear-gradient(90deg,{accent},{accent2}); box-shadow:0 12px 30px {glow1}; transition: background .4s ease, box-shadow .4s ease; }}'
            '.btn.pri:hover{{ box-shadow:0 16px 40px {glow1}, 0 0 30px {glow1}; }}'
            '.link3:hover{{ border-color:{accent}; color:{accent}; }}'
            '.sz-pill:hover{{ border-color:{accent}; }}'
            '.size-chip.on{{ background:linear-gradient(90deg,{accent},{accent2}); transition: background .4s ease; }}'
            '@media (prefers-reduced-motion:reduce){{ .tm-ball,.tm-particles *{{ animation:none!important; }} }}'
            '</style>'
        ).format(**tt)
        team_style = team_style.replace('{', '{{').replace('}', '}}')
        # Atmosphere layers
        team_atmos = (
            '<div class="tm-atmos" aria-hidden="true">'
            '<div class="tm-pitch"></div>'
            '<div class="tm-particles"><i></i><i></i><i></i><i></i><i></i></div>'
            '<div class="tm-ball">⚽</div>'
            '</div>'
        )

    # Jersey Stadium Experience
    jersey_exp = ""
    if not is_mug and club_id:
        club_theme = cfg.CLUB_THEMES.get(club_id, {})
        ac = club_theme.get("ac", "#18E875")
        ac2 = club_theme.get("ac2", "#0D7A46")
        glow1 = club_theme.get("glow1", "rgba(24,232,117,.12)")
        jersey_exp = (
            '<div class="jersey-exp" style="--je-ac:{ac};--je-ac2:{ac2};--je-glow:{glow}">'
            '<div class="je-section"><div class="je-head"><h2><span class="bar"></span>{reveal_t}</h2>'
            '<p class="je-sub">{reveal_sub}</p></div>'
            '<div class="je-reveal" id="jeReveal">'
            '<div class="je-curtain left"></div><div class="je-curtain right"></div>'
            '<div class="je-stadium-lines"></div><div class="je-halo"></div>'
            '<div class="je-jersey"><img src="/img/{first}" alt="{name}"></div>'
            '<div class="je-spotlight"></div>'
            '<div class="je-nameplate"><b>{name}</b><span>{club_tag}</span></div>'
            '<div class="je-reveal-btn" onclick="triggerReveal()">{reveal_btn}</div></div></div>'
            '<div class="je-section"><div class="je-head"><h2><span class="bar"></span>{locker_t}</h2>'
            '<p class="je-sub">{locker_sub}</p></div>'
            '<div class="je-locker">'
            '<div class="je-locker-slot" style="border-color:{ac}33">'
            '<div class="je-locker-jersey"><img src="/img/{first}" alt=""></div>'
            '<div class="je-locker-name">{name}</div>'
            '<div class="je-locker-num">#{num}</div></div>'
            '<div class="je-locker-shelf">'
            '<div class="je-shelf-item"><span>⚽</span>{t_shelf1}</div>'
            '<div class="je-shelf-item"><span>👟</span>{t_shelf2}</div>'
            '<div class="je-shelf-item"><span>🧤</span>{t_shelf3}</div>'
            '</div></div></div>'
            '<div class="je-section"><div class="je-head"><h2><span class="bar"></span>{tunnel_t}</h2></div>'
            '<div class="je-tunnel">'
            '<div class="je-tunnel-wall left"></div>'
            '<div class="je-tunnel-road"></div>'
            '<div class="je-tunnel-wall right"></div>'
            '<div class="je-tunnel-light"></div>'
            '<div class="je-tunnel-end">⚽ {pitch}</div>'
            '</div></div></div>'
        ).format(
            ac=ac, ac2=ac2, glow=glow1, first=p["imgs"][0], name=name,
            reveal_t=d.get("je_reveal_t", "Jersey Reveal") if en else "كشف الزي",
            reveal_sub=d.get("je_reveal_sub", "Your new kit awaits") if en else "طقمك الجديد في انتظارك",
            reveal_btn=d.get("je_reveal_btn", "REVEAL") if en else "كشف",
            club_tag=cfg.club_name(p, en).upper(),
            locker_t=d.get("je_locker_t", "Locker Room") if en else "غرفة تبديل الملابس",
            locker_sub=d.get("je_locker_sub", "Your jersey, your spot") if en else "قمصك، مكانك",
            t_shelf1=d.get("je_shelf1", "Match Ball") if en else "كرة المباراة",
            t_shelf2=d.get("je_shelf2", "Boots") if en else "الحذاء",
            t_shelf3=d.get("je_shelf3", "Gloves") if en else "القفازات",
            tunnel_t=d.get("je_tunnel_t", "Walk to Pitch") if en else "المشي نحو الملعب",
            pitch=d.get("je_pitch", "PITCH") if en else "الملعب",
            num=str(abs(hash(p["id"])) % 99 + 1),
        )

    body = (
        team_style + atmos_html("light")
        + '<div class="wrap pg-wrap">'
        + team_atmos
        + '<input type="hidden" id="prod_id" value="{id}">'
        '{live_drop}'
        '<a class="back" href="/home">← {back}</a>'
        '<div class="pg">'
        '<div class="gal"><div class="gmain" onclick="openLB(gi)">'
        '<div class="gmain-ref"></div>'
        '<img id="gmain" src="/img/{first}" alt="{name}" onerror="this.onerror=null;this.style.display=\'none\';var f=document.createElement(\'div\');f.className=\'pimg-fallback\';f.textContent=\'⚽\';this.parentElement.appendChild(f)">'
        '{gal_nav}</div>'
        '{thumbs_block}'
        '<p class="zoom-hint">🔍 {zh}</p></div>'
        '<div class="pinfo">{team_label}<h1>{name}</h1><p class="pcatline">{cat}</p>'
        '<div class="pprice">{pr}</div>{trust}{trust_info}'
        '{sizes}'
        '<div class="qtysec"><div class="lbl">{ql}</div>'
        '<div class="qty"><button onclick="chgQ(-1)">−</button><span class="qn" id="qty">1</span><button onclick="chgQ(1)">+</button></div></div>'
        '{matchday_btn}'
        '<button class="btn pri orderbtn" onclick="var q=parseInt(document.getElementById(\'qty\').textContent,10);addCart(\'{id}\',selSize||\'\',q)">🛒 {add}</button>'
        '<button class="btn wa orderbtn" style="margin-top:10px" onclick="orderDirect(\'{id}\')">💬 {ow}</button>'
        '<button class="btn ghost orderbtn" style="margin-top:10px" onclick="openPriceDrop(\'{id}\')">🔔 {pd}</button>'
        '{notify}'
        '<div class="links3">'
        '<div class="link3" onclick="openModal(\'m-sizes\')"><span class="ic">📏</span>{a}</div>'
        '<div class="link3" onclick="openModal(\'m-wash\')"><span class="ic">🧺</span>{b}</div>'
        '<div class="link3" onclick="openModal(\'m-ret\')"><span class="ic">🔄</span>{c}</div></div>'
        '</div></div>'
        '{outfit}'
        '{jersey_exp}'
        '{ratings}{yml}'
        '</div>'
    ).format(back=d["back"], first=p["imgs"][0], name=name, gal_nav=gal_nav, thumbs_block=thumbs_block,
             gthumbs=gthumbs, zh=d["zoom_hint"], cat=cat, pr=pr, trust=trust, trust_info=trust_info,
             sizes=sizes, ql=d["qty_label"], id=p["id"], add=d["add"], ow=d["order_wa"],
             pd=d["pd_title"],
             notify=notify, a=d["prod_links_sz"], b=d["prod_links_wash"], c=d["prod_links_ret"],
             ratings=ratings, yml=yml, matchday_btn=matchday_btn, outfit=outfit_html,
             jersey_exp=jersey_exp, live_drop=live_drop, team_label=team_label)

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
      window.open('https://wa.me/message/KZFSQ7ONXMY2M1?text='+encodeURIComponent(msg),'_blank');
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
            + auth_box_html("lp_") +
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
    themes = club_themes()

    def _order_team(o):
        for it in o["data"].get("items", []):
            p = next((x for x in cfg.PRODUCTS if x["id"] == it.get("id")), None)
            if p and p.get("club_id"):
                return p["club_id"]
        return None

    def _team_theme(cid):
        if cid and cid in themes:
            t = themes[cid]
            return {"ac": t.get("ac", "#18E875"), "ac2": t.get("ac2", "#0B9F50"),
                    "glow": t.get("glow", "#18E875"), "tint": t.get("tint", "#18E875"),
                    "name": cfg.CLUBS.get(cid, {}).get(en and "en" or "ar", ""),
                    "emoji": cfg.CLUBS.get(cid, {}).get("emoji", "⚽"),
                    "cid": cid}
        return {"ac": "#00E676", "ac2": "#16A765", "glow": "#00E676", "tint": "#00E676",
                "name": "GOLAZOX", "emoji": "⚽", "cid": ""}

    def _mk_css(ac, glow):
        return ('--mk-ac:{ac};--mk-ac2:{ac2};--mk-glow:{glow};'
                '--mk-glow1:{glow1};--mk-glow2:{glow2};--mk-border:{border};--mk-ac-soft:{acsoft}').format(
            ac=ac, ac2=_team_theme(None)["ac2"], glow=hex_rgba(glow, 0.35),
            glow1=hex_rgba(ac, 0.10), glow2=hex_rgba(ac, 0.04),
            border=hex_rgba(ac, 0.15), acsoft=hex_rgba(ac, 0.12))

    def _step_icon(i):
        return ["✓", "✓", "✓", "✓", "✓"][i] if i < 5 else "●"

    def _status_journey(o, th):
        st = o["status"]
        if st == "cancelled":
            return ('<div class="mk-journey" style="border-color:rgba(239,68,68,.15)">'
                    '<div class="mk-journey-title" style="color:#FCA5A5">{lbl}</div>'
                    '<div style="text-align:center;color:rgba(255,255,255,.6);padding:8px 0">{msg}</div></div>').format(
                lbl=d.get("st_cancelled", "Cancelled"), msg="—")
        idx = ORDER_FLOW.index(st) if st in ORDER_FLOW else -1
        labels = [d.get("st_pending", "Pending"), d.get("st_confirmed", "Confirmed"),
                  d.get("st_preparing", "Preparing"), d.get("st_delivering", "Delivering"),
                  d.get("st_delivered", "Delivered")]
        steps = ""
        for i in range(5):
            cls = "done" if i < idx else ("cur" if i == idx else "")
            steps += ('<div class="mk-step {cls}">'
                      '<div class="mk-step-dot">{icon}</div>'
                      '<div class="mk-step-lbl">{lbl}</div>'
                      '{line}</div>').format(cls=cls, icon=_step_icon(i) if i < idx else ("▶" if i == idx else "○"),
                                            lbl=labels[i],
                                            line='<div class="mk-step-line"></div>' if i < 4 else "")
        return ('<div class="mk-journey" style="{css}">'
                '<div class="mk-journey-title">⚽ {title}</div>'
                '<div class="mk-journey-steps">{steps}</div></div>').format(
            css=_mk_css(th["ac"], th["glow"]), title=d.get("tick_progress", "Order Journey"), steps=steps)

    def _main_ticket(o):
        dta = o["data"]
        code = o["code"]
        th = _team_theme(_order_team(o))
        item = dta.get("items", [{}])[0] if dta.get("items") else {}
        p = next((x for x in cfg.PRODUCTS if x["id"] == item.get("id")), None)
        team_name = th["name"]
        item_name = item.get("name", "—")
        item_size = item.get("size", "—")
        item_qty = item.get("qty", 1)
        order_total = fmt_cur(dta.get("total", 0))
        order_date = dta.get("date", "—")
        order_status = d.get("st_" + o["status"], o["status"])
        match_id = "GX-" + code.replace("GX-", "") if code.startswith("GX-") else "GX-" + code
        seat_no = str(u["id"]).zfill(4)
        gate = "G" + str(hash(code) % 20 + 1).zfill(2)
        section = "S" + str(hash(code) % 10 + 1)
        row_letter = chr(65 + (hash(code) % 8))
        barcode_num = code.replace("GX-", "").replace("-", "").zfill(12)
        css = _mk_css(th["ac"], th["glow"])
        ticket = (
            '<div class="mk-ticket" style="{css}">'
            '<div class="mk-ticket-top">'
            '<div class="mk-ticket-brand"><h3>GOLAZOX</h3><div class="mk-ticket-sub">MATCHDAY TICKET</div></div>'
            '<div class="mk-matchup">'
            '<div class="mk-team"><div class="mk-team-role">HOME</div><div class="mk-team-name">GOLAZOX</div></div>'
            '<div class="mk-vs">VS</div>'
            '<div class="mk-team"><div class="mk-team-role">TEAM</div><div class="mk-team-name">{emoji} {team}</div></div>'
            '</div></div>'
            '<div class="mk-ticket-mid">'
            '<div class="mk-detail-grid">'
            '<div class="mk-detail"><div class="mk-detail-label">{item_lbl}</div><div class="mk-detail-value">{item_name}</div></div>'
            '<div class="mk-detail"><div class="mk-detail-label">{size_lbl}</div><div class="mk-detail-value">{size}</div></div>'
            '<div class="mk-detail"><div class="mk-detail-label">{qty_lbl}</div><div class="mk-detail-value">{qty}</div></div>'
            '<div class="mk-detail"><div class="mk-detail-label">{total_lbl}</div><div class="mk-detail-value mk-highlight">{total}</div></div>'
            '<div class="mk-detail"><div class="mk-detail-label">{order_lbl}</div><div class="mk-detail-value" style="font-family:monospace">#{code}</div></div>'
            '<div class="mk-detail"><div class="mk-detail-label">{date_lbl}</div><div class="mk-detail-value">{date}</div></div>'
            '<div class="mk-detail"><div class="mk-detail-label">{status_lbl}</div><div class="mk-detail-value" style="color:{ac}">{status}</div></div>'
            '<div class="mk-detail"><div class="mk-detail-label">{match_lbl}</div><div class="mk-detail-value" style="font-family:monospace">{match_id}</div></div>'
            '</div></div>'
            '<div class="mk-ticket-bottom">'
            '<div class="mk-barcode"><div class="mk-barcode-lines"></div><div class="mk-barcode-id">{barcode}</div></div>'
            '<div class="mk-ticket-meta">'
            '<div class="mk-meta-item"><div class="mk-meta-label">SEAT</div><div class="mk-meta-val">{seat}</div></div>'
            '<div class="mk-meta-item"><div class="mk-meta-label">GATE</div><div class="mk-meta-val">{gate}</div></div>'
            '<div class="mk-meta-item"><div class="mk-meta-label">SECTION</div><div class="mk-meta-val">{section}</div></div>'
            '<div class="mk-meta-item"><div class="mk-meta-label">ROW</div><div class="mk-meta-val">{row}</div></div>'
            '</div></div>'
            '<div class="mk-ticket-actions">'
            '<a class="hbtn" href="/ticket?code={code}">{view_lbl}</a>'
            '<a class="hbtn" href="/track?code={code}">{track_lbl}</a>'
            '<button class="hbtn" onclick="openReorder(\'{code}\')">{reorder_lbl}</button>'
            '</div></div>'
        ).format(
            css=css, emoji=th["emoji"], team=esc(team_name),
            item_lbl="ITEM" if en else "المنتج", item_name=esc(item_name),
            size_lbl="SIZE" if en else "المقاس", size=esc(item_size),
            qty_lbl="QTY" if en else "الكمية", qty=item_qty,
            total_lbl="TOTAL" if en else "الإجمالي", total=order_total,
            order_lbl="ORDER" if en else "رقم الطلب", code=esc(code),
            date_lbl="DATE" if en else "التاريخ", date=esc(order_date),
            status_lbl="STATUS" if en else "الحالة", status=esc(order_status), ac=th["ac"],
            match_lbl="MATCH ID", match_id=esc(match_id),
            barcode=barcode_num, seat=seat_no, gate=gate, section=section, row=row_letter,
            view_lbl="🎫 " + d.get("acc_view", "View"),
            track_lbl="🚚 " + d.get("acc_track", "Track"),
            reorder_lbl="🔄 " + d.get("acc_reorder", "Reorder")
        )
        return ticket, _status_journey(o, th), th

    def _mini_ticket(o):
        dta = o["data"]
        code = o["code"]
        th = _team_theme(_order_team(o))
        item = dta.get("items", [{}])[0] if dta.get("items") else {}
        p = next((x for x in cfg.PRODUCTS if x["id"] == item.get("id")), None)
        img = ("/img/" + esc(p["imgs"][0])) if p and p.get("imgs") else ""
        img_html = ('<img src="' + img + '" alt="" loading="lazy">') if img else esc(th["emoji"])
        st_cls = "st-" + o["status"]
        status_txt = d.get("st_" + o["status"], o["status"])
        css = _mk_css(th["ac"], th["glow"])
        return ('<div class="mk-mini" style="{css}" onclick="mkDetail(\'{code}\')">'
                '<div class="mk-mini-top">'
                '<div class="mk-mini-img">{img}</div>'
                '<div class="mk-mini-info">'
                '<div class="mk-mini-team">{emoji} {team}</div>'
                '<div class="mk-mini-name">{name}</div>'
                '</div>'
                '<span class="mk-mini-status {st_cls}">{status}</span>'
                '</div>'
                '<div class="mk-mini-bottom">'
                '<div><div class="mk-mini-code">#{code}</div><div class="mk-mini-date">{date}</div></div>'
                '<div class="mk-mini-price">{total}</div>'
                '</div></div>'
        ).format(
            css=css, code=esc(code), emoji=th["emoji"], team=esc(th["name"]),
            name=esc(item.get("name", "—")), st_cls=st_cls, status=esc(status_txt),
            date=esc(dta.get("date", "")), total=fmt_cur(dta.get("total", 0)),
            img=img_html
        )

    # --- Build sections ---
    active_orders = [o for o in orders if o["status"] != "delivered" and o["status"] != "cancelled"]
    past_orders = [o for o in orders if o["status"] == "delivered" or o["status"] == "cancelled"]

    # Main ticket (most recent active order, or most recent overall)
    current_order = active_orders[-1] if active_orders else (orders[-1] if orders else None)
    main_ticket_html = ""
    journey_html = ""
    main_theme = _team_theme(None)

    if current_order:
        main_ticket_html, journey_html, main_theme = _main_ticket(current_order)
    else:
        main_ticket_html = (
            '<div class="mk-empty">🏟️ {no_match}</div>'
            '<a class="mk-explore" href="/teams">{explore}</a>'
        ).format(no_match="ما عندك مباراة حالية" if not en else "No match in progress",
                 explore="اكتشف الفرق ⚽" if not en else "Explore Teams ⚽")

    # Past mini tickets
    mini_html = ""
    if past_orders:
        for o in reversed(past_orders):
            mini_html += _mini_ticket(o)
    mini_section = ""
    if mini_html:
        mini_section = (
            '<div class="mk-section-head"><h3>{title}</h3><div class="mk-sh-line"></div></div>'
            '<div class="mk-mini-tickets">{tickets}</div>'
        ).format(title="طلباتي السابقة" if not en else "Previous Orders", tickets=mini_html)

    # Fan Card
    notifs = db.user_notifs(u["id"])
    unread = db.user_notif_unread(u["id"])
    fav_clubs_list = db.user_favs(u["id"])
    fav_names = []
    for fc in fav_clubs_list:
        c = cfg.CLUBS.get(fc, {})
        if c:
            fav_names.append(c.get("emoji", "⚽") + " " + c.get(en and "en" or "ar", ""))
    fav_str = " · ".join(fav_names[:5]) if fav_names else "—"
    member_since = (u.get("created") or "")[:4] or "—"
    pass_code = "GX-%s-%s" % (str(u["id"]).zfill(4), str(abs(hash(u.get("phone",""))) % 9999).zfill(4))
    fan_card = (
        '<div class="mk-fan" style="{css}">'
        '<div class="mk-fan-strip">'
        '<div class="mk-fan-strip-title">GOLAZOX</div>'
        '<div class="mk-fan-strip-sub">FAN PASS</div>'
        '</div>'
        '<div class="mk-fan-body">'
        '<div class="mk-fan-brand">GOLAZOX STADIUM</div>'
        '<div class="mk-fan-sub">FAN TICKET</div>'
        '<div class="mk-fan-header">'
        '<div class="mk-fan-avatar">{initial}</div>'
        '<div><div class="mk-fan-name">{name}</div>'
        '<div class="mk-fan-id">{phone}</div></div>'
        '</div>'
        '<div class="mk-fan-grid">'
        '<div class="mk-fan-stat"><div class="mk-fan-stat-val">#{uid}</div><div class="mk-fan-stat-lbl">{fanid_lbl}</div></div>'
        '<div class="mk-fan-stat"><div class="mk-fan-stat-val">{since}</div><div class="mk-fan-stat-lbl">{since_lbl}</div></div>'
        '<div class="mk-fan-stat"><div class="mk-fan-stat-val">{orders}</div><div class="mk-fan-stat-lbl">{orders_lbl}</div></div>'
        '<div class="mk-fan-stat"><div class="mk-fan-stat-val">{spent}</div><div class="mk-fan-stat-lbl">{spent_lbl}</div></div>'
        '</div>'
        '</div>'
        '<div class="mk-fan-qr">'
        '<div class="mk-fan-qr-lbl">GOLAZOX FAN</div>'
        '<div class="mk-fan-qr-box"></div>'
        '<div class="mk-fan-qr-code">{pass_code}</div>'
        '</div>'
        '</div>'
    ).format(
        css=_mk_css(main_theme["ac"], main_theme["glow"]),
        initial=esc((u.get("name") or "P")[0].upper()),
        name=esc(u.get("name", "") or "Player"),
        phone=esc(u.get("phone", "") or ""),
        uid=u["id"],
        fanid_lbl="FAN ID" if en else "رقم العضوية",
        since=esc(member_since), since_lbl="MEMBER SINCE" if en else "عضو منذ",
        orders=len(orders), orders_lbl="ORDERS" if en else "الطلبات",
        spent=fmt_cur(spent), spent_lbl="TOTAL SPENT" if en else "إجمالي الصرف",
        pass_code=esc(pass_code)
    )

    # Tabs
    tabs = [
        ("mk-t-orders", "📦 " + d["acc_orders"]),
        ("mk-t-favs", "❤️ " + d["acc_favs"]),
        ("mk-t-sizes", "📏 " + d["acc_sizes"]),
        ("mk-t-data", "✏️ " + d["acc_data"]),
        ("mk-t-notifs", "🔔 " + d["acc_notifs"] + (('<span style="background:var(--mk-ac,#18E875);color:#050607;border-radius:999px;padding:1px 7px;font-size:.65rem;font-weight:900;margin-inline-start:4px">%d</span>' % unread) if unread else "")),
    ]
    tabs_html = "".join(
        '<button class="mk-tab{on}" data-tab="{sid}" onclick="mkTab(\'{sid}\')">{lbl}</button>'.format(
            on=" on" if i == 0 else "", sid=sid, lbl=lbl)
        for i, (sid, lbl) in enumerate(tabs)
    )

    # Notifications
    if notifs:
        n_html = "".join(
            '<div style="padding:10px 14px;border-radius:10px;background:rgba(255,255,255,.03);margin-bottom:6px;border:1px solid rgba(255,255,255,.04)">'
            '<p style="font-weight:700;font-size:.88rem;color:#fff">{txt}</p>'
            '<span style="font-size:.7rem;color:rgba(255,255,255,.35)">{dt}</span></div>'.format(
                txt=esc(x["text"]), dt=esc(x["created"]))
            for x in notifs)
    else:
        n_html = '<p style="text-align:center;color:rgba(255,255,255,.4);padding:20px">{msg}</p>'.format(msg=d["acc_notifs_empty"])

    # Saved sizes
    saved_sizes = db.user_sizes(u["id"])
    sz_prods = [p for p in cfg.PRODUCTS if p["id"] in saved_sizes and not p.get("hidden")]
    if sz_prods:
        sz_html = ""
        for p in sz_prods:
            sz_html += ('<div class="mk-szrow"><a href="/product/{id}">{e} {n}</a><span class="pill">{sw} {s}</span></div>').format(
                id=p["id"], e=p.get("emoji", "⚽"), n=esc(p.get("name_ar") if not en else p.get("name_en")),
                sw=d["size_w"], s=esc(saved_sizes[p["id"]]))
        sizes_html = sz_html
    else:
        sizes_html = '<p style="text-align:center;color:rgba(255,255,255,.4);padding:20px">{msg}</p>'.format(msg=d["acc_sizes_empty"])

    # Data form
    data_html = (
        '<div class="mk-data-fld"><label>{phone_lbl}</label><input value="{phone}" readonly></div>'
        '<div class="mk-data-fld"><label>{name_lbl}</label><input id="pd_name" value="{name}"></div>'
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">'
        '<div class="mk-data-fld"><label>{area_lbl}</label><input id="pd_area" value="{area}"></div>'
        '<div class="mk-data-fld"><label>{addr_lbl}</label><input id="pd_addr" value="{addr}"></div></div>'
        '<button class="mk-explore" style="width:100%;margin-top:8px" onclick="saveAccountData()">{sv}</button>'
    ).format(
        phone_lbl=d.get("acc_login_id", "Phone"), phone=esc(u.get("phone", "") or ""),
        name_lbl=d.get("co_name", "Name"), name=esc(u.get("name", "") or ""),
        area_lbl=d.get("co_area", "Area"), area=esc(u.get("area", "") or ""),
        addr_lbl=d.get("co_address", "Address"), addr=esc(u.get("address", "") or ""),
        sv=d.get("ok_saved", "Save")
    )

    # Main body
    body = (
        '<div class="wrap" style="max-width:800px;margin:0 auto;padding:0 16px">'
        '<div class="mk-hero" style="border-radius:0 0 24px 24px;margin:0 -16px 24px">'
        '<div class="mk-lights"></div><div class="mk-lights"></div><div class="mk-lights"></div>'
        '<div class="mk-lights"></div><div class="mk-lights"></div>'
        '<div class="mk-grass"></div>'
        '<div class="mk-subtitle">⚽ GOLAZOX</div>'
        '<div class="mk-title">{hero_title}</div>'
        '</div>'
        '{fan_card}'
        '<div class="mk-tabs">{tabs}</div>'
        '<div class="mk-sec on" id="mk-t-orders">'
        '<div class="mk-sec-inner">{main_ticket}{journey}{mini_section}</div>'
        '</div>'
        '<div class="mk-sec" id="mk-t-favs"><div class="mk-sec-inner"><div id="favsBox"></div></div></div>'
        '<div class="mk-sec" id="mk-t-sizes"><div class="mk-sec-inner">{sizes}</div></div>'
        '<div class="mk-sec" id="mk-t-data"><div class="mk-sec-inner">{data}</div></div>'
        '<div class="mk-sec" id="mk-t-notifs"><div class="mk-sec-inner">{notifs}</div></div>'
        '<div class="mk-logout"><button onclick="authOut()">{logout}</button></div>'
        '</div>'
        '<div class="mk-detail-overlay" id="mkDetailOverlay" onclick="mkDetailClose(event)">'
        '<button class="mk-detail-close" onclick="mkDetailClose()">✕</button>'
        '<div id="mkDetailBody"></div>'
        '</div>'
    ).format(
        hero_title="記憶你的MATCH IS READY ⚽" if False else (
            ("記憶你的" + d["acc_welcome"] + " ⚽") if False else
            (d["acc_welcome"] + " ⚽ — YOUR MATCH IS READY" if en else d["acc_welcome"] + " ⚽ — تذكرتك جاهزة للمباراة")
        ),
        fan_card=fan_card, tabs=tabs_html,
        main_ticket=main_ticket_html, journey=journey_html, mini_section=mini_section,
        sizes=sizes_html, data=data_html, notifs=n_html,
        logout=d.get("ac_logout", "Logout")
    )
    return base_page(body)


def enter_page():
    en = lang() == "en"
    d = cfg.L[lang()]
    return """<!DOCTYPE html>
<html lang="LANG" dir="DIR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GOLAZOX — Stadium Entry</title>
<meta name="theme-color" content="#050607">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚽</text></svg>">
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Poppins:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'FONT','Segoe UI',sans-serif;background:#050607;color:#fff;min-height:100vh;overflow:hidden}
.st{position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:30px 20px;overflow:hidden}
.st-bg{position:absolute;inset:0;background:radial-gradient(ellipse 120% 60% at 50% 100%,rgba(16,37,26,.6),transparent 60%),radial-gradient(ellipse 80% 40% at 50% 0%,rgba(16,37,26,.4),transparent 50%),linear-gradient(180deg,#050607 0%,#0A0D0C 40%,#0B1712 100%);z-index:0}
.grass{position:absolute;bottom:0;left:0;right:0;height:28%;background:repeating-linear-gradient(0deg,transparent 0 44px,rgba(255,255,255,.03) 44px 88px),linear-gradient(180deg,rgba(16,37,26,.5),rgba(11,23,18,.8));z-index:1}
.grass::before{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:160px;height:160px;border:2px solid rgba(255,255,255,.08);border-radius:50%;z-index:1}
.grass::after{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:2px;height:60px;background:rgba(255,255,255,.06);z-index:1}
.light{position:absolute;top:-40px;width:3px;height:100px;background:linear-gradient(180deg,rgba(255,255,255,.6),transparent);border-radius:0 0 2px 2px;z-index:2;animation:lPulse 4s ease-in-out infinite}
.light:nth-child(1){left:8%;animation-delay:0s}
.light:nth-child(2){left:25%;animation-delay:1.2s;height:80px}
.light:nth-child(3){right:25%;animation-delay:2.4s;height:70px}
.light:nth-child(4){right:8%;animation-delay:0.6s}
.light::after{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:80px;height:160px;background:radial-gradient(ellipse,rgba(255,255,255,.08),transparent 70%);pointer-events:none}
@keyframes lPulse{0%,100%{opacity:.2}50%{opacity:.55}}
.crowd{position:absolute;bottom:28%;left:0;right:0;height:80px;z-index:1;background:linear-gradient(180deg,transparent,rgba(5,6,7,.9));mask-image:repeating-linear-gradient(90deg,transparent 0 6px,black 6px 12px,transparent 12px 18px);-webkit-mask-image:repeating-linear-gradient(90deg,transparent 0 6px,black 6px 12px,transparent 12px 18px)}
.fog{position:absolute;bottom:20%;left:0;right:0;height:100px;z-index:2;background:linear-gradient(180deg,transparent,rgba(255,255,255,.015),transparent);pointer-events:none;animation:fogDrift 12s ease-in-out infinite}
@keyframes fogDrift{0%,100%{transform:translateX(0)}50%{transform:translateX(20px)}}
.vig{position:absolute;inset:0;z-index:3;pointer-events:none;background:radial-gradient(ellipse at center,transparent 40%,rgba(5,6,7,.7) 100%)}
.content{position:relative;z-index:10;display:flex;flex-direction:column;align-items:center}
.logo{font-size:2.8rem;font-weight:900;letter-spacing:6px;color:#F5F7F5;text-shadow:0 0 40px rgba(24,232,117,.15),0 0 80px rgba(24,232,117,.05);animation:logoIn 1s ease both}
.logo-sub{font-size:.65rem;font-weight:800;letter-spacing:8px;color:rgba(24,232,117,.5);margin-top:4px;animation:logoIn 1s ease .2s both}
@keyframes logoIn{from{opacity:0;transform:translateY(20px) scale(.95)}to{opacity:1;transform:none}}
.welcome{font-size:1.1rem;font-weight:700;color:rgba(255,255,255,.7);margin-top:20px;letter-spacing:1px;animation:fadeUp .8s ease .4s both}
.tagline{font-size:.82rem;color:rgba(255,255,255,.35);margin-top:8px;letter-spacing:2px;font-weight:600;animation:fadeUp .8s ease .5s both}
.lang-section{margin-top:32px;animation:fadeUp .8s ease .6s both}
.lang-label{font-size:.7rem;font-weight:800;letter-spacing:3px;color:rgba(255,255,255,.3);margin-bottom:14px;text-transform:uppercase}
.lang-btns{display:flex;gap:14px;flex-wrap:wrap;justify-content:center}
.lang-btn{display:flex;align-items:center;gap:12px;padding:16px 36px;border-radius:16px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);color:#F5F7F5;font-weight:800;font-size:1rem;text-decoration:none;min-width:220px;backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);transition:all .3s;cursor:pointer;position:relative;overflow:hidden}
.lang-btn::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(24,232,117,.05),transparent);opacity:0;transition:opacity .3s}
.lang-btn:hover{border-color:rgba(24,232,117,.3);box-shadow:0 0 30px rgba(24,232,117,.08);transform:translateY(-2px)}
.lang-btn:hover::before{opacity:1}
.lang-btn:active{transform:scale(.98)}
.landing-gate{display:flex;flex-direction:column;align-items:center}
.enter-site-btn{
  margin-top:28px;
  display:flex;
  align-items:center;
  gap:14px;
  min-width:280px;
  justify-content:center;
  padding:15px 20px;
  border-radius:18px;
  border:1px solid rgba(24,232,117,.35);
  background:linear-gradient(135deg,rgba(24,232,117,.14),rgba(255,255,255,.045));
  color:#F5F7F5;
  box-shadow:0 0 35px rgba(24,232,117,.10),inset 0 0 25px rgba(24,232,117,.04);
  cursor:pointer;
  font:inherit;
  transition:transform .25s ease,box-shadow .25s ease,border-color .25s ease,opacity .25s ease;
}
.enter-site-btn:hover{transform:translateY(-3px);border-color:rgba(24,232,117,.65);box-shadow:0 0 45px rgba(24,232,117,.20),inset 0 0 30px rgba(24,232,117,.07)}
.enter-site-btn:active{transform:scale(.98)}
.enter-ball{font-size:1.55rem;filter:drop-shadow(0 0 10px rgba(24,232,117,.35))}
.enter-copy{display:flex;flex-direction:column;align-items:flex-start;gap:2px}
.enter-copy b{font-size:.95rem;letter-spacing:1.5px}
.enter-copy small{font-size:.58rem;letter-spacing:1.5px;color:rgba(255,255,255,.42)}
.enter-arrow{font-size:1.25rem;color:#18E875}
.lang-section[hidden]{display:none!important}
.lang-section.lang-show{display:block;animation:fU .55s ease both}
.landing-gate.gate-hide{animation:gateOut .35s ease forwards;pointer-events:none}
@keyframes gateOut{to{opacity:0;transform:translateY(-12px) scale(.98)}}
@media(max-width:560px){
  .enter-site-btn{min-width:240px;width:min(88vw,320px);padding:14px 16px}
  .enter-copy b{font-size:.82rem}
  .enter-copy small{font-size:.52rem}
}
.lang-btn .flag{font-size:1.3rem}
.lang-btn .lname{display:flex;flex-direction:column;align-items:flex-start}
.lang-btn .lname span{font-size:.65rem;color:rgba(255,255,255,.4);font-weight:600;letter-spacing:2px}
.brand{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);color:rgba(111,143,122,.4);font-size:.7rem;font-weight:900;letter-spacing:4px;z-index:10}
.particles{position:absolute;inset:0;z-index:1;pointer-events:none;overflow:hidden}
.particle{position:absolute;width:2px;height:2px;background:rgba(255,255,255,.3);border-radius:50%;animation:pFloat linear infinite}
@keyframes pFloat{0%{transform:translateY(100vh) scale(0);opacity:0}10%{opacity:1}90%{opacity:1}100%{transform:translateY(-10vh) scale(1);opacity:0}}
@keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.light,.fog{animation:none!important}.logo,.logo-sub,.welcome,.tagline,.lang-section{animation:none!important;opacity:1;transform:none}}
@media (max-width:560px){.logo{font-size:2rem;letter-spacing:4px}.welcome{font-size:.95rem}.lang-btn{min-width:180px;padding:14px 24px;font-size:.9rem}}
</style></head>
<body>
<div class="st">
<div class="st-bg"></div><div class="grass"></div><div class="crowd"></div><div class="fog"></div>
<div class="light"></div><div class="light"></div><div class="light"></div><div class="light"></div>
<div class="vig"></div><div class="particles" id="particles"></div>
<div class="content">
<div class="logo">GOLAZOX</div>
<div class="logo-sub">FOOTBALL UNIVERSE</div>
<div id="landingGate" class="landing-gate">
<div class="welcome">__WELC__</div>
<div class="tagline">__TAG__</div>
<button id="enterSiteBtn" class="enter-site-btn" type="button">
<span class="enter-ball">⚽</span>
<span class="enter-copy"><b>ENTER GOLAZOX</b><small>ENTER THE FOOTBALL UNIVERSE</small></span>
<span class="enter-arrow">→</span>
</button>
</div>
<div id="languagePanel" class="lang-section" hidden>
<div class="lang-label">CHOOSE YOUR LANGUAGE</div>
<div class="lang-btns">
<a href="/enter/ar" class="lang-btn"><span class="flag">🇸🇦</span><span class="lname">العربية<span>ARABIC</span></span></a>
<a href="/enter/en" class="lang-btn"><span class="flag">🇬🇧</span><span class="lname">English<span>UNITED KINGDOM</span></span></a>
</div>
</div>
</div>
<div class="brand">GOLAZOX</div>
</div>
<script>
(function(){
  var c=document.getElementById('particles');
  if(c){
    for(var i=0;i<12;i++){
      var p=document.createElement('div');
      p.className='particle';
      p.style.left=Math.random()*100+'%';
      p.style.animationDuration=(8+Math.random()*12)+'s';
      p.style.animationDelay=Math.random()*8+'s';
      p.style.width=p.style.height=(1+Math.random()*2)+'px';
      c.appendChild(p);
    }
  }

  var btn=document.getElementById('enterSiteBtn');
  var gate=document.getElementById('landingGate');
  var panel=document.getElementById('languagePanel');

  if(btn && gate && panel){
    btn.addEventListener('click',function(){
      btn.disabled=true;
      gate.classList.add('gate-hide');
      setTimeout(function(){
        gate.style.display='none';
        panel.hidden=false;
        panel.classList.add('lang-show');
      },330);
    });
  }
})();
</script>
</body></html>""".replace("LANG", "en" if en else "ar") \
        .replace("DIR", "ltr" if en else "rtl") \
        .replace("FONT", "Poppins" if en else "Cairo") \
        .replace("__WELC__", d["ent_welc"]).replace("__TAG__", d["ent_tag"])


PEN_ZONES = {"tl": (-110, 92), "tc": (0, 92), "tr": (110, 92), "bl": (-110, 172), "br": (110, 172)}


def penalty_page(code):
    en = lang() == "en"
    d = cfg.L[lang()]
    practice = not code
    if not practice:
        o = db.order_get(code)
        if not o:
            return base_page('<div class="wrap"><h2>404</h2></div>')
    zones = "".join(
        ("<button class='pen-zone' data-z='{z}' style='left:calc(50% {dx});top:{dy}px' onclick='penShoot(this)'>{lb}</button>"
         ).format(z=z, dx=("+ 110px" if x > 0 else ("- 110px" if x < 0 else "")), dy=y, lb=d["pen_" + z])
        for z, (x, y) in PEN_ZONES.items())
    head_title = ("🎯 " + ("PENALTY CHALLENGE" if en else "تحدي البنالتي")) if practice else ("⚽ PENALTY — " + code)
    head_link = "" if practice else '<a class="hbtn" href="/ticket?code={code}">{tk}</a>'.format(code=esc(code), tk=d["ok_ticket"])
    note = (d.get("pen_practice_note", "العب بلا حدود — تدرب على تسديداتك.") if not en
            else d.get("pen_practice_note_en", "Free practice — sharpen your aim, no limit.")) if practice else d["pen_once"]
    body = (
        '<div class="wrap pen-std">'
        '<div class="pen-head"><span class="pen-code">{title}</span>'
        '{link}</div>'
        '<div class="pen-pitch">'
        '<div class="pen-stripes"></div><div class="pen-crowd"></div>'
        '<div class="pen-lights"></div><div class="pen-lights right"></div>'
        '<div class="pen-goal"></div>{zones}'
        '<div class="pen-keeper" id="penKeeper"><div class="kd l"></div><div class="kd r"></div><div class="kh"></div><div class="kb"></div></div>'
        '<div class="pen-ball" id="penBall">⚽</div>'
        '<div class="pen-result" id="penRes"></div>'
        '</div>'
        '<p class="pen-note">{once}</p></div>'
    ).format(title=esc(head_title), link=head_link, zones=zones, once=esc(note))
    page_js = """<script>
var PEN_CODE=__PEN_CODE_JSON__;
var PEN_PRACTICE=__PEN_PRACTICE_JS__;
var ZP={tl:['calc(50% - 110px)','92px'],tc:['50%','92px'],tr:['calc(50% + 110px)','92px'],bl:['calc(50% - 110px)','172px'],br:['calc(50% + 110px)','172px']};
var PEN_DONE=PEN_PRACTICE?false:(localStorage.getItem('pen_'+PEN_CODE)=='1');
function penShow(goal,once){
  var t=goal?gxT('pen_goal'):gxT('pen_saved');
  var sub=goal?('+10 '+gxT('pen_pts')):(once?gxT('pen_once'):gxT('pen_saved_t'));
  var res=$('penRes');
  var actions = PEN_PRACTICE
    ? '<button class="btn pri" onclick="penAgain()">'+gxT('pen_go')+'</button><a class="btn ghost" href="/home">'+gxT('pen_back')+'</a>'
    : '<a class="btn" style="background:#25D366;color:#fff" href="/track?code='+PEN_CODE+'">'+gxT('pen_track')+'</a><a class="btn ghost" href="/home">'+gxT('pen_back')+'</a>';
  res.innerHTML='<span class="big">'+t+'</span><span class="pts">'+(PEN_PRACTICE?'':sub)+'</span>'
    +'<div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:6px">'+actions+'</div>';
  res.classList.add('show');
  if(goal&&!once) confetti(50);
}
function penAgain(){
  PEN_DONE=false; $('penRes').classList.remove('show'); $('penRes').innerHTML='';
  $('penBall').style.left='50%'; $('penBall').style.top='352px';
  $('penKeeper').style.left='50%'; $('penKeeper').style.top='168px';
}
function penShoot(btn){
  if(PEN_DONE) return;
  var z=btn.getAttribute('data-z');
  if(PEN_PRACTICE){
    PEN_DONE=true;
    var zones=['tl','tc','tr','bl','br'];
    var keeper=zones[Math.floor(Math.random()*zones.length)];
    var goal = z!==keeper || Math.random()<0.22;
    var ball=$('penBall'), keep=$('penKeeper');
    ball.style.left=ZP[z][0]; ball.style.top=ZP[z][1];
    keep.style.left=ZP[keeper][0]; keep.style.top=ZP[keeper][1];
    setTimeout(function(){ penShow(goal,false); }, 480);
    return;
  }
  fetch('/api/penalty/play',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:PEN_CODE,shot:z,device:gxDev()})})
  .then(function(r){return r.json();}).then(function(dd){
    if(dd.error==='notfound'){ toast('404'); return; }
    PEN_DONE=true; localStorage.setItem('pen_'+PEN_CODE,'1');
    var ball=$('penBall'), keep=$('penKeeper');
    if(dd.fresh){
      ball.style.left=ZP[z][0]; ball.style.top=ZP[z][1];
      if(dd.keeper&&ZP[dd.keeper]){ keep.style.left=ZP[dd.keeper][0]; keep.style.top=ZP[dd.keeper][1]; }
      penShow(dd.goal,false);
    } else { penShow(dd.goal,true); }
  });
}
document.addEventListener('DOMContentLoaded',function(){
  if(PEN_DONE && !PEN_PRACTICE){
    fetch('/api/penalty/status?code='+PEN_CODE).then(function(r){return r.json();}).then(function(dd){
      if(dd.done) penShow(dd.goal,true);
    });
  }
});
</script>""".replace("__PEN_CODE_JSON__", json.dumps(code)).replace("__PEN_PRACTICE_JS__", "true" if practice else "false")
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
<title>GOLAZOX — Football Universe</title>
<meta name="theme-color" content="#050607">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚽</text></svg>">
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Poppins:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'FONT','Segoe UI',sans-serif;background:#050607;color:#fff;min-height:100vh;overflow:hidden}
.st{position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:30px 20px;overflow:hidden}
.st-bg{position:absolute;inset:0;background:radial-gradient(ellipse 120% 60% at 50% 100%,rgba(16,37,26,.6),transparent 60%),radial-gradient(ellipse 80% 40% at 50% 0%,rgba(16,37,26,.4),transparent 50%),linear-gradient(180deg,#050607 0%,#0A0D0C 40%,#0B1712 100%);z-index:0}
.grass{position:absolute;bottom:0;left:0;right:0;height:28%;background:repeating-linear-gradient(0deg,transparent 0 44px,rgba(255,255,255,.03) 44px 88px),linear-gradient(180deg,rgba(16,37,26,.5),rgba(11,23,18,.8));z-index:1}
.grass::before{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:160px;height:160px;border:2px solid rgba(255,255,255,.08);border-radius:50%;z-index:1}
.grass::after{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:2px;height:60px;background:rgba(255,255,255,.06);z-index:1}
.light{position:absolute;top:-40px;width:3px;height:100px;background:linear-gradient(180deg,rgba(255,255,255,.6),transparent);border-radius:0 0 2px 2px;z-index:2;animation:lP 4s ease-in-out infinite}
.light:nth-child(1){left:8%}.light:nth-child(2){left:25%;animation-delay:1.2s;height:80px}
.light:nth-child(3){right:25%;animation-delay:2.4s;height:70px}.light:nth-child(4){right:8%;animation-delay:.6s}
.light::after{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:80px;height:160px;background:radial-gradient(ellipse,rgba(255,255,255,.08),transparent 70%);pointer-events:none}
@keyframes lP{0%,100%{opacity:.2}50%{opacity:.55}}
.crowd{position:absolute;bottom:28%;left:0;right:0;height:80px;z-index:1;background:linear-gradient(180deg,transparent,rgba(5,6,7,.9));mask-image:repeating-linear-gradient(90deg,transparent 0 6px,black 6px 12px,transparent 12px 18px);-webkit-mask-image:repeating-linear-gradient(90deg,transparent 0 6px,black 6px 12px,transparent 12px 18px)}
.fog{position:absolute;bottom:20%;left:0;right:0;height:100px;z-index:2;background:linear-gradient(180deg,transparent,rgba(255,255,255,.015),transparent);pointer-events:none;animation:fD 12s ease-in-out infinite}
@keyframes fD{0%,100%{transform:translateX(0)}50%{transform:translateX(20px)}}
.vig{position:absolute;inset:0;z-index:3;pointer-events:none;background:radial-gradient(ellipse at center,transparent 40%,rgba(5,6,7,.7) 100%)}
.content{position:relative;z-index:10;display:flex;flex-direction:column;align-items:center}
.logo{font-size:2.8rem;font-weight:900;letter-spacing:6px;color:#F5F7F5;text-shadow:0 0 40px rgba(24,232,117,.15),0 0 80px rgba(24,232,117,.05);animation:lI 1s ease both}
.logo-sub{font-size:.65rem;font-weight:800;letter-spacing:8px;color:rgba(24,232,117,.5);margin-top:4px;animation:lI 1s ease .2s both}
@keyframes lI{from{opacity:0;transform:translateY(20px) scale(.95)}to{opacity:1;transform:none}}
.welcome{font-size:1.1rem;font-weight:700;color:rgba(255,255,255,.7);margin-top:20px;letter-spacing:1px;animation:fU .8s ease .4s both}
.tagline{font-size:.82rem;color:rgba(255,255,255,.35);margin-top:8px;letter-spacing:2px;font-weight:600;animation:fU .8s ease .5s both}
.lang-section{margin-top:32px;animation:fU .8s ease .6s both}
.lang-label{font-size:.7rem;font-weight:800;letter-spacing:3px;color:rgba(255,255,255,.3);margin-bottom:14px;text-transform:uppercase}
.lang-btns{display:flex;gap:14px;flex-wrap:wrap;justify-content:center}
.lang-btn{display:flex;align-items:center;gap:12px;padding:16px 36px;border-radius:16px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);color:#F5F7F5;font-weight:800;font-size:1rem;text-decoration:none;min-width:220px;backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);transition:all .3s;cursor:pointer;position:relative;overflow:hidden}
.lang-btn::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(24,232,117,.05),transparent);opacity:0;transition:opacity .3s}
.lang-btn:hover{border-color:rgba(24,232,117,.3);box-shadow:0 0 30px rgba(24,232,117,.08);transform:translateY(-2px)}
.lang-btn:hover::before{opacity:1}
.lang-btn:active{transform:scale(.98)}
.lang-btn .flag{font-size:1.3rem}
.lang-btn .lname{display:flex;flex-direction:column;align-items:flex-start}
.lang-btn .lname span{font-size:.65rem;color:rgba(255,255,255,.4);font-weight:600;letter-spacing:2px}
.brand{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);color:rgba(111,143,122,.4);font-size:.7rem;font-weight:900;letter-spacing:4px;z-index:10}
.particles{position:absolute;inset:0;z-index:1;pointer-events:none;overflow:hidden}
.particle{position:absolute;width:2px;height:2px;background:rgba(255,255,255,.3);border-radius:50%;animation:pF linear infinite}
@keyframes pF{0%{transform:translateY(100vh) scale(0);opacity:0}10%{opacity:1}90%{opacity:1}100%{transform:translateY(-10vh) scale(1);opacity:0}}
@keyframes fU{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.light,.fog{animation:none!important}.logo,.logo-sub,.welcome,.tagline,.lang-section{animation:none!important;opacity:1;transform:none}}
@media (max-width:560px){.logo{font-size:2rem;letter-spacing:4px}.welcome{font-size:.95rem}.lang-btn{min-width:180px;padding:14px 24px;font-size:.9rem}}
</style></head>
<body>
<div class="st">
<div class="st-bg"></div><div class="grass"></div><div class="crowd"></div><div class="fog"></div>
<div class="light"></div><div class="light"></div><div class="light"></div><div class="light"></div>
<div class="vig"></div><div class="particles" id="particles"></div>
<div class="content">
<div class="logo">GOLAZOX</div>
<div class="logo-sub">FOOTBALL UNIVERSE</div>
<div class="welcome">__WT__</div>
<div class="tagline">__WS__</div>
<div class="lang-section">
<div class="lang-label">CHOOSE YOUR LANGUAGE</div>
<div class="lang-btns">
<a href="/enter/ar" class="lang-btn"><span class="flag">🇸🇦</span><span class="lname">العربية<span>ARABIC</span></span></a>
<a href="/enter/en" class="lang-btn"><span class="flag">🇬🇧</span><span class="lname">English<span>ENGLISH</span></span></a>
</div></div></div>
<div class="brand">GOLAZOX</div>
</div>
<script>
(function(){var c=document.getElementById('particles');if(!c)return;
for(var i=0;i<12;i++){var p=document.createElement('div');p.className='particle';p.style.left=Math.random()*100+'%';p.style.animationDuration=(8+Math.random()*12)+'s';p.style.animationDelay=Math.random()*8+'s';p.style.width=p.style.height=(1+Math.random()*2)+'px';c.appendChild(p)}})();
</script>
</body></html>""".replace("LANG", "en" if en else "ar") \
        .replace("DIR", "ltr" if en else "rtl") \
        .replace("FONT", "Poppins" if en else "Cairo") \
        .replace("__WT__", d["welcome_t"]).replace("__WS__", d["welcome_s"])


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
        return ('<div class="mtk-item"><span class="mtk-item-ic">{e}</span>'
                '<div class="mtk-item-info"><b>{n}</b><span>{s}{q} × {pr} {c}</span></div></div>').format(
            e=it.get("emoji", "⚽"), n=esc(it.get("name", "")),
            s=(d["size_w"] + esc(it["size"]) + " · ") if it.get("size") and it.get("kind") != "mug" else "",
            q=it.get("qty", 1), pr=fmt_cur(it.get("price", 0)), c=cur())
    items_html = "".join(item_html(i) for i in items)
    qr = "https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=" + url_for("track", code=code, _external=True)
    wa_msg = d["tk_msg"].format(code=code)
    idx = ORDER_FLOW.index(status) if status in ORDER_FLOW else -1

    # Status emoji mapping
    status_emoji = {"received": "⚽", "preparing": "🧵", "ready": "📦", "out_for_delivery": "🚚", "delivered": "🏆", "cancelled": "❌"}
    st_emoji = status_emoji.get(status, "⚽")

    # Match Journey timeline
    tj = ""
    if status != "cancelled":
        tj_steps = [("tstage_ok", "⚽"), ("tstage_pay", "💳"), ("tstage_prep", "🧵"),
                    ("tstage_way", "🚚"), ("tstage_done", "🏆")]
        tj_inner = "".join(
            '<div class="mtk-jstep {cls}"><div class="mtk-jdot">{ic}</div><b>{lbl}</b></div>'.format(
                cls="done" if i <= idx else ("cur" if i == idx else ""), ic=ic, lbl=d[k])
            for i, (k, ic) in enumerate(tj_steps))
        pct = int(idx / 4 * 100) if idx >= 0 else 0
        # Ball position on the timeline
        ball_left = min(100, max(0, pct))
        tj = ('<div class="mtk-journey">'
              '<div class="mtk-jtitle">⚽ ORDER JOURNEY</div>'
              '<div class="mtk-jtrack"><div class="mtk-jfill" style="width:{pct}%"></div>'
              '<div class="mtk-jball" style="left:{ball}%">⚽</div></div>'
              '<div class="mtk-jsteps">{inner}</div></div>').format(
            inner=tj_inner, pct=pct, ball=ball_left)

    # Delivered celebration
    goal_celebration = ""
    if status == "delivered":
        goal_celebration = '<div class="mtk-goal" id="mtkGoal">🏆 GOOOOAL! ⚽<br><span>طلبك وصل بنجاح!</span></div>'

    body = (
        '<div class="mtk-page">'
        # Stadium lights effect
        '<div class="mtk-lights"><div class="mtk-light"></div><div class="mtk-light"></div></div>'
        '<div class="wrap mtk-wrap">'
        '<div class="mtk-ticket" id="mtkTicket">'
        # Ticket top branding
        '<div class="mtk-header">'
        '<div class="mtk-brand">⚽ GOLAZOX</div>'
        '<div class="mtk-matchday">MATCHDAY TICKET</div></div>'
        # Perforation line
        '<div class="mtk-perf"></div>'
        # Ticket code
        '<div class="mtk-code-section">'
        '<div class="mtk-code">{code}</div>'
        '<div class="mtk-code-label">MATCH ID</div></div>'
        # Perforation line
        '<div class="mtk-perf"></div>'
        # Order items
        '<div class="mtk-items-section">'
        '<div class="mtk-section-title">YOUR ORDER</div>'
        '{items}</div>'
        # Status
        '<div class="mtk-status-section">'
        '<div class="mtk-status-label">STATUS</div>'
        '<div class="mtk-status-pill">{st_emoji} {sl}</div></div>'
        # Journey
        '{journey}'
        # Goal celebration
        '{goal}'
        # QR Code
        '<div class="mtk-qr">'
        '<img src="{qr}" alt="QR" width="120">'
        '<div class="mtk-qr-label">.Scan to track</div></div>'
        # Perforation line
        '<div class="mtk-perf"></div>'
        # Footer
        '<div class="mtk-footer">'
        '<div class="mtk-footer-brand">GOLAZOX STADIUM</div>'
        '<div class="mtk-footer-date">{dt} · {tm}</div></div>'
        '</div>'
        # Buttons
        '<div class="mtk-btns">'
        '<button class="btn ghost" onclick="shareTk()">{sh}</button>'
        '<button class="btn ghost" onclick="window.print()">{sv}</button>'
        '<button class="btn ghost" onclick="location.href=\'/track?code={code}\'">{tr}</button>'
        '<a class="btn wa2" target="_blank" rel="noopener" href="https://wa.me/{wa}?text={wm}">{cw}</a></div>'
        '<div style="text-align:center;margin-top:18px"><a class="back" href="/home">← {b}</a></div>'
        '</div></div>'
    ).format(code=code, items=items_html, st_emoji=st_emoji, sl=status_label,
             journey=tj, goal=goal_celebration, qr=qr,
             dt=data.get("date", ""), tm=data.get("time", ""),
             sh=d["tk_share"], sv=d["tk_save"], tr=d["tk_track"],
             tg=cfg.WHATSAPP, wm=esc(wa_msg), cw=d["tk_wa"], b=d["back"])

    page_js = """<script>
function shareTk(){ var url=location.href;
  if(navigator.share){ navigator.share({title:'GOLAZOX Match Ticket',url:url}); } else { navigator.clipboard.writeText(url); toast(url); } }
document.addEventListener('DOMContentLoaded',function(){
  var ticket=document.getElementById('mtkTicket');
  if(ticket){ ticket.classList.add('mtk-reveal'); }
  var goal=document.getElementById('mtkGoal');
  if(goal){ setTimeout(function(){ goal.classList.add('show'); confetti(20); },600); setTimeout(function(){ goal.classList.remove('show'); },3000); }
});
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
    # Always show the entrance screen first.
    return welcome_page()


@app.route("/home")
def home():
    if request.cookies.get("gx_entry_completed") != "1" or not has_lang():
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
    r = Response(jersey_tunnel_page(l), content_type="text/html")
    r.set_cookie("lang", l, max_age=31536000)
    return r



def jersey_tunnel_page(selected_lang):
    en = selected_lang == "en"
    products = [p for p in cfg.PRODUCTS if p.get("kind") == "jersey" and not p.get("hidden")][:6]
    cards = []
    for p in products:
        name = p.get("name_en" if en else "name_ar", p.get("id", "Jersey"))
        img = (p.get("imgs") or [""])[0]
        cards.append(
            '<div class="jt-jersey"><div class="jt-card"><img src="/img/__IMG__" alt=""><span>__NAME__</span></div></div>'
            .replace("__IMG__", esc(img))
            .replace("__NAME__", esc(name))
        )
    cards_html = "".join(cards)

    lang_code = "en" if en else "ar"
    direction = "ltr" if en else "rtl"
    font = "Poppins" if en else "Cairo"
    sub = "YOUR TEAM. YOUR JERSEY. YOUR GAME." if en else "فريقك. قميصك. لعبتك."
    copy = (
        "Walk through the tunnel and enter the GOLAXOX matchday experience."
        if en else "اعبر النفق وادخل تجربة GOLAXOX في أجواء المباراة."
    )
    enter = "ENTER THE STADIUM" if en else "ادخل الملعب"

    html = """<!doctype html>
<html lang="__LANG__" dir="__DIR__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>GOLAXOX — Jersey Tunnel</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@500;700;800;900&family=Poppins:wght@600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden}
body{font-family:'__FONT__','Segoe UI',sans-serif;background:#030605;color:#fff}
.jt{position:fixed;inset:0;overflow:hidden;background:
radial-gradient(circle at 50% 18%,rgba(24,232,117,.22),transparent 30%),
linear-gradient(180deg,#020403 0%,#07140d 52%,#020403 100%)}
.jt-floor{position:absolute;left:50%;bottom:-18%;width:130%;height:70%;
transform:translateX(-50%) perspective(650px) rotateX(65deg);
background:
linear-gradient(90deg,transparent 49.7%,rgba(255,255,255,.16) 49.9%,rgba(255,255,255,.16) 50.1%,transparent 50.3%),
repeating-linear-gradient(90deg,rgba(255,255,255,.02) 0 40px,transparent 40px 80px),
linear-gradient(180deg,#0c2a1b,#06120c 70%,#020403)}
.jt-floor:after{content:"";position:absolute;left:50%;top:8%;width:180px;height:180px;
transform:translateX(-50%);border:2px solid rgba(255,255,255,.1);border-radius:50%}
.jt-light{position:absolute;top:-10%;width:190px;height:420px;
background:radial-gradient(ellipse at 50% 10%,rgba(255,255,255,.34),rgba(24,232,117,.1) 38%,transparent 72%);
filter:blur(12px);animation:jtPulse 3s ease-in-out infinite}
.jt-light.a{left:5%}.jt-light.b{right:5%;animation-delay:1s}
.jt-fog{position:absolute;left:-15%;right:-15%;bottom:10%;height:24%;
background:linear-gradient(180deg,transparent,rgba(255,255,255,.05),transparent);
filter:blur(20px);animation:jtFog 8s ease-in-out infinite alternate}
.jt-crowd{position:absolute;left:0;right:0;bottom:28%;height:13%;opacity:.7;
background:
radial-gradient(circle at 10% 50%,rgba(255,255,255,.18) 0 2px,transparent 3px),
radial-gradient(circle at 35% 40%,rgba(24,232,117,.2) 0 2px,transparent 3px),
radial-gradient(circle at 65% 55%,rgba(255,255,255,.15) 0 2px,transparent 3px),
radial-gradient(circle at 90% 42%,rgba(24,232,117,.2) 0 2px,transparent 3px);
background-size:48px 48px,55px 55px,50px 50px,63px 63px;
animation:jtCrowd 5s linear infinite}
.jt-meta{position:absolute;top:18px;left:20px;right:20px;display:flex;justify-content:space-between;
font-size:.6rem;letter-spacing:2px;color:rgba(255,255,255,.42);z-index:5}
.jt-live{color:#18e875}
.jt-side{position:absolute;top:14%;bottom:13%;width:18%;display:flex;flex-direction:column;justify-content:space-between;z-index:3}
.jt-left{left:2%}.jt-right{right:2%}
.jt-jersey{width:min(150px,14vw);filter:drop-shadow(0 14px 30px rgba(0,0,0,.6));animation:jtFloat 4s ease-in-out infinite}
.jt-jersey:nth-child(2){animation-delay:.5s}.jt-jersey:nth-child(3){animation-delay:1s}
.jt-card{padding:7px;border-radius:16px;background:rgba(0,0,0,.28);border:1px solid rgba(24,232,117,.16);
backdrop-filter:blur(7px)}
.jt-card img{display:block;width:100%;aspect-ratio:3/4;object-fit:contain}
.jt-card span{display:block;margin-top:4px;font-size:.55rem;color:rgba(255,255,255,.65)}
.jt-center{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
text-align:center;z-index:4;padding:20px}
.jt-kicker{font-size:.62rem;letter-spacing:4px;color:#18e875;font-weight:900}
.jt-title{font-size:clamp(2.5rem,6vw,5.4rem);font-weight:900;letter-spacing:.08em;text-shadow:0 0 45px rgba(24,232,117,.22)}
.jt-sub{margin-top:8px;font-size:.9rem;letter-spacing:2px;color:rgba(255,255,255,.62)}
.jt-copy{margin-top:12px;max-width:520px;font-size:.78rem;line-height:1.7;color:rgba(255,255,255,.45)}
.jt-ball{font-size:2.6rem;margin:18px 0 10px;filter:drop-shadow(0 0 18px rgba(255,255,255,.22));animation:jtBall 2.2s ease-in-out infinite}
.jt-enter{border:1px solid rgba(24,232,117,.48);background:linear-gradient(135deg,#18e875,#0bb95b);
color:#031009;border-radius:16px;padding:14px 25px;min-width:250px;font-weight:900;cursor:pointer;
box-shadow:0 0 34px rgba(24,232,117,.25);transition:.25s transform,.25s box-shadow}
.jt-enter:hover{transform:translateY(-3px);box-shadow:0 0 50px rgba(24,232,117,.35)}.jt-sound{position:absolute;left:18px;bottom:18px;z-index:8;border:1px solid rgba(24,232,117,.25);background:rgba(0,0,0,.48);color:#fff;border-radius:999px;padding:9px 12px;font-weight:800;backdrop-filter:blur(10px);cursor:pointer}.jt-sound.on{border-color:rgba(24,232,117,.6);box-shadow:0 0 18px rgba(24,232,117,.18)}
@keyframes jtPulse{0%,100%{opacity:.45}50%{opacity:1}}
@keyframes jtFog{from{transform:translateX(-3%)}to{transform:translateX(3%)}}
@keyframes jtCrowd{from{transform:translateX(0)}to{transform:translateX(48px)}}
@keyframes jtFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
@keyframes jtBall{0%,100%{transform:translateY(0) rotate(0)}50%{transform:translateY(-7px) rotate(10deg)}}
@media(max-width:760px){
  .jt-side{display:none}.jt-title{font-size:2.35rem}.jt-sub{font-size:.72rem}.jt-copy{font-size:.7rem;max-width:315px}
  .jt-enter{width:88vw;min-height:54px}
}
@media(prefers-reduced-motion:reduce){
  .jt-light,.jt-fog,.jt-crowd,.jt-jersey,.jt-ball{animation:none}
}
</style></head>
<body>
<div class="jt">
  <div class="jt-floor"></div><div class="jt-light a"></div><div class="jt-light b"></div>
  <div class="jt-fog"></div><div class="jt-crowd"></div>
  <div class="jt-meta"><span>GOLAXOX • MATCHDAY</span><span class="jt-live">● STADIUM LIVE</span></div>
  <div class="jt-side jt-left">__CARDS__</div><div class="jt-side jt-right">__CARDS__</div>
  <section class="jt-center">
    <div class="jt-kicker">JERSEY TUNNEL</div>
    <div class="jt-title">GOLAXOX</div>
    <div class="jt-sub">__SUB__</div>
    <div class="jt-copy">__COPY__</div>
    <div class="jt-ball">⚽</div>
    <button class="jt-enter" onclick="enterStadium()">⚽ __ENTER__</button>
  </section>
</div>
<script>
function enterStadium(){
  var root=document.querySelector('.jt');
  if(root){root.style.transition='opacity .65s ease,transform .65s ease';root.style.opacity='0';root.style.transform='scale(1.03)';}
  setTimeout(function(){
    document.cookie='gx_entry_completed=1; Max-Age=31536000; Path=/; SameSite=Lax';
    location.href='/home';
  },650);
}
</script>


</body></html>"""

    html = html.replace("__LANG__", lang_code)
    html = html.replace("__DIR__", direction)
    html = html.replace("__FONT__", font)
    html = html.replace("__CARDS__", cards_html)
    html = html.replace("__SUB__", sub)
    html = html.replace("__COPY__", copy)
    html = html.replace("__ENTER__", enter)

    # The HTML template was originally escaped for %-formatting; undo that
    # escaping now that we no longer use %-formatting.
    html = html.replace("%", "%")
    return html

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


@app.route("/admin/notifs")
def admin_notifs_page():
    if not admin_auth():
        if current_user():
            return blocked_page()
        return redirect("/admin/login")
    an = db.admin_notifs(200)
    rows = ""
    for x in an:
        rows += ('<tr class="{un}"><td>{txt}</td><td style="white-space:nowrap">{dt}</td></tr>').format(
            un="un" if not x["read"] else "", txt=esc(x["text"]), dt=esc(x["created"]))
    db.admin_notif_read_all()
    body = ('<div class="adm">'
            '<div class="hd-in" style="justify-content:space-between;padding:14px 0"><b style="font-size:1.2rem">🔔 مركز الإشعارات</b>'
            '<a href="/admin" class="hbtn">← لوحة التحكم</a></div>'
            '<div class="adm-card"><table class="anbox" style="max-height:none;border:0"><tr><th>الإشعار</th><th>التاريخ</th></tr>{rows}</table></div>'
            '</div>').format(rows=rows if rows else '<tr><td colspan="2"><p class="mnote">لا توجد إشعارات</p></td></tr>')
    return admin_template(body)


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
    items = []
    for it in data.get("items", []):
        p = next((x for x in cfg.PRODUCTS if x["id"] == it.get("id")), None)
        if not p:
            continue
        qty = max(1, int(it.get("qty", 1)))
        items.append({
            "id": p["id"], "size": it.get("size", "OS"), "qty": qty,
            "name": it.get("name", p.get("name_ar", p["id"])),
            "price": eff_price(p), "emoji": p.get("emoji", "⚽"), "kind": p["kind"]})
    data["items"] = items
    sub = sum(i["price"] * i["qty"] for i in items)
    deliv = cfg.DELIVERY_FEE if items else 0
    disc = min(max(0, float(data.get("discount", 0))), sub)
    data["delivery"] = deliv
    data["total"] = max(0, sub + deliv - disc)
    u = current_user()
    if u:
        data["user_id"] = u["id"]
    code = db.order_create(data)
    try:
        nm = data.get("name", "")
        db.admin_notif_add("order", "🛒 طلب جديد %s — %s" % (code, nm))
    except Exception:
        pass
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


# ---------- virtual try-on (real AI adapter, privacy-safe) ----------
import tempfile
import base64 as _b64


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
    tpl = (os.environ.get("OTP_EMAIL_SUBJECT", "") or "").strip()
    return tpl or "رمز التحقق لتسجيل الدخول إلى GOLAZOX"


def otp_email_text(code):
    tpl = (os.environ.get("OTP_EMAIL_TEXT", "") or "").strip()
    if not tpl:
        tpl = ("مرحبًا،\n\nرمز التحقق الخاص بك هو:\n\n{code}\n\n"
               "الرمز صالح لمدة 10 دقائق.\n"
               "إذا لم تطلب تسجيل الدخول، يمكنك تجاهل هذه الرسالة.\n\nGOLAZOX")
    return tpl.replace("{code}", code)


def otp_email_html(code):
    return ("<div style='font-family:Arial,Helvetica,sans-serif;background:#f4f4f4;padding:24px'>"
            "<div style='max-width:480px;margin:auto;background:#ffffff;border-radius:14px;padding:28px;text-align:center'>"
            "<div style='font-size:24px;font-weight:900;color:#0B1712'>GOLAZOX</div>"
            "<p style='color:#555;margin:18px 0 22px'>رمز التحقق لتسجيل الدخول</p>"
            "<div style='font-size:36px;letter-spacing:10px;font-weight:900;color:#0B9F50'>%s</div>"
            "<p style='color:#888;font-size:13px;margin-top:22px'>الرمز صالح لمدة 10 دقائق.<br>"
            "إذا لم تطلب تسجيل الدخول، يمكنك تجاهل هذه الرسالة.</p></div></div>" % code)


def _log_resend_error(code, raw):
    body = (raw or "").strip()
    sms_log("[EMAIL OTP] Resend HTTP status: %s" % code)
    if len(body) > 800:
        body = body[:800] + "..."
    sms_log("[EMAIL OTP] Resend response body: %s" % body)
    try:
        import json as _json
        j = _json.loads(body)
        if isinstance(j, dict):
            if "statusCode" in j:
                sms_log("[EMAIL OTP] Resend error code: %s" % j.get("statusCode"))
            if "name" in j:
                sms_log("[EMAIL OTP] Resend error name: %s" % j.get("name"))
            if "message" in j:
                sms_log("[EMAIL OTP] Resend error message: %s" % j.get("message"))
            if "code" in j:
                sms_log("[EMAIL OTP] Resend error code: %s" % j.get("code"))
            if "errors" in j:
                sms_log("[EMAIL OTP] Resend error details: %s" % j.get("errors"))
    except Exception:
        sms_log("[EMAIL OTP] Resend response is not JSON (see body above)")


def send_email(to, subject, text, html=None):
    key = (os.environ.get("RESEND_API_KEY", "") or "").strip()
    frm = (os.environ.get("RESEND_FROM", "") or "onboarding@resend.dev").strip()
    sms_log("[EMAIL OTP] send requested to %s" % to)
    sms_log("[EMAIL OTP] config resend_key=%s from=%s" % (bool(key), bool(frm)))
    if not (key and frm):
        sms_log("[EMAIL OTP] Resend ERROR: config missing (RESEND_API_KEY/RESEND_FROM)")
        return (False, "notcfg")
    try:
        import json as _json
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        payload = {"from": frm, "to": [to], "subject": subject, "text": text}
        if html:
            payload["html"] = html
        data = _json.dumps(payload).encode("utf-8")
        req = Request(os.environ.get("RESEND_ENDPOINT", "") or "https://api.resend.com/emails",
                      data=data,
                      headers={"Authorization": "Bearer %s" % key,
                               "Content-Type": "application/json",
                               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"})
        sms_log("[EMAIL OTP] Resend request started")
        resp = urlopen(req, timeout=30)
        body = resp.read().decode("utf-8", "replace")
        resp.close()
        sms_log("[EMAIL OTP] Resend send success -> %s" % to)
        return (True, body)
    except HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")
        except Exception:
            detail = str(e)
        _log_resend_error(e.code, detail)
        return (False, "provider")
    except Exception as e:
        sms_log("[EMAIL OTP] Resend ERROR: %r" % e)
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


def mask_contact(c):
    if c and "@" in c:
        local, dom = c.split("@", 1)
        keep = 2 if len(local) > 2 else 1
        return (local[:keep] + "***@" + dom[:1] + "***")
    if c:
        return (c[:3] + "***" + c[-2:])
    return "none"


@app.route("/api/auth/otp", methods=["POST"])
def api_auth_otp():
    sms_log("[EMAIL OTP] Request received")
    data = request.get_json(force=True)
    contact, mode = auth_contact(data)
    if not contact:
        sms_log("[EMAIL OTP] Email validation FAILED")
        return json_d({"ok": False, "error": "bad"})
    sms_log("[EMAIL OTP] Email validation passed (mode=%s)" % mode)
    if otp_rate_blocked(contact):
        sms_log("[EMAIL OTP] rate blocked %s" % mask_contact(contact))
        return json_d({"ok": False, "error": "rate_limit"})
    allow = otp_rate_allow_send(contact)
    if allow is False:
        sms_log("[EMAIL OTP] rate limit %s" % mask_contact(contact))
        return json_d({"ok": False, "error": "rate_limit"})
    if allow == "gap":
        return json_d({"ok": False, "error": "rate_gap"})
    code = db.otp_new(contact)
    sms_log("[EMAIL OTP] OTP generated and saved")
    registered = db.user_by_phone(contact) is not None
    demo = os.environ.get("DEMO_OTP", "0") == "1"
    if mode == "email":
        if not (os.environ.get("RESEND_API_KEY", "") or "").strip():
            if demo:
                return json_d({"ok": True, "demo": True, "otp": code, "registered": registered})
            sms_log("email OTP blocked: RESEND_API_KEY not set on the server (set DEMO_OTP=1 only for local dev)")
            return json_d({"ok": False, "error": "sms_notcfg", "registered": registered})
        sms_log("[EMAIL OTP] Calling send_email() -> %s" % mask_contact(contact))
        sms_log("[EMAIL OTP] API send started")
        ok, detail = send_email(contact, otp_email_subject(), otp_email_text(code), otp_email_html(code))
        if not ok:
            sms_log("[EMAIL OTP] Resend send FAILED")
            return json_d({"ok": False, "error": "email_send_failed", "registered": registered})
        sms_log("[EMAIL OTP] Resend send success")
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
    is_admin_mail = (contact.lower() == cfg.ADMIN_EMAIL.lower())
    if is_admin_mail:
        session.pop("admin_ok", None)
        return json_d({"ok": True, "admin_pending": True, "role": u["role"]})
    return json_d({"ok": True, "role": u["role"]})


@app.route("/api/auth/admin_verify", methods=["POST"])
def api_auth_admin_verify():
    u = current_user()
    if not u:
        return json_d({"ok": False, "reason": "noauth"})
    if u.get("phone", "").lower() != cfg.ADMIN_EMAIL.lower():
        return json_d({"ok": False, "reason": "noauth"})
    answer = str(request.get_json(force=True).get("answer", "") or "").strip()
    expected = cfg.ADMIN_ANSWER.strip()
    norm = lambda s: "".join(ch for ch in s
                             .replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
                             .replace("ى", "ي").replace("ة", "ه")
                             .replace("ؤ", "و").replace("ئ", "ي")
                             if not (ch.isspace() or ch.isdigit()))
    if norm(answer).lower() == norm(expected).lower():
        session["admin_ok"] = True
        session.permanent = True
        return json_d({"ok": True})
    return json_d({"ok": False, "reason": "wrong"})


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
    session.pop("admin_ok", None)
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
        "resend_key": bool((os.environ.get("RESEND_API_KEY", "") or "").strip()),
        "resend_from": bool((os.environ.get("RESEND_FROM", "") or "").strip()),
        "sms_provider": (os.environ.get("SMS_PROVIDER", "") or "").strip(),
        "demo_otp": (os.environ.get("DEMO_OTP", "") or "").strip(),
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


@app.route("/api/account/notifs/read", methods=["POST"])
def api_account_notifs_read():
    u = current_user()
    if not u:
        return json_d({"ok": False})
    db.user_notif_read_all(u["id"])
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
        want = it.get("size", "OS")
        sizes = [sz for sz in cfg.SIZE_ORDER if st.get(sz, 0) > 0] if p["kind"] != "mug" else []
        if p["kind"] == "mug":
            sizes = ["OS"] if st.get("OS", 0) > 0 else []
        available = bool(sizes)
        out.append({"id": it["id"], "name": it.get("name", ""),
                    "name_ar": p.get("name_ar", ""), "name_en": p.get("name_en", ""),
                    "emoji": p.get("emoji", "⚽"),
                    "size": want, "qty": it.get("qty", 1),
                    "sizes": sizes, "stock": available})
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
    try:
        db.admin_notif_add("review", "⭐ مراجعة جديدة على %s من %s" % (pid, name[:30]))
    except Exception:
        pass
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


def notify_order_status(o, code, new_st):
    """Send the customer an in-account notification when the order status changes."""
    try:
        if not o:
            return
        uid = o["data"].get("user_id")
        old_st = o["status"]
        if uid and new_st and new_st != old_st:
            st_names = {
                "pending": "📝 تم استلام طلبك",
                "confirmed": "✅ تم تأكيد طلبك",
                "preparing": "👕 جاري تجهيز طلبك",
                "delivering": "🚚 طلبك خرج للتوصيل",
                "delivered": "🏠 تم تسليم طلبك",
                "cancelled": "❌ تم إلغاء طلبك",
            }
            txt = (st_names.get(new_st, "📢 تم تحديث طلبك") + " #" + code)
            db.user_notif_add(uid, txt)
    except Exception:
        pass


def admin_login_page(msg=""):
    body = (
        '<div class="wrap"><div style="max-width:420px;margin:0 auto;text-align:center;padding-top:60px">'
        '<div class="adm-login-card">'
        '<div class="adm-login-icon">⚽</div>'
        '<div class="adm-login-brand">GOLAZOX</div>'
        '<h2 class="adm-login-title">لوحة التحكم</h2>'
        '<p class="adm-login-sub">أدخل بيانات المدير للمتابعة</p>'
        + msg +
        '<form method="post" action="/admin/login" style="display:grid;gap:12px;margin-top:20px">'
        '<div class="adm-field">'
        '<label class="adm-label">البريد الإلكتروني</label>'
        '<input class="adm-input" type="email" name="email" placeholder="admin@golazox.com" autofocus required>'
        '</div>'
        '<div class="adm-field">'
        '<label class="adm-label">كلمة المرور</label>'
        '<input class="adm-input" type="password" name="pw" placeholder="••••••••" required>'
        '</div>'
        '<button class="btn pri big" type="submit">دخول لوحة التحكم</button>'
        '</form>'
        '<p style="margin-top:20px"><a class="back" href="/home">← العودة للموقع</a></p>'
        '</div></div>')
    return base_page(body)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("pw", "")
        if email != cfg.ADMIN_EMAIL.lower() or pw != cfg.ADMIN_PASS:
            return admin_login_page("<div class='adm-msg err'>البريد الإلكتروني أو كلمة المرور غير صحيحة</div>")
        session["admin_ok"] = True
        return redirect("/admin")
    if admin_auth():
        return redirect("/admin")
    return admin_login_page("")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_ok", None)
    session.pop("user_id", None)
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
            code = request.form.get("code", "")
            new_st = request.form.get("status", "pending")
            o = db.order_get(code)
            db.order_update(code, status=new_st,
                            payment=request.form.get("payment", "pending"))
            notify_order_status(o, code, new_st)
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
                new_st = request.form.get("status", o["status"])
                db.order_update(code, data=dta, status=new_st,
                                payment=request.form.get("payment", o["payment"]))
                notify_order_status(o, code, new_st)
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
        if act == "whatsapp_settings":
            wa = request.form.get("whatsapp", "").strip().replace("+", "").replace(" ", "").replace("-", "")
            if wa:
                cfg.WHATSAPP = wa
                db.settings_set("whatsapp", wa)
            return admin_page("<div class='msg'>✅ تم حفظ رقم واتساب</div>")
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
            rec["price"] = cfg.PRICE_JERSEY if rec["kind"] == "jersey" else cfg.PRICE_MUG
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
        if act == "notif_read":
            db.admin_notif_read_all()
            return admin_page("<div class='msg'>تم تحديد الكل كمقروء</div>")
        if act == "ad_save":
            aid = int(request.form.get("aid", 0) or 0)
            ta = request.form.get("text_ar", "").strip()
            te = request.form.get("text_en", "").strip()
            link = request.form.get("link", "").strip()
            place = request.form.get("place", "home")
            if aid:
                db.ad_update(aid, ta, te, link, place)
            else:
                db.ad_add(ta, te, link, place)
            return admin_page("<div class='msg'>✅ تم حفظ الإعلان</div>")
        if act == "ad_toggle":
            db.ad_toggle(int(request.form.get("aid", 0) or 0), request.form.get("active", "1") == "1")
            return admin_page("<div class='msg'>تم الحفظ</div>")
        if act == "ad_del":
            db.ad_delete(int(request.form.get("aid", 0) or 0))
            return admin_page("<div class='msg'>🗑 تم حذف الإعلان</div>")
        if act == "comp_new":
            comps = db.settings_get("competitions") or []
            if not isinstance(comps, list):
                comps = []
            comps.append({
                "title": request.form.get("title", "").strip(),
                "description": request.form.get("description", "").strip(),
                "start": request.form.get("start", ""),
                "end": request.form.get("end", ""),
                "participants": []
            })
            db.settings_set("competitions", comps)
            return admin_page("<div class='msg'>✅ تم إنشاء المسابقة</div>")
        if act == "comp_del":
            comps = db.settings_get("competitions") or []
            if isinstance(comps, list):
                idx = int(request.form.get("idx", 0) or 0) - 1
                if 0 <= idx < len(comps):
                    comps.pop(idx)
                    db.settings_set("competitions", comps)
            return admin_page("<div class='msg'>🗑 تم حذف المسابقة</div>")
        if act == "comp_add_participant":
            comps = db.settings_get("competitions") or []
            if isinstance(comps, list):
                idx = int(request.form.get("idx", 0) or 0) - 1
                if 0 <= idx < len(comps):
                    name = request.form.get("name", "").strip()
                    if name:
                        comps[idx].setdefault("participants", []).append(name)
                        db.settings_set("competitions", comps)
            return admin_page("<div class='msg'>✅ تمت إضافة المشارك</div>")
        if act == "draw_run":
            comps = db.settings_get("competitions") or []
            if isinstance(comps, list):
                idx = int(request.form.get("comp_idx", 0) or 0) - 1
                if 0 <= idx < len(comps):
                    participants = comps[idx].get("participants", [])
                    if participants:
                        import random
                        winner = random.choice(participants)
                        return admin_page('<div class="msg" style="font-size:1.2rem;text-align:center;padding:30px">🎉 الفائز: <b style="color:#E11D48;font-size:1.5rem">{}</b></div>'.format(esc(winner)))
                    return admin_page("<div class='msg'>⚠️ لا يوجد مشاركين في المسابقة</div>")
            return admin_page("<div class='msg'>⚠️ اختر مسابقة صحيحة</div>")
    return admin_page("")


def reload_stock():
    global STOCK
    STOCK = db.get_stock()


@app.route("/api/admin/notifs")
def api_admin_notifs():
    if not admin_auth():
        return json_d({"error": "unauthorized"}), 401
    return json_d({
        "unread": db.admin_notif_unread(),
        "list": db.admin_notifs(60),
    })


@app.route("/api/admin/notifs/read", methods=["POST"])
def api_admin_notifs_read():
    if not admin_auth():
        return json_d({"error": "unauthorized"}), 401
    db.admin_notif_read_all()
    return json_d({"ok": True, "unread": 0})


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

    n_orders_total = len(orders)
    n_orders_pending = len([o for o in orders if o["status"] == "pending"])
    rev = sum(o["data"].get("total", 0) for o in orders if o["status"] not in ("cancelled",))
    n_ready = len(ready)
    n_cust = len(db.users_list())

    today = datetime.date.today().strftime("%Y-%m-%d")
    ym = today[:7]
    rev_today = sum(o["data"].get("total", 0) for o in orders
                    if o["status"] != "cancelled" and o["data"].get("date") == today)
    rev_month = sum(o["data"].get("total", 0) for o in orders
                    if o["status"] != "cancelled" and str(o["data"].get("date", "")).startswith(ym))
    today_orders = len([o for o in orders if o["data"].get("date") == today])

    cntq = {}
    for o in orders:
        for it in o["data"].get("items", []):
            pid = it.get("id", "")
            if pid:
                cntq[pid] = cntq.get(pid, 0) + it.get("qty", 1)
    ranked = sorted(cntq.items(), key=lambda kv: -kv[1])
    top = "—"
    if ranked:
        tp = next((x for x in cfg.PRODUCTS if x["id"] == ranked[0][0]), None)
        top = (tp.get("name_ar", "") if tp else ranked[0][0]) or ranked[0][0]

    n_products = len(cfg.PRODUCTS)
    n_instock = sum(1 for p in cfg.PRODUCTS if sum(eff_stock(p).values()) > 0)
    n_outstock = n_products - n_instock
    super_role = admin_role() == "super_admin"
    n_unread = db.admin_notif_unread()

    msg_html = '<div class="adm-flash">' + msg + '</div>' if msg else ''

    st_opts_html = "".join('<option value="%s">%s</option>' % (v, lb) for v, lb in st_opts)
    pay_opts_html = "".join('<option value="%s">%s</option>' % (v, lb) for v, lb in pay_opts)

    # --- Dashboard section ---
    dash_orders = ""
    for o in orders[:10]:
        d = o["data"]
        items = ", ".join(i.get("name", "") for i in d.get("items", [])[:2])
        st_cls = {"pending": "st-new", "confirmed": "st-ok", "preparing": "st-warn", "delivering": "st-info", "delivered": "st-ok", "cancelled": "st-err"}.get(o["status"], "")
        dash_orders += ('<tr><td><b>{c}</b></td><td>{n}</td><td>{i}</td><td>{t}</td>'
                        '<td><span class="st-chip {cls}">{s}</span></td><td><a href="#" onclick="admNav(\'orders\');return false">فتح</a></td></tr>').format(
            c=o["code"], n=esc(d.get("name", "—")), i=esc(items),
            t=fmt_cur(d.get("total", 0)),
            cls=st_cls, s=o["status"])

    dash_cust = ""
    for u in db.users_list()[:5]:
        uo = db.orders_by_user(u["id"])
        us = sum(x["data"].get("total", 0) for x in uo if x["status"] != "cancelled")
        dash_cust += '<tr><td>{name}</td><td>{phone}</td><td>{n}</td><td>{sp}</td></tr>'.format(
            name=esc(u["name"] or "—"), phone=esc(u["phone"]), n=len(uo), sp=fmt_cur(us))

    sec_dashboard = (
        '<div class="adm-section" id="adm-dashboard">'
        '<div class="adm-stat-grid">'
        '<div class="adm-stat"><div class="adm-stat-icon">📦</div><div class="adm-stat-val">{n1}</div><div class="adm-stat-label">إجمالي الطلبات</div></div>'
        '<div class="adm-stat"><div class="adm-stat-icon">🕐</div><div class="adm-stat-val">{n2}</div><div class="adm-stat-label">طلبات اليوم</div></div>'
        '<div class="adm-stat"><div class="adm-stat-icon">👥</div><div class="adm-stat-val">{nc}</div><div class="adm-stat-label">العملاء</div></div>'
        '<div class="adm-stat"><div class="adm-stat-icon">👕</div><div class="adm-stat-val">{np}</div><div class="adm-stat-label">المنتجات</div></div>'
        '<div class="adm-stat"><div class="adm-stat-icon">✅</div><div class="adm-stat-val">{ni}</div><div class="adm-stat-label">متوفر</div></div>'
        '<div class="adm-stat"><div class="adm-stat-icon">❌</div><div class="adm-stat-val">{no}</div><div class="adm-stat-label">نفذ</div></div>'
        '<div class="adm-stat"><div class="adm-stat-icon">💰</div><div class="adm-stat-val">{rt}</div><div class="adm-stat-label">إيراد اليوم</div></div>'
        '<div class="adm-stat"><div class="adm-stat-icon">📈</div><div class="adm-stat-val">{rm}</div><div class="adm-stat-label">إيراد الشهر</div></div>'
        '</div>'
        '<div class="adm-card"><h3>📦 أحدث الطلبات</h3>'
        '<div class="adm-tbl-wrap"><table class="adm-tbl"><thead><tr><th>الرقم</th><th>العميل</th><th>المنتجات</th><th>الإجمالي</th><th>الحالة</th><th></th></tr></thead>'
        '<tbody>{dash_orders}</tbody></table></div></div>'
        '<div class="adm-card"><h3>👥 أحدث العملاء</h3>'
        '<div class="adm-tbl-wrap"><table class="adm-tbl"><thead><tr><th>الاسم</th><th>الهاتف</th><th>الطلبات</th><th>المصروف</th></tr></thead>'
        '<tbody>{dash_cust}</tbody></table></div></div>'
        '</div>'
    ).format(n1=n_orders_total, n2=today_orders, nc=n_cust, np=n_products, ni=n_instock, no=n_outstock,
             rt=fmt_cur(rev_today), rm=fmt_cur(rev_month), dash_orders=dash_orders, dash_cust=dash_cust)

    # --- Orders section ---
    orders_rows = ""
    for o in orders[:100]:
        d = o["data"]
        items = ", ".join(i.get("name", "") for i in d.get("items", [])[:2])
        st_sel = "".join('<option value="%s"%s>%s</option>' % (v, " selected" if v == o["status"] else "", lb) for v, lb in st_opts)
        pay_sel = "".join('<option value="%s"%s>%s</option>' % (v, " selected" if v == o["payment"] else "", lb) for v, lb in pay_opts)
        orders_rows += ('<tr><td><b>{c}</b><br><small>{dt}</small></td><td>{n}<br><small>{ph}</small></td>'
                        '<td>{i}</td><td>{t}</td>'
                        '<td><form method="post" style="display:flex;gap:4px;align-items:center" class="inline-form">'
                        '<input type="hidden" name="act" value="order"><input type="hidden" name="code" value="{c}">'
                        '<select name="status" class="adm-sel-sm">{st_sel}</select>'
                        '<select name="payment" class="adm-sel-sm">{pay_sel}</select>'
                        '<button class="adm-btn-sm">حفظ</button></form></td>'
                        '<td><a href="/admin/order/{c}" class="adm-btn-sm">فتح</a></td></tr>').format(
            c=o["code"], dt=o.get("created", ""), n=esc(d.get("name", "—")), ph=esc(d.get("phone", "")),
            i=esc(items), t=fmt_cur(d.get("total", 0)), st_sel=st_sel, pay_sel=pay_sel)

    sec_orders = (
        '<div class="adm-section" id="adm-orders" style="display:none">'
        '<div class="adm-card"><h3>📦 إدارة الطلبات</h3>'
        '<div class="adm-tbl-wrap"><table class="adm-tbl"><thead><tr><th>الرقم / التاريخ</th><th>العميل</th><th>المنتجات</th><th>الإجمالي</th><th>الحالة / الدفع</th><th></th></tr></thead>'
        '<tbody>{rows}</tbody></table></div></div></div>'
    ).format(rows=orders_rows)

    # --- Customers section ---
    cust_rows = ""
    for u in db.users_list():
        uo = db.orders_by_user(u["id"])
        us = sum(x["data"].get("total", 0) for x in uo if x["status"] != "cancelled")
        st_sel = "".join('<option value="%s"%s>%s</option>' % (v, " selected" if v == u["status"] else "", lb) for v, lb in [("active", "نشط"), ("disabled", "موقوف")])
        cust_rows += ('<tr><td>{name}</td><td>{phone}</td><td>{n}</td><td>{sp}</td>'
                      '<td>{last_login}</td>'
                      '<td><form method="post" style="display:flex;gap:4px;align-items:center" class="inline-form">'
                      '<input type="hidden" name="act" value="cust"><input type="hidden" name="uid" value="{uid}">'
                      '<select name="status" class="adm-sel-sm">{st_sel}</select>'
                      '<button class="adm-btn-sm">حفظ</button></form></td></tr>').format(
            uid=u["id"], name=esc(u["name"] or "—"), phone=esc(u["phone"]),
            n=len(uo), sp=fmt_cur(us), last_login=u.get("last_login", "—"), st_sel=st_sel)

    sec_customers = (
        '<div class="adm-section" id="adm-customers" style="display:none">'
        '<div class="adm-card"><h3>👥 إدارة العملاء</h3>'
        '<div class="adm-tbl-wrap"><table class="adm-tbl"><thead><tr><th>الاسم</th><th>الهاتف</th><th>الطلبات</th><th>المصروف</th><th>آخر دخول</th><th>الحالة</th></tr></thead>'
        '<tbody>{rows}</tbody></table></div></div></div>'
    ).format(rows=cust_rows)

    # --- Products section (JERSEYS) ---
    jersey_rows = ""
    for p in cfg.PRODUCTS:
        if p["kind"] != "jersey":
            continue
        st = eff_stock(p)
        st_txt = " ".join("%s:%d" % (k, v) for k, v in st.items())
        total_q = sum(st.values())
        club_name = cfg.CLUBS.get(p.get("club_id", ""), {}).get("ar", "") if p.get("club_id") else "—"
        bad = ",".join(p.get("badges", []))
        jersey_rows += ('<tr><td>{em} <b>{id}</b> {name}<br><small>{club} · {price} {cu}{hid}</small></td>'
                        '<td><form method="post" style="display:grid;gap:4px;max-width:440px" class="inline-form">'
                        '<input type="hidden" name="act" value="product_save"><input type="hidden" name="pid" value="{id}">'
                        '<input name="name_ar" value="{na}" placeholder="عربي" class="adm-input-sm">'
                        '<input name="name_en" value="{ne}" placeholder="EN" class="adm-input-sm">'
                        '<input name="emoji" value="{em}" class="adm-input-xs" placeholder="إيموجي">'
                        '<input name="badges" value="{bad}" class="adm-input-sm" placeholder="badges">'
                        '<input name="stock" value="{st_txt}" class="adm-input-sm" placeholder="مخزون">'
                        '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
                        '<label class="adm-check">⭐ جديد<input type="checkbox" name="b_new" value="1"{bnew}></label>'
                        '<label class="adm-check">🔥 الأكثر مبيعًا<input type="checkbox" name="b_best" value="1"{bbest}></label>'
                        '<label class="adm-check">إخفاء<input type="checkbox" name="hidden"{hc}></label>'
                        '<button class="adm-btn-sm">حفظ</button></div></form></td>'
                        '<td>{stock}<br><small>{total} قطعة</small></td>'
                        '<td><form method="post" onsubmit="return confirm(\'هل تريد حذف المنتج؟\')" class="inline-form">'
                        '<input type="hidden" name="act" value="product_del"><input type="hidden" name="pid" value="{id}">'
                        '<button class="adm-btn-sm adm-btn-danger">حذف</button></form></td></tr>'
                        ).format(id=p["id"], em=p.get("emoji", "👕"), name=p.get("name_ar", ""),
                                 club=club_name, price=fmt_cur(eff_price(p)), cu=cur(),
                                 hid=" · مخفي" if p.get("hidden") else "",
                                 na=p.get("name_ar", ""), ne=p.get("name_en", ""),
                                 bad=bad, st_txt=st_txt, stock=st_txt,
                                 total=total_q, hc=" checked" if p.get("hidden") else "",
                                 bnew=" checked" if "new" in p.get("badges", []) else "",
                                 bbest=" checked" if "best" in p.get("badges", []) else "")

    # --- Caps section (mugs) ---
    cap_rows = ""
    for p in cfg.PRODUCTS:
        if p["kind"] != "mug":
            continue
        st = eff_stock(p)
        st_txt = " ".join("%s:%d" % (k, v) for k, v in st.items())
        total_q = sum(st.values())
        club_name = cfg.CLUBS.get(p.get("club_id", ""), {}).get("ar", "") if p.get("club_id") else "—"
        bad = ",".join(p.get("badges", []))
        cap_rows += ('<tr><td>{em} <b>{id}</b> {name}<br><small>{club} · {price} {cu}{hid}</small></td>'
                     '<td><form method="post" style="display:grid;gap:4px;max-width:440px" class="inline-form">'
                     '<input type="hidden" name="act" value="product_save"><input type="hidden" name="pid" value="{id}">'
                     '<input name="name_ar" value="{na}" placeholder="عربي" class="adm-input-sm">'
                     '<input name="name_en" value="{ne}" placeholder="EN" class="adm-input-sm">'
                     '<input name="emoji" value="{em}" class="adm-input-xs" placeholder="إيموجي">'
                     '<input name="badges" value="{bad}" class="adm-input-sm" placeholder="badges">'
                     '<input name="stock" value="{st_txt}" class="adm-input-sm" placeholder="مخزون">'
                     '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
                     '<label class="adm-check">⭐ جديد<input type="checkbox" name="b_new" value="1"{bnew}></label>'
                     '<label class="adm-check">🔥 الأكثر مبيعًا<input type="checkbox" name="b_best" value="1"{bbest}></label>'
                     '<label class="adm-check">إخفاء<input type="checkbox" name="hidden"{hc}></label>'
                     '<button class="adm-btn-sm">حفظ</button></div></form></td>'
                     '<td>{stock}<br><small>{total} قطعة</small></td>'
                     '<td><form method="post" onsubmit="return confirm(\'هل تريد حذف المنتج؟\')" class="inline-form">'
                     '<input type="hidden" name="act" value="product_del"><input type="hidden" name="pid" value="{id}">'
                     '<button class="adm-btn-sm adm-btn-danger">حذف</button></form></td></tr>'
                     ).format(id=p["id"], em=p.get("emoji", "☕"), name=p.get("name_ar", ""),
                              club=club_name, price=fmt_cur(eff_price(p)), cu=cur(),
                              hid=" · مخفي" if p.get("hidden") else "",
                              na=p.get("name_ar", ""), ne=p.get("name_en", ""),
                              bad=bad, st_txt=st_txt, stock=st_txt,
                              total=total_q, hc=" checked" if p.get("hidden") else "",
                              bnew=" checked" if "new" in p.get("badges", []) else "",
                              bbest=" checked" if "best" in p.get("badges", []) else "")

    prod_add_form = (
        '<div class="adm-card"><h3>➕ إضافة منتج جديد</h3>'
        '<form method="post" style="display:grid;gap:8px;max-width:620px" class="inline-form">'
        '<input type="hidden" name="act" value="product_save">'
        '<div style="display:flex;gap:8px;flex-wrap:wrap">'
        '<input name="pid" placeholder="المعرّف (مثال: j7)" required class="adm-input-sm">'
        '<select name="kind" class="adm-sel-sm"><option value="jersey">تيشيرت</option><option value="mug">مق</option></select>'
        '<select name="club" class="adm-sel-sm"><option value="">بدون نادي</option>' + club_opts + '</select></div>'
        '<div style="display:flex;gap:8px;flex-wrap:wrap"><input name="name_ar" placeholder="الاسم (عربي)" required class="adm-input-sm">'
        '<input name="name_en" placeholder="الاسم (إنجليزي)" class="adm-input-sm"></div>'
        '<div style="display:flex;gap:8px;flex-wrap:wrap"><input name="emoji" value="👕" class="adm-input-xs">'
        '<input name="colors" value="#E11D48,#F97316" class="adm-input-sm" placeholder="ألوان">'
        '<input name="badges" placeholder="badges (offer)" class="adm-input-sm"></div>'
        '<div style="display:flex;gap:14px;align-items:center">'
        '<label class="adm-check">⭐ جديد<input type="checkbox" name="b_new" value="1"></label>'
        '<label class="adm-check">🔥 الأكثر مبيعًا<input type="checkbox" name="b_best" value="1"></label></div>'
        '<input name="imgs" placeholder="الصور مفصولة بفاصلة (j7_1,j7_2)" class="adm-input-sm">'
        '<input name="stock" placeholder="المخزون: S:3,M:5,L:8,XL:4,2XL:2,3XL:0" class="adm-input-sm">'
        '<button class="adm-btn-sm adm-btn-primary">💾 حفظ المنتج</button></form></div>'
    )

    sec_products = (
        '<div class="adm-section" id="adm-products" style="display:none">'
        '<div class="adm-card"><h3>👕 التيشرتات</h3>'
        '<div class="adm-tbl-wrap"><table class="adm-tbl"><thead><tr><th>المنتج</th><th>تعديل</th><th>المخزون</th><th></th></tr></thead>'
        '<tbody>{jersey_rows}</tbody></table></div></div>'
        '<div class="adm-card"><h3>☕ المقّات</h3>'
        '<div class="adm-tbl-wrap"><table class="adm-tbl"><thead><tr><th>المنتج</th><th>تعديل</th><th>المخزون</th><th></th></tr></thead>'
        '<tbody>{cap_rows}</tbody></table></div></div>'
        '{prod_add_form}'
        '</div>'
    ).format(jersey_rows=jersey_rows, cap_rows=cap_rows, prod_add_form=prod_add_form)

    # --- Teams section ---
    team_rows = ""
    for cid, c in cfg.CLUBS.items():
        t = club_themes().get(cid, {})
        team_rows += (
            '<div class="adm-team-card">'
            '<div class="adm-team-emoji">{emoji}</div>'
            '<div class="adm-team-name">{ar}<br><small style="color:#78817D">{en}</small></div>'
            '<div class="adm-team-colors">'
            '<label><span class="adm-color-dot" style="background:{ac}"></span>أساسي<input type="color" value="{ac}" class="adm-color-pick"></label>'
            '<label><span class="adm-color-dot" style="background:{ac2}"></span>ثانوي<input type="color" value="{ac2}" class="adm-color-pick"></label>'
            '</div></div>'
        ).format(emoji=c.get("emoji", "⚽"), ar=c.get("ar", cid), en=c.get("en", cid),
                 ac=t.get("ac", c.get("accent", "#E11D48")),
                 ac2=t.get("ac2", c.get("accent2", "#F97316")))

    sec_teams = (
        '<div class="adm-section" id="adm-teams" style="display:none">'
        '<div class="adm-card"><h3>⚽ الأندية</h3>'
        '<div class="adm-team-grid">{team_rows}</div></div></div>'
    ).format(team_rows=team_rows)

    # --- Sizes section ---
    size_chart = ""
    for sz in cfg.SIZE_ORDER:
        sc = cfg.SIZE_CHART.get(sz, {})
        size_chart += (
            '<tr><td><b>{sz}</b></td>'
            '<td><input name="len_{sz}" value="{len}" class="adm-input-xs"></td>'
            '<td><input name="wid_{sz}" value="{wid}" class="adm-input-xs"></td>'
            '<td><input name="hgt_{sz}" value="{hgt}" class="adm-input-xs"></td>'
            '<td><input name="wgt_{sz}" value="{wgt}" class="adm-input-xs"></td></tr>'
        ).format(sz=sz, len=sc.get("length", ""), wid=sc.get("width", ""),
                 hgt=sc.get("height", ""), wgt=sc.get("weight", ""))

    sec_sizes = (
        '<div class="adm-section" id="adm-sizes" style="display:none">'
        '<div class="adm-card"><h3>📏 دليل المقاسات الآسيوي</h3>'
        '<div class="adm-tbl-wrap"><table class="adm-tbl"><thead><tr><th>المقاس</th><th>الطول (سم)</th><th>العرض (سم)</th><th>الطول (سم)</th><th>الوزن (كجم)</th></tr></thead>'
        '<tbody>{size_chart}</tbody></table></div>'
        '<div class="adm-notice">⚠️ هذا الدليل تقريبي — الأطوال والعرض بالسنتيمتر، والأوزان بالكيلوجرام.</div></div></div>'
    ).format(size_chart=size_chart)

    # --- Competitions section ---
    comps = db.settings_get("competitions") or []
    if not isinstance(comps, list):
        comps = []
    comp_rows = ""
    for i, cp in enumerate(comps):
        comp_rows += (
            '<tr><td>#{idx}</td><td>{title}</td><td>{desc}</td><td>{start}</td><td>{end}</td>'
            '<td><a href="#" onclick="admNav(\'draw\');return false" class="adm-btn-sm">سحب</a></td></tr>'
        ).format(idx=i + 1, title=esc(cp.get("title", "")), desc=esc(cp.get("description", "")),
                 start=esc(cp.get("start", "")), end=esc(cp.get("end", "")))

    if not comp_rows:
        comp_rows = '<tr><td colspan="6" class="adm-empty">لا توجد مسابقات</td></tr>'

    sec_competitions = (
        '<div class="adm-section" id="adm-competitions" style="display:none">'
        '<div class="adm-card"><h3>🏆 المسابقات</h3>'
        '<div class="adm-tbl-wrap"><table class="adm-tbl"><thead><tr><th>#</th><th>العنوان</th><th>الوصف</th><th>البداية</th><th>النهاية</th><th></th></tr></thead>'
        '<tbody>{comp_rows}</tbody></table></div></div>'
        '<div class="adm-card"><h3>➕ مسابقة جديدة</h3>'
        '<form method="post" style="display:grid;gap:8px;max-width:560px" class="inline-form">'
        '<input type="hidden" name="act" value="comp_new">'
        '<input name="title" placeholder="عنوان المسابقة" class="adm-input-sm" required>'
        '<input name="description" placeholder="الوصف" class="adm-input-sm">'
        '<div style="display:flex;gap:10px"><input name="start" type="datetime-local" class="adm-input-sm"><input name="end" type="datetime-local" class="adm-input-sm"></div>'
        '<button class="adm-btn-sm adm-btn-primary">💾 إنشاء</button></form></div></div>'
    ).format(comp_rows=comp_rows)

    # --- Draw section ---
    comp_sel_opts = "".join('<option value="%d">%s</option>' % (i, esc(cp.get("title", "—" + str(i + 1)))) for i, cp in enumerate(comps))
    sec_draw = (
        '<div class="adm-section" id="adm-draw" style="display:none">'
        '<div class="adm-card"><h3>🎯 السحب العشوائي</h3>'
        '<form method="post" style="display:grid;gap:8px;max-width:560px" class="inline-form">'
        '<input type="hidden" name="act" value="draw_run">'
        '<select name="comp_idx" class="adm-sel-sm">{comp_sel_opts}</select>'
        '<button class="adm-btn-sm adm-btn-primary" type="submit">⚽ ابدأ السحب</button></form>'
        '<div id="drawResult" style="margin-top:16px"></div></div></div>'
    ).format(comp_sel_opts=comp_sel_opts if comp_sel_opts else '<option value="">— لا توجد مسابقات —</option>')

    # --- Penalty section ---
    pen_conn = db._conn() if hasattr(db, '_conn') else None
    pen_rows = ""
    try:
        import db as _db
        _conn = _db._conn()
        pen_all = [dict(r) for r in _conn.execute("SELECT * FROM penalties ORDER BY id DESC LIMIT 50").fetchall()]
        _conn.close()
        total_pen = len(pen_all)
        goals = sum(1 for p in pen_all if p.get("outcome") == "goal")
        saved = total_pen - goals
        for pp in pen_all[:20]:
            pen_rows += '<tr><td>{code}</td><td>{out}</td><td>{dt}</td></tr>'.format(
                code=esc(pp.get("order_code", "")), out="هدف ⚽" if pp.get("outcome") == "goal" else "تصدي 🧤",
                dt=esc(pp.get("created", "")))
    except Exception:
        total_pen = goals = saved = 0
        pen_rows = '<tr><td colspan="3" class="adm-empty">لا توجد بيانات</td></tr>'

    sec_penalty = (
        '<div class="adm-section" id="adm-penalty" style="display:none">'
        '<div class="adm-stat-grid">'
        '<div class="adm-stat"><div class="adm-stat-icon">⚽</div><div class="adm-stat-val">{total}</div><div class="adm-stat-label">إجمالي</div></div>'
        '<div class="adm-stat"><div class="adm-stat-icon">🥅</div><div class="adm-stat-val">{goals}</div><div class="adm-stat-label">أهداف</div></div>'
        '<div class="adm-stat"><div class="adm-stat-icon">🧤</div><div class="adm-stat-val">{saved}</div><div class="adm-stat-label">تصديات</div></div>'
        '</div>'
        '<div class="adm-card"><h3>⚽ أحدث التحديات</h3>'
        '<div class="adm-tbl-wrap"><table class="adm-tbl"><thead><tr><th>رقم الطلب</th><th>النتيجة</th><th>التاريخ</th></tr></thead>'
        '<tbody>{pen_rows}</tbody></table></div></div></div>'
    ).format(total=total_pen, goals=goals, saved=saved, pen_rows=pen_rows)

    # --- Analytics section ---
    top_products_html = ""
    for pid, q in ranked[:8]:
        tp = next((x for x in cfg.PRODUCTS if x["id"] == pid), None)
        if not tp:
            continue
        bar_w = max(5, int(q / max(cntq.values()) * 100)) if cntq else 5
        top_products_html += (
            '<div class="adm-bar-row">'
            '<div class="adm-bar-label">{em} {n}</div>'
            '<div class="adm-bar-track"><div class="adm-bar-fill" style="width:{w}%"></div></div>'
            '<div class="adm-bar-val">{q}</div></div>'
        ).format(em=tp.get("emoji", ""), n=esc(tp.get("name_ar", pid)), w=bar_w, q=q)

    team_cnt = {}
    for o in orders:
        for it in o["data"].get("items", []):
            pid = it.get("id", "")
            tp = next((x for x in cfg.PRODUCTS if x["id"] == pid), None)
            if tp and tp.get("club_id"):
                team_cnt[tp["club_id"]] = team_cnt.get(tp["club_id"], 0) + it.get("qty", 1)
    team_ranked = sorted(team_cnt.items(), key=lambda kv: -kv[1])
    top_teams_html = ""
    if team_ranked:
        max_tv = team_ranked[0][1]
        for cid, q in team_ranked[:8]:
            c = cfg.CLUBS.get(cid, {})
            bar_w = max(5, int(q / max_tv * 100))
            top_teams_html += (
                '<div class="adm-bar-row">'
                '<div class="adm-bar-label">{em} {n}</div>'
                '<div class="adm-bar-track"><div class="adm-bar-fill" style="width:{w}%;background:var(--bar-ac,#E11D48)"></div></div>'
                '<div class="adm-bar-val">{q}</div></div>'
            ).format(em=c.get("emoji", "⚽"), n=esc(c.get("ar", cid)), w=bar_w, q=q)

    status_dist = {}
    for o in orders:
        s = o.get("status", "pending")
        status_dist[s] = status_dist.get(s, 0) + 1

    sec_analytics = (
        '<div class="adm-section" id="adm-analytics" style="display:none">'
        '<div class="adm-stat-grid">'
        '<div class="adm-stat"><div class="adm-stat-icon">📦</div><div class="adm-stat-val">{nt}</div><div class="adm-stat-label">إجمالي الطلبات</div></div>'
        '<div class="adm-stat"><div class="adm-stat-icon">💰</div><div class="adm-stat-val">{rev}</div><div class="adm-stat-label">إجمالي الإيراد</div></div>'
        '<div class="adm-stat"><div class="adm-stat-icon">👥</div><div class="adm-stat-val">{nc}</div><div class="adm-stat-label">العملاء</div></div>'
        '</div>'
        '<div class="adm-card"><h3>🏆 المنتجات الأكثر طلبًا</h3>{top_products}</div>'
        '<div class="adm-card"><h3>⚽ الأندية الأكثر طلبًا</h3>{top_teams}</div>'
        '<div class="adm-card"><h3>📊 توزيع الحالات</h3>'
        '<div class="adm-status-bars">{status_bars}</div></div></div>'
    ).format(nt=n_orders_total, rev=fmt_cur(rev), nc=n_cust,
             top_products=top_products_html if top_products_html else '<p class="adm-empty">لا توجد بيانات</p>',
             top_teams=top_teams_html if top_teams_html else '<p class="adm-empty">لا توجد بيانات</p>',
             status_bars="".join(
                 '<div class="adm-bar-row"><div class="adm-bar-label">{s}</div>'
                 '<div class="adm-bar-track"><div class="adm-bar-fill" style="width:{w}%"></div></div>'
                 '<div class="adm-bar-val">{c}</div></div>'.format(
                     s=s, c=c, w=max(5, int(c / max(status_dist.values()) * 100)) if status_dist else 5)
                 for s, c in sorted(status_dist.items(), key=lambda kv: -kv[1])
             ))

    # --- Settings section ---
    theme_rows = ""
    for cid, c in cfg.CLUBS.items():
        t = club_themes().get(cid, {})
        theme_rows += (
            '<div class="adm-theme-row">'
            '<div class="adm-theme-label">{emoji} {ar}</div>'
            '<div class="adm-theme-inputs">'
            '<label>أساسي<input type="color" name="ac_{cid}" value="{ac}" class="adm-color-pick"></label>'
            '<label>ثانوي<input type="color" name="ac2_{cid}" value="{ac2}" class="adm-color-pick"></label>'
            '<label>توهج<input type="color" name="glow_{cid}" value="{glow}" class="adm-color-pick"></label>'
            '<label>الصفحة<input type="color" name="tint_{cid}" value="{tint}" class="adm-color-pick"></label>'
            '<label class="adm-check">إعادة<div style="margin-top:2px"><input type="checkbox" name="reset_{cid}"></div></label>'
            '</div></div>'
        ).format(emoji=c.get("emoji", ""), ar=c.get("ar", cid), cid=cid,
                 ac=t.get("ac", "#E11D48"), ac2=t.get("ac2", "#F97316"),
                 glow=t.get("glow", "#E11D48"), tint=t.get("tint", "#E11D48"))

    pp_rw = passport_rewards()
    pp_form = ""
    for l in range(4):
        r = pp_rw.get(str(l), pp_rw.get(l, {"d": 0, "p": 0}))
        pp_form += (
            '<div class="adm-pp-row">'
            '<b class="adm-pp-label">{name}</b>'
            '<input name="pp_d_{l}" type="number" step="0.5" value="{d}" class="adm-input-xs" placeholder="خصم %">'
            '<input name="pp_p_{l}" type="number" value="{p}" class="adm-input-xs" placeholder="نقاط"></div>'
        ).format(name=dl.get("lv_" + str(l), str(l)), l=l, d=r.get("d", 0), p=r.get("p", 0))

    adm_rows = ""
    for u in db.users_list():
        if u["role"] not in ("admin", "super_admin"):
            continue
        togg = ""
        if super_role and u["role"] == "admin":
            togg = ('<form method="post" style="display:inline" class="inline-form">'
                     '<input type="hidden" name="act" value="admins_toggle">'
                     '<input type="hidden" name="uid" value="{uid}"><input type="hidden" name="role" value="customer">'
                     '<button class="adm-btn-sm adm-btn-danger">إلغاء</button></form>').format(uid=u["id"])
        adm_rows += '<tr><td>{name}</td><td>{phone}</td><td>{role}</td><td>{t}</td></tr>'.format(
            name=esc(u["name"] or "—"), phone=esc(u["phone"]), role=u["role"], t=togg)

    adm_card = ""
    if super_role:
        adm_card = (
            '<div class="adm-card"><h3>👥 إدارة المديرين</h3>'
            '<form method="post" style="display:grid;gap:8px;max-width:420px;margin-bottom:12px" class="inline-form">'
            '<input type="hidden" name="act" value="admins">'
            '<input name="name" placeholder="اسم المدير" class="adm-input-sm">'
            '<input name="phone" placeholder="رقم الهاتف" class="adm-input-sm">'
            '<button class="adm-btn-sm adm-btn-primary">إضافة مدير</button></form>'
            '<div class="adm-tbl-wrap"><table class="adm-tbl"><thead><tr><th>الاسم</th><th>الهاتف</th><th>الدور</th><th></th></tr></thead>'
            '<tbody>{adm_rows}</tbody></table></div></div>'
        ).format(adm_rows=adm_rows)

    sec_settings = (
        '<div class="adm-section" id="adm-settings" style="display:none">'
        '<div class="adm-card"><h3>💬 إعدادات واتساب</h3>'
        '<form method="post" style="display:grid;gap:8px;max-width:420px" class="inline-form">'
        '<input type="hidden" name="act" value="whatsapp_settings">'
        '<label style="font-size:.82rem;color:var(--muted)">رقم واتساب (بدون + أو مسافات)</label>'
        '<input name="whatsapp" value="{wa}" class="adm-input-sm" placeholder="97338818226">'
        '<button class="adm-btn-sm adm-btn-primary">حفظ رقم واتساب</button></form>'
        '<div class="adm-notice" style="margin-top:8px">يُستخدم هذا الرقم في جميع أزرار التواصل عبر واتساب في الموقع.</div></div>'
        '<div class="adm-card"><h3>🎨 ثيمات الأندية</h3>'
        '<form method="post" class="inline-form"><input type="hidden" name="act" value="club_theme">'
        '{theme_rows}'
        '<button class="adm-btn-sm adm-btn-primary">حفظ الثيمات</button></form></div>'
        '<div class="adm-card"><h3>🎫 مكافآت الجواز</h3>'
        '<form method="post" style="display:grid;gap:8px;max-width:560px" class="inline-form">'
        '<input type="hidden" name="act" value="pp_rewards">'
        '{pp_form}'
        '<button class="adm-btn-sm adm-btn-primary">حفظ المكافآت</button></form></div>'
        '{adm_card}'
        '<div class="adm-card"><h3>📢 إدارة الإعلانات</h3>'
        '<form method="post" style="display:grid;gap:8px;max-width:560px" class="inline-form">'
        '<input type="hidden" name="act" value="ad_save">'
        '<input name="text_ar" placeholder="نص الإعلان (عربي)" class="adm-input-sm" required>'
        '<input name="text_en" placeholder="Announcement text (EN)" class="adm-input-sm">'
        '<input name="link" placeholder="الرابط (اختياري)" class="adm-input-sm">'
        '<select name="place" class="adm-sel-sm"><option value="home">الرئيسية</option>'
        '<option value="products">صفحة المنتجات</option><option value="banner">شريط علوي</option></select>'
        '<button class="adm-btn-sm adm-btn-primary">💾 حفظ الإعلان</button></form></div>'
        '<div class="adm-card"><h3>⚡ MATCHDAY</h3>'
        '<form method="post" style="display:grid;gap:8px;max-width:560px" class="inline-form">'
        '<input type="hidden" name="act" value="match">'
        '<div style="display:flex;gap:10px">{club_opts_h} {club_opts_a}</div>'
        '<input name="kickoff" type="datetime-local" value="{mk}" class="adm-input-sm">'
        '<input name="result" placeholder="النتيجة (مثلاً 2-1)" value="{mr}" class="adm-input-sm">'
        '<div style="display:flex;gap:10px"><button class="adm-btn-sm adm-btn-primary">حفظ</button>'
        '<button class="adm-btn-sm" formaction="/admin" name="act" value="match_clear">مسح</button></div></form></div>'
        '<div class="adm-card"><h3>🔥 NEW DROP</h3>'
        '<form method="post" style="display:grid;gap:8px;max-width:560px" class="inline-form">'
        '<input type="hidden" name="act" value="drop">'
        '<div style="display:flex;gap:10px"><input name="drop_ar" placeholder="اسم الإصدار (عربي)" value="{dar}" class="adm-input-sm">'
        '<input name="drop_en" placeholder="Drop name (EN)" value="{den}" class="adm-input-sm"></div>'
        '<input name="target" type="datetime-local" value="{dtg}" class="adm-input-sm">'
        '<input name="img" placeholder="صورة (j1_1)" value="{dimg}" class="adm-input-sm">'
        '<input name="pids" placeholder="منتجات الإصدار (j1,j2)" value="{dids}" class="adm-input-sm">'
        '<div style="display:flex;gap:10px"><button class="adm-btn-sm adm-btn-primary">حفظ</button>'
        '<button class="adm-btn-sm" formaction="/admin" name="act" value="drop_clear">مسح</button></div></form></div>'
        '</div>'
    ).format(
        theme_rows=theme_rows, pp_form=pp_form, adm_card=adm_card,
        wa=cfg.WHATSAPP,
        club_opts_h=club_opts, club_opts_a=club_opts.replace('name="home"', 'name="away"'),
        mk=(m["kickoff"].replace(" ", "T") if m and m.get("kickoff") else ""),
        mr=(m["result"] if m and m.get("result") else ""),
        dar=(dr["ar"] if dr else ""), den=(dr["en"] if dr else ""),
        dtg=(dr["target"].replace(" ", "T") if dr else ""), dimg=(dr["img"] if dr else ""),
        dids=",".join(dr["product_ids"]) if dr else "")

    body = (
        msg_html
        + sec_dashboard
        + sec_orders
        + sec_customers
        + sec_products
        + sec_teams
        + sec_sizes
        + sec_competitions
        + sec_draw
        + sec_penalty
        + sec_analytics
        + sec_settings
    )
    return admin_template(body)


def admin_template(body, title="Dashboard"):
    return """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GOLAZOX Admin — """ + esc(title) + """</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#050607;--card:rgba(255,255,255,.045);--border:rgba(255,255,255,.10);--text:#F5F7F5;--muted:#78817D;--accent:#18E875;--accent2:#0B9F50;--sidebar-w:240px;--bar-ac:#18E875}
body{font-family:'Cairo','Segoe UI',sans-serif;background:var(--bg);color:var(--text);font-size:14px;min-height:100vh}
a{text-decoration:none;color:inherit}

/* ---- Sidebar ---- */
.adm-sidebar{position:fixed;top:0;right:0;width:var(--sidebar-w);height:100vh;background:rgba(255,255,255,.03);border-left:1px solid var(--border);display:flex;flex-direction:column;z-index:100;overflow-y:auto;transition:transform .25s}
.adm-sidebar-brand{padding:18px 16px 12px;font-size:1.1rem;font-weight:900;color:var(--text);display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border)}
.adm-sidebar-brand span{font-size:1.4rem}
.adm-nav{flex:1;padding:8px 0}
.adm-nav-item{display:flex;align-items:center;gap:10px;padding:10px 16px;cursor:pointer;color:var(--muted);transition:all .15s;border-right:3px solid transparent;font-weight:600}
.adm-nav-item:hover,.adm-nav-item.active{color:var(--text);background:rgba(255,255,255,.06);border-right-color:var(--accent)}
.adm-nav-item .nav-icon{font-size:1.1rem;width:24px;text-align:center}
.adm-nav-item .nav-label{font-size:.88rem}
.adm-sidebar-footer{padding:12px 16px;border-top:1px solid var(--border)}
.adm-sidebar-footer a{display:block;padding:6px 0;color:var(--muted);font-weight:600;font-size:.85rem}
.adm-sidebar-footer a:hover{color:var(--text)}

/* ---- Hamburger (mobile) ---- */
.adm-hamburger{display:none;position:fixed;top:12px;right:12px;z-index:200;width:40px;height:40px;background:rgba(255,255,255,.08);border:1px solid var(--border);border-radius:10px;cursor:pointer;align-items:center;justify-content:center;font-size:1.3rem;color:var(--text)}
.adm-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:90}
.adm-overlay.show{display:block}

/* ---- Main ---- */
.adm-main{margin-right:var(--sidebar-w);padding:24px 28px 60px;min-height:100vh}
.adm-topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.adm-topbar h1{font-size:1.2rem;font-weight:900}
.adm-topbar-actions{display:flex;gap:8px}

/* ---- Cards ---- */
.adm-card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px;margin-bottom:16px;overflow-x:auto}
.adm-card h3{font-size:1rem;font-weight:900;margin-bottom:12px;color:var(--text)}

/* ---- Stat cards ---- */
.adm-stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:18px}
.adm-stat{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;text-align:center}
.adm-stat-icon{font-size:1.4rem;margin-bottom:4px}
.adm-stat-val{font-size:1.6rem;font-weight:900;color:var(--accent)}
.adm-stat-label{font-size:.78rem;color:var(--muted);margin-top:2px}

/* ---- Tables ---- */
.adm-tbl-wrap{overflow-x:auto}
.adm-tbl{width:100%;border-collapse:collapse;font-size:.85rem}
.adm-tbl th{text-align:right;padding:8px 10px;color:var(--muted);border-bottom:1px solid var(--border);font-weight:700;white-space:nowrap}
.adm-tbl td{padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.05);vertical-align:top}
.adm-tbl tr:hover{background:rgba(255,255,255,.03)}
.adm-empty{text-align:center;color:var(--muted);padding:20px}

/* ---- Forms / Inputs ---- */
.adm-input-sm{background:rgba(255,255,255,.06);border:1px solid var(--border);border-radius:8px;padding:7px 10px;color:var(--text);font-family:inherit;font-size:.85rem;width:100%;max-width:100%}
.adm-input-xs{background:rgba(255,255,255,.06);border:1px solid var(--border);border-radius:6px;padding:5px 8px;color:var(--text);font-family:inherit;font-size:.82rem;width:72px}
.adm-sel-sm{background:rgba(255,255,255,.06);border:1px solid var(--border);border-radius:8px;padding:6px 8px;color:var(--text);font-family:inherit;font-size:.82rem;color-scheme:dark}
.adm-sel-sm option{background:#0B1712;color:#F4F7F5}
.adm-btn-sm{background:rgba(255,255,255,.08);border:1px solid var(--border);border-radius:8px;padding:6px 14px;font-weight:700;cursor:pointer;font-family:inherit;color:var(--text);font-size:.82rem;transition:all .15s}
.adm-btn-sm:hover{background:rgba(255,255,255,.14)}
.adm-btn-primary{background:var(--accent);border-color:var(--accent);color:#fff}
.adm-btn-primary:hover{background:var(--accent2)}
.adm-btn-danger{background:rgba(220,38,38,.2);border-color:rgba(220,38,38,.3);color:#f87171}
.adm-btn-danger:hover{background:rgba(220,38,38,.35)}
.adm-check{font-size:.8rem;color:var(--muted);display:flex;align-items:center;gap:4px;cursor:pointer}
.adm-check input{accent-color:var(--accent)}

/* ---- Flash message ---- */
.adm-flash{background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.3);color:#6ee7b7;border-radius:10px;padding:10px 14px;margin-bottom:16px;font-weight:600}

/* ---- Status chips ---- */
.st-chip{display:inline-block;padding:2px 8px;border-radius:999px;font-size:.75rem;font-weight:700}
.st-new{background:rgba(251,191,36,.15);color:#fbbf24}
.st-ok{background:rgba(16,185,129,.15);color:#6ee7b7}
.st-warn{background:rgba(245,158,11,.15);color:#fbbf24}
.st-info{background:rgba(59,130,246,.15);color:#93c5fd}
.st-err{background:rgba(239,68,68,.15);color:#fca5a5}

/* ---- Bar chart ---- */
.adm-bar-row{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.adm-bar-label{width:140px;text-align:right;font-size:.82rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex-shrink:0}
.adm-bar-track{flex:1;height:18px;background:rgba(255,255,255,.06);border-radius:4px;overflow:hidden}
.adm-bar-fill{height:100%;background:var(--accent);border-radius:4px;transition:width .4s}
.adm-bar-val{width:40px;text-align:left;font-size:.82rem;font-weight:700;flex-shrink:0}

/* ---- Teams grid ---- */
.adm-team-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
.adm-team-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center}
.adm-team-emoji{font-size:2rem;margin-bottom:6px}
.adm-team-name{font-weight:800;margin-bottom:8px}
.adm-team-colors{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
.adm-team-colors label{display:flex;align-items:center;gap:4px;font-size:.78rem;color:var(--muted)}
.adm-color-dot{width:14px;height:14px;border-radius:50%;display:inline-block;border:1px solid var(--border)}
.adm-color-pick{width:28px;height:24px;border:none;background:none;cursor:pointer;padding:0}

/* ---- Theme row (settings) ---- */
.adm-theme-row{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.05);flex-wrap:wrap}
.adm-theme-label{min-width:160px;font-weight:700}
.adm-theme-inputs{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.adm-theme-inputs label{display:flex;align-items:center;gap:4px;font-size:.78rem;color:var(--muted)}

/* ---- Passport row ---- */
.adm-pp-row{display:flex;gap:8px;align-items:center;margin-bottom:6px}
.adm-pp-label{width:100px;font-weight:700;font-size:.85rem}

/* ---- Notice ---- */
.adm-notice{background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.2);color:#fbbf24;border-radius:8px;padding:8px 12px;font-size:.82rem;margin-top:10px}

/* ---- Mobile ---- */
@media(max-width:768px){
.adm-sidebar{transform:translateX(100%)}
.adm-sidebar.open{transform:translateX(0)}
.adm-hamburger{display:flex}
.adm-main{margin-right:0;padding:60px 14px 40px}
.adm-stat-grid{grid-template-columns:repeat(2,1fr)}
.adm-team-grid{grid-template-columns:1fr 1fr}
.adm-bar-label{width:80px;font-size:.75rem}
}
</style></head>
<body>
<button class="adm-hamburger" onclick="document.querySelector('.adm-sidebar').classList.toggle('open');document.querySelector('.adm-overlay').classList.toggle('show')">☰</button>
<div class="adm-overlay" onclick="document.querySelector('.adm-sidebar').classList.remove('open');this.classList.remove('show')"></div>
<nav class="adm-sidebar" id="admSidebar">
<div class="adm-sidebar-brand"><span>⚽</span> GOLAZOX</div>
<div class="adm-nav" id="admNav">
<div class="adm-nav-item active" onclick="admNav('dashboard')" data-sec="dashboard"><span class="nav-icon">🏠</span><span class="nav-label">لوحة التحكم</span></div>
<div class="adm-nav-item" onclick="admNav('orders')" data-sec="orders"><span class="nav-icon">📦</span><span class="nav-label">الطلبات</span></div>
<div class="adm-nav-item" onclick="admNav('customers')" data-sec="customers"><span class="nav-icon">👥</span><span class="nav-label">العملاء</span></div>
<div class="adm-nav-item" onclick="admNav('products')" data-sec="products"><span class="nav-icon">👕</span><span class="nav-label">المنتجات</span></div>
<div class="adm-nav-item" onclick="admNav('teams')" data-sec="teams"><span class="nav-icon">⚽</span><span class="nav-label">الأندية</span></div>
<div class="adm-nav-item" onclick="admNav('sizes')" data-sec="sizes"><span class="nav-icon">📏</span><span class="nav-label">المقاسات</span></div>
<div class="adm-nav-item" onclick="admNav('competitions')" data-sec="competitions"><span class="nav-icon">🏆</span><span class="nav-label">المسابقات</span></div>
<div class="adm-nav-item" onclick="admNav('draw')" data-sec="draw"><span class="nav-icon">🎯</span><span class="nav-label">السحب</span></div>
<div class="adm-nav-item" onclick="admNav('penalty')" data-sec="penalty"><span class="nav-icon">⚽</span><span class="nav-label">الركلات</span></div>
<div class="adm-nav-item" onclick="admNav('analytics')" data-sec="analytics"><span class="nav-icon">📊</span><span class="nav-label">التحليلات</span></div>
<div class="adm-nav-item" onclick="admNav('settings')" data-sec="settings"><span class="nav-icon">⚙️</span><span class="nav-label">الإعدادات</span></div>
</div>
<div class="adm-sidebar-footer">
<a href="/home">الموقع</a>
<a href="/admin/logout">خروج</a>
</div>
</nav>
<main class="adm-main">
<div class="adm-topbar"><h1>GOLAZOX Admin</h1><div class="adm-topbar-actions"><a href="/home" class="adm-btn-sm">الموقع</a><a href="/admin/logout" class="adm-btn-sm">خروج</a></div></div>
BODY
</main>
<script>
function admNav(sec){
var items=document.querySelectorAll('.adm-nav-item');
var secs=document.querySelectorAll('.adm-section');
items.forEach(function(el){el.classList.toggle('active',el.getAttribute('data-sec')===sec)});
secs.forEach(function(el){el.style.display=el.id==='adm-'+sec?'block':'none'});
document.querySelector('.adm-sidebar').classList.remove('open');
document.querySelector('.adm-overlay').classList.remove('show');
window.scrollTo(0,0);
}
</script>
</body></html>""".replace("BODY", body)


if __name__ == "__main__":
    seed_super_admin()
    sms_log("[EMAIL OTP] startup resend_key=%s resend_from=%s"
            % (bool((os.environ.get("RESEND_API_KEY", "") or "").strip()),
               bool((os.environ.get("RESEND_FROM", "") or "").strip())))
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
