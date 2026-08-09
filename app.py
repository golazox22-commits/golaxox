# -*- coding: utf-8 -*-
"""
golazox — Premium Football Club Jersey Store
T-shirts (Club Jerseys) + Mugs. Ordering via WhatsApp only.
Full AR/EN language switch, dark premium design, product gallery, size guide.
"""
import os
import json
from flask import Flask, request, redirect, Response, send_file

app = Flask(__name__)

# ============================== CONFIG ==============================
WHATSAPP = os.environ.get("WHATSAPP", "97338818226")
PRICE_JERSEY = 7.0
PRICE_MUG = 6.0
STATIC_IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img")

# ============================== SIZE CHART ==============================
# Editable per product: add "sizes": {...} to a product to override these.
SIZE_ORDER = ["S", "M", "L", "XL", "2XL", "3XL"]
SIZE_CHART = {
    "S":   {"chest": 50, "length": 68, "height": "160–168", "weight": "50–60"},
    "M":   {"chest": 52, "length": 70, "height": "165–173", "weight": "58–68"},
    "L":   {"chest": 54, "length": 72, "height": "170–178", "weight": "65–75"},
    "XL":  {"chest": 56, "length": 74, "height": "175–183", "weight": "72–82"},
    "2XL": {"chest": 58, "length": 76, "height": "180–188", "weight": "80–90"},
    "3XL": {"chest": 60, "length": 78, "height": "185–193", "weight": "88–100"},
}

# ============================== PRODUCTS ==============================
# imgs = base names of photos placed in static/img (e.g. "j1_1" -> j1_1.jpg/png/webp).
# If the file does not exist yet, a colored placeholder is generated automatically.
JERSEYS = [
    {"id": "j1", "kind": "jersey", "club_ar": "ريال مدريد", "club_en": "Real Madrid",
     "name_ar": "تيشيرت ريال مدريد", "name_en": "Real Madrid Jersey",
     "colors": ["#F8F9FA", "#C9A24B"], "emoji": "👕", "imgs": ["j1_1", "j1_2"]},
    {"id": "j2", "kind": "jersey", "club_ar": "برشلونة", "club_en": "Barcelona",
     "name_ar": "تيشيرت برشلونة", "name_en": "Barcelona Jersey",
     "colors": ["#002D72", "#A50044"], "emoji": "👕", "imgs": ["j2_1", "j2_2"]},
    {"id": "j3", "kind": "jersey", "club_ar": "ليفربول", "club_en": "Liverpool",
     "name_ar": "تيشيرت ليفربول", "name_en": "Liverpool Jersey",
     "colors": ["#C8102E", "#7A0C20"], "emoji": "👕", "imgs": ["j3_1", "j3_2"]},
    {"id": "j4", "kind": "jersey", "club_ar": "مانشستر سيتي", "club_en": "Manchester City",
     "name_ar": "تيشيرت مانشستر سيتي", "name_en": "Manchester City Jersey",
     "colors": ["#6CABDD", "#1C2C5B"], "emoji": "👕", "imgs": ["j4_1", "j4_2"]},
    {"id": "j5", "kind": "jersey", "club_ar": "الهلال", "club_en": "Al-Hilal",
     "name_ar": "تيشيرت الهلال", "name_en": "Al-Hilal Jersey",
     "colors": ["#1E4FA3", "#0C2D6E"], "emoji": "👕", "imgs": ["j5_1", "j5_2"]},
    {"id": "j6", "kind": "jersey", "club_ar": "النصر", "club_en": "Al-Nassr",
     "name_ar": "تيشيرت النصر", "name_en": "Al-Nassr Jersey",
     "colors": ["#F7D033", "#1B1B1B"], "emoji": "👕", "imgs": ["j6_1", "j6_2"]},
]

MUGS = [
    {"id": "m1", "kind": "mug", "name_ar": "مق كأس العالم", "name_en": "World Cup Mug",
     "colors": ["#1B1B1B", "#C9A24B"], "emoji": "☕", "imgs": ["m1_1"]},
    {"id": "m2", "kind": "mug", "name_ar": "مق الكرة", "name_en": "Football Mug",
     "colors": ["#C8102E", "#7A0C20"], "emoji": "☕", "imgs": ["m2_1"]},
    {"id": "m3", "kind": "mug", "name_ar": "مق ريال مدريد", "name_en": "Real Madrid Mug",
     "colors": ["#F8F9FA", "#C9A24B"], "emoji": "☕", "imgs": ["m3_1"]},
    {"id": "m4", "kind": "mug", "name_ar": "مق الهلال", "name_en": "Al-Hilal Mug",
     "colors": ["#1E4FA3", "#0C2D6E"], "emoji": "☕", "imgs": ["m4_1"]},
]

ALL = {p["id"]: p for p in (JERSEYS + MUGS)}


def item_name(p, en):
    return p.get("name_en" if en else "name_ar", "")


def club_name(p, en):
    return p.get("club_en" if en else "club_ar", "")


