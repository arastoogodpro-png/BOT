# ═══════════════════════════════════════════════════════════════
# FLUXBOT PV v3 — دکمه‌های پیوی + جایزه + گردونه + تبدیل سکه
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
CHANNEL = "@RPCITY_PHANTOM"
DEV = "@arastoo_ff"
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))
SPIN_COOLDOWN = 60  # ثانیه — ضد اسپم گردونه

# ═══ ذخیره‌سازی ═══
DATA_PATHS = ["/data/bot_data.json", "/app/data/bot_data.json",
              "/tmp/bot_data.json", "./bot_data.json"]
for _p in ["/data", "/app/data", "/tmp"]:
    try: os.makedirs(_p, exist_ok=True)
    except: pass

DEFAULTS = {
    "users": [], "known_users": {}, "invite_codes": {},
    "code_to_user": {}, "invited_users": {}, "points": {},
    "daily_rewards": {}, "spinner_last": {}, "items": {},
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
            return
        except: pass

data = _read()
for k, v in DEFAULTS.items():
    if k not in data or not isinstance(data[k], type(v)):
        data[k] = v.copy() if isinstance(v, (dict, list)) else v

def save(): _write(data)

# ═══ Helpers ═══
def today_str():
    return datetime.now(IRAN_TZ).strftime("%Y-%m-%d")

def is_group(cid):
    return bool(cid) and str(cid).lower().startswith("g")

def is_private(cid):
    return bool(cid) and not is_group(cid)

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
    if uid not in data["users"]:
        data["users"].append(uid); save()
    if name:
        ku = data["known_users"]
        if uid not in ku: ku[uid] = {}
        if ku[uid].get("name") != name:
            ku[uid]["name"] = name
            ku[uid]["last_seen"] = time.time()
            save()

def get_points(uid): return data["points"].get(str(uid), 0)

def add_points(uid, amount):
    uid = str(uid)
    data["points"][uid] = data["points"].get(uid, 0) + amount
    save()

def get_or_create_code(uid):
    uid = str(uid)
    if uid in data["invite_codes"]:
        code = data["invite_codes"][uid]
        data["code_to_user"][code] = uid
        return code
    existing = set(data["invite_codes"].values())
    code = str(random.randint(100000, 999999))
    for _ in range(200):
        if code not in existing: break
        code = str(random.randint(100000, 999999))
    data["invite_codes"][uid] = code
    data["code_to_user"][code] = uid
    save()
    return code

def special_id(uid):
    h = hashlib.md5(str(uid).encode()).hexdigest()[:8].upper()
    return f"FLUX-{h}"

# ═══ آیتم‌های کمیاب ═══
ITEMS = [
    ("gem",       "💎 الماس درخشان"),
    ("gold",      "⚜️ نشان طلایی"),
    ("crown",     "👑 تاج سلطنتی"),
    ("medal",     "🎖️ مدال افتخار"),
    ("sapphire",  "💠 نگین آبی"),
    ("staff",     "🔱 عصای جادویی"),
    ("trophy",    "🏆 جام قهرمانی"),
    ("star",      "🌟 ستاره درخشان"),
]

# ═══ دکمه‌ها ═══
BTN_INVITE_ENTER = "🎟️ زدن کد دعوت"
BTN_POINTS       = "⭐ امتیاز من"
BTN_INVITE_SHOW  = "🎫 کد دعوت من"
BTN_DAILY        = "🎁 جایزه روزانه"
BTN_SPINNER      = "🎡 گردونه شانس"
BTN_CONVERT      = "💎 تبدیل سکه به آیتم"

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
            pair = BUTTONS[i:i+2]
            made = [b.button_simple(id=bid, text=txt) for bid, txt in pair]
            if len(made) == 2: b.row(made[0], made[1])
            else: b.row(made[0])
        return b.build()
    except Exception as e:
        print(f"⚠️ keypad: {e}", flush=True)
        return None

LABEL_TO_BID = {
    BTN_INVITE_ENTER: "btn_invite_enter", BTN_POINTS: "btn_points",
    BTN_INVITE_SHOW: "btn_invite_show", BTN_DAILY: "btn_daily",
    BTN_SPINNER: "btn_spinner", BTN_CONVERT: "btn_convert",
    "زدن کد": "btn_invite_enter", "زدن کد دعوت": "btn_invite_enter",
    "امتیاز": "btn_points", "امتیاز من": "btn_points",
    "کد دعوت": "btn_invite_show", "کد دعوت من": "btn_invite_show",
    "جایزه": "btn_daily", "جایزه روزانه": "btn_daily",
    "گردونه": "btn_spinner", "گردونه شانس": "btn_spinner",
    "تبدیل": "btn_convert", "تبدیل سکه": "btn_convert",
    "تبدیل سکه به آیتم": "btn_convert", "آیتم": "btn_convert",
}

def get_button_id(message):
    try:
        for attr in ("button_id", "buttonId", "callback_data", "callbackData",
                     "aux_data", "auxData", "raw_data", "rawData", "data"):
            v = getattr(message, attr, None)
            if v is None: continue
            if isinstance(v, str):
                try: v = json.loads(v)
                except: continue
            if not isinstance(v, dict): continue
            for k in ("button_id", "buttonId", "callback_data", "callbackData", "id"):
                c = v.get(k)
                if isinstance(c, (str, int)) and str(c).startswith("btn_"):
                    return str(c)
            for k in ("data", "button", "payload", "aux_data", "auxData", "button_data"):
                nv = v.get(k)
                if isinstance(nv, str):
                    try: nv = json.loads(nv)
                    except: continue
                if isinstance(nv, dict):
                    for kk in ("button_id", "buttonId", "id", "callback_data", "callbackData"):
                        c = nv.get(kk)
                        if isinstance(c, (str, int)) and str(c).startswith("btn_"):
                            return str(c)
    except: pass
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
            f"🆔 شناسه: `{special_id(uid)}`\n\n"
            f"⚡ FLUXBOT")

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
            f"⏰ فقط **{remain}** ثانیه دیگه می‌تونی بچرخونی!\n\n"
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

