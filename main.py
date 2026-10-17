# ═══════════════════════════════════════════════════════════════
# FLUXBOT PV v4.1 — اصلاح باگ ارسال سفارش به ادمین
# ═══════════════════════════════════════════════════════════════
import os, json, time, re, asyncio, random, hashlib
from datetime import datetime, timezone, timedelta
from rubka import Robot
from rubka.keypad import ChatKeypadBuilder

TOKEN = os.getenv("RUBIKA_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("❌ RUBIKA_TOKEN تنظیم نشده است.")

bot = Robot(token=TOKEN)

# ═══ تنظیمات ═══
OWNER_ID = "u0KUJo1004f46bafc48e536f282693b6"
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))
SPIN_COOLDOWN = 86400  # ۲۴ ساعت
ADMIN_SPECIAL_ID = "FLUX-F834C581"  # شناسه ادمین
ITEM_PRICE = 10  # قیمت هر آیتم به امتیاز

# ═══ ذخیره‌سازی ═══
DATA_PATHS = [
    "/data/bot_data.json", "/app/data/bot_data.json",
    "/app/bot_data.json", "/tmp/bot_data.json", "./bot_data.json",
]
for _p in ["/data", "/app/data", "/tmp"]:
    try: os.makedirs(_p, exist_ok=True)
    except: pass

DEFAULTS = {
    "users": [], "known_users": {}, "invite_codes": {},
    "code_to_user": {}, "invited_users": {}, "points": {},
    "daily_rewards": {}, "spinner_last": {}, "items": {},
    "orders": {}, 
}

def _read():
    for p in DATA_PATHS:
        try:
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    v = json.load(f)
                if isinstance(v, dict): return v
        except: pass
    return {}

def _write(d):
    for p in DATA_PATHS:
        try:
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            os.replace(tmp, p)
            return True
        except: pass
    return False

data = _read()
if "started_users" in data and isinstance(data["started_users"], list):
    if not data.get("users"): data["users"] = list(data["started_users"])
for k, v in DEFAULTS.items():
    if k not in data or not isinstance(data[k], type(v)):
        data[k] = v.copy() if isinstance(v, (dict, list)) else v

def save(): _write(data)

# ═══ Helpers ═══
def today_str(): return datetime.now(IRAN_TZ).strftime("%Y-%m-%d")
def is_group(cid): return bool(cid) and str(cid).lower().startswith("g")
def is_private(cid): return bool(cid) and not is_group(cid)

def safe_name(v, uid=None):
    if not v: return None
    n = re.sub(r"(?<![\w])@[A-Za-z0-9_.]+", "", str(v)).strip()
    if not n or (uid is not None and n == str(uid)): return None
    return n

def display_name(uid):
    u = data["known_users"].get(str(uid), {})
    if isinstance(u, dict):
        n = safe_name(u.get("name"), uid)
        if n: return n
    return "کاربر"

def register(uid, name=None):
    if not uid: return
    uid = str(uid)
    changed = False
    if uid not in data["users"]:
        data["users"].append(uid); changed = True
    if name:
        ku = data["known_users"]
        if uid not in ku: ku[uid] = {}
        if ku[uid].get("name") != name:
            ku[uid]["name"] = name
            ku[uid]["last_seen"] = time.time()
            changed = True
    if changed: save()

def get_points(uid): return data["points"].get(str(uid), 0)

def add_points(uid, amount):
    uid = str(uid)
    new_val = data["points"].get(uid, 0) + amount
    if new_val < 0: new_val = 0
    data["points"][uid] = new_val
    save()

def get_or_create_code(uid):
    uid = str(uid)
    if uid in data["invite_codes"]:
        code = data["invite_codes"][uid]
        data["code_to_user"][code] = uid
        return code
    existing = set(data["invite_codes"].values())
    for _ in range(200):
        code = str(random.randint(100000, 999999))
        if code not in existing: break
    data["invite_codes"][uid] = code
    data["code_to_user"][code] = uid
    save()
    return code