# ============================== TRANSLATIONS ==============================
L = {
    "ar": {
        "nav_home": "الرئيسية", "nav_jerseys": "تيشرتات الأندية", "nav_mugs": "المقّات",
        "nav_sizes": "دليل المقاسات", "nav_order": "طريقة الطلب", "nav_contact": "تواصل معنا",
        "lang_name": "English",
        "badge": "متجر تيشرتات الأندية والمقّات الرياضية",
        "hero_t1": "تشكيلة تيشرتات الأندية",
        "hero_t2": "والمقّات الرياضية",
        "hero_sub": "تشكيلة فخمة ومتجددة من تيشرتات الأندية والمقّات الرياضية بجودة عالية وسعر ثابت — اطلب الآن عبر واتساب.",
        "hero_cta_j": "تسوّق التيشرتات", "hero_cta_m": "شوف المقّات",
        "sec_jerseys": "تيشرتات الأندية", "sec_jerseys_sub": "سعر موحد 7 د.ب — المقاسات الآسيوية S إلى 3XL",
        "sec_mugs": "المقّات", "sec_mugs_sub": "سعر موحد 6 د.ب",
        "cat_jersey": "تيشيرت النادي", "cat_mug": "مق رياضي",
        "view": "عرض المنتج",
        "price_jersey": "7 د.ب", "price_mug": "6 د.ب",
        "size_label": "اختر المقاس", "size_guide": "دليل المقاسات",
        "qty_label": "الكمية", "order_wa": "اطلب عبر واتساب",
        "zoom_hint": "اضغط على الصورة لتكبيرها",
        "img_of": "من",
        "quick_title": "كل ما تحتاج معرفته قبل الطلب",
        "quick_size_t": "دليل المقاسات", "quick_size_d": "اعرف مقاسك المناسب قبل الطلب",
        "quick_wash_t": "طريقة الغسيل", "quick_wash_d": "حافظ على تيشرتك لأطول فترة",
        "quick_ret_t": "شروط الاستبدال", "quick_ret_d": "تعرف على سياسة الاستبدال",
        "view_details": "عرض التفاصيل",
        "prod_links_sz": "دليل المقاسات", "prod_links_wash": "العناية بالمنتج", "prod_links_ret": "الاستبدال",
        "szt_head": "دليل المقاسات الآسيوية",
        "szt_size": "المقاس", "szt_chest": "عرض الصدر", "szt_length": "طول التيشرت",
        "szt_height": "الطول المناسب", "szt_weight": "الوزن المناسب",
        "szt_cm": "سم", "szt_kg": "كغ",
        "szt_note": "ملاحظة: المقاسات الآسيوية عادةً تكون أصغر من بعض المقاسات الأوروبية. للحصول على المقاس المناسب، يُفضّل قياس تيشرت تملكه ومقارنة قياساته مع الجدول.",
        "szt_tip": "نصيحة: للحصول على أفضل مقاس، قِس تيشرتًا مناسبًا لك تملكه حاليًا وقارن القياسات مع الجدول.",
        "szt_measure": "أين أقيس؟", "szt_chest_how": "عرض الصدر", "szt_len_how": "طول التيشرت",
        "wash_title": "طريقة غسل الملابس الرياضية",
        "wash_1": "اقلب القميص من الداخل إلى الخارج.",
        "wash_2": "استخدم الماء البارد أو الفاتر فقط.",
        "wash_3": "استخدم كمية قليلة من مسحوق الغسيل اللطيف.",
        "wash_4": "يُفضّل غسله يدويًا أو باستخدام برنامج الملابس الحساسة.",
        "wash_5": "لا تستخدم المبيض (الكلور).",
        "wash_6": "اتركه يجف في مكان مظلل، وتجنب أشعة الشمس المباشرة.",
        "wash_7": "لا تقم بكي الشعارات أو الأرقام مباشرة.",
        "wash_8": "لا تنقع القميص في الماء لفترة طويلة.",
        "wash_warn": "غسل قمصان نسخة اللاعبين بالماء الساخن أو وضعها في النشافة قد يؤدي إلى تلف الشعارات أو تقشر الأرقام.",
        "ret_title": "شروط الاستبدال",
        "ret_1t": "مدة الاستبدال", "ret_1d": "يمكن استبدال المنتج خلال مدة لا تزيد عن 3 أيام من الطلب.",
        "ret_2t": "حالة المنتج", "ret_2d": "يجب الحفاظ على المنتج بحالته الأصلية، وعدم إزالة تاغ المقاس أو رمي الحلقات والكيس الرمادي الخاص بالمنتج.",
        "ret_3t": "تبديل المقاس", "ret_3d": "في حال طلب تبديل المقاس، يتم احتساب رسوم التوصيل مرة أخرى حسب رسوم التوصيل المعتمدة.",
        "ret_4t": "القطعة التالفة", "ret_4d": "في حال وصول قطعة تالفة، يكون مبلغ التوصيل على المتجر.",
        "ret_warn": "يرجى التأكد من اختيار المقاس الصحيح قبل تأكيد الطلب لتجنب رسوم التوصيل الخاصة بالاستبدال.",
        "how_title": "طريقة الطلب",
        "how_1": "اختر القطعة التي تعجبك (تيشيرت أو مق).",
        "how_2": "حدد المقاس والكمية المطلوبة.",
        "how_3": "اضغط على زر «اطلب عبر واتساب».",
        "how_4": "أكّد الطلب في واتساب واستلم توصيلك.",
        "contact_title": "تواصل معنا",
        "contact_sub": "نرد على استفساراتكم وطلباتكم على مدار اليوم.",
        "contact_wa": "تواصل عبر واتساب", "contact_num": "+973 3881 8226",
        "back": "رجوع للرئيسية",
        "footer_title": "معلومات المتجر",
        "footer_copy": "© 2026 golazox — جميع الحقوق محفوظة",
        "welcome_t": "أهلاً وسهلاً بك في متجرنا ⚽",
        "welcome_s": "اكتشف تشكيلة تيشرتات الأندية والمقّات الرياضية واختر القطعة المفضلة لديك.",
        "welcome_ar": "العربية", "welcome_en": "English",
        "close": "إغلاق",
        "hello": "السلام عليكم، أريد طلب ",
        "jersey_w": "تيشيرت ", "mug_w": "مق ",
        "size_w": "المقاس ", "qty_w": "الكمية ",
        "golazox": "golazox",
    },
    "en": {
        "nav_home": "Home", "nav_jerseys": "Club Jerseys", "nav_mugs": "Mugs",
        "nav_sizes": "Size Guide", "nav_order": "How to Order", "nav_contact": "Contact Us",
        "lang_name": "عربي",
        "badge": "Football Club Jerseys & Sports Mugs Store",
        "hero_t1": "Football Club Jerseys",
        "hero_t2": "& Sports Mugs",
        "hero_sub": "A premium collection of club jerseys and sports mugs at a flat fixed price — order now on WhatsApp.",
        "hero_cta_j": "Shop Jerseys", "hero_cta_m": "View Mugs",
        "sec_jerseys": "Club Jerseys", "sec_jerseys_sub": "Flat price 7 BHD — Asian sizes S to 3XL",
        "sec_mugs": "Mugs", "sec_mugs_sub": "Flat price 6 BHD",
        "cat_jersey": "Club Jersey", "cat_mug": "Sports Mug",
        "view": "View Product",
        "price_jersey": "7 BHD", "price_mug": "6 BHD",
        "size_label": "Select Size", "size_guide": "Size Guide",
        "qty_label": "Quantity", "order_wa": "Order via WhatsApp",
        "zoom_hint": "Tap the image to zoom",
        "img_of": "of",
        "quick_title": "Everything you need to know before ordering",
        "quick_size_t": "Size Guide", "quick_size_d": "Find your perfect fit",
        "quick_wash_t": "Washing Method", "quick_wash_d": "Keep your jersey for longer",
        "quick_ret_t": "Return Policy", "quick_ret_d": "Learn about our return policy",
        "view_details": "View Details",
        "prod_links_sz": "Size Guide", "prod_links_wash": "Product Care", "prod_links_ret": "Returns",
        "szt_head": "Asian Size Guide",
        "szt_size": "Size", "szt_chest": "Chest Width", "szt_length": "Jersey Length",
        "szt_height": "Suggested Height", "szt_weight": "Suggested Weight",
        "szt_cm": "cm", "szt_kg": "kg",
        "szt_note": "Note: Asian sizes may run smaller than European sizes. For the best fit, measure a shirt you already own and compare its measurements with our size chart.",
        "szt_tip": "Tip: For the best fit, measure a shirt you already own and compare its measurements with our size chart.",
        "szt_measure": "Where do I measure?", "szt_chest_how": "Chest Width", "szt_len_how": "Jersey Length",
        "wash_title": "How to Wash Sports Clothing",
        "wash_1": "Turn the shirt inside out.",
        "wash_2": "Use only cold or lukewarm water.",
        "wash_3": "Use a small amount of gentle detergent.",
        "wash_4": "Prefer hand washing or the delicate cycle.",
        "wash_5": "Do not use bleach.",
        "wash_6": "Dry in a shaded place, away from direct sunlight.",
        "wash_7": "Do not iron logos or numbers directly.",
        "wash_8": "Do not soak the shirt for a long time.",
        "wash_warn": "Washing player-version shirts in hot water or putting them in the dryer may damage the logos or peel off the numbers.",
        "ret_title": "Return Policy",
        "ret_1t": "Return period", "ret_1d": "Products can be exchanged within no more than 3 days from the order date.",
        "ret_2t": "Product condition", "ret_2d": "The product must be kept in its original condition, keeping the size tag, hangers and the grey bag, without removing them.",
        "ret_3t": "Size exchange", "ret_3d": "For size exchanges, delivery fees will be charged again according to the approved delivery fees.",
        "ret_4t": "Damaged item", "ret_4d": "If the item arrives damaged, the delivery fee is covered by the store.",
        "ret_warn": "Please make sure to choose the correct size before confirming your order to avoid exchange delivery fees.",
        "how_title": "How to Order",
        "how_1": "Choose the piece you like (jersey or mug).",
        "how_2": "Select the size and quantity.",
        "how_3": "Press the «Order via WhatsApp» button.",
        "how_4": "Confirm the order on WhatsApp and receive your delivery.",
        "contact_title": "Contact Us",
        "contact_sub": "We respond to your questions and orders all day long.",
        "contact_wa": "Chat on WhatsApp", "contact_num": "+973 3881 8226",
        "back": "Back to Home",
        "footer_title": "Store Info",
        "footer_copy": "© 2026 golazox — All rights reserved",
        "welcome_t": "Welcome to our store ⚽",
        "welcome_s": "Discover our collection of football club jerseys and sports mugs and find your favorite piece.",
        "welcome_ar": "العربية", "welcome_en": "English",
        "close": "Close",
        "hello": "Hello, I would like to order ",
        "jersey_w": "jersey ", "mug_w": "mug ",
        "size_w": "size ", "qty_w": "quantity ",
        "golazox": "golazox",
    },
}


