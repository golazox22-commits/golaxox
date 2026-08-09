# -*- coding: utf-8 -*-
"""
golazox — متجر تيشيرتات ومعدات رياضية | Sports store (T-shirts + equipment)
Ordering is done via WhatsApp cart checkout.
"""
import os
from flask import Flask, request, redirect

app = Flask(__name__)

# ============================== CONFIG ==============================
STORE_NAME = "golazox"
# WhatsApp number in international format WITHOUT the leading + (Bahrain: 973...)
WHATSAPP = os.environ.get("WHATSAPP", "97338818226")
CURRENCY_AR = "د.ب"
CURRENCY_EN = "BHD"
TSHIRT_PRICE = 7.0
EQUIP_PRICE = 6.0

# ============================== PRODUCTS ==============================
# Each product: id, emoji (placeholder until real photos), tile gradient, names
TSHIRTS = [
    {"id": "t1", "emoji": "👕", "g1": "#1E293B", "g2": "#334155", "name_ar": "تيشيرت أسود GOLAZOX", "name_en": "Black GOLAZOX Tee"},
    {"id": "t2", "emoji": "👕", "g1": "#F1F5F9", "g2": "#CBD5E1", "name_ar": "تيشيرت أبيض GOLAZOX", "name_en": "White GOLAZOX Tee"},
    {"id": "t3", "emoji": "👕", "g1": "#1D4ED8", "g2": "#3B82F6", "name_ar": "تيشيرت أزرق رياضي", "name_en": "Blue Sport Tee"},
    {"id": "t4", "emoji": "👕", "g1": "#475569", "g2": "#94A3B8", "name_ar": "تيشيرت رمادي رياضي", "name_en": "Grey Sport Tee"},
]

EQUIPMENT = [
    {"id": "e1", "emoji": "🏋️", "g1": "#0F172A", "g2": "#334155", "name_ar": "دمبل مطاطي", "name_en": "Rubber Dumbbell"},
    {"id": "e2", "emoji": "🪢", "g1": "#0F766E", "g2": "#14B8A6", "name_ar": "حبل قفز", "name_en": "Jump Rope"},
    {"id": "e3", "emoji": "➿", "g1": "#B45309", "g2": "#F59E0B", "name_ar": "حزام مقاومة", "name_en": "Resistance Band"},
    {"id": "e4", "emoji": "🥤", "g1": "#1D4ED8", "g2": "#60A5FA", "name_ar": "زجاجة ماء رياضية", "name_en": "Sports Water Bottle"},
    {"id": "e5", "emoji": "🎒", "g1": "#7C3AED", "g2": "#A78BFA", "name_ar": "حقيبة جيم", "name_en": "Gym Bag"},
    {"id": "e6", "emoji": "🧤", "g1": "#B91C1C", "g2": "#EF4444", "name_ar": "كفوف رفع أوزان", "name_en": "Lifting Grips"},
]

ALL = TSHIRTS + EQUIPMENT
PRICE = {p["id"]: (TSHIRT_PRICE if p["id"].startswith("t") else EQUIP_PRICE) for p in ALL}