# 🔒 تابع شناسه بدون تغییر
def special_id(uid):
    h = hashlib.md5(str(uid).encode()).hexdigest()[:8].upper()
    return f"FLUX-{h}"

# 🔧 تابع استخراج آیدی پیام (ضد باگ)
def extract_msg_id(result):
    try:
        if isinstance(result, dict):
            if "data" in result and isinstance(result["data"], dict):
                mid = result["data"].get("message_id")
                if mid: return str(mid)
            mid = result.get("message_id")
            if mid: return str(mid)
        elif hasattr(result, "message_id"):
            return str(result.message_id)
        elif hasattr(result, "id"):
            return str(result.id)
    except Exception as e:
        print(f"⚠️ extract_msg_id: {e}", flush=True)
    return None

# 🔧 تابع استخراج آیدی ریپلای (ضد باگ)
def extract_reply_msg_id(message):
    try:
        mid = getattr(message, 'reply_to_message_id', None)
        if mid: return str(mid)
        rt = (getattr(message, 'reply_to_message', None) or
              getattr(message, 'reply_message', None) or
              getattr(message, 'reply_to', None))
        if rt:
            if isinstance(rt, dict):
                mid = rt.get('message_id') or rt.get('id')
                if mid: return str(mid)
            else:
                mid = getattr(rt, 'message_id', None) or getattr(rt, 'id', None)
                if mid: return str(mid)
    except: pass
    return None

# ═══ آیتم‌ها ═══
ITEMS = [
    ("gem",      "💎 الماس درخشان"),
    ("gold",     "⚜️ نشان طلایی"),
    ("crown",    "👑 تاج سلطنتی"),
    ("medal",    "🎖️ مدال افتخار"),
    ("sapphire", "💠 نگین آبی"),
    ("staff",    "🔱 عصای جادویی"),
    ("trophy",   "🏆 جام قهرمانی"),
    ("star",     "🌟 ستاره درخشان"),
]

# ═══ دکمه‌ها ═══
BTN_INVITE_ENTER = "🎟️ زدن کد دعوت"
BTN_POINTS       = "⭐ امتیاز من"
BTN_INVITE_SHOW  = "🎫 کد دعوت من"
BTN_DAILY        = "🎁 جایزه روزانه"
BTN_SPINNER      = "🎡 گردونه شانس"
BTN_CONVERT      = "💎 تبدیل سکه به آیتم"
BTN_ORDER        = "🛒 سفارش"

BUTTONS = [
    ("btn_invite_enter", BTN_INVITE_ENTER),
    ("btn_points",       BTN_POINTS),
    ("btn_invite_show",  BTN_INVITE_SHOW),
    ("btn_daily",        BTN_DAILY),
    ("btn_spinner",      BTN_SPINNER),
    ("btn_convert",      BTN_CONVERT),
]

def build_keypad():
    try:
        b = ChatKeypadBuilder()
        for i in range(0, len(BUTTONS), 2):
            b.row(
                b.button_simple(id=BUTTONS[i][0], text=BUTTONS[i][1]),
                b.button_simple(id=BUTTONS[i+1][0], text=BUTTONS[i+1][1])
            )
        b.row(b.button_simple(id="btn_order", text=BTN_ORDER)) # دکمه دراز سفارش
        return b.build()
    except Exception as e:
        print(f"⚠️ keypad: {e}", flush=True)
        return None

LABEL_TO_BID = {
    BTN_INVITE_ENTER: "btn_invite_enter", BTN_POINTS: "btn_points",
    BTN_INVITE_SHOW: "btn_invite_show", BTN_DAILY: "btn_daily",
    BTN_SPINNER: "btn_spinner", BTN_CONVERT: "btn_convert", BTN_ORDER: "btn_order",
    "زدن کد": "btn_invite_enter", "زدن کد دعوت": "btn_invite_enter",
    "امتیاز": "btn_points", "امتیاز من": "btn_points",
    "کد دعوت": "btn_invite_show", "کد دعوت من": "btn_invite_show",
    "جایزه": "btn_daily", "جایزه روزانه": "btn_daily",
    "گردونه": "btn_spinner", "گردونه شانس": "btn_spinner",
    "تبدیل": "btn_convert", "تبدیل سکه": "btn_convert",
    "تبدیل سکه به آیتم": "btn_convert", "آیتم": "btn_convert",
    "سفارش": "btn_order", "خرید": "btn_order",
}