# ============================== HELPERS ==============================
def lang():
    c = request.cookies.get("lang")
    if c in ("ar", "en"):
        return c
    a = request.args.get("lang")
    if a in ("ar", "en"):
        return a
    return "ar"


def has_lang_cookie():
    return request.cookies.get("lang") in ("ar", "en")


def t(k):
    return L[lang()].get(k, L["ar"].get(k, k))


def json_d(o):
    return json.dumps(o, ensure_ascii=False)


def img_src(base):
    return "/img/" + base


def price(p):
    return "7.0" if p["kind"] == "jersey" else "6.0"


# ============================== PLACEHOLDER SVG ==============================
def placeholder_svg(p, idx=1):
    cols = p.get("colors", ["#1B1B1B", "#333"])
    en = lang() == "en"
    label = (p.get("name_en") if en else p.get("name_ar")) or "golazox"
    emoji = p.get("emoji", "⚽")
    sub = "PHOTO SOON" if en else "الصورة قريبًا"
    brand = "GOLAZOX"
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="COL1"/><stop offset="1" stop-color="COL2"/>
</linearGradient></defs>
<rect width="600" height="600" fill="url(#g)"/>
<circle cx="545" cy="55" r="90" fill="#FFFFFF" opacity="0.06"/>
<circle cx="70" cy="540" r="120" fill="#000000" opacity="0.10"/>
<text x="300" y="285" font-size="150" text-anchor="middle">EMOJI</text>
<rect x="180" y="395" rx="26" width="240" height="54" fill="#FFFFFF" opacity="0.16"/>
<text x="300" y="431" font-size="30" font-family="Arial, sans-serif" font-weight="700" fill="#FFFFFF" text-anchor="middle">LABEL</text>
<text x="300" y="485" font-size="22" font-family="Arial, sans-serif" fill="#FFFFFF" opacity="0.85" text-anchor="middle">SUB</text>
<text x="300" y="545" font-size="20" font-family="Arial, sans-serif" font-weight="900" letter-spacing="4" fill="#FFFFFF" opacity="0.55" text-anchor="middle">BRAND</text>
</svg>""".replace("COL1", cols[0]).replace("COL2", cols[1]) \
        .replace("EMOJI", emoji).replace("LABEL", label) \
        .replace("SUB", sub).replace("BRAND", brand)


@app.route("/img/<name>")
def img(name):
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".avif"):
        pth = os.path.join(STATIC_IMG, name + ext)
        if os.path.exists(pth):
            return send_file(pth)
    base = name.split("_")[0]
    p = ALL.get(base)
    if not p:
        p = {"colors": ["#1B1B1B", "#333"], "emoji": "⚽",
             "name_ar": "golazox", "name_en": "golazox"}
    svg = placeholder_svg(p)
    return Response(svg, mimetype="image/svg+xml")


# ============================== HTML BUILDERS ==============================
def size_table_html(chart):
    en = lang() == "en"
    d = L[lang()]
    head = ("<tr><th>{s}</th><th>{c}</th><th>{l}</th><th>{h}</th><th>{w}</th></tr>").format(
        s=d["szt_size"], c=d["szt_chest"], l=d["szt_length"], h=d["szt_height"], w=d["szt_weight"])
    rows = ""
    for sz in SIZE_ORDER:
        if sz not in chart:
            continue
        r = chart[sz]
        rows += ("<tr><td class='sz'>{sz}</td><td>{c} {cm}</td><td>{l} {cm}</td>"
                 "<td>{h}</td><td>{w} {kg}</td></tr>").format(
            sz=sz, c=r["chest"], l=r["length"], h=r["height"], w=r["weight"],
            cm=d["szt_cm"], kg=d["szt_kg"])
    return "<table class='szt'>" + head + rows + "</table>"


def size_diagram():
    en = lang() == "en"
    chest = "عرض الصدر" if not en else "Chest"
    length = "طول التيشرت" if not en else "Length"
    return """<svg class="szt-ill" viewBox="0 0 260 250">
<path d="M62 34 L98 20 L120 46 L140 46 L162 20 L198 34 L212 84 L182 98 L176 212 L84 212 L78 98 L48 84 Z"
      fill="#1E293B" stroke="#F8FAFC" stroke-width="3" stroke-linejoin="round"/>