# ============================== TRANSLATIONS ==============================
L = {
    "ar": {
        "nav_home": "الرئيسية",
        "nav_tshirts": "تيشيرتات",
        "nav_equipment": "المعدات",
        "cart": "السلة",
        "lang_name": "English",
        "badge": "⚡ متجر golazox الرسمي",
        "hero_title": "جهّز نفسك للملعبة",
        "hero_title_b": "بأسلوب GOLAZOX",
        "hero_sub": "تيشيرتات رياضية ومعدات تدريب بأسعار موحّدة وثابتة — الطلب من الواتساب بضغطة زر.",
        "hero_cta_shop": "تسوّق الآن",
        "hero_cta_wa": "تواصل واتساب",
        "t_price": "7 د.ب",
        "e_price": "6 د.ب",
        "add": "أضف للسلة",
        "added": "✓ تمت الإضافة",
        "cat_tshirts": "تيشيرتات الرياضة",
        "cat_tshirts_sub": "سعر موحّد 7 د.ب للتشيكة الواحدة",
        "cat_equipment": "المعدات الرياضية",
        "cat_equipment_sub": "سعر موحّد 6 د.ب للقطعة",
        "cart_title": "سلة الطلب",
        "cart_empty": "سلتك فارغة — أضف منتجاتك.",
        "cart_item": "عنصر",
        "cart_total": "الإجمالي",
        "cart_checkout": "إرسال الطلب عبر واتساب",
        "cart_clear": "إفراغ السلة",
        "cart_close": "إغلاق",
        "currency": "د.ب",
        "order_intro": "سلام عليكم golazox 👋",
        "order_items": "أبغى أطلب:",
        "order_total": "الإجمالي",
        "whatsapp": "واتساب",
        "footer_contact": "تواصل معنا",
        "footer_note": "© 2026 golazox — جميع الحقوق محفوظة",
    },
    "en": {
        "nav_home": "Home",
        "nav_tshirts": "T-shirts",
        "nav_equipment": "Equipment",
        "cart": "Cart",
        "lang_name": "عربي",
        "badge": "⚡ Official golazox store",
        "hero_title": "Gear up for the game",
        "hero_title_b": "the GOLAZOX way",
        "hero_sub": "Sport t-shirts and training equipment at flat, fixed prices — order on WhatsApp with one tap.",
        "hero_cta_shop": "Shop now",
        "hero_cta_wa": "Chat on WhatsApp",
        "t_price": "7 BHD",
        "e_price": "6 BHD",
        "add": "Add to cart",
        "added": "✓ Added",
        "cat_tshirts": "Sport T-shirts",
        "cat_tshirts_sub": "Flat price 7 BHD each",
        "cat_equipment": "Sport Equipment",
        "cat_equipment_sub": "Flat price 6 BHD each",
        "cart_title": "Your cart",
        "cart_empty": "Your cart is empty — add some products.",
        "cart_item": "item",
        "cart_total": "Total",
        "cart_checkout": "Send order via WhatsApp",
        "cart_clear": "Clear cart",
        "cart_close": "Close",
        "currency": "BHD",
        "order_intro": "Hello golazox 👋",
        "order_items": "I would like to order:",
        "order_total": "Total",
        "whatsapp": "WhatsApp",
        "footer_contact": "Contact us",
        "footer_note": "© 2026 golazox — All rights reserved",
    },
}


def lang():
    return request.cookies.get("lang") or request.args.get("lang") or "ar"


def t(k):
    d = L[lang()]
    return d.get(k, L["ar"].get(k, k))


def fmt(x):
    return "%.2f" % x


