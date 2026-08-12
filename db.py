# -*- coding: utf-8 -*-
"""
golazox — SQLite persistence (orders, notify-me, special requests, stock overrides,
polls, votes, settings).
"""
import json
import os
import sqlite3
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golazox.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE, data TEXT, status TEXT DEFAULT 'pending',
  payment TEXT DEFAULT 'pending', created TEXT);
CREATE TABLE IF NOT EXISTS notify(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product TEXT, size TEXT, phone TEXT, country TEXT,
  created TEXT, notified INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS requests(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  data TEXT, status TEXT DEFAULT 'new', created TEXT);
CREATE TABLE IF NOT EXISTS stock(
  product TEXT, size TEXT, qty INTEGER, PRIMARY KEY(product, size));
CREATE TABLE IF NOT EXISTS polls(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  data TEXT, start TEXT, end TEXT, status TEXT DEFAULT 'open', created TEXT);
CREATE TABLE IF NOT EXISTS votes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  poll INTEGER, option TEXT, device TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS penalties(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_code TEXT UNIQUE, device TEXT, outcome TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product TEXT, device TEXT, name TEXT, design INTEGER, fabric INTEGER, quality INTEGER,
  size_rating INTEGER, fit TEXT, text TEXT, photo TEXT, verified INTEGER DEFAULT 0,
  status TEXT DEFAULT 'pending', reported INTEGER DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product TEXT, phone TEXT, device TEXT, price REAL, triggered INTEGER DEFAULT 0,
  active INTEGER DEFAULT 1, created TEXT);
CREATE TABLE IF NOT EXISTS points(
  device TEXT PRIMARY KEY, total INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS pts_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, device TEXT, delta INTEGER, label TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT UNIQUE, email TEXT DEFAULT '', name TEXT DEFAULT '', role TEXT DEFAULT 'customer',
  status TEXT DEFAULT 'active', lang TEXT DEFAULT 'ar', theme TEXT DEFAULT 'light',
  font TEXT DEFAULT 'b', area TEXT DEFAULT '', address TEXT DEFAULT '',
  password TEXT DEFAULT '', favs TEXT DEFAULT '[]', sizes TEXT DEFAULT '{}',
  created TEXT, last_login TEXT);
CREATE TABLE IF NOT EXISTS otps(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT, code TEXT, expires TEXT, used INTEGER DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS admin_notifications(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT, text TEXT, read INTEGER DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS ads(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  text_ar TEXT, text_en TEXT, link TEXT, place TEXT DEFAULT 'home',
  active INTEGER DEFAULT 1, created TEXT);
CREATE TABLE IF NOT EXISTS user_notifications(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER, text TEXT, read INTEGER DEFAULT 0, created TEXT);
"""


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=12000")
    return conn


def init_db(products, prefix="GOAL"):
    conn = _conn()
    conn.executescript(_SCHEMA)
    # migrate older databases that lack new users columns
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "password" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN password TEXT DEFAULT ''")
    if "email" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")
    if "favs" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN favs TEXT DEFAULT '[]'")
    if "sizes" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN sizes TEXT DEFAULT '{}'")
    # seed stock defaults for products that have none in DB
    for p in products:
        for size, qty in p.get("stock", {}).items():
            cur = conn.execute("SELECT qty FROM stock WHERE product=? AND size=?", (p["id"], size))
            if cur.fetchone() is None:
                conn.execute("INSERT INTO stock(product,size,qty) VALUES(?,?,?)",
                             (p["id"], size, qty))
    cur = conn.execute("SELECT value FROM settings WHERE key='order_prefix'").fetchone()
    if cur is None:
        conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('order_prefix',?)",
                     (json.dumps(prefix),))
    conn.commit()
    conn.close()


def get_stock():
    """returns {product: {size: qty}} from DB (authoritative)."""
    conn = _conn()
    rows = conn.execute("SELECT product,size,qty FROM stock").fetchall()
    conn.close()
    out = {}
    for r in rows:
        out.setdefault(r["product"], {})[r["size"]] = r["qty"]
    return out


def set_stock(product, size, qty):
    conn = _conn()
    conn.execute("INSERT INTO stock(product,size,qty) VALUES(?,?,?) "
                 "ON CONFLICT(product,size) DO UPDATE SET qty=excluded.qty",
                 (product, size, qty))
    conn.commit()
    conn.close()


# ---- orders ----
def order_code():
    prefix = settings_get("order_prefix") or "GOAL"
    conn = _conn()
    row = conn.execute("SELECT MAX(id) m FROM orders").fetchone()
    conn.close()
    n = 1000 + ((row["m"] or 0) + 1)
    return "%s-%d" % (prefix, n)


def order_create(data):
    conn = _conn()
    code = order_code()
    conn.execute("INSERT INTO orders(code,data,status,payment,created) VALUES(?,?,?,?,?)",
                 (code, json.dumps(data, ensure_ascii=False), "pending", "pending",
                  datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    return code


def order_get(code):
    conn = _conn()
    row = conn.execute("SELECT * FROM orders WHERE code=?", (code,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["data"] = json.loads(d["data"])
    return d


def order_update(code, status=None, payment=None, data=None):
    conn = _conn()
    if status:
        conn.execute("UPDATE orders SET status=? WHERE code=?", (status, code))
    if payment:
        conn.execute("UPDATE orders SET payment=? WHERE code=?", (payment, code))
    if data is not None:
        conn.execute("UPDATE orders SET data=? WHERE code=?", (json.dumps(data, ensure_ascii=False), code))
    conn.commit()
    conn.close()


def orders_list(status=None):
    conn = _conn()
    if status:
        rows = conn.execute("SELECT * FROM orders WHERE status=? ORDER BY id DESC", (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 300").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["data"] = json.loads(d["data"])
        except Exception:
            d["data"] = {}
        out.append(d)
    return out


# ---- notify ----
def notify_add(product, size, phone, country):
    conn = _conn()
    cur = conn.execute("SELECT id FROM notify WHERE product=? AND size=? AND phone=?",
                       (product, size, phone))
    if cur.fetchone():
        conn.close()
        return False
    conn.execute("INSERT INTO notify(product,size,phone,country,created,notified) VALUES(?,?,?,?,?,0)",
                 (product, size, phone, country, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    return True


def notify_list(ready_only=False):
    conn = _conn()
    if ready_only:
        rows = conn.execute("SELECT * FROM notify WHERE notified=1 ORDER BY id DESC").fetchall()
    else:
        rows = conn.execute("SELECT * FROM notify ORDER BY id DESC LIMIT 300").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def notify_mark_ready(product, size):
    conn = _conn()
    conn.execute("UPDATE notify SET notified=1 WHERE product=? AND size=? AND notified=0",
                 (product, size))
    conn.commit()
    conn.close()


# ---- admin notification center ----
def admin_notif_add(kind, text):
    conn = _conn()
    conn.execute("INSERT INTO admin_notifications(kind,text,read,created) VALUES(?,?,0,?)",
                 (kind, text, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()


def admin_notifs(limit=60):
    conn = _conn()
    rows = conn.execute("SELECT * FROM admin_notifications ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def admin_notif_unread():
    conn = _conn()
    n = conn.execute("SELECT COUNT(*) c FROM admin_notifications WHERE read=0").fetchone()["c"]
    conn.close()
    return n or 0


def admin_notif_read_all():
    conn = _conn()
    conn.execute("UPDATE admin_notifications SET read=1 WHERE read=0")
    conn.commit()
    conn.close()


# ---- announcements / ads ----
def ads_list(place=None, active_only=False):
    conn = _conn()
    q = "SELECT * FROM ads"
    conds, params = [], []
    if place:
        conds.append("place=?"); params.append(place)
    if active_only:
        conds.append("active=1")
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY id DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def ad_add(text_ar, text_en, link, place):
    conn = _conn()
    conn.execute("INSERT INTO ads(text_ar,text_en,link,place,active,created) VALUES(?,?,?,?,1,?)",
                 (text_ar, text_en, link, place, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()


def ad_update(aid, text_ar, text_en, link, place):
    conn = _conn()
    conn.execute("UPDATE ads SET text_ar=?, text_en=?, link=?, place=? WHERE id=?",
                 (text_ar, text_en, link, place, aid))
    conn.commit()
    conn.close()


def ad_toggle(aid, active):
    conn = _conn()
    conn.execute("UPDATE ads SET active=? WHERE id=?", (1 if active else 0, aid))
    conn.commit()
    conn.close()


def ad_delete(aid):
    conn = _conn()
    conn.execute("DELETE FROM ads WHERE id=?", (aid,))
    conn.commit()
    conn.close()


# ---- per-user notifications ----
def user_notif_add(user_id, text):
    conn = _conn()
    conn.execute("INSERT INTO user_notifications(user_id,text,read,created) VALUES(?,?,0,?)",
                 (user_id, text, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()


def user_notifs(user_id, limit=60):
    conn = _conn()
    rows = conn.execute("SELECT * FROM user_notifications WHERE user_id=? ORDER BY id DESC LIMIT ?",
                        (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def user_notif_unread(user_id):
    conn = _conn()
    n = conn.execute("SELECT COUNT(*) c FROM user_notifications WHERE user_id=? AND read=0",
                     (user_id,)).fetchone()["c"]
    conn.close()
    return n or 0


def user_notif_read_all(user_id):
    conn = _conn()
    conn.execute("UPDATE user_notifications SET read=1 WHERE user_id=? AND read=0", (user_id,))
    conn.commit()
    conn.close()


# ---- special requests ----
def request_add(data):
    conn = _conn()
    ref = "REQ-" + str(1000 + (conn.execute("SELECT COUNT(*) c FROM requests").fetchone()["c"] or 0) + 1)
    conn.execute("INSERT INTO requests(data,status,created) VALUES(?,?,?)",
                 (json.dumps(data, ensure_ascii=False), "new",
                  datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    return ref


def requests_list():
    conn = _conn()
    rows = conn.execute("SELECT * FROM requests ORDER BY id DESC LIMIT 300").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["data"] = json.loads(d["data"])
        except Exception:
            d["data"] = {}
        out.append(d)
    return out


def request_status(rid, status):
    conn = _conn()
    conn.execute("UPDATE requests SET status=? WHERE id=?", (status, rid))
    conn.commit()
    conn.close()


# ---- polls & votes ----
def poll_save(data):
    conn = _conn()
    conn.execute("INSERT INTO polls(data,start,end,status,created) VALUES(?,?,?,?,?)",
                 (json.dumps(data, ensure_ascii=False), data.get("start", ""), data.get("end", ""),
                  data.get("status", "open"), datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()


def poll_update(pid, data):
    conn = _conn()
    conn.execute("UPDATE polls SET data=?, start=?, end=?, status=? WHERE id=?",
                 (json.dumps(data, ensure_ascii=False), data.get("start", ""), data.get("end", ""),
                  data.get("status", "open"), pid))
    conn.commit()
    conn.close()


def polls_list():
    conn = _conn()
    rows = conn.execute("SELECT * FROM polls ORDER BY id DESC").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["data"] = json.loads(d["data"])
        except Exception:
            d["data"] = {}
        out.append(d)
    return out


def poll_get(pid):
    for p in polls_list():
        if p["id"] == pid:
            return p
    return None


def vote_add(poll_id, option, device):
    conn = _conn()
    cur = conn.execute("SELECT id FROM votes WHERE poll=? AND device=?", (poll_id, device))
    if cur.fetchone():
        conn.close()
        return False
    conn.execute("INSERT INTO votes(poll,option,device,created) VALUES(?,?,?,?)",
                 (poll_id, option, device, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    return True


def votes_count(poll_id):
    conn = _conn()
    rows = conn.execute("SELECT option, COUNT(*) c FROM votes WHERE poll=? GROUP BY option", (poll_id,)).fetchall()
    conn.close()
    return {r["option"]: r["c"] for r in rows}


def votes_total(poll_id):
    conn = _conn()
    r = conn.execute("SELECT COUNT(*) c FROM votes WHERE poll=?", (poll_id,)).fetchone()
    conn.close()
    return r["c"] if r else 0


def voted(poll_id, device):
    conn = _conn()
    r = conn.execute("SELECT id FROM votes WHERE poll=? AND device=?", (poll_id, device)).fetchone()
    conn.close()
    return r is not None


# ---- settings (match / drop / delivery) ----
def settings_get(key):
    conn = _conn()
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    if not r:
        return None
    try:
        return json.loads(r["value"])
    except Exception:
        return r["value"]


def settings_set(key, value):
    conn = _conn()
    conn.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, json.dumps(value, ensure_ascii=False)))
    conn.commit()
    conn.close()


# ---- club themes (dynamic per-club site theme) ----
def club_theme_get(cid):
    v = settings_get("club_theme_" + cid)
    return v if isinstance(v, dict) else None


def club_theme_set(cid, theme):
    settings_set("club_theme_" + cid, theme)


# ---- admin-managed products (add / edit / remove / hide) ----
def products_overrides():
    v = settings_get("admin_products")
    return v if isinstance(v, list) else []


def save_products_overrides(items):
    settings_set("admin_products", items)


def merge_products(base):
    """Base cfg products merged with admin overrides (full-replacement dicts,
    'remove' deletes, 'is_new' appends)."""
    overrides = products_overrides()
    if not overrides:
        return list(base)
    removed = {o["id"] for o in overrides if o.get("remove")}
    edits = {o["id"]: o for o in overrides if o.get("id") and not o.get("remove") and not o.get("is_new")}
    out = []
    for p in base:
        if p["id"] in removed:
            continue
        out.append(edits.get(p["id"], p))
    for o in overrides:
        if o.get("is_new") and o.get("id") and o["id"] not in removed:
            out.append(o)
    return out


# ---- price overrides & price-drop alerts ----
def set_price(pid, price):
    conn = _conn()
    conn.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 ("price_" + pid, json.dumps(float(price))))
    conn.commit()
    conn.close()


def get_price_override(pid):
    v = settings_get("price_" + pid)
    return float(v) if v is not None else None


def alert_add(product, phone, device, price):
    conn = _conn()
    conn.execute("INSERT INTO alerts(product,phone,device,price,triggered,active,created) "
                 "VALUES(?,?,?,?,0,1,?)",
                 (product, phone, device, price,
                  datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()


def alerts_list():
    conn = _conn()
    rows = conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 300").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def alerts_for(device):
    conn = _conn()
    rows = conn.execute("SELECT * FROM alerts WHERE device=? ORDER BY id DESC", (device,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def alert_cancel(aid, device):
    conn = _conn()
    conn.execute("UPDATE alerts SET active=0 WHERE id=? AND device=?", (aid, device))
    conn.commit()
    conn.close()


def alert_trigger(product):
    conn = _conn()
    cur = conn.execute("UPDATE alerts SET triggered=1 WHERE product=? AND active=1 AND triggered=0",
                       (product,))
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n


# ---- goal points (server ledger, keyed by device) ----
def points_get(device):
    conn = _conn()
    r = conn.execute("SELECT total FROM points WHERE device=?", (device,)).fetchone()
    conn.close()
    return r["total"] if r else 0


def points_add(device, delta, label=""):
    conn = _conn()
    conn.execute("INSERT INTO points(device,total) VALUES(?,?) "
                 "ON CONFLICT(device) DO UPDATE SET total=total+excluded.total",
                 (device, delta))
    conn.execute("INSERT INTO pts_log(device,delta,label,created) VALUES(?,?,?,?)",
                 (device, delta, label, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    return points_get(device)


# ---- penalty challenge (one attempt per order) ----
def penalty_play(order_code, device, shot):
    conn = _conn()
    r = conn.execute("SELECT outcome FROM penalties WHERE order_code=?", (order_code,)).fetchone()
    if r:
        conn.close()
        return {"fresh": False, "goal": r["outcome"] == "goal", "shot": None}
    o = conn.execute("SELECT id FROM orders WHERE code=?", (order_code,)).fetchone()
    if not o:
        conn.close()
        return {"fresh": False, "error": "notfound"}
    zones = ["tl", "tc", "tr", "bl", "br"]
    keeper = zones[sum(ord(ch) for ch in order_code) % 5]
    goal = shot != keeper
    conn.execute("INSERT INTO penalties(order_code,device,outcome,created) VALUES(?,?,?,?)",
                 (order_code, device, "goal" if goal else "saved",
                  datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    if goal:
        points_add(device, 10, "penalty")
    return {"fresh": True, "goal": goal, "keeper": keeper, "shot": shot}


def penalty_status(order_code):
    conn = _conn()
    r = conn.execute("SELECT outcome FROM penalties WHERE order_code=?", (order_code,)).fetchone()
    conn.close()
    if not r:
        return {"done": False, "goal": None}
    return {"done": True, "goal": r["outcome"] == "goal"}


# ---- professional reviews ----
def review_add(product, device, name, design, fabric, quality, size_rating, fit, text, photo, verified):
    conn = _conn()
    conn.execute(
        "INSERT INTO reviews(product,device,name,design,fabric,quality,size_rating,fit,text,photo,"
        "verified,status,reported,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (product, device, name, design, fabric, quality, size_rating, fit, text, photo,
         1 if verified else 0, "approved" if not photo else "pending", 0,
         datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()


def reviews_list(product=None, status=None):
    conn = _conn()
    q = "SELECT * FROM reviews"
    args = []
    if product and status:
        q += " WHERE product=? AND status=?"
        args = [product, status]
    elif product:
        q += " WHERE product=?"
        args = [product]
    elif status:
        q += " WHERE status=?"
        args = [status]
    q += " ORDER BY id DESC LIMIT 300"
    rows = conn.execute(q, args).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def review_set_status(rid, status):
    conn = _conn()
    conn.execute("UPDATE reviews SET status=? WHERE id=?", (status, rid))
    conn.commit()
    conn.close()


def review_report(rid):
    conn = _conn()
    conn.execute("UPDATE reviews SET reported=1 WHERE id=?", (rid,))
    conn.commit()
    conn.close()


def review_verified(product, device):
    conn = _conn()
    rows = conn.execute("SELECT data FROM orders").fetchall()
    for r in rows:
        try:
            d = json.loads(r["data"])
        except Exception:
            continue
        if d.get("device") != device:
            continue
        if any((i.get("id") == product) for i in d.get("items", [])):
            conn.close()
            return True
    conn.close()
    return False


# ---- users & auth ----
def user_create(phone, name="", role="customer", lang="ar", email=""):
    conn = _conn()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        cur = conn.execute(
            "INSERT INTO users(phone,email,name,role,status,lang,theme,font,created,last_login) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (phone, email, name, role, "active", lang, "dark", "b", now, now))
        conn.commit()
        uid = cur.lastrowid
    except Exception:
        conn.rollback()
        r = conn.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()
        uid = r["id"] if r else None
    conn.close()
    return uid


def user_by_phone(phone):
    conn = _conn()
    r = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    return dict(r) if r else None


def user_by_id(uid):
    conn = _conn()
    r = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return dict(r) if r else None


def user_update(uid, **kw):
    allowed = ("name", "email", "role", "status", "lang", "theme", "font", "area", "address", "password", "favs", "sizes", "phone")
    fields = {k: v for k, v in kw.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join("%s=?" % k for k in fields)
    vals = list(fields.values()) + [uid]
    conn = _conn()
    conn.execute("UPDATE users SET %s WHERE id=?" % sets, vals)
    conn.commit()
    conn.close()


def user_favs(uid):
    u = user_by_id(uid)
    if not u:
        return []
    try:
        v = json.loads(u.get("favs") or "[]")
        return v if isinstance(v, list) else []
    except Exception:
        return []


def user_favs_set(uid, favs):
    user_update(uid, favs=json.dumps([f for f in favs if f], ensure_ascii=False))


def user_sizes(uid):
    u = user_by_id(uid)
    if not u:
        return {}
    try:
        v = json.loads(u.get("sizes") or "{}")
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def user_size_set(uid, pid, size):
    sizes = user_sizes(uid)
    sizes[pid] = size
    user_update(uid, sizes=json.dumps(sizes, ensure_ascii=False))


def users_list():
    conn = _conn()
    rows = conn.execute("SELECT * FROM users ORDER BY id ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def user_touch(uid):
    conn = _conn()
    conn.execute("UPDATE users SET last_login=? WHERE id=?",
                 (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), uid))
    conn.commit()
    conn.close()


def orders_by_user(uid):
    out = []
    for o in orders_list():
        if o["data"].get("user_id") == uid:
            out.append(o)
    return out


def otp_new(phone):
    conn = _conn()
    conn.execute("DELETE FROM otps WHERE phone=? AND used=0", (phone,))
    code = str(100000 + int(__import__("random").random() * 900000))
    if len(code) != 6:
        code = code.zfill(6)[-6:]
    exp = (datetime.datetime.now() + datetime.timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M")
    conn.execute("INSERT INTO otps(phone,code,expires,used,created) VALUES(?,?,?,0,?)",
                 (phone, code, exp, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    return code


def otp_verify(phone, code):
    conn = _conn()
    r = conn.execute(
        "SELECT id, expires FROM otps WHERE phone=? AND code=? AND used=0 ORDER BY id DESC LIMIT 1",
        (phone, str(code))).fetchone()
    if not r:
        conn.close()
        return False
    try:
        exp = datetime.datetime.strptime(r["expires"], "%Y-%m-%d %H:%M")
    except Exception:
        exp = datetime.datetime.now() - datetime.timedelta(minutes=1)
    if exp < datetime.datetime.now():
        conn.close()
        return False
    conn.execute("UPDATE otps SET used=1 WHERE id=?", (r["id"],))
    conn.commit()
    conn.close()
    return True


def otp_state(phone, code):
    """Return (state, otp_id): ok / expired / wrong / used."""
    conn = _conn()
    r = conn.execute(
        "SELECT id, expires, used FROM otps WHERE phone=? AND code=? ORDER BY id DESC LIMIT 1",
        (phone, str(code))).fetchone()
    conn.close()
    if not r:
        return ("wrong", None)
    try:
        exp = datetime.datetime.strptime(r["expires"], "%Y-%m-%d %H:%M")
    except Exception:
        exp = datetime.datetime.now() - datetime.timedelta(minutes=1)
    if r["used"]:
        return ("used", None)
    if exp < datetime.datetime.now():
        return ("expired", None)
    return ("ok", r["id"])


def otp_consume(oid):
    conn = _conn()
    conn.execute("UPDATE otps SET used=1 WHERE id=?", (oid,))
    conn.commit()
    conn.close()