<line x1="52" y1="120" x2="208" y2="120" stroke="#FBBF24" stroke-width="3"/>
<polygon points="52,120 62,115 62,125" fill="#FBBF24"/>
<polygon points="208,120 198,115 198,125" fill="#FBBF24"/>
<text x="130" y="111" text-anchor="middle" font-size="15" font-weight="700" fill="#FBBF24" font-family="Arial">CHEST_LBL</text>
<line x1="238" y1="30" x2="238" y2="214" stroke="#60A5FA" stroke-width="3"/>
<polygon points="238,30 233,40 243,40" fill="#60A5FA"/>
<polygon points="238,214 233,204 243,204" fill="#60A5FA"/>
<text x="251" y="122" text-anchor="middle" font-size="15" font-weight="700" fill="#60A5FA" font-family="Arial" transform="rotate(90 251 122)">LEN_LBL</text>
</svg>""".replace("CHEST_LBL", chest).replace("LEN_LBL", length)


def product_card(p):
    en = lang() == "en"
    d = L[lang()]
    name = item_name(p, en)
    cat = d["cat_mug"] if p["kind"] == "mug" else d["cat_jersey"]
    pr = d["price_mug"] if p["kind"] == "mug" else d["price_jersey"]
    first = img_src(p["imgs"][0])
    return (
        '<a class="pcard" href="/product/{id}">'
        '<div class="pimg" style="background:linear-gradient(135deg,{c1},{c2});">'
        '<img src="{src}" alt="{name}" loading="lazy"></div>'
        '<div class="pbody"><span class="pcat">{cat}</span>'
        '<h3>{name}</h3>'
        '<div class="pfoot"><b>{pr}</b><span class="pview">{view} ←</span></div></div></a>'
    ).format(id=p["id"], c1=p["colors"][0], c2=p["colors"][1], src=first,
             name=name.replace('"', "&quot;"), cat=cat, pr=pr, view=d["view"])


def modals_html():
    en = lang() == "en"
    d = L[lang()]
    chart = dict(SIZE_CHART)

    # ---- size guide modal ----
    wash_steps = "".join(
        "<li><b>{n}</b> {txt}</li>".format(n=i + 1, txt=d["wash_" + str(i + 1)]) for i in range(8))
    ret_items = "".join(
        "<li><b>{t}</b> — {x}</li>".format(t=d["ret_" + str(i) + "t"], x=d["ret_" + str(i) + "d"]) for i in range(1, 5))

    def modal(mid, title, body, wide=False):
        return ('<div class="mback" id="{id}" onclick="closeModal(\'{id}\')">'
                '<div class="mbox {w}" onclick="event.stopPropagation()">'
                '<div class="mhead"><h3>{t}</h3><button class="mx" onclick="closeModal(\'{id}\')">✕</button></div>'
                '<div class="mbody">{b}</div></div></div>').format(id=mid, w="wide" if wide else "", t=title, b=body)

    size_body = (
        "<p class='mnote'>{note}</p>".format(note=d["szt_note"])
        + size_table_html(chart)
        + "<h4 class='msec'>{measure}</h4>".format(measure=d["szt_measure"])
        + "<div class='szill-wrap'>" + size_diagram() + "</div>"
        + "<p class='mtip'>💡 {tip}</p>".format(tip=d["szt_tip"])
    )

    wash_body = (
        "<ol class='steps'>" + wash_steps + "</ol>"
        + "<div class='mwarning'>⚠️ {w}</div>".format(w=d["wash_warn"])
    )

    ret_body = (
        "<ul class='ret'>" + ret_items + "</ul>"
        + "<div class='mwarning'>⚠️ {w}</div>".format(w=d["ret_warn"])
    )

    how_body = ("<ol class='steps how'>" +
                "".join("<li>{x}</li>".format(x=d["how_" + str(i + 1)]) for i in range(4)) +
                "</ol>")

    contact_body = (
        "<p class='mnote'>{sub}</p>".format(sub=d["contact_sub"])
        + "<a class='btn wa big' target='_blank' rel='noopener' href='https://wa.me/{num}'>💬 {wa}</a>".format(
            num=WHATSAPP, wa=d["contact_wa"])
        + "<p class='cnum'>{n}</p>".format(n=d["contact_num"])
    )

    return (modal("m-sizes", d["szt_head"], size_body, wide=True)
            + modal("m-wash", d["wash_title"], wash_body, wide=True)
            + modal("m-ret", d["ret_title"], ret_body, wide=True)
            + modal("m-how", d["how_title"], how_body)
            + modal("m-contact", d["contact_title"], contact_body))


def header_html(active=""):
    en = lang() == "en"
    d = L[lang()]
    def nav(id, key, onclick=""):
        cls = " on" if id == active else ""
        if onclick:
            return "<a class='nv{cls}' href='javascript:void(0)' onclick='{oc}'>{t}</a>".format(cls=cls, oc=onclick, t=d[key])
        href = "#top" if id == "home" else ("/product/placeholder" if False else "#")
        return "<a class='nv{cls}' href='{h}'>{t}</a>".format(cls=cls, h=href, t=d[key])
    links = (nav("home", "nav_home", "scrollTop()")
             + nav("jerseys", "nav_jerseys", "goSec('jerseys')")
             + nav("mugs", "nav_mugs", "goSec('mugs')")
             + nav("sizes", "nav_sizes", "openModal('m-sizes')")
             + nav("order", "nav_order", "openModal('m-how')")
             + nav("contact", "nav_contact", "openModal('m-contact')"))
    other = "ar" if en else "en"
    return (
        '<header class="hd"><div class="hd-in">'
        '<a href="/home" class="logo"><span class="ball">⚽</span>golazox</a>'
        '<nav class="nav">{links}</nav>'
        '<button class="langbtn" onclick="setLang(\'{other}\')">{lname}</button>'
        '</div></header>').format(links=links, other=other, lname=d["lang_name"])


def footer_html():
    en = lang() == "en"
    d = L[lang()]
    links = ("<a href='javascript:void(0)' onclick='openModal(\"m-sizes\")'>{0}</a>"
             "<a href='javascript:void(0)' onclick='openModal(\"m-wash\")'>{1}</a>"
             "<a href='javascript:void(0)' onclick='openModal(\"m-ret\")'>{2}</a>"
             "<a href='javascript:void(0)' onclick='openModal(\"m-how\")'>{3}</a>"
             "<a href='javascript:void(0)' onclick='openModal(\"m-contact\")'>{4}</a>").format(
        d["nav_sizes"], d["wash_title"], d["ret_title"], d["how_title"], d["nav_contact"])
    return (
        '<footer class="ft"><div class="ft-in">'
        '<div class="ft-brand"><span class="ball">⚽</span>golazox</div>'
        '<div class="ft-title">{t}</div>'
        '<div class="ft-links">{links}</div>'
        '<p class="ft-copy">{copy}</p>'
        '</div></footer>').format(t=d["footer_title"], links=links, copy=d["footer_copy"])


# ============================== PAGES ==============================
def base_page(body, active=""):
    en = lang() == "en"
    d = L[lang()]
    js_t = json_d({k: d[k] for k in ("close", "hello", "jersey_w", "mug_w", "size_w", "qty_w", "img_of")})
    return """<!DOCTYPE html>
