# ═══════════════════════════════════════════════════════════════
# FLUXBOT PV v5.2 — تاریخ شمسی، تنظیم زمان دقیق و آپدیت همگانی
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
ADMIN_SPECIAL_ID = "FLUX-F834C581"
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))
SPIN_COOLDOWN = 86400
ITEM_PRICE = 10

# ═══ ابزار تبدیل تاریخ شمسی ═══
def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) - 80 + gd + g_d_m[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd

def jalali_to_gregorian(jy, jm, jd):
    if jy > 979:
        gy = 1600
        jy -= 979
    else:
        gy = 621
    days = (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + 78 + jd + ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186)
    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365: days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    sal_a = [0, 31, 29 if (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1
    return gy, gm, gd

def format_jalali(ts):
    dt = datetime.fromtimestamp(ts, tz=IRAN_TZ)
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    return f"{jy}/{jm:02d}/{jd:02d} - {dt.hour:02d}:{dt.minute:02d}"

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
    "orders": {}, "admin_chat_id": None,
    "phantom_wheel": {
        "participants": [], 
        "prize": "", 
        "end_time": 0
    }
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

def register(uid, name=None, chat_id=None):
    if not uid: return
    uid = str(uid)
    changed = False
    if uid not in data["users"]:
        data["users"].append(uid); changed = True
    
    ku = data["known_users"]
    if uid not in ku: ku[uid] = {}
    
    if name and ku[uid].get("name") != name:
        ku[uid]["name"] = name
        ku[uid]["last_seen"] = time.time()
        changed = True
    
    if chat_id and is_private(chat_id):
        if ku[uid].get("chat_id") != chat_id:
            ku[uid]["chat_id"] = chat_id
            changed = True
    
    if chat_id and special_id(uid) == ADMIN_SPECIAL_ID:
        if data.get("admin_chat_id") != chat_id:
            data["admin_chat_id"] = chat_id
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

def special_id(uid):
    h = hashlib.md5(str(uid).encode()).hexdigest()[:8].upper()
    return f"FLUX-{h}"

def extract_msg_id(result):
    try:
        if isinstance(result, dict):
            if "data" in result and isinstance(result["data"], dict):
                mid = result["data"].get("message_id")
                if mid: return str(mid)
            mid = result.get("message_id")
            if mid: return str(mid)
        elif hasattr(result, "message_id"): return str(result.message_id)
        elif hasattr(result, "id"): return str(result.id)
    except: pass
    return None

def extract_reply_msg_id(message):
    try:
        mid = getattr(message, 'reply_to_message_id', None)
        if mid: return str(mid)
        rt = (getattr(message, 'reply_to_message', None) or
              getattr(message, 'reply_message', None) or
              getattr(message, 'reply_to', None))
        if rt:
            if isinstance(rt, dict): mid = rt.get('message_id') or rt.get('id')
            else: mid = getattr(rt, 'message_id', None) or getattr(rt, 'id', None)
            if mid: return str(mid)
    except: pass
    return None

# ═══ آیتم‌ها ═══
ITEMS = [
    ("gem", "💎 الماس درخشان"), ("gold", "⚜️ نشان طلایی"),
    ("crown", "👑 تاج سلطنتی"), ("medal", "🎖️ مدال افتخار"),
    ("sapphire", "💠 نگین آبی"), ("staff", "🔱 عصای جادویی"),
    ("trophy", "🏆 جام قهرمانی"), ("star", "🌟 ستاره درخشان"),
]

# ═══ دکمه‌ها ═══
BTN_INVITE_ENTER = "🎟️ زدن کد دعوت"
BTN_POINTS       = "⭐ امتیاز من"
BTN_INVITE_SHOW  = "🎫 کد دعوت من"
BTN_DAILY        = "🎁 جایزه روزانه"
BTN_SPINNER      = "🎡 گردونه شانس"
BTN_CONVERT      = "💎 تبدیل سکه به آیتم"
BTN_ORDER        = "🛒 سفارش"
BTN_PHANTOM      = "🎰 گردونه فانتوم"

BTN_WHEEL_JOIN   = "🙋 شرکت در گردونه"
BTN_WHEEL_PRIZE  = "🎁 جایزه گردونه"
BTN_WHEEL_BACK   = "🔙 بازگشت به منو"

def get_main_keypad():
    try:
        b = ChatKeypadBuilder()
        b.row(b.button_simple(id="btn_invite_enter", text=BTN_INVITE_ENTER), b.button_simple(id="btn_points", text=BTN_POINTS))
        b.row(b.button_simple(id="btn_invite_show", text=BTN_INVITE_SHOW), b.button_simple(id="btn_daily", text=BTN_DAILY))
        b.row(b.button_simple(id="btn_spinner", text=BTN_SPINNER), b.button_simple(id="btn_convert", text=BTN_CONVERT))
        b.row(b.button_simple(id="btn_order", text=BTN_ORDER))
        b.row(b.button_simple(id="btn_phantom", text=BTN_PHANTOM))
        return b.build()
    except Exception as e:
        print(f"⚠️ keypad: {e}", flush=True)
        return None

def get_wheel_keypad():
    try:
        b = ChatKeypadBuilder()
        b.row(b.button_simple(id="btn_wheel_join", text=BTN_WHEEL_JOIN), b.button_simple(id="btn_wheel_prize", text=BTN_WHEEL_PRIZE))
        b.row(b.button_simple(id="btn_wheel_back", text=BTN_WHEEL_BACK))
        return b.build()
    except: return None

def get_start_keypad():
    try:
        b = ChatKeypadBuilder()
        b.row(b.button_simple(id="btn_start_again", text="🚀 /start"))
        return b.build()
    except: return None

LABEL_TO_BID = {
    BTN_INVITE_ENTER: "btn_invite_enter", BTN_POINTS: "btn_points",
    BTN_INVITE_SHOW: "btn_invite_show", BTN_DAILY: "btn_daily",
    BTN_SPINNER: "btn_spinner", BTN_CONVERT: "btn_convert", BTN_ORDER: "btn_order",
    BTN_PHANTOM: "btn_phantom", BTN_WHEEL_JOIN: "btn_wheel_join",
    BTN_WHEEL_PRIZE: "btn_wheel_prize", BTN_WHEEL_BACK: "btn_wheel_back"
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
    except: pass
    return None

# ═══ متن‌ها ═══
def text_invite_show(uid):
    return (f"🎫 کد دعوت شما\n━━━━━━━━━━━━━━━━━━━\n\n`{get_or_create_code(uid)}`\n\n"
            f"🎁 هر کسی کدت رو بزنه: **+۱۵ امتیاز** برات\n"
            f"🎁 خودت هم وقتی کدشون رو بزنی: **+۱۰ امتیاز**\n\n"
            f"⭐ امتیاز فعلی: `{get_points(uid)}`\n\n⚡ FLUXBOT")

def text_points(uid):
    count = sum(1 for v in data["invited_users"].values() if v == str(uid))
    return (f"⭐ امتیاز من\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"💎 امتیاز: `{get_points(uid)}`\n👥 دعوت‌شده: `{count}`\n"
            f"🎫 کد: `{get_or_create_code(uid)}`\n🆔 شناسه: `{special_id(uid)}`\n\n⚡ FLUXBOT")

def text_daily_ok(pts, amount):
    return (f"🎁 جایزه روزانه!\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎉 تبریک! امروز **{amount}** امتیاز گرفتی!\n\n"
            f"💰 امتیاز کل: `{pts}`\n⏰ جایزه بعدی: فردا\n\n⚡ FLUXBOT")

def text_daily_already():
    return ("🎁 جایزه روزانه\n━━━━━━━━━━━━━━━━━━━\n\n⏰ امروز جایزه‌ات رو گرفتی!\n\n📌 فردا دوباره بیا\n\n⚡ FLUXBOT")

def text_spinner_result(pts, amount):
    return (f"🎡 گردونه شانس!\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎉 گردونه چرخید و **{amount}** امتیاز بردی!\n\n💰 امتیاز کل: `{pts}`\n\n⚡ FLUXBOT")

def text_spinner_cooldown(remain):
    return (f"🎡 گردونه شانس\n━━━━━━━━━━━━━━━━━━━\n\n⏰ فقط **{remain}** دیگه می‌تونی بچرخونی!\n\n📌 صبور باش رفیق 🌱\n\n⚡ FLUXBOT")

def text_convert_menu(pts):
    lines = [f"💎 تبدیل سکه به آیتم\n━━━━━━━━━━━━━━━━━━━\n",
             f"با هر **۱۰ امتیاز**، یک آیتم کمیاب دلخواهت رو بگیر!\n",
             f"💰 امتیاز فعلی: `{pts}`\n",
             f"━━━━━━━━━━━━━━━━━━━\n🎁 آیتم‌های موجود:\n"]
    for i, (key, label) in enumerate(ITEMS, 1): lines.append(f"{i}️⃣ {label}")
    lines.append(f"\n📝 عدد آیتم مورد نظرت رو بفرست (1 تا {len(ITEMS)})")
    lines.append("💡 برای انصراف: «انصراف»\n\n⚡ FLUXBOT")
    return "\n".join(lines)

def text_convert_no_points(pts):
    return (f"💎 تبدیل سکه به آیتم\n━━━━━━━━━━━━━━━━━━━\n\n⚠️ امتیاز کافی نداری!\n\n"
            f"💰 امتیاز فعلی: `{pts}`\n🎯 حداقل لازم: `10`\n\n"
            f"💡 از «🎁 جایزه روزانه» یا «🎡 گردونه» امتیاز بگیر\n\n⚡ FLUXBOT")

def text_convert_ok(item_label, new_pts, inventory):
    inv_lines = [f"• {label} × {inventory.get(k, 0)}" for k, label in ITEMS if inventory.get(k, 0) > 0]
    inv_text = "\n".join(inv_lines) if inv_lines else "📭 خالی"
    return (f"💎 تبریک! آیتم دریافت کردی\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎁 آیتم جدید: {item_label}\n\n💰 امتیاز باقی‌مانده: `{new_pts}`\n\n"
            f"🗃️ آیتم‌های شما:\n{inv_text}\n\n⚡ FLUXBOT")

def text_order_prompt():
    return (f"🛒 ثبت سفارش\n━━━━━━━━━━━━━━━━━━━\n\nلطفاً سفارش خود را تایپ کنید.\n\n"
            f"⚠️ **(اول امتیاز خود را ببینید تا ببینید که امتیاز کافی برای دریافت ایتم رو دارید)**\n\n"
            f"در انتهای سفارش خود، **تعداد آیتم کمیاب** رو وارد کنید.\n\n"
            f"💡 **مثال:**\n`من ۱ ماهی ، ۱ دارو و ۵ استیک میخوام 7`\n"
            f"(یعنی ۷ آیتم نیاز داری که میشه ۷۰ امتیاز)\n\n"
            f"💡 برای انصراف: «انصراف»\n⏱️ ۲ دقیقه فعال\n\n⚡ FLUXBOT")

def text_order_not_enough(pts, needed):
    return (f"🛒 ثبت سفارش\n━━━━━━━━━━━━━━━━━━━\n\n❌ موجودی کافی نیست!\n\n"
            f"💰 امتیاز فعلی شما: `{pts}`\n🎯 امتیاز لازم برای این سفارش: `{needed}`\n\n"
            f"💡 از «🎁 جایزه روزانه» یا «🎡 گردونه» امتیاز بگیر\n\n⚡ FLUXBOT")

def text_order_success(pts, item_count):
    return (f"🛒 سفارش شما ثبت شد!\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ سفارش شما به مدیریت ارسال شد.\n🔢 تعداد آیتم: `{item_count}`\n"
            f"💎 امتیاز کسر شده: `{item_count * ITEM_PRICE}`\n"
            f"💰 امتیاز باقی‌مانده: `{pts}`\n\n⏳ منتظر پاسخ مدیریت باشید...\n\n⚡ FLUXBOT")

def text_phantom_wheel():
    wheel = data["phantom_wheel"]
    parts = wheel["participants"]
    end_time = wheel.get("end_time", 0)
    
    txt = "🎰 **گردونه فانتوم**\n━━━━━━━━━━━━━━━━━━━\n\n"
    
    if end_time > 0:
        txt += f"⏳ **زمان پایان:** {format_jalali(end_time)}\n"
    else:
        txt += "⏳ **زمان پایان:** هنوز تنظیم نشده\n"
        
    txt += f"\n👥 **لیست شرکت‌کنندگان ({len(parts)} نفر):**\n"
    if not parts:
        txt += "📭 هنوز کسی شرکت نکرده است.\n"
    else:
        for i, p in enumerate(parts, 1):
            txt += f"{i}. {p['name']} - {p['rubika_id']}\n"
            
    txt += "\n👇 برای شرکت روی دکمه زیر بزنید.\n\n⚡ FLUXBOT"
    return txt

# ═══ State ═══
WAITING_INVITE, WAITING_CONVERT, WAITING_ORDER = {}, {}, {}
WAITING_WHEEL_NAME, WAITING_WHEEL_ID = {}, {}

# ═══ تسک انتخاب برنده ═══
async def phantom_wheel_timer(end_time):
    try:
        now = time.time()
        if end_time <= now:
            return
        
        wait_sec = end_time - now
        await asyncio.sleep(wait_sec)
        
        if data["phantom_wheel"].get("end_time") != end_time:
            return
            
        parts = data["phantom_wheel"]["participants"]
        if not parts:
            data["phantom_wheel"]["end_time"] = 0
            save()
            return
            
        winner = random.choice(parts)
        prize = data["phantom_wheel"].get("prize", "").strip()
        prize_text = prize if prize else "⚠️ جایزه‌ای برای این دوره ثبت نشده بود."
        
        admin_chat = data.get("admin_chat_id")
        if admin_chat:
            try:
                await bot.send_message(chat_id=admin_chat, text=f"🏆 **برنده گردونه فانتوم انتخاب شد:**\n\n👤 {winner['name']} - {winner['rubika_id']}")
            except: pass
            
        broadcast_text = (
            f"🎉 **گردونه فانتوم به پایان رسید!** 🎉\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"🏆 برنده خوش‌شانس این دوره:\n"
            f"👤 **{winner['name']}** - {winner['rubika_id']}\n\n"
            f"🎁 **جایزه:**\n{prize_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ FLUXBOT"
        )
        
        for u, info in data["known_users"].items():
            cid = info.get("chat_id")
            if cid:
                try:
                    await bot.send_message(chat_id=cid, text=broadcast_text)
                    await asyncio.sleep(0.5)
                except: pass
                
        data["phantom_wheel"]["participants"] = []
        data["phantom_wheel"]["end_time"] = 0
        save()
        
    except Exception as e:
        print(f"❌ Wheel timer error: {e}", flush=True)

async def run_wheel_timer_check():
    end_time = data["phantom_wheel"].get("end_time", 0)
    if end_time > time.time():
        asyncio.create_task(phantom_wheel_timer(end_time))
        print(f"⏳ Wheel timer restored. Ends at {format_jalali(end_time)}", flush=True)

# ═══ پردازش‌ها ═══
async def process_invite(uid, code):
    code, uid = str(code).strip(), str(uid)
    if uid in data["invited_users"]: return "❌ شما قبلاً کد دعوت وارد کرده‌اید!\n\n⚡ FLUXBOT"
    if data["invite_codes"].get(uid) == code: return "❌ نمی‌توانید کد خودتان را وارد کنید!\n\n⚡ FLUXBOT"
    owner = data["code_to_user"].get(code)
    if not owner: return f"❌ کد `{code}` معتبر نیست.\n\n⚡ FLUXBOT"
    data["invited_users"][uid] = owner
    add_points(owner, 15); add_points(uid, 10)
    return (f"✅ تبریک!\n━━━━━━━━━━━━━━━━━━━\n\n👤 صاحب کد: {display_name(owner)}\n\n"
            f"⭐ شما: **+۱۰ امتیاز**\n⭐ صاحب کد: **+۱۵ امتیاز**\n\n"
            f"💰 امتیاز شما: `{get_points(uid)}`\n\n⚡ FLUXBOT")

async def do_button(chat_id, uid, bid):
    uid = str(uid)
    if bid == "btn_start_again":
        kp = get_main_keypad()
        await bot.send_message(chat_id=chat_id, text="⚡ FLUXBOT\n\n🌟 خوش آمدید!\n\n👇 از منوی پایین انتخاب کنید:", chat_keypad=kp, chat_keypad_type="New")
        return

    if bid == "btn_invite_show": await bot.send_message(chat_id=chat_id, text=text_invite_show(uid))
    elif bid == "btn_invite_enter":
        WAITING_INVITE[uid] = time.time(); WAITING_CONVERT.pop(uid, None); WAITING_ORDER.pop(uid, None)
        await bot.send_message(chat_id=chat_id, text=("🎟️ زدن کد دعوت\n━━━━━━━━━━━━━━━━━━━\n\n"
            "کد ۶ رقمی خود را ارسال کنید.\n\n🎁 با وارد کردن کد:\n├ شما: +۱۰ امتیاز\n└ صاحب کد: +۱۵ امتیاز\n\n"
            "💡 برای لغو: «انصراف»\n⏱️ ۲ دقیقه فعال\n\n⚡ FLUXBOT"))
    elif bid == "btn_points": await bot.send_message(chat_id=chat_id, text=text_points(uid))
    elif bid == "btn_daily":
        today = today_str()
        if data["daily_rewards"].get(uid) == today: await bot.send_message(chat_id=chat_id, text=text_daily_already()); return
        amount = random.randint(1, 20); data["daily_rewards"][uid] = today; add_points(uid, amount)
        await bot.send_message(chat_id=chat_id, text=text_daily_ok(get_points(uid), amount))
    elif bid == "btn_spinner":
        now = time.time(); last = data["spinner_last"].get(uid, 0)
        if now - last < SPIN_COOLDOWN:
            remain = int(SPIN_COOLDOWN - (now - last)); hours = remain // 3600; mins = (remain % 3600) // 60
            rem_str = f"{hours} ساعت و {mins} دقیقه" if hours > 0 else f"{mins} دقیقه"
            await bot.send_message(chat_id=chat_id, text=text_spinner_cooldown(rem_str)); return
        data["spinner_last"][uid] = now; save()
        await bot.send_message(chat_id=chat_id, text="🎡 گردونه در حال چرخش...\n\n⏳ صبر کن...\n\n✨ ▫️▫️▫️▫️▫️ ✨")
        asyncio.create_task(spinner_task(chat_id, uid))
    elif bid == "btn_convert":
        pts = get_points(uid)
        if pts < ITEM_PRICE: await bot.send_message(chat_id=chat_id, text=text_convert_no_points(pts)); return
        WAITING_CONVERT[uid] = time.time(); WAITING_INVITE.pop(uid, None); WAITING_ORDER.pop(uid, None)
        await bot.send_message(chat_id=chat_id, text=text_convert_menu(pts))
    elif bid == "btn_order":
        WAITING_ORDER[uid] = time.time(); WAITING_INVITE.pop(uid, None); WAITING_CONVERT.pop(uid, None)
        await bot.send_message(chat_id=chat_id, text=text_order_prompt())
        
    elif bid == "btn_phantom":
        kp = get_wheel_keypad()
        await bot.send_message(chat_id=chat_id, text=text_phantom_wheel(), chat_keypad=kp, chat_keypad_type="New")
        
    elif bid == "btn_wheel_join":
        WAITING_WHEEL_NAME[uid] = time.time()
        WAITING_WHEEL_ID.pop(uid, None)
        await bot.send_message(chat_id=chat_id, text="📝 لطفاً **نام خود** را وارد کنید:")
        
    elif bid == "btn_wheel_prize":
        prize = data["phantom_wheel"].get("prize", "").strip()
        if not prize:
            await bot.send_message(chat_id=chat_id, text="🎁 **جایزه گردونه فانتوم:**\n━━━━━━━━━━━━━━━━━━━\n\n⚠️ هنوز جایزه‌ای ثبت نشده است.\n\n⚡ FLUXBOT")
        else:
            await bot.send_message(chat_id=chat_id, text=f"🎁 **جایزه گردونه فانتوم:**\n━━━━━━━━━━━━━━━━━━━\n\n{prize}\n\n⚡ FLUXBOT")
        
    elif bid == "btn_wheel_back":
        kp = get_main_keypad()
        await bot.send_message(chat_id=chat_id, text="⚡ FLUXBOT\n\n🌟 به منوی اصلی بازگشتید.\n\n👇 انتخاب کنید:", chat_keypad=kp, chat_keypad_type="New")

async def spinner_task(chat_id, uid):
    try:
        await asyncio.sleep(5); amount = random.randint(1, 20); add_points(uid, amount)
        await bot.send_message(chat_id=chat_id, text=text_spinner_result(get_points(uid), amount))
    except: pass

def _extract_sender_name(message):
    for attr in ("sender_name", "from_name", "first_name", "author"):
        try:
            v = getattr(message, attr, None)
            if v and isinstance(v, str): return v.strip()
        except: pass
    return None

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

        try: register(uid, _extract_sender_name(message), chat_id)
        except: pass

        # ═══ پنل ادمین ═══
        if special_id(uid) == ADMIN_SPECIAL_ID:
            reply_mid = extract_reply_msg_id(message)
            if reply_mid and reply_mid in data["orders"]:
                order_data = data["orders"][reply_mid]
                target_chat = order_data.get("chat_id") if isinstance(order_data, dict) else None
                if raw_text and target_chat:
                    try:
                        await bot.send_message(chat_id=target_chat, text=(f"📩 **پاسخ به سفارش شما**\n━━━━━━━━━━━━━━━━━━━\n\n{raw_text}\n\n⚡ FLUXBOT"))
                        await bot.send_message(chat_id=chat_id, text="✅ پاسخ شما برای کاربر ارسال شد.", reply_to_message_id=message.message_id)
                    except Exception as e:
                        await bot.send_message(chat_id=chat_id, text=f"❌ خطا در ارسال: {e}", reply_to_message_id=message.message_id)
                    return

            m_del = re.match(r'^حذف\s+(\d+)\s+امتیاز\s+از\s+(FLUX-[A-F0-9]{8})$', raw_text, re.IGNORECASE)
            if m_del:
                amount = int(m_del.group(1)); target_sid = m_del.group(2).upper()
                target_uid = next((u for u in data["users"] if special_id(u) == target_sid), None)
                if not target_uid:
                    await bot.send_message(chat_id=chat_id, text="❌ کاربری با این شناسه یافت نشد.", reply_to_message_id=message.message_id); return
                add_points(target_uid, -amount)
                await bot.send_message(chat_id=chat_id, text=(f"✅ **امتیاز کسر شد**\n\n👤 کاربر: `{target_sid}`\n➖ کسر شده: `{amount}`\n💰 امتیاز جدید: `{get_points(target_uid)}`"), reply_to_message_id=message.message_id)
                return
                
            if raw_text == "آپدیت":
                b_text = ("🚀 **نسخه جدید ربات آماده است!** 🚀\n━━━━━━━━━━━━━━━━━━━\n\n"
                          "دوستان عزیز، امکانات جدید و هیجان‌انگیزی به ربات اضافه شده است.\n\n"
                          "🌟 برای استفاده از منوی جدید، روی دکمه زیر بزنید:")
                success, failed = 0, 0
                status_msg = await bot.send_message(chat_id=chat_id, text="⏳ در حال ارسال همگانی...")
                start_kp = get_start_keypad()
                for u in data["users"]:
                    info = data["known_users"].get(u, {})
                    cid = info.get("chat_id")
                    if cid:
                        try:
                            # ارسال همراه با دکمه استارت
                            await bot.send_message(chat_id=cid, text=b_text, chat_keypad=start_kp, chat_keypad_type="New")
                            success += 1
                            await asyncio.sleep(0.2)
                        except: failed += 1
                try: await bot.delete_message(chat_id=chat_id, message_id=extract_msg_id(status_msg))
                except: pass
                await bot.send_message(chat_id=chat_id, text=f"✅ **ارسال همگانی انجام شد.**\nموفق: {success}\nناموفق: {failed}")
                return

            m_remove = re.match(r'^حذف\s+(\d+)$', raw_text)
            if m_remove:
                idx = int(m_remove.group(1))
                parts = data["phantom_wheel"]["participants"]
                if 1 <= idx <= len(parts):
                    removed = parts.pop(idx - 1)
                    save()
                    await bot.send_message(chat_id=chat_id, text=f"✅ کاربر **{removed['name']}** از گردونه حذف شد.", reply_to_message_id=message.message_id)
                else:
                    await bot.send_message(chat_id=chat_id, text="❌ شماره وارد شده در لیست وجود ندارد.", reply_to_message_id=message.message_id)
                return

            m_prize = re.match(r'^تغییر جایزه به ([\s\S]+)$', raw_text)
            if m_prize:
                new_prize = m_prize.group(1).strip()
                data["phantom_wheel"]["prize"] = new_prize
                save()
                await bot.send_message(chat_id=chat_id, text=f"✅ جایزه گردونه با موفقیت تغییر کرد:\n\n{new_prize}", reply_to_message_id=message.message_id)
                return

            # ═══ تنظیم زمان پایان (ساعت یا تاریخ دقیق شمسی) ═══
            m_end = re.match(r'^پایان گردونه فانتوم ([\s\S]+)$', raw_text)
            if m_end:
                time_str = m_end.group(1).strip()
                end_time = 0
                
                # حالت ۱: تاریخ کامل شمسی (مثلا 1405/08/20 18:00)
                m_date = re.match(r'^(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})$', time_str)
                if m_date:
                    jy, jm, jd, hour, minute = map(int, m_date.groups())
                    try:
                        gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
                        dt = datetime(gy, gm, gd, hour, minute, tzinfo=IRAN_TZ)
                        end_time = dt.timestamp()
                    except Exception as e:
                        await bot.send_message(chat_id=chat_id, text=f"❌ تاریخ نامعتبر است: {e}", reply_to_message_id=message.message_id)
                        return
                # حالت ۲: ساعت (مثلا 5)
                elif time_str.isdigit():
                    end_time = time.time() + int(time_str) * 3600
                # حالت ۳: دقیقه (برای تست)
                elif "دقیقه" in time_str:
                    nums = re.findall(r'\d+', time_str)
                    if nums: end_time = time.time() + int(nums[0]) * 60
                
                if end_time > 0:
                    if end_time <= time.time():
                        await bot.send_message(chat_id=chat_id, text="❌ زمان وارد شده در گذشته است!", reply_to_message_id=message.message_id)
                        return
                        
                    data["phantom_wheel"]["end_time"] = end_time
                    save()
                    asyncio.create_task(phantom_wheel_timer(end_time))
                    
                    await bot.send_message(chat_id=chat_id, text=(f"✅ **زمان پایان تنظیم شد.**\n\n⏳ پایان در: {format_jalali(end_time)}\n\nربات به صورت خودکار در این زمان برنده را انتخاب می‌کند."), reply_to_message_id=message.message_id)
                else:
                    await bot.send_message(chat_id=chat_id, text="❌ فرمت زمان نامعتبر است.\nمثال ساعت: `پایان گردونه فانتوم 5`\nمثال تاریخ: `پایان گردونه فانتوم 1405/08/20 18:00`", reply_to_message_id=message.message_id)
                return

        # ═══ شناسه ═══
        if raw_text in ("شناسه", "/شناسه", "شناسم", "آیدی من", "/id"):
            reply_uid = None
            try:
                rt = (getattr(message, 'reply_to_message', None) or getattr(message, 'reply_message', None) or getattr(message, 'reply_to', None))
                if rt:
                    if isinstance(rt, dict): reply_uid = rt.get('sender_id') or rt.get('user_id') or rt.get('from_id')
                    else: reply_uid = getattr(rt, 'sender_id', None) or getattr(rt, 'user_id', None) or getattr(rt, 'from_id', None)
            except: pass
            if reply_uid: text = f"🆔 شناسه کاربر\n━━━━━━━━━━━━━━━━━━━\n\n`{special_id(reply_uid)}`\n\n⚡ FLUXBOT"
            else: text = f"🆔 شناسه مخصوص شما\n━━━━━━━━━━━━━━━━━━━\n\n`{special_id(uid)}`\n\n💡 برای دیدن شناسه دیگران، روی پیامشون ریپلای کن و بنویس `شناسه`\n\n⚡ FLUXBOT"
            await bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=message.message_id); return

        if not is_private(chat_id): return

        # ═══ دکمه‌ها ═══
        bid = get_button_id(message)
        if bid:
            WAITING_INVITE.pop(uid, None); WAITING_CONVERT.pop(uid, None); WAITING_ORDER.pop(uid, None)
            WAITING_WHEEL_NAME.pop(uid, None); WAITING_WHEEL_ID.pop(uid, None)
            try: await do_button(chat_id, uid, bid)
            except Exception as e: print(f"⚠️ button {bid}: {e}", flush=True)
            return

        # ═══ ثبت‌نام گردونه - نام ═══
        wait_name = WAITING_WHEEL_NAME.get(uid, 0)
        if wait_name and time.time() - wait_name < 120:
            if raw_text in ("انصراف", "لغو"):
                WAITING_WHEEL_NAME.pop(uid, None)
                await bot.send_message(chat_id=chat_id, text="✅ لغو شد.\n\n⚡ FLUXBOT"); return
            
            WAITING_WHEEL_NAME.pop(uid, None)
            WAITING_WHEEL_ID[uid] = {"name": raw_text, "ts": time.time()}
            await bot.send_message(chat_id=chat_id, text="✅ ثبت شد.\n\nحالا **آیدی روبیکا** خود را وارد کنید (مثال: `@arastoo`):")
            return

        # ═══ ثبت‌نام گردونه - آیدی ═══
        wait_id = WAITING_WHEEL_ID.get(uid)
        if wait_id and time.time() - wait_id["ts"] < 120:
            if raw_text in ("انصراف", "لغو"):
                WAITING_WHEEL_ID.pop(uid, None)
                await bot.send_message(chat_id=chat_id, text="✅ لغو شد.\n\n⚡ FLUXBOT"); return
                
            if not raw_text.startswith("@"):
                await bot.send_message(chat_id=chat_id, text="❌ آیدی نامعتبر است. حتماً باید با `@` شروع شود. دوباره وارد کنید:")
                return
                
            name = wait_id["name"]
            rubika_id = raw_text
            WAITING_WHEEL_ID.pop(uid, None)
            
            parts = data["phantom_wheel"]["participants"]
            if any(p["uid"] == uid for p in parts):
                await bot.send_message(chat_id=chat_id, text="⚠️ شما قبلاً در این گردونه ثبت‌نام کرده‌اید!\n\n⚡ FLUXBOT")
                return
                
            parts.append({"uid": uid, "name": name, "rubika_id": rubika_id})
            save()
            
            kp = get_wheel_keypad()
            await bot.send_message(chat_id=chat_id, text=f"🎉 **ثبت‌نام شما با موفقیت انجام شد!**\n\n👤 نام: {name}\n🆔 آیدی: {rubika_id}\n\nموفق باشید! 🍀", chat_keypad=kp, chat_keypad_type="New")
            return

        # ═══ ثبت سفارش ═══
        wait_ts = WAITING_ORDER.get(uid, 0)
        if wait_ts and time.time() - wait_ts < 120:
            if raw_text in ("انصراف", "لغو", "/cancel"): WAITING_ORDER.pop(uid, None); await bot.send_message(chat_id=chat_id, text="✅ لغو شد.\n\n⚡ FLUXBOT"); return
            m_num = re.search(r'(\d+)\s*$', raw_text)
            if m_num:
                item_count = int(m_num.group(1)); cost = item_count * ITEM_PRICE; user_pts = get_points(uid)
                if user_pts < cost: WAITING_ORDER.pop(uid, None); await bot.send_message(chat_id=chat_id, text=text_order_not_enough(user_pts, cost)); return
                
                admin_chat = data.get("admin_chat_id")
                if not admin_chat:
                    await bot.send_message(chat_id=chat_id, text="❌ خطا: مدیر یافت نشد."); return

                add_points(uid, -cost); WAITING_ORDER.pop(uid, None)
                admin_text = (f"📥 **سفارش جدید**\n━━━━━━━━━━━━━━━━━━━\n\n👤 کاربر: {display_name(uid)}\n"
                    f"🆔 شناسه: `{special_id(uid)}`\n\n📝 **متن سفارش:**\n{raw_text}\n\n"
                    f"💰 **اطلاعات مالی:**\n🔢 تعداد آیتم: `{item_count}`\n💎 امتیاز کسر شده: `{cost}`\n\n"
                    f"💡 برای پاسخ، روی همین پیام ریپلای کنید.\n\n⚡ FLUXBOT")
                try:
                    sent = await bot.send_message(chat_id=admin_chat, text=admin_text)
                    mid = extract_msg_id(sent)
                    if mid:
                        data["orders"][mid] = {"uid": uid, "chat_id": chat_id, "name": display_name(uid)}
                        save()
                    await bot.send_message(chat_id=chat_id, text=text_order_success(get_points(uid), item_count))
                except Exception as e:
                    add_points(uid, cost); print(f"⚠️ Order forward error: {e}", flush=True)
                    await bot.send_message(chat_id=chat_id, text=f"❌ خطا در ارتباط با مدیریت. امتیاز بازگشت داده شد.\n(خطا: {e})")
                return
            else: await bot.send_message(chat_id=chat_id, text="⚠️ لطفاً در انتهای پیام خود تعداد آیتم‌ها را به عدد بنویسید.\nمثال: `... میخوام 5`"); return

        # ═══ زدن کد دعوت ═══
        wait_ts = WAITING_INVITE.get(uid, 0)
        if wait_ts and time.time() - wait_ts < 120:
            if raw_text in ("انصراف", "لغو", "/cancel"): WAITING_INVITE.pop(uid, None); await bot.send_message(chat_id=chat_id, text="✅ لغو شد.\n\n⚡ FLUXBOT"); return
            m = re.match(r'^\s*(\d{6})\s*$', raw_text)
            if m:
                WAITING_INVITE.pop(uid, None); res = await process_invite(uid, m.group(1)); await bot.send_message(chat_id=chat_id, text=res); return
            WAITING_INVITE.pop(uid, None); await bot.send_message(chat_id=chat_id, text="❌ کد باید دقیقاً ۶ رقم باشد.\n\n⚡ FLUXBOT"); return

        # ═══ تبدیل سکه ═══
        wait_ts = WAITING_CONVERT.get(uid, 0)
        if wait_ts and time.time() - wait_ts < 120:
            if raw_text in ("انصراف", "لغو", "/cancel"): WAITING_CONVERT.pop(uid, None); await bot.send_message(chat_id=chat_id, text="✅ لغو شد.\n\n⚡ FLUXBOT"); return
            m = re.match(r'^\s*(\d+)\s*$', raw_text)
            if m:
                idx = int(m.group(1))
                if 1 <= idx <= len(ITEMS):
                    WAITING_CONVERT.pop(uid, None); pts = get_points(uid)
                    if pts < ITEM_PRICE: await bot.send_message(chat_id=chat_id, text=text_convert_no_points(pts)); return
                    add_points(uid, -ITEM_PRICE); key, label = ITEMS[idx - 1]
                    inv = data["items"].setdefault(uid, {}); inv[key] = inv.get(key, 0) + 1; save()
                    await bot.send_message(chat_id=chat_id, text=text_convert_ok(label, get_points(uid), inv)); return
                else: await bot.send_message(chat_id=chat_id, text=f"❌ عدد باید بین 1 تا {len(ITEMS)} باشد."); return
            WAITING_CONVERT.pop(uid, None); await bot.send_message(chat_id=chat_id, text="❌ ورودی نامعتبر. دوباره تلاش کن.\n\n⚡ FLUXBOT"); return

        if raw_text in LABEL_TO_BID:
            try: await do_button(chat_id, uid, LABEL_TO_BID[raw_text])
            except: pass
            return

        kp = get_main_keypad()
        await bot.send_message(chat_id=chat_id, text="⚡ FLUXBOT\n\n🌟 خوش آمدید!\n\n👇 از منوی پایین انتخاب کنید:", chat_keypad=kp, chat_keypad_type="New")

    except Exception as e:
        print(f"❌ HANDLER: {type(e).__name__}: {e}", flush=True)

async def cleanup_loop():
    while True:
        try:
            now = time.time()
            for d in (WAITING_INVITE, WAITING_CONVERT, WAITING_ORDER, WAITING_WHEEL_NAME):
                for k in list(d.keys()):
                    if now - d[k] > 300: d.pop(k, None)
            for k in list(WAITING_WHEEL_ID.keys()):
                if now - WAITING_WHEEL_ID[k]["ts"] > 300: WAITING_WHEEL_ID.pop(k, None)
        except: pass
        await asyncio.sleep(60)

async def main():
    print("=" * 50, flush=True)
    print("🤖 FLUXBOT PV v5.2 STARTING...", flush=True)
    print(f"👑 ADMIN: {ADMIN_SPECIAL_ID}", flush=True)
    try: asyncio.create_task(cleanup_loop())
    except: pass
    try: asyncio.create_task(run_wheel_timer_check())
    except: pass
    try: await bot.run()
    except Exception as e: print(f"❌ RUN ERROR: {type(e).__name__}: {e}", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