def text_shenase(uid, is_self=True):
    if is_self:
        return (f"🆔 شناسه مخصوص شما\n━━━━━━━━━━━━━━━━━━━\n\n"
                f"`{special_id(uid)}`\n\n"
                f"💡 این شناسه منحصر به فرد توست.\n"
                f"📌 برای دیدن شناسه دیگران، روی پیامشون ریپلای کن و بنویس `شناسه`\n\n⚡ FLUXBOT")
    return (f"🆔 شناسه کاربر\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"`{special_id(uid)}`\n\n⚡ FLUXBOT")

# ═══ State ═══
WAITING_INVITE = {}
WAITING_CONVERT = {}

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
    add_points(owner, 15)   # صاحب کد: +۱۵
    add_points(uid, 10)     # واردکننده: +۱۰
    return (f"✅ تبریک!\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 صاحب کد: {display_name(owner)}\n\n"
            f"⭐ شما: **+۱۰ امتیاز**\n"
            f"⭐ صاحب کد: **+۱۵ امتیاز**\n\n"
            f"💰 امتیاز شما: `{get_points(uid)}`\n\n⚡ FLUXBOT")

# ═══ دکمه‌ها ═══
async def do_button(chat_id, uid, bid):
    uid = str(uid)

    if bid == "btn_invite_show":
        await bot.send_message(chat_id=chat_id, text=text_invite_show(uid))

    elif bid == "btn_invite_enter":
        WAITING_INVITE[uid] = time.time()
        WAITING_CONVERT.pop(uid, None)
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
            await bot.send_message(chat_id=chat_id, text=text_spinner_cooldown(remain))
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
        if pts < 10:
            await bot.send_message(chat_id=chat_id, text=text_convert_no_points(pts))
            return
        WAITING_CONVERT[uid] = time.time()
        WAITING_INVITE.pop(uid, None)
        await bot.send_message(chat_id=chat_id, text=text_convert_menu(pts))

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
            await bot.send_message(chat_id=chat_id, text=txt,
                                   chat_keypad=kp, chat_keypad_type="New")
            return
        except Exception as e:
            print(f"⚠️ send keypad: {e}", flush=True)
    try:
        await bot.send_message(chat_id=chat_id, text=txt)
    except Exception as e:
        print(f"⚠️ send plain: {e}", flush=True)

# ═══ استخراج اطلاعات ═══
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

def extract_reply_sender(message):
    try:
        rt = (getattr(message, 'reply_to_message', None) or
              getattr(message, 'reply_message', None) or
              getattr(message, 'reply_to', None))
        if rt:
            for attr in ("sender_id", "user_id", "from_id"):
                v = getattr(rt, attr, None)
                if v: return str(v)
            if isinstance(rt, dict):
                for k in ("sender_id", "user_id", "from_id"):
                    if rt.get(k): return str(rt[k])
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
                cap = (getattr(message, "caption", None) or
                       getattr(message, "text_caption", None) or "")
                if cap: raw_text = str(cap).strip()
        except: pass

        try: register(uid, _extract_sender_name(message))
        except: pass

        # ═══ شناسه — در PV و گروه کار می‌کند (متنی، بدون دکمه) ═══
        if raw_text in ("شناسه", "/شناسه", "شناسم", "آیدی من", "/id"):
            try:
                reply_uid = extract_reply_sender(message)
                if reply_uid:
                    text = text_shenase(reply_uid, is_self=(reply_uid == uid))
                else:
                    text = text_shenase(uid, is_self=True)
                await bot.send_message(chat_id=chat_id, text=text,
                                       reply_to_message_id=message.message_id)
            except Exception as e:
                print(f"⚠️ shenase: {e}", flush=True)
            return

        # ═══ بقیه فقط PV ═══
        if not is_private(chat_id):
            return

        # ۱) دکمه
        bid = get_button_id(message)
        if bid:
            WAITING_INVITE.pop(uid, None)
            WAITING_CONVERT.pop(uid, None)
            try:
                await do_button(chat_id, uid, bid)
            except Exception as e:
                print(f"⚠️ button {bid}: {e}", flush=True)
                try:
                    await bot.send_message(chat_id=chat_id,
                        text="⚠️ خطا رخ داد. دوباره امتحان کن.\n\n⚡ FLUXBOT")
                except: pass
            return

        # ۲) انتظار کد دعوت
        wait_ts = WAITING_INVITE.get(uid, 0)
        if wait_ts and time.time() - wait_ts < 120:
            if raw_text in ("انصراف", "لغو", "/cancel", "cancel"):
                WAITING_INVITE.pop(uid, None)
                try: await bot.send_message(chat_id=chat_id, text="✅ لغو شد.\n\n⚡ FLUXBOT")
                except: pass
                return
            m = re.match(r'^\s*(\d{6})\s*$', raw_text)
            if m:
                WAITING_INVITE.pop(uid, None)
                res = await process_invite(uid, m.group(1))
                try: await bot.send_message(chat_id=chat_id, text=res)
                except: pass
                return
            WAITING_INVITE.pop(uid, None)
            try:
                await bot.send_message(chat_id=chat_id,
                    text="❌ کد باید دقیقاً ۶ رقم باشد.\n\n⚡ FLUXBOT")
            except: pass
            return

        # ۳) انتظار انتخاب آیتم
        wait_ts = WAITING_CONVERT.get(uid, 0)
        if wait_ts and time.time() - wait_ts < 120:
            if raw_text in ("انصراف", "لغو", "/cancel", "cancel"):
                WAITING_CONVERT.pop(uid, None)
                try: await bot.send_message(chat_id=chat_id, text="✅ لغو شد.\n\n⚡ FLUXBOT")
                except: pass
                return
            m = re.match(r'^\s*(\d+)\s*$', raw_text)
            if m:
                idx = int(m.group(1))
                if 1 <= idx <= len(ITEMS):
                    WAITING_CONVERT.pop(uid, None)
                    pts = get_points(uid)
                    if pts < 10:
                        try: await bot.send_message(chat_id=chat_id,
                            text=text_convert_no_points(pts))
                        except: pass
                        return
                    add_points(uid, -10)
                    key, label = ITEMS[idx - 1]
                    inv = data["items"].setdefault(uid, {})
                    inv[key] = inv.get(key, 0) + 1
                    save()
                    try:
                        await bot.send_message(chat_id=chat_id,
                            text=text_convert_ok(label, get_points(uid), inv))
                    except: pass
                    return
                else:
                    try: await bot.send_message(chat_id=chat_id,
                        text=text_convert_invalid())
                    except: pass
                    return
            WAITING_CONVERT.pop(uid, None)
            try:
                await bot.send_message(chat_id=chat_id,
                    text="❌ ورودی نامعتبر. دوباره تلاش کن.\n\n⚡ FLUXBOT")
            except: pass
            return

        # ۴) تایپ متن دکمه
        if raw_text in LABEL_TO_BID:
            try:
                await do_button(chat_id, uid, LABEL_TO_BID[raw_text])
            except Exception as e:
                print(f"⚠️ label: {e}", flush=True)
            return

        # ۵) هر پیام دیگر → منو
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
            for d in (WAITING_INVITE, WAITING_CONVERT):
                for k in list(d.keys()):
                    if now - d[k] > 300:
                        d.pop(k, None)
        except: pass
        await asyncio.sleep(60)

# ═══ اجرا ═══
async def main():
    print("🤖 FLUXBOT PV v3 STARTING...", flush=True)
    print(f"👑 OWNER: {OWNER_ID}", flush=True)
    print(f"👥 کاربران: {len(data['users'])}", flush=True)
    print(f"🎁 SPIN_COOLDOWN: {SPIN_COOLDOWN}s", flush=True)
    try: asyncio.create_task(cleanup_loop())
    except: pass
    try:
        await bot.run()
    except Exception as e:
        print(f"❌ RUN: {type(e).__name__}: {e}", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