<html lang="LANG" dir="DIR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>golazox</title>
<meta name="description" content="golazox — football club jerseys & sports mugs, order on WhatsApp">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚽</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Poppins:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
:root { --bg:#0B0F19; --card:#141B2B; --card2:#182136; --line:#263049; --txt:#F8FAFC; --mut:#9AA7BD;
        --red:#E63946; --orange:#F77F00; --green:#25D366; --gold:#C9A24B; }
html { scroll-behavior: smooth; }
body { font-family: 'FONT', 'Segoe UI', Tahoma, sans-serif; background: var(--bg); color: var(--txt);
       min-height: 100vh; }
a { text-decoration: none; color: inherit; }
img { display: block; }
.hd { position: sticky; top: 0; z-index: 90; background: rgba(11,15,25,.92); backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--line); }
.hd-in { max-width: 1120px; margin: 0 auto; padding: 12px 18px; display: flex; align-items: center; gap: 14px; }
.logo { font-size: 23px; font-weight: 900; letter-spacing: .5px; display: flex; align-items: center; gap: 8px; color: #fff; }
.logo .ball { font-size: 22px; }
.nav { display: flex; gap: 2px; flex: 1; flex-wrap: wrap; }
.nav .nv { padding: 8px 13px; border-radius: 999px; font-size: 14px; font-weight: 700; color: var(--mut); cursor: pointer; white-space: nowrap; }
.nav .nv:hover { color: #fff; background: var(--card2); }
.nav .nv.on { background: linear-gradient(90deg, var(--red), var(--orange)); color: #fff; }
.langbtn { background: var(--card2); border: 1px solid var(--line); color: #fff; font-family: inherit;
           font-size: 13px; font-weight: 700; padding: 8px 15px; border-radius: 999px; cursor: pointer; }
.langbtn:hover { border-color: var(--gold); color: var(--gold); }
.wrap { max-width: 1120px; margin: 0 auto; padding: 26px 18px 70px; }
.hero { position: relative; overflow: hidden; border: 1px solid var(--line); border-radius: 26px;
        background: radial-gradient(1200px 500px at 80% -10%, #2A1A3A 0%, var(--bg) 60%),
                    radial-gradient(900px 400px at 10% 120%, #1E2A44 0%, var(--bg) 55%);
        padding: 52px 38px; margin-bottom: 34px; }
.hero:before { content:''; position:absolute; inset:0; opacity:.35;
  background: repeating-linear-gradient(0deg, transparent 0 28px, rgba(255,255,255,.025) 28px 30px),
              repeating-linear-gradient(90deg, transparent 0 28px, rgba(255,255,255,.025) 28px 30px); }
.hero-in { position: relative; }
.badge { display: inline-block; background: rgba(230,57,70,.14); color: #FF8A93; border: 1px solid rgba(230,57,70,.35);
         font-size: 13px; font-weight: 800; padding: 7px 15px; border-radius: 999px; margin-bottom: 16px; }
.hero h1 { font-size: 46px; line-height: 1.12; font-weight: 900; }
.hero h1 .g { background: linear-gradient(90deg, var(--red), var(--orange)); -webkit-background-clip: text;
              background-clip: text; color: transparent; }
.hero p { margin-top: 14px; color: var(--mut); font-size: 16px; line-height: 1.9; max-width: 620px; }
.hero-btns { margin-top: 26px; display: flex; gap: 12px; flex-wrap: wrap; }
.btn { display: inline-flex; align-items: center; gap: 8px; font-weight: 800; font-size: 15px; padding: 13px 26px;
       border-radius: 999px; border: none; cursor: pointer; font-family: inherit; }
.btn.pri { background: linear-gradient(90deg, var(--red), var(--orange)); color: #fff; box-shadow: 0 12px 30px rgba(230,57,70,.35); }
.btn.pri:hover { transform: translateY(-2px); }
.btn.ghost { background: var(--card2); border: 1px solid var(--line); color: #fff; }
.btn.ghost:hover { border-color: var(--gold); }
.btn.wa { background: var(--green); color: #0b2c1a; box-shadow: 0 12px 30px rgba(37,211,102,.3); }
.btn.wa:hover { transform: translateY(-2px); }
.btn.big { width: 100%; justify-content: center; padding: 15px; font-size: 16px; }
.sec { margin-bottom: 40px; }
.sec-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }
.sec-head h2 { font-size: 26px; font-weight: 900; display: flex; align-items: center; gap: 10px; }
.sec-head h2 .bar { width: 6px; height: 26px; border-radius: 4px; background: linear-gradient(180deg, var(--red), var(--orange)); }
.sec-sub { color: var(--mut); font-size: 14px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 20px; }
.pcard { background: var(--card); border: 1px solid var(--line); border-radius: 20px; overflow: hidden;
         transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease; }
.pcard:hover { transform: translateY(-5px); border-color: rgba(230,57,70,.6); box-shadow: 0 18px 44px rgba(0,0,0,.45); }
.pimg { height: 230px; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.pimg img { width: 100%; height: 100%; object-fit: cover; transition: transform .3s ease; }
.pcard:hover .pimg img { transform: scale(1.05); }
.pbody { padding: 15px 16px 16px; }
.pcat { font-size: 11.5px; font-weight: 800; letter-spacing: .4px; text-transform: uppercase; color: var(--orange); }
.pbody h3 { font-size: 16.5px; font-weight: 800; margin-top: 5px; }
.pfoot { display: flex; align-items: center; justify-content: space-between; margin-top: 12px; }
.pfoot b { font-size: 17px; color: var(--gold); }
.pview { font-size: 13px; font-weight: 800; color: var(--mut); }
.pcard:hover .pview { color: #fff; }
.quick { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 18px; }
.qcard { background: var(--card); border: 1px solid var(--line); border-radius: 20px; padding: 24px 22px;
         cursor: pointer; transition: transform .16s ease, border-color .16s ease; }
.qcard:hover { transform: translateY(-4px); border-color: rgba(247,127,0,.6); }
.qic { width: 56px; height: 56px; border-radius: 16px; display: flex; align-items: center; justify-content: center;
       font-size: 27px; background: linear-gradient(135deg, var(--card2), #1E2A44); margin-bottom: 16px; }
.qcard h3 { font-size: 17px; font-weight: 800; }
.qcard p { color: var(--mut); font-size: 13.5px; line-height: 1.7; margin: 7px 0 14px; }
.qview { color: var(--red); font-weight: 800; font-size: 14px; }
.ft { border-top: 1px solid var(--line); background: #080C14; }
.ft-in { max-width: 1120px; margin: 0 auto; padding: 40px 18px 34px; text-align: center; }
.ft-brand { font-size: 24px; font-weight: 900; display: flex; align-items: center; justify-content: center; gap: 8px; }
.ft-title { color: var(--mut); font-size: 14px; margin-top: 18px; font-weight: 800; }
.ft-links { display: flex; gap: 8px 22px; justify-content: center; flex-wrap: wrap; margin-top: 14px; }
.ft-links a { color: var(--mut); font-size: 14px; font-weight: 700; }
.ft-links a:hover { color: #fff; }
.ft-copy { color: #5B6782; font-size: 13px; margin-top: 22px; }
/* ---- product page ---- */
.pg { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; align-items: start; }
.gal { position: sticky; top: 90px; }
.gmain { position: relative; border: 1px solid var(--line); border-radius: 22px; overflow: hidden; cursor: zoom-in; background: var(--card); }
.gmain img { width: 100%; height: 460px; object-fit: cover; }
.gar { position: absolute; top: 50%; transform: translateY(-50%); width: 42px; height: 42px; border-radius: 50%;
       background: rgba(11,15,25,.6); color: #fff; border: 1px solid var(--line); font-size: 18px; cursor: pointer; z-index: 2; }
.gar:hover { background: var(--red); }
.gar.r { inset-inline-end: 12px; } .gar.l { inset-inline-start: 12px; }
.gthumb { display: flex; gap: 10px; margin-top: 12px; }
.gthumb img { width: 74px; height: 74px; object-fit: cover; border-radius: 12px; border: 2px solid var(--line); cursor: pointer; opacity: .7; }
.gthumb img.on { border-color: var(--red); opacity: 1; }
.gcount { position: absolute; bottom: 10px; inset-inline-start: 10px; background: rgba(11,15,25,.72); color: #fff;
          font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 999px; }
.pinfo h1 { font-size: 30px; font-weight: 900; }
.pcatline { color: var(--orange); font-weight: 800; font-size: 13px; letter-spacing: .5px; text-transform: uppercase; margin-top: 6px; }
.pprice { margin-top: 14px; font-size: 26px; font-weight: 900; color: var(--gold); }
.szsec { margin-top: 24px; }
.szsec .lbl { font-weight: 800; font-size: 15px; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between; }
.szlink { color: var(--red); font-weight: 800; font-size: 13.5px; cursor: pointer; }
.szsec .sizes { display: flex; gap: 9px; flex-wrap: wrap; }
.size-chip { min-width: 56px; padding: 12px 8px; text-align: center; background: var(--card2); border: 1.5px solid var(--line);
             border-radius: 12px; font-weight: 800; font-size: 14.5px; cursor: pointer; color: #fff; }
.size-chip:hover { border-color: var(--gold); }
.size-chip.on { background: linear-gradient(90deg, var(--red), var(--orange)); border-color: transparent; }
.qtysec { margin-top: 22px; }
.qtysec .lbl { font-weight: 800; font-size: 15px; margin-bottom: 10px; }
.qty { display: inline-flex; align-items: center; gap: 4px; background: var(--card2); border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
.qty button { width: 44px; height: 44px; background: none; border: none; color: #fff; font-size: 20px; font-weight: 800; cursor: pointer; }
.qty button:hover { background: var(--line); }
.qty .qn { min-width: 44px; text-align: center; font-size: 17px; font-weight: 900; }
.orderbtn { width: 100%; margin-top: 26px; }
.links3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 26px; }
.link3 { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 14px 10px;
        text-align: center; font-weight: 800; font-size: 13.5px; cursor: pointer; color: var(--mut); }
.link3:hover { color: #fff; border-color: rgba(230,57,70,.6); }
.link3 .ic { display: block; font-size: 22px; margin-bottom: 6px; }
.zoom-hint { color: var(--mut); font-size: 12.5px; margin-top: 8px; text-align: center; }
.back { display: inline-flex; align-items: center; gap: 6px; color: var(--mut); font-weight: 800; font-size: 14px; margin-bottom: 18px; }
.back:hover { color: #fff; }
/* ---- modals ---- */
.mback { position: fixed; inset: 0; background: rgba(4,7,12,.72); backdrop-filter: blur(4px); z-index: 300;
         display: none; align-items: center; justify-content: center; padding: 18px; }
.mback.open { display: flex; }
.mbox { background: var(--card); border: 1px solid var(--line); border-radius: 22px; width: 100%; max-width: 560px;
        max-height: 86vh; display: flex; flex-direction: column; animation: pop .18s ease; }
.mbox.wide { max-width: 700px; }
@keyframes pop { from { transform: scale(.96); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.mhead { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--line); }
.mhead h3 { font-size: 18px; font-weight: 900; }
.mx { width: 32px; height: 32px; border-radius: 50%; background: var(--card2); border: 1px solid var(--line); color: #fff; cursor: pointer; }
.mbody { padding: 20px; overflow-y: auto; }
.mnote { color: var(--mut); font-size: 14px; line-height: 1.8; margin-bottom: 14px; }
.mwarning { background: rgba(230,57,70,.12); border: 1px solid rgba(230,57,70,.4); color: #FFB3BA;
            border-radius: 14px; padding: 13px 15px; font-size: 13.5px; line-height: 1.8; margin-top: 16px; }
.mtip { background: rgba(201,162,75,.1); border: 1px solid rgba(201,162,75,.35); color: #F3DFA9;
        border-radius: 14px; padding: 13px 15px; font-size: 13.5px; line-height: 1.8; margin-top: 14px; }
.szt { width: 100%; border-collapse: collapse; margin: 6px 0 18px; }
.szt th { background: var(--card2); color: #fff; padding: 11px 8px; font-size: 13px; text-align: center; }
.szt td { padding: 11px 8px; font-size: 13.5px; text-align: center; border-bottom: 1px solid var(--line); color: var(--mut); }
.szt td.sz { font-weight: 900; color: var(--red); font-size: 15px; }
.szt tr:hover td { background: rgba(255,255,255,.02); }
.szill-wrap { display: flex; justify-content: center; margin: 6px 0 18px; }
.szt-ill { width: 230px; height: auto; }
.msec { font-weight: 900; font-size: 15px; margin: 6px 0 12px; }
.steps { list-style: none; counter-reset: st; }
.steps li { counter-increment: st; position: relative; padding: 9px 0 9px 44px; font-size: 14.5px; color: var(--mut); line-height: 1.8; }
.steps li:before { content: counter(st); position: absolute; inset-inline-start: 0; top: 9px; width: 30px; height: 30px;
                   border-radius: 50%; background: linear-gradient(135deg, var(--red), var(--orange)); color: #fff;
                   font-weight: 900; font-size: 14px; display: flex; align-items: center; justify-content: center; }
.steps li b { color: #fff; }
.ret { list-style: none; }
.ret li { position: relative; padding: 11px 0 11px 24px; border-bottom: 1px dashed var(--line); font-size: 14px; color: var(--mut); line-height: 1.8; }
.ret li:last-child { border-bottom: none; }
.ret li:before { content: '→'; position: absolute; inset-inline-start: 0; color: var(--red); font-weight: 900; }
.ret li b { color: #fff; }
.cnum { text-align: center; color: var(--mut); font-weight: 800; margin-top: 12px; }
/* ---- welcome ---- */
.welc { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center;
        text-align: center; padding: 30px 20px; position: relative; overflow: hidden;
        background: radial-gradient(900px 500px at 50% -20%, #2A1A3A 0%, var(--bg) 60%); }
.welc:before { content:''; position:absolute; inset:0; opacity:.4;
  background: repeating-linear-gradient(0deg, transparent 0 32px, rgba(255,255,255,.03) 32px 34px),
              repeating-linear-gradient(90deg, transparent 0 32px, rgba(255,255,255,.03) 32px 34px); }
.welc-in { position: relative; max-width: 560px; }
.welc .ball { font-size: 70px; }
.welc h1 { font-size: 34px; font-weight: 900; margin-top: 18px; line-height: 1.4; }
.welc p { color: var(--mut); margin-top: 14px; font-size: 16px; line-height: 1.9; }
.wlang { display: flex; gap: 14px; justify-content: center; margin-top: 30px; flex-wrap: wrap; }
.wlang a { padding: 15px 34px; border-radius: 16px; font-weight: 900; font-size: 16px; border: 1px solid var(--line);
           background: var(--card); color: #fff; }
.wlang a:hover { border-color: var(--gold); transform: translateY(-2px); }
.wlang a:first-child { background: linear-gradient(90deg, var(--red), var(--orange)); border-color: transparent; }
.welc .brand { margin-top: 26px; color: #5B6782; font-size: 13px; font-weight: 800; letter-spacing: 2px; }
/* ---- lightbox ---- */
.lb { position: fixed; inset: 0; background: rgba(4,7,12,.94); z-index: 400; display: none; align-items: center; justify-content: center; cursor: zoom-out; }
.lb.open { display: flex; }
.lb img { max-width: 92vw; max-height: 92vh; border-radius: 12px; }
/* ---- responsive ---- */
@media (max-width: 900px) {
  .pg { grid-template-columns: 1fr; }
  .gal { position: static; }
  .gmain img { height: 340px; }
  .hero h1 { font-size: 34px; }
  .nav { order: 3; width: 100%; justify-content: center; }
}
@media (max-width: 560px) {
  .grid { grid-template-columns: repeat(2, 1fr); gap: 12px; }
  .pimg { height: 165px; }
  .hero { padding: 36px 22px; }
  .hero h1 { font-size: 28px; }
  .links3 { grid-template-columns: 1fr; }
  .gmain img { height: 300px; }
}
</style>
</head>
<body>
HEADER
BODY
FOOTER
MODALS
<div class="lb" id="lb" onclick="closeLB()"><img id="lbimg" alt=""></div>
<script>
var WA = '__WA__';
var T = __JS_T__;
function setLang(l){ document.cookie='lang='+l+';path=/;max-age=31536000;SameSite=Lax'; location.href='/home'; }
function scrollTop(){ window.scrollTo({top:0, behavior:'smooth'}); }
function goSec(id){ var el=document.getElementById(id); if(el){ el.scrollIntoView({behavior:'smooth'}); } }
function openModal(id){ var m=document.getElementById(id); if(m) m.classList.add('open'); }
function closeModal(id){ var m=document.getElementById(id); if(m) m.classList.remove('open'); }
function selectSize(el){ var s=document.querySelectorAll('.size-chip'); for(var i=0;i<s.length;i++) s[i].classList.remove('on'); el.classList.add('on'); }
function chgQ(d){ var q=document.getElementById('qty'); var v=parseInt(q.textContent,10)+d; if(v<1)v=1; if(v>99)v=99; q.textContent=v; }
var gi=0, gN=0;
function setGal(i, arr){ gi=i; gN=arr.length; var img=document.getElementById('gmain'); var t=document.getElementById('gthumbs');
  img.src='/img/'+arr[i]; document.getElementById('gcount').textContent=(i+1)+' '+T.of+' '+gN;
  var h=''; for(var k=0;k<gN;k++){ h+="<img src='/img/"+arr[k]+"' class='"+(k===i?'on':'')+"' onclick='setGal("+k+",GARR)' alt=''>"; }
  t.innerHTML=h; var l=document.getElementById('garr'); if(l) l.style.display=gN>1?'':'none'; }
function movGal(d, arr){ var n=arr.length; setGal((gi+d+n)%n, arr); }
function openLB(src){ document.getElementById('lbimg').src=src; document.getElementById('lb').classList.add('open'); }
function closeLB(){ document.getElementById('lb').classList.remove('open'); }
function orderWA(kind, name){
  var chip=document.querySelector('.size-chip.on'); var sz=chip?chip.dataset.sz:null;
  var q=parseInt(document.getElementById('qty').textContent,10);
  var msg=T.hello+(kind==='mug'?T.mug_w:T.jersey_w)+name;
  if(sz) msg+=', '+T.size_w+sz;
  msg+=', '+T.qty_w+q;
  window.open('https://wa.me/'+WA+'?text='+encodeURIComponent(msg), '_blank');
}
</script>
</body>
</html>""".replace("LANG", "en" if en else "ar") \
        .replace("DIR", "ltr" if en else "rtl") \
        .replace("FONT", "Poppins" if en else "Cairo") \
        .replace("HEADER", header_html(active)) \
        .replace("FOOTER", footer_html()) \
        .replace("MODALS", modals_html()) \
        .replace("__WA__", WHATSAPP) \
        .replace("__JS_T__", js_t) \
        .replace("BODY", body)


def home_body():
    en = lang() == "en"
    d = L[lang()]
    jgrid = "".join(product_card(p) for p in JERSEYS)
    mgrid = "".join(product_card(p) for p in MUGS)
    quick = (
        '<div class="qcard" onclick="openModal(\'m-sizes\')"><div class="qic">📏</div>'
        '<h3>{a}</h3><p>{b}</p><span class="qview">{c} ←</span></div>'
        '<div class="qcard" onclick="openModal(\'m-wash\')"><div class="qic">🧺</div>'
        '<h3>{d}</h3><p>{e}</p><span class="qview">{c} ←</span></div>'
        '<div class="qcard" onclick="openModal(\'m-ret\')"><div class="qic">🔄</div>'
        '<h3>{f}</h3><p>{g}</p><span class="qview">{c} ←</span></div>'
    ).format(a=d["quick_size_t"], b=d["quick_size_d"], c=d["view_details"],
             d=d["quick_wash_t"], e=d["quick_wash_d"], f=d["quick_ret_t"], g=d["quick_ret_d"])
    return (
        '<div class="wrap"><div class="hero"><div class="hero-in">'
        '<span class="badge">{badge}</span>'
        '<h1>{t1}<br><span class="g">{t2}</span></h1>'
        '<p>{sub}</p>'
        '<div class="hero-btns">'
        '<a class="btn pri" href="javascript:void(0)" onclick="goSec(\'jerseys\')">{cj}</a>'
        '<a class="btn ghost" href="javascript:void(0)" onclick="goSec(\'mugs\')">{cm}</a>'
        '</div></div></div>'
        '<div class="sec" id="jerseys"><div class="sec-head">'
        '<h2><span class="bar"></span>{sj}</h2><span class="sec-sub">{sj_sub}</span></div>'
        '<div class="grid">{jgrid}</div></div>'
        '<div class="sec" id="mugs"><div class="sec-head">'
        '<h2><span class="bar"></span>{sm}</h2><span class="sec-sub">{sm_sub}</span></div>'
        '<div class="grid">{mgrid}</div></div>'
        '<div class="sec" id="info"><div class="sec-head"><h2><span class="bar"></span>{qt}</h2></div>'
        '<div class="quick">{quick}</div></div>'
        '</div>'
    ).format(badge=d["badge"], t1=d["hero_t1"], t2=d["hero_t2"], sub=d["hero_sub"],
             cj=d["hero_cta_j"], cm=d["hero_cta_m"], sj=d["sec_jerseys"], sj_sub=d["sec_jerseys_sub"],
             sm=d["sec_mugs"], sm_sub=d["sec_mugs_sub"], qt=d["quick_title"],
             jgrid=jgrid, mgrid=mgrid, quick=quick)


def product_body(pid):
    en = lang() == "en"
    d = L[lang()]
    p = ALL.get(pid)
    if not p:
        return '<div class="wrap"><p>404</p></div>'
    name = item_name(p, en)
    is_mug = p["kind"] == "mug"
    cat = d["cat_mug"] if is_mug else d["cat_jersey"]
    pr = d["price_mug"] if is_mug else d["price_jersey"]
    club = club_name(p, en)
    title_line = name if is_mug else (club + " — " + d["cat_jersey"])
    arr = json_d(p["imgs"])
    gthumbs = "".join(
        "<img src='{s}' class='{c}' onclick='setGal({i},GARR)' alt=''>".format(
            s=img_src(p["imgs"][i]), c="on" if i == 0 else "", i=i)
        for i in range(len(p["imgs"])))
    sizes = ""
    if not is_mug:
        chips = ""
        for sz in SIZE_ORDER:
            chips += "<button class='size-chip' data-sz='{s}' onclick='selectSize(this)'>{s}</button>".format(s=sz)
        sizes = ('<div class="szsec"><div class="lbl"><span>{sl}</span>'
                 '<span class="szlink" onclick="openModal(\'m-sizes\')">📏 {sg}</span></div>'
                 '<div class="sizes">{chips}</div></div>').format(sl=d["size_label"], sg=d["size_guide"], chips=chips)
    links3 = ('<div class="links3">'
              '<div class="link3" onclick="openModal(\'m-sizes\')"><span class="ic">📏</span>{a}</div>'
              '<div class="link3" onclick="openModal(\'m-wash\')"><span class="ic">🧺</span>{b}</div>'
              '<div class="link3" onclick="openModal(\'m-ret\')"><span class="ic">🔄</span>{c}</div>'
              '</div>').format(a=d["prod_links_sz"], b=d["prod_links_wash"], c=d["prod_links_ret"])
    return (
        '<div class="wrap">'
        '<a class="back" href="/home">← {back}</a>'
        '<div class="pg">'
        '<div class="gal">'
        '<div class="gmain" onclick="openLB(document.getElementById(\'gmain\').src)">'
        '<img id="gmain" src="{src}" alt="{name}">'
        '<span class="gcount" id="gcount">1 {of} {n}</span>'
        '<button class="gar r" id="garr" onclick="event.stopPropagation();movGal(1,GARR)">‹</button>'
        '<button class="gar l" id="garr2" onclick="event.stopPropagation();movGal(-1,GARR)">›</button>'
        '</div>'
        '<div class="gthumb" id="gthumbs">{gthumbs}</div>'
        '<p class="zoom-hint">🔍 {zh}</p>'
        '</div>'
        '<div class="pinfo">'
        '<h1>{name}</h1><p class="pcatline">{cat}</p>'
        '<div class="pprice">{pr}</div>'
        '{sizes}'
        '<div class="qtysec"><div class="lbl">{ql}</div>'
        '<div class="qty"><button onclick="chgQ(-1)">−</button><span class="qn" id="qty">1</span><button onclick="chgQ(1)">+</button></div></div>'
        '<button class="btn wa orderbtn" onclick="orderWA(\'{kind}\',\'{oname}\')">💬 {ow}</button>'
        '{links3}'
        '</div></div></div>'
        '<script>var GARR={arr};setGal(0,GARR);</script>'
    ).format(back=d["back"], src=img_src(p["imgs"][0]), name=name.replace("'", "\\'"),
             of=d["img_of"], n=len(p["imgs"]), zh=d["zoom_hint"], gthumbs=gthumbs,
             cat=cat, pr=pr, sizes=sizes, ql=d["qty_label"],
             kind=p["kind"], oname=name.replace("'", "\\'"), ow=d["order_wa"],
             links3=links3, arr=arr, title_line=title_line)


def welcome_page():
    en = lang() == "en"
    d = L[lang()]
    return """<!DOCTYPE html>
<html lang="LANG" dir="DIR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>golazox</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚽</text></svg>">
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Poppins:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'FONT','Segoe UI',Tahoma,sans-serif;background:#0B0F19;color:#F8FAFC;min-height:100vh}
.welc{min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:30px 20px;position:relative;overflow:hidden;
background:radial-gradient(900px 500px at 50% -20%,#2A1A3A 0%,#0B0F19 60%)}
.welc:before{content:'';position:absolute;inset:0;opacity:.4;background:repeating-linear-gradient(0deg,transparent 0 32px,rgba(255,255,255,.03) 32px 34px),repeating-linear-gradient(90deg,transparent 0 32px,rgba(255,255,255,.03) 32px 34px)}
.welc-in{position:relative;max-width:560px}
.welc .ball{font-size:74px}
.welc h1{font-size:34px;font-weight:900;margin-top:18px;line-height:1.5}
.welc p{color:#9AA7BD;margin-top:14px;font-size:16px;line-height:1.9}
.wlang{display:flex;gap:14px;justify-content:center;margin-top:30px;flex-wrap:wrap}
.wlang a{padding:15px 34px;border-radius:16px;font-weight:900;font-size:16px;border:1px solid #263049;background:#141B2B;color:#fff}
.wlang a:hover{border-color:#C9A24B;transform:translateY(-2px)}
.wlang a:first-child{background:linear-gradient(90deg,#E63946,#F77F00);border-color:transparent}
.brand{margin-top:26px;color:#5B6782;font-size:13px;font-weight:800;letter-spacing:2px}
</style></head>
<body>
<div class="welc"><div class="welc-in">
<div class="ball">⚽</div>
<h1>__WT__</h1><p>__WS__</p>
<div class="wlang">
<a href="/lang/ar">__WAR__</a><a href="/lang/en">__WEN__</a>
</div>
<div class="brand">GOLAZOX</div>
</div></div>
</body></html>""".replace("LANG", "en" if en else "ar") \
        .replace("DIR", "ltr" if en else "rtl") \
        .replace("FONT", "Poppins" if en else "Cairo") \
        .replace("__WT__", d["welcome_t"]) \
        .replace("__WS__", d["welcome_s"]) \
        .replace("__WAR__", d["welcome_ar"]) \
        .replace("__WEN__", d["welcome_en"])


# ============================== ROUTES ==============================
@app.route("/")
def index():
    if not has_lang_cookie():
        return welcome_page()
    return redirect("/home")


@app.route("/home")
def home():
    if not has_lang_cookie():
        return redirect("/")
    return base_page(home_body(), active="home")


@app.route("/product/<pid>")
def product(pid):
    if not has_lang_cookie():
        return redirect("/")
    if pid not in ALL:
        return redirect("/home")
    return base_page(product_body(pid), active="")


@app.route("/lang/<l>")
def setlang(l):
    r = redirect("/home" if request.cookies.get("lang") else "/")
    r.set_cookie("lang", l, max_age=31536000)
    return r


@app.route("/health")
def health():
    return "ok"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