def get_button_id(message):
    try:
        candidates = []
        for attr in ("button_id", "buttonId", "callback_data", "callbackData",
                     "aux_data", "auxData", "raw_data", "rawData", "data"):
            try:
                v = getattr(message, attr, None)
                if v is not None: candidates.append(v)
            except: pass
        for v in candidates:
            if isinstance(v, str):
                s = v.strip()
                if s.startswith("btn_"): return s
                try: v = json.loads(v)
                except: continue
            if isinstance(v, dict):
                for k in ("button_id", "buttonId", "callback_data", "callbackData", "id"):
                    c = v.get(k)
                    if isinstance(c, (str, int)):
                        s = str(c).strip()
                        if s.startswith("btn_"): return s
                for k in ("data", "button", "payload", "aux_data", "auxData", "button_data", "callback_query"):
                    nv = v.get(k)
                    if isinstance(nv, str):
                        s = nv.strip()
                        if s.startswith("btn_"): return s
                        try: nv = json.loads(nv)
                        except: continue
                    if isinstance(nv, dict):
                        for kk in ("button_id", "buttonId", "id", "callback_data", "callbackData"):
                            c = nv.get(kk)
                            if isinstance(c, (str, int)):
                                s = str(c).strip()
                                if s.startswith("btn_"): return s
    except Exception as e: print(f"⚠️ btn_id: {e}", flush=True)
    return None

# ═══ متن‌ها ═══
def text_invite_show(uid):
    return (f"🎫 کد دعوت شما\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"`{get_or_create_code(uid)}`\n\n"
            f"💡 این کد رو به دوستانت بده.\n\n"
            f"🎁 هر کسی کدت رو بزنه: **+۱۵ امتیاز** برات\n"
            f"🎁 خودت هم وقتی کدشون رو بزنی: **+۱۰ امتیاز**\n\n"
            f"⭐ امتیاز فعلی: `{get_points(uid)}`\n\n⚡ FLUXBOT")

def text_points(uid):
    count = sum(1 for v in data["invited_users"].values() if v == str(uid))
    return (f"⭐ امتیاز من\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"💎 امتیاز: `{get_points(uid)}`\n"
            f"👥 دعوت‌شده: `{count}`\n"
            f"🎫 کد: `{get_or_create_code(uid)}`\n"
            f"🆔 شناسه: `{special_id(uid)}`\n\n⚡ FLUXBOT")

def text_daily_ok(pts, amount):
    return (f"🎁 جایزه روزانه!\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎉 تبریک! امروز **{amount}** امتیاز گرفتی!\n\n"
            f"💰 امتیاز کل: `{pts}`\n\n"
            f"⏰ جایزه بعدی: فردا\n\n⚡ FLUXBOT")

def text_daily_already():
    return ("🎁 جایزه روزانه\n━━━━━━━━━━━━━━━━━━━\n\n"
            "⏰ امروز جایزه‌ات رو گرفتی!\n\n"
            "📌 فردا دوباره بیا\n\n⚡ FLUXBOT")

def text_spinner_result(pts, amount):
    return (f"🎡 گردونه شانس!\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎉 گردونه چرخید و **{amount}** امتیاز بردی!\n\n"
            f"💰 امتیاز کل: `{pts}`\n\n⚡ FLUXBOT")

def text_spinner_cooldown(remain):
    return (f"🎡 گردونه شانس\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"⏰ فقط **{remain}** دیگه می‌تونی بچرخونی!\n\n"
            f"📌 صبور باش رفیق 🌱\n\n⚡ FLUXBOT")