# ============================== PAGE ==============================
def page():
    l = lang()
    en = l == "en"
    ar = not en
    d = L[l]
    cur = CURRENCY_EN if en else CURRENCY_AR

    def price_str(pid):
        return ("%.1f %s" % (PRICE[pid], cur)) if PRICE[pid] == int(PRICE[pid]) else ("%.2f %s" % (PRICE[pid], cur))

    def prod_card(p):
        name = p["name_en"] if en else p["name_ar"]
        return (
            '<div class="prod" data-id="%s">'
            '<div class="ptile" style="background:linear-gradient(135deg,%s,%s);">'
            '<span class="pemoji">%s</span>'
            '<span class="pprice">%s</span>'
            "</div>"
            '<div class="pbody"><h3>%s</h3>'
            '<button class="padd" onclick="addToCart(\'%s\',this)">%s</button></div>'
            "</div>"
        ) % (p["id"], p["g1"], p["g2"], p["emoji"], price_str(p["id"]), name, p["id"], d["add"])

    tshirts_html = "".join(prod_card(p) for p in TSHIRTS)
    equip_html = "".join(prod_card(p) for p in EQUIPMENT)

    prods_json = json_dumps([
        {"id": p["id"], "name": p["name_en"] if en else p["name_ar"],
         "price": PRICE[p["id"]], "currency": cur, "emoji": p["emoji"]}
        for p in ALL
    ])

    dir_attr = "ltr" if en else "rtl"
    wa = "https://wa.me/" + WHATSAPP

    return """<!DOCTYPE html>
<html lang="__LANG__" dir="__DIR__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>golazox — __T_HERO__</title>
<meta name="description" content="__T_SUB__">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Poppins:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: '__FONT__', 'Segoe UI', Tahoma, sans-serif; background: #F4F7FB; color: #0F172A; }
a { text-decoration: none; color: inherit; }
.header { position: sticky; top: 0; z-index: 90; background: #0F172A; color: #FFF; display: flex; align-items: center; justify-content: space-between; padding: 14px 24px; gap: 12px; flex-wrap: wrap; }
.logo { font-size: 24px; font-weight: 900; letter-spacing: .5px; display: flex; align-items: center; gap: 6px; }
.logo .dot { color: #B4F542; }
.nav { display: flex; gap: 4px; flex-wrap: wrap; }
.nav a { padding: 8px 14px; border-radius: 999px; font-size: 14px; font-weight: 700; color: #CBD5E1; }
.nav a:hover { background: #1E293B; color: #FFF; }
.right { display: flex; align-items: center; gap: 10px; }
.langbtn { background: #1E293B; border: 1px solid #334155; color: #FFF; font-family: inherit; font-size: 13px; font-weight: 700; padding: 7px 14px; border-radius: 999px; cursor: pointer; }
.langbtn:hover { border-color: #B4F542; color: #B4F542; }
.cartbtn { position: relative; background: #B4F542; color: #0F172A; font-family: inherit; font-weight: 800; font-size: 14px; padding: 9px 16px; border-radius: 999px; cursor: pointer; border: none; display: flex; align-items: center; gap: 6px; }
.cartbtn .cbadge { position: absolute; top: -7px; inset-inline-end: -7px; background: #EF4444; color: #FFF; font-size: 11px; font-weight: 800; min-width: 20px; height: 20px; border-radius: 999px; display: flex; align-items: center; justify-content: center; padding: 0 4px; display: none; }
.container { max-width: 1080px; margin: 0 auto; padding: 26px 18px 60px; }
.hero { display: flex; align-items: center; gap: 26px; background: linear-gradient(120deg, #0F172A 0%, #1E293B 100%); color: #FFF; border-radius: 26px; padding: 40px 34px; margin-bottom: 34px; flex-wrap: wrap; }
.hero-tx { flex: 1.2; min-width: 260px; }
.hero .badge { display: inline-block; background: rgba(180,245,66,.15); color: #B4F542; border: 1px solid rgba(180,245,66,.35); font-size: 13px; font-weight: 800; padding: 7px 14px; border-radius: 999px; margin-bottom: 14px; }
.hero h1 { font-size: 38px; line-height: 1.15; font-weight: 900; }
.hero h1 .hl { color: #B4F542; }
.hero p { margin-top: 10px; opacity: .88; font-size: 15.5px; line-height: 1.8; max-width: 520px; }
.hero-btns { margin-top: 22px; display: flex; gap: 12px; flex-wrap: wrap; }
.btn { display: inline-flex; align-items: center; gap: 8px; font-weight: 800; font-size: 15px; padding: 13px 26px; border-radius: 999px; border: none; cursor: pointer; font-family: inherit; }
.btn.pri { background: #B4F542; color: #0F172A; box-shadow: 0 10px 24px rgba(180,245,66,.25); }
.btn.pri:hover { transform: translateY(-2px); }
.btn.wa { background: #25D366; color: #FFF; box-shadow: 0 10px 24px rgba(37,211,102,.25); }
.btn.wa:hover { transform: translateY(-2px); }
.hero-art { flex: 1; min-width: 220px; display: flex; align-items: center; justify-content: center; font-size: 110px; filter: drop-shadow(0 20px 40px rgba(180,245,66,.25)); }
.sec { margin-bottom: 34px; }
.sec-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
.sec-head h2 { font-size: 24px; font-weight: 900; color: #0F172A; }
.sec-head .sec-sub { color: #64748B; font-size: 14px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(215px, 1fr)); gap: 18px; }
.prod { background: #FFF; border: 1px solid #E2E8F0; border-radius: 18px; overflow: hidden; box-shadow: 0 4px 16px rgba(15,23,42,.05); transition: transform .14s ease, box-shadow .14s ease; }
.prod:hover { transform: translateY(-4px); box-shadow: 0 14px 30px rgba(15,23,42,.12); }
.ptile { position: relative; height: 170px; display: flex; align-items: center; justify-content: center; }
.pemoji { font-size: 64px; filter: drop-shadow(0 10px 18px rgba(0,0,0,.25)); }
.pprice { position: absolute; top: 12px; inset-inline-end: 12px; background: rgba(255,255,255,.92); color: #0F172A; font-weight: 800; font-size: 13px; padding: 6px 12px; border-radius: 999px; }
.pbody { padding: 16px; }
.pbody h3 { font-size: 15px; font-weight: 800; color: #0F172A; min-height: 40px; }
.padd { width: 100%; margin-top: 12px; background: #0F172A; color: #FFF; border: none; font-family: inherit; font-weight: 800; font-size: 14px; padding: 11px; border-radius: 12px; cursor: pointer; }
.padd:hover { background: #B4F542; color: #0F172A; }
.padd.done { background: #16A34A; color: #FFF; }
.cart-overlay { position: fixed; inset: 0; background: rgba(15,23,42,.5); z-index: 200; display: none; }
.cart-overlay.open { display: block; }
.cart-drawer { position: fixed; top: 0; bottom: 0; inset-inline-end: 0; width: 390px; max-width: 92vw; background: #FFF; z-index: 201; display: none; flex-direction: column; box-shadow: -10px 0 40px rgba(0,0,0,.2); }
html[dir="ltr"] .cart-drawer { box-shadow: 10px 0 40px rgba(0,0,0,.2); }
.cart-drawer.open { display: flex; }
.cart-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 18px; border-bottom: 1px solid #E2E8F0; }
.cart-head b { font-size: 17px; }
.cart-x { border: none; background: #F1F5F9; width: 32px; height: 32px; border-radius: 50%; font-size: 15px; cursor: pointer; }
.cart-body { flex: 1; overflow-y: auto; padding: 14px 18px; }
.cart-empty { text-align: center; color: #64748B; padding: 40px 10px; font-size: 15px; }
.ci { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px dashed #E2E8F0; }
.ci .ci-emoji { font-size: 34px; }
.ci .ci-tx { flex: 1; min-width: 0; }
.ci .ci-tx b { display: block; font-size: 14px; }
.ci .ci-tx span { font-size: 13px; color: #64748B; }
.qty { display: flex; align-items: center; gap: 8px; }
.qty button { width: 28px; height: 28px; border-radius: 50%; border: 1px solid #CBD5E1; background: #FFF; font-size: 16px; font-weight: 800; cursor: pointer; }
.qty button:hover { border-color: #0F172A; }
.qty .qn { min-width: 20px; text-align: center; font-weight: 800; }
.cart-foot { padding: 16px 18px; border-top: 1px solid #E2E8F0; background: #F8FAFC; }
.cart-total { display: flex; justify-content: space-between; font-size: 16px; font-weight: 800; margin-bottom: 12px; }
.wa-checkout { width: 100%; background: #25D366; color: #FFF; border: none; border-radius: 12px; font-family: inherit; font-weight: 800; font-size: 15px; padding: 14px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; }
.wa-checkout:hover { transform: translateY(-1px); }
.cart-clear { text-align: center; margin-top: 10px; background: none; border: none; color: #EF4444; font-family: inherit; font-size: 13px; cursor: pointer; font-weight: 700; }
.footer { background: #0F172A; color: #94A3B8; text-align: center; padding: 34px 22px; font-size: 14px; }
.footer .f-logo { font-size: 22px; font-weight: 900; color: #FFF; }
.footer .f-logo .dot { color: #B4F542; }
.footer a { color: #B4F542; font-weight: 700; }
.footer .f-note { margin-top: 12px; }
@media (max-width: 560px) {
  .hero h1 { font-size: 28px; }
  .hero-art { font-size: 80px; }
  .grid { grid-template-columns: repeat(2, 1fr); gap: 12px; }
  .ptile { height: 130px; }
  .pemoji { font-size: 48px; }
}
</style>
</head>
<body>
<div class="header">
  <div class="logo">golazox<span class="dot">.</span></div>
  <div class="nav">
    <a href="#top">__T_HOME__</a>
    <a href="#tshirts">__T_TEE__</a>
    <a href="#equip">__T_EQ__</a>
  </div>
  <div class="right">
    <button class="langbtn" onclick="setLang('__LANG_OTHER__')">__T_LANG_NAME__</button>
    <button class="cartbtn" onclick="openCart()">🛒 <span>__T_CART__</span><span class="cbadge" id="cbadge">0</span></button>
  </div>
</div>

<div class="container" id="top">
  <div class="hero">
    <div class="hero-tx">
      <span class="badge">__T_BADGE__</span>
      <h1>__T_HERO__ <span class="hl">__T_HERO_B__</span></h1>
      <p>__T_SUB__</p>
      <div class="hero-btns">
        <a class="btn pri" href="#tshirts">🛍️ __T_SHOP__</a>
        <a class="btn wa" target="_blank" rel="noopener" href="__WA__">💬 __T_WA__</a>
      </div>
    </div>
    <div class="hero-art">⚡</div>
  </div>

  <div class="sec" id="tshirts">
    <div class="sec-head">
      <h2>__T_CAT_TEE__</h2>
      <span class="sec-sub">__T_CAT_TEE_SUB__</span>
    </div>
    <div class="grid">__TSHIRTS__</div>
  </div>

  <div class="sec" id="equip">
    <div class="sec-head">
      <h2>__T_CAT_EQ__</h2>
      <span class="sec-sub">__T_CAT_EQ_SUB__</span>
    </div>
    <div class="grid">__EQUIP__</div>
  </div>
</div>

<div class="footer">
  <div class="f-logo">golazox<span class="dot">.</span></div>
  <p style="margin-top:6px;">💬 <a target="_blank" rel="noopener" href="__WA__">__T_WA_CONTACT__</a> · +973 3881 8226</p>
  <p class="f-note">__T_FOOTER__</p>
</div>

<div class="cart-overlay" id="co" onclick="closeCart()"></div>
<div class="cart-drawer" id="cd">
  <div class="cart-head"><b>🛒 __T_CART__</b><button class="cart-x" onclick="closeCart()">✕</button></div>
  <div class="cart-body" id="cb"></div>
  <div class="cart-foot" id="cf">
    <div class="cart-total"><span>__T_TOTAL__</span><span id="ctotal">0.00 __CUR__</span></div>
    <button class="wa-checkout" onclick="checkout()">💬 __T_CHECKOUT__</button>
    <button class="cart-clear" onclick="clearCart()">🗑 __T_CLEAR__</button>
  </div>
</div>

<script>
var PRODUCTS = __PRODS__;
var T = __TR__;
function t(k) { return T[k] || k; }
var CART = JSON.parse(localStorage.getItem('golazox_cart') || '[]');
function find(id) { for (var i = 0; i < PRODUCTS.length; i++) if (PRODUCTS[i].id === id) return PRODUCTS[i]; return null; }
function count() { var n = 0; CART.forEach(function(c) { n += c.qty; }); return n; }
function save() { localStorage.setItem('golazox_cart', JSON.stringify(CART)); render(); }
function addToCart(id, btn) {
  var f = null;
  CART.forEach(function(c) { if (c.id === id) f = c; });
  if (f) f.qty++; else CART.push({ id: id, qty: 1 });
  save();
  if (btn) { btn.textContent = t('added'); btn.classList.add('done'); setTimeout(function() { btn.textContent = t('add'); btn.classList.remove('done'); }, 1200); }
}
function changeQty(id, d) {
  for (var i = 0; i < CART.length; i++) if (CART[i].id === id) {
    CART[i].qty += d;
    if (CART[i].qty <= 0) CART.splice(i, 1);
    break;
  }
  save();
}
function clearCart() { CART = []; save(); }
function total() { var s = 0; CART.forEach(function(c) { var p = find(c.id); if (p) s += p.price * c.qty; }); return s; }
function render() {
  var b = document.getElementById('cbadge');
  var n = count();
  b.textContent = n; b.style.display = n ? 'flex' : 'none';
  var box = document.getElementById('cb');
  if (!CART.length) {
    box.innerHTML = '<div class="cart-empty">🛒<br>' + t('empty') + '</div>';
    document.getElementById('ctotal').textContent = '0.00 ' + t('cur');
    return;
  }
  var html = '';
  CART.forEach(function(c) {
    var p = find(c.id);
    if (!p) return;
    html += '<div class="ci"><div class="ci-emoji">' + p.emoji + '</div>' +
      '<div class="ci-tx"><b>' + p.name + '</b><span>' + p.price.toFixed(p.price % 1 === 0 ? 1 : 2) + ' ' + t('cur') + '</span></div>' +
      '<div class="qty"><button onclick="changeQty(\'' + p.id + '\',-1)">−</button><span class="qn">' + c.qty + '</span><button onclick="changeQty(\'' + p.id + '\',1)">+</button></div></div>';
  });
  box.innerHTML = html;
  var tot = total();
  document.getElementById('ctotal').textContent = tot.toFixed(tot % 1 === 0 ? 1 : 2) + ' ' + t('cur');
}
function openCart() { document.getElementById('cd').classList.add('open'); document.getElementById('co').classList.add('open'); }
function closeCart() { document.getElementById('cd').classList.remove('open'); document.getElementById('co').classList.remove('open'); }
function pfmt(v) { return v.toFixed(v % 1 === 0 ? 1 : 2); }
function checkout() {
  if (!CART.length) { alert(t('empty')); return; }
  var lines = [t('intro'), '', t('items')];
  var i = 0;
  CART.forEach(function(c) {
    var p = find(c.id);
    if (!p) return;
    i++;
    var sub = p.price * c.qty;
    lines.push(i + ') ' + p.name + ' × ' + c.qty + ' = ' + pfmt(sub) + ' ' + t('cur'));
  });
  lines.push('', t('total') + ': ' + pfmt(total()) + ' ' + t('cur'));
  var msg = lines.join('\\n');
  window.open('https://wa.me/' + __WA__ + '?text=' + encodeURIComponent(msg), '_blank');
}
function setLang(l) { document.cookie = 'lang=' + l + ';path=/;max-age=31536000;SameSite=Lax'; location.reload(); }
render();
</script>
</body>
</html>
""".replace("__LANG__", "en" if en else "ar") \
    .replace("__DIR__", dir_attr) \
    .replace("__FONT__", "Poppins" if en else "Cairo") \
    .replace("__LANG_OTHER__", "ar" if en else "en") \
    .replace("__T_LANG_NAME__", d["lang_name"]) \
    .replace("__WA__", wa) \
    .replace("__CUR__", cur) \
    .replace("__T_HOME__", d["nav_home"]) \
    .replace("__T_TEE__", d["nav_tshirts"]) \
    .replace("__T_EQ__", d["nav_equipment"]) \
    .replace("__T_CART__", d["cart"]) \
    .replace("__T_BADGE__", d["badge"]) \
    .replace("__T_HERO__", d["hero_title"]) \
    .replace("__T_HERO_B__", d["hero_title_b"]) \
    .replace("__T_SUB__", d["hero_sub"]) \
    .replace("__T_SHOP__", d["hero_cta_shop"]) \
    .replace("__T_WA__", d["hero_cta_wa"]) \
    .replace("__T_CAT_TEE__", d["cat_tshirts"]) \
    .replace("__T_CAT_TEE_SUB__", d["cat_tshirts_sub"]) \
    .replace("__T_CAT_EQ__", d["cat_equipment"]) \
    .replace("__T_CAT_EQ_SUB__", d["cat_equipment_sub"]) \
    .replace("__T_TOTAL__", d["cart_total"]) \
    .replace("__T_CHECKOUT__", d["cart_checkout"]) \
    .replace("__T_CLEAR__", d["cart_clear"]) \
    .replace("__T_WA_CONTACT__", d["whatsapp"]) \
    .replace("__T_FOOTER__", d["footer_note"]) \
    .replace("__TSHIRTS__", tshirts_html) \
    .replace("__EQUIP__", equip_html) \
    .replace("__PRODS__", prods_json) \
    .replace("__TR__", json_dumps(d))


def json_dumps(o):
    import json
    return json.dumps(o, ensure_ascii=False)


@app.route("/")
def index():
    return page()


@app.route("/lang/<l>")
def setlang(l):
    r = redirect("/")
    r.set_cookie("lang", l, max_age=31536000)
    return r


@app.route("/health")
def health():
    return "ok"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