def text_convert_menu(pts):
    lines = [
        "💎 تبدیل سکه به آیتم\n━━━━━━━━━━━━━━━━━━━\n",
        "با هر **۱۰ امتیاز**، یک آیتم کمیاب دلخواهت رو بگیر!\n",
        f"💰 امتیاز فعلی: `{pts}`\n",
        "━━━━━━━━━━━━━━━━━━━\n",
        "🎁 آیتم‌های موجود:\n",
    ]
    for i, (key, label) in enumerate(ITEMS, 1):
        lines.append(f"{i}️⃣ {label}")
    lines.append(f"\n📝 عدد آیتم مورد نظرت رو بفرست (1 تا {len(ITEMS)})")
    lines.append("💡 برای انصراف: «انصراف»")
    lines.append("\n⚡ FLUXBOT")
    return "\n".join(lines)

def text_convert_no_points(pts):
    return (f"💎 تبدیل سکه به آیتم\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ امتیاز کافی نداری!\n\n"
            f"💰 امتیاز فعلی: `{pts}`\n"
            f"🎯 حداقل لازم: `10`\n\n"
            f"💡 از «🎁 جایزه روزانه» یا «🎡 گردونه» امتیاز بگیر\n\n⚡ FLUXBOT")

def text_convert_ok(item_label, new_pts, inventory):
    inv_lines = [f"• {label} × {inventory.get(k, 0)}"
                 for k, label in ITEMS if inventory.get(k, 0) > 0]
    inv_text = "\n".join(inv_lines) if inv_lines else "📭 خالی"
    return (f"💎 تبریک! آیتم دریافت کردی\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎁 آیتم جدید: {item_label}\n\n"
            f"💰 امتیاز باقی‌مانده: `{new_pts}`\n\n"
            f"🗃️ آیتم‌های شما:\n{inv_text}\n\n⚡ FLUXBOT")

def text_convert_invalid():
    return (f"❌ عدد باید بین 1 تا {len(ITEMS)} باشد.\n\n"
            f"مثال: `3`\n\n⚡ FLUXBOT")

def text_order_prompt():
    return (f"🛒 ثبت سفارش\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"لطفاً سفارش خود را تایپ کنید.\n\n"
            f"⚠️ **(اول امتیاز خود را ببینید تا ببینید که امتیاز کافی برای دریافت ایتم رو دارید)**\n\n"
            f"در انتهای سفارش خود، **تعداد آیتم کمیاب** رو وارد کنید.\n\n"
            f"💡 **مثال:**\n"
            f"`من ۱ ماهی ، ۱ دارو و ۵ استیک میخوام 7`\n"
            f"(یعنی ۷ آیتم نیاز داری که میشه ۷۰ امتیاز)\n\n"
            f"💡 برای انصراف: «انصراف»\n⏱️ ۲ دقیقه فعال\n\n⚡ FLUXBOT")

def text_order_not_enough(pts, needed):
    return (f"🛒 ثبت سفارش\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"❌ موجودی کافی نیست!\n\n"
            f"💰 امتیاز فعلی شما: `{pts}`\n"
            f"🎯 امتیاز لازم برای این سفارش: `{needed}`\n\n"
            f"💡 از «🎁 جایزه روزانه» یا «🎡 گردونه» امتیاز بگیر\n\n⚡ FLUXBOT")

def text_order_success(pts, item_count):
    return (f"🛒 سفارش شما ثبت شد!\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ سفارش شما به مدیریت ارسال شد.\n"
            f"🔢 تعداد آیتم: `{item_count}`\n"
            f"💎 امتیاز کسر شده: `{item_count * ITEM_PRICE}`\n"
            f"💰 امتیاز باقی‌مانده: `{pts}`\n\n"
            f"⏳ منتظر پاسخ مدیریت باشید...\n\n⚡ FLUXBOT")

# ═══ State ═══
WAITING_INVITE = {}
WAITING_CONVERT = {}
WAITING_ORDER = {}

# ═══ پردازش کد دعوت ═══
async def process_invite(uid, code):
    code = str(code).strip()
    uid = str(uid)
    if uid in data["invited_users"]:
        return "❌ شما قبلاً کد دعوت وارد کرده‌اید!\n\n⚡ FLUXBOT"
    own = data["invite_codes"].get(uid)
    if own and own == code:
        return "❌ نمی‌توانید کد خودتان را وارد کنید!\n\n⚡ FLUXBOT"
    owner = data["code_to_user"].get(code)
    if not owner:
        return f"❌ کد `{code}` معتبر نیست.\n\n⚡ FLUXBOT"
    data["invited_users"][uid] = owner
    add_points(owner, 15)
    add_points(uid, 10)
    return (f"✅ تبریک!\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 صاحب کد: {display_name(owner)}\n\n"
            f"⭐ شما: **+۱۰ امتیاز**\n"
            f"⭐ صاحب کد: **+۱۵ امتیاز**\n\n"
            f"💰 امتیاز شما: `{get_points(uid)}`\n\n⚡ FLUXBOT")

# ═══ اجرای دکمه ═══
async def do_button(chat_id, uid, bid):
    uid = str(uid)

    if bid == "btn_invite_show":
        await bot.send_message(chat_id=chat_id, text=text_invite_show(uid))

    elif bid == "btn_invite_enter":
        WAITING_INVITE[uid] = time.time()
        WAITING_CONVERT.pop(uid, None)
        WAITING_ORDER.pop(uid, None)
        await bot.send_message(chat_id=chat_id, text=(
            "🎟️ زدن کد دعوت\n━━━━━━━━━━━━━━━━━━━\n\n"
            "کد ۶ رقمی خود را ارسال کنید.\n\n"
            "🎁 با وارد کردن کد:\n"
            "├ شما: +۱۰ امتیاز\n"
            "└ صاحب کد: +۱۵ امتیاز\n\n"
            "💡 برای لغو: «انصراف»\n⏱️ ۲ دقیقه فعال\n\n⚡ FLUXBOT"))

    elif bid == "btn_points":
        await bot.send_message(chat_id=chat_id, text=text_points(uid))

    elif bid == "btn_daily":
        today = today_str()
        if data["daily_rewards"].get(uid) == today:
            await bot.send_message(chat_id=chat_id, text=text_daily_already())
            return
        amount = random.randint(1, 20)
        data["daily_rewards"][uid] = today
        add_points(uid, amount)
        await bot.send_message(chat_id=chat_id, text=text_daily_ok(get_points(uid), amount))

    elif bid == "btn_spinner":
        now = time.time()
        last = data["spinner_last"].get(uid, 0)
        if now - last < SPIN_COOLDOWN:
            remain = int(SPIN_COOLDOWN - (now - last))
            hours = remain // 3600
            mins = (remain % 3600) // 60
            rem_str = f"{hours} ساعت و {mins} دقیقه" if hours > 0 else f"{mins} دقیقه"
            await bot.send_message(chat_id=chat_id, text=text_spinner_cooldown(rem_str))
            return
        data["spinner_last"][uid] = now
        save()
        await bot.send_message(chat_id=chat_id, text=(
            "🎡 گردونه در حال چرخش...\n\n"
            "⏳ صبر کن...\n\n"
            "✨ ▫️▫️▫️▫️▫️ ✨"))
        asyncio.create_task(spinner_task(chat_id, uid))

    elif bid == "btn_convert":
        pts = get_points(uid)
        if pts < ITEM_PRICE:
            await bot.send_message(chat_id=chat_id, text=text_convert_no_points(pts))
            return
        WAITING_CONVERT[uid] = time.time()
        WAITING_INVITE.pop(uid, None)
        WAITING_ORDER.pop(uid, None)
        await bot.send_message(chat_id=chat_id, text=text_convert_menu(pts))

    elif bid == "btn_order":
        WAITING_ORDER[uid] = time.time()
        WAITING_INVITE.pop(uid, None)
        WAITING_CONVERT.pop(uid, None)
        await bot.send_message(chat_id=chat_id, text=text_order_prompt())

async def spinner_task(chat_id, uid):
    try:
        await asyncio.sleep(5)
        amount = random.randint(1, 20)
        add_points(uid, amount)
        await bot.send_message(chat_id=chat_id, text=text_spinner_result(get_points(uid), amount))
    except Exception as e:
        print(f"⚠️ spinner task: {e}", flush=True)

async def send_menu(chat_id):
    kp = build_keypad()
    txt = "⚡ FLUXBOT\n\n🌟 خوش آمدید!\n\n👇 از منوی پایین انتخاب کنید:"
    if kp:
        try:
            await bot.send_message(chat_id=chat_id, text=txt, chat_keypad=kp, chat_keypad_type="New")
            return
        except: pass
    try: await bot.send_message(chat_id=chat_id, text=txt)
    except: pass

# ═══ استخراج نام فرستنده ═══
def _extract_sender_name(message):
    for attr in ("sender_name", "from_name", "first_name", "author", "sender_title"):
        try:
            v = getattr(message, attr, None)
            if v and isinstance(v, str): return v.strip()
        except: pass
    for attr in ("sender", "from_user", "user"):
        try:
            s = getattr(message, attr, None)
            if s is None: continue
            if isinstance(s, dict):
                for k in ("first_name", "name", "title"):
                    if s.get(k): return str(s[k]).strip()
            else:
                for k in ("first_name", "name", "title"):
                    v = getattr(s, k, None)
                    if v: return str(v).strip()
        except: pass
    return None

# ═══ هندلر اصلی ═══
@bot.on_message()
async def handle_message(bot, message):
    try:
        chat_id = str(message.chat_id) if message.chat_id else ""
        uid = str(message.sender_id) if message.sender_id else ""
        if not chat_id or not uid: return

        raw_text = ""
        try:
            t = getattr(message, "text", None)
            if t: raw_text = str(t).strip()
            else:
                cap = (getattr(message, "caption", None) or getattr(message, "text_caption", None) or "")
                if cap: raw_text = str(cap).strip()
        except: pass

        try: register(uid, _extract_sender_name(message))
        except: pass

        # ═══ ۱. بررسی پاسخ ادمین به سفارشات ═══
        if special_id(uid) == ADMIN_SPECIAL_ID:
            reply_mid = extract_reply_msg_id(message)
            if reply_mid and reply_mid in data["orders"]:
                customer_uid = data["orders"][reply_mid]
                if raw_text:
                    try:
                        await bot.send_message(chat_id=customer_uid, text=(
                            f"📩 **پاسخ به سفارش شما**\n━━━━━━━━━━━━━━━━━━━\n\n"
                            f"{raw_text}\n\n⚡ FLUXBOT"))
                        await bot.send_message(chat_id=chat_id, text="✅ پاسخ شما برای کاربر ارسال شد.",
                                               reply_to_message_id=message.message_id)
                    except Exception as e:
                        await bot.send_message(chat_id=chat_id, text=f"❌ خطا در ارسال: {e}",
                                               reply_to_message_id=message.message_id)
                    return

            # ═══ ۲. دستور حذف امتیاز (فقط برای ادمین) ═══
            m_del = re.match(r'^حذف\s+(\d+)\s+امتیاز\s+از\s+(FLUX-[A-F0-9]{8})$', raw_text, re.IGNORECASE)
            if m_del:
                amount = int(m_del.group(1))
                target_sid = m_del.group(2).upper()
                target_uid = None
                for u in data["users"]:
                    if special_id(u) == target_sid:
                        target_uid = u
                        break
                if not target_uid:
                    await bot.send_message(chat_id=chat_id, text="❌ کاربری با این شناسه یافت نشد.",
                                           reply_to_message_id=message.message_id)
                    return
                add_points(target_uid, -amount)
                await bot.send_message(chat_id=chat_id, text=(
                    f"✅ **امتیاز کسر شد**\n\n"
                    f"👤 کاربر: `{target_sid}`\n"
                    f"➖ کسر شده: `{amount}`\n"
                    f"💰 امتیاز جدید: `{get_points(target_uid)}`"),
                    reply_to_message_id=message.message_id)
                return

        # ═══ ۳. شناسه (در PV و گروه) ═══
        if raw_text in ("شناسه", "/شناسه", "شناسم", "آیدی من", "/id"):
            reply_uid = None
            try:
                rt = (getattr(message, 'reply_to_message', None) or getattr(message, 'reply_message', None) or getattr(message, 'reply_to', None))
                if rt:
                    if isinstance(rt, dict): reply_uid = rt.get('sender_id') or rt.get('user_id') or rt.get('from_id')
                    else: reply_uid = getattr(rt, 'sender_id', None) or getattr(rt, 'user_id', None) or getattr(rt, 'from_id', None)
            except: pass
            
            if reply_uid:
                text = f"🆔 شناسه کاربر\n━━━━━━━━━━━━━━━━━━━\n\n`{special_id(reply_uid)}`\n\n⚡ FLUXBOT"
            else:
                text = f"🆔 شناسه مخصوص شما\n━━━━━━━━━━━━━━━━━━━\n\n`{special_id(uid)}`\n\n💡 این شناسه منحصر به فرد توست.\n📌 برای دیدن شناسه دیگران، روی پیامشون ریپلای کن و بنویس `شناسه`\n\n⚡ FLUXBOT"
            await bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=message.message_id)
            return

        # ═══ بقیه فقط PV ═══
        if not is_private(chat_id): return

        # ═══ ۴. بررسی دکمه‌ها ═══
        bid = get_button_id(message)
        if bid:
            WAITING_INVITE.pop(uid, None)
            WAITING_CONVERT.pop(uid, None)
            WAITING_ORDER.pop(uid, None)
            try:
                await do_button(chat_id, uid, bid)
            except Exception as e:
                print(f"⚠️ button {bid}: {e}", flush=True)
            return

        # ═══ ۵. حالت انتظار ثبت سفارش ═══
        wait_ts = WAITING_ORDER.get(uid, 0)
        if wait_ts and time.time() - wait_ts < 120:
            if raw_text in ("انصراف", "لغو", "/cancel", "cancel"):
                WAITING_ORDER.pop(uid, None)
                await bot.send_message(chat_id=chat_id, text="✅ لغو شد.\n\n⚡ FLUXBOT")
                return
            
            m_num = re.search(r'(\d+)\s*$', raw_text)
            if m_num:
                item_count = int(m_num.group(1))
                cost = item_count * ITEM_PRICE
                user_pts = get_points(uid)
                
                if user_pts < cost:
                    WAITING_ORDER.pop(uid, None)
                    await bot.send_message(chat_id=chat_id, text=text_order_not_enough(user_pts, cost))
                    return
                
                # 🔧 استفاده مستقیم از OWNER_ID برای اطمینان از ارسال
                admin_uid = OWNER_ID 
                
                add_points(uid, -cost)
                WAITING_ORDER.pop(uid, None)

                admin_text = (
                    f"📥 **سفارش جدید**\n━━━━━━━━━━━━━━━━━━━\n\n"
                    f"👤 کاربر: {display_name(uid)}\n"
                    f"🆔 شناسه: `{special_id(uid)}`\n\n"
                    f"📝 **متن سفارش:**\n{raw_text}\n\n"
                    f"💰 **اطلاعات مالی:**\n"
                    f"🔢 تعداد آیتم: `{item_count}`\n"
                    f"💎 امتیاز کسر شده: `{cost}`\n\n"
                    f"💡 برای پاسخ، روی همین پیام ریپلای کنید.\n\n⚡ FLUXBOT"
                )
                
                try:
                    sent = await bot.send_message(chat_id=admin_uid, text=admin_text)
                    mid = extract_msg_id(sent)
                    
                    if mid:
                        data["orders"][mid] = uid
                        save()
                        
                    await bot.send_message(chat_id=chat_id, text=text_order_success(get_points(uid), item_count))
                except Exception as e:
                    add_points(uid, cost)
                    print(f"⚠️ Order forward error: {e}", flush=True)
                    await bot.send_message(chat_id=chat_id, text=f"❌ خطا در ارتباط با مدیریت. امتیاز بازگشت داده شد.\n(خطا: {e})")
                return
            else:
                await bot.send_message(chat_id=chat_id, text="⚠️ لطفاً در انتهای پیام خود تعداد آیتم‌ها را به عدد بنویسید.\nمثال: `... میخوام 5`")
                return

        # ═══ ۶. حالت انتظار کد دعوت ═══
        wait_ts = WAITING_INVITE.get(uid, 0)
        if wait_ts and time.time() - wait_ts < 120:
            if raw_text in ("انصراف", "لغو", "/cancel", "cancel"):
                WAITING_INVITE.pop(uid, None)
                await bot.send_message(chat_id=chat_id, text="✅ لغو شد.\n\n⚡ FLUXBOT")
                return
            m = re.match(r'^\s*(\d{6})\s*$', raw_text)
            if m:
                WAITING_INVITE.pop(uid, None)
                res = await process_invite(uid, m.group(1))
                await bot.send_message(chat_id=chat_id, text=res)
                return
            WAITING_INVITE.pop(uid, None)
            await bot.send_message(chat_id=chat_id, text="❌ کد باید دقیقاً ۶ رقم باشد.\n\n⚡ FLUXBOT")
            return

        # ═══ ۷. حالت انتظار انتخاب آیتم ═══
        wait_ts = WAITING_CONVERT.get(uid, 0)
        if wait_ts and time.time() - wait_ts < 120:
            if raw_text in ("انصراف", "لغو", "/cancel", "cancel"):
                WAITING_CONVERT.pop(uid, None)
                await bot.send_message(chat_id=chat_id, text="✅ لغو شد.\n\n⚡ FLUXBOT")
                return
            m = re.match(r'^\s*(\d+)\s*$', raw_text)
            if m:
                idx = int(m.group(1))
                if 1 <= idx <= len(ITEMS):
                    WAITING_CONVERT.pop(uid, None)
                    pts = get_points(uid)
                    if pts < ITEM_PRICE:
                        await bot.send_message(chat_id=chat_id, text=text_convert_no_points(pts))
                        return
                    add_points(uid, -ITEM_PRICE)
                    key, label = ITEMS[idx - 1]
                    inv = data["items"].setdefault(uid, {})
                    inv[key] = inv.get(key, 0) + 1
                    save()
                    await bot.send_message(chat_id=chat_id, text=text_convert_ok(label, get_points(uid), inv))
                    return
                else:
                    await bot.send_message(chat_id=chat_id, text=text_convert_invalid())
                    return
            WAITING_CONVERT.pop(uid, None)
            await bot.send_message(chat_id=chat_id, text="❌ ورودی نامعتبر. دوباره تلاش کن.\n\n⚡ FLUXBOT")
            return

        # ═══ ۸. تایپ متن دکمه ═══
        if raw_text in LABEL_TO_BID:
            try: await do_button(chat_id, uid, LABEL_TO_BID[raw_text])
            except Exception as e: print(f"⚠️ label: {e}", flush=True)
            return

        # ═══ ۹. هر پیام دیگر → منو ═══
        await send_menu(chat_id)

    except Exception as e:
        print(f"❌ HANDLER: {type(e).__name__}: {e}", flush=True)
        import traceback
        try: traceback.print_exc()
        except: pass

# ═══ پاک‌سازی ═══
async def cleanup_loop():
    while True:
        try:
            now = time.time()
            for d in (WAITING_INVITE, WAITING_CONVERT, WAITING_ORDER):
                for k in list(d.keys()):
                    if now - d[k] > 300:
                        d.pop(k, None)
        except: pass
        await asyncio.sleep(60)

# ═══ اجرا ═══
async def main():
    print("=" * 50, flush=True)
    print("🤖 FLUXBOT PV v4.1 STARTING...", flush=True)
    print(f"👑 ADMIN_ID: {ADMIN_SPECIAL_ID}", flush=True)
    print(f"👥 کاربران: {len(data['users'])}", flush=True)
    print("=" * 50, flush=True)

    try: asyncio.create_task(cleanup_loop())
    except: pass
    try:
        await bot.run()
    except Exception as e:
        print(f"❌ RUN ERROR: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
