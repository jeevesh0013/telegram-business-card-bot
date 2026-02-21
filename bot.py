import re
import qrcode
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler, ContextTypes, filters,
)
from telegram.constants import ParseMode
import os
# ── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")


FIRST, LAST, PHONE, EMAIL, ORG, TITLE, LOGO, THEME, CONFIRM = range(9)

THEMES = {
    "ocean":    {"label": "🌊 Ocean",    "bg": [(10,25,70),(20,60,130)],  "accent": (80,180,255), "text": (255,255,255)},
    "forest":   {"label": "🌿 Forest",   "bg": [(10,35,15),(25,85,40)],   "accent": (80,220,120), "text": (255,255,255)},
    "crimson":  {"label": "🔴 Crimson",  "bg": [(70,10,10),(160,25,25)],  "accent": (255,100,100),"text": (255,255,255)},
    "midnight": {"label": "🌙 Midnight", "bg": [(8,8,25),(20,20,55)],     "accent": (140,140,255),"text": (220,220,255)},
    "gold":     {"label": "✨ Gold",     "bg": [(50,35,5),(110,80,15)],   "accent": (255,210,50), "text": (255,255,255)},
    "rose":     {"label": "🌸 Rose",     "bg": [(70,15,35),(155,40,80)],  "accent": (255,140,170),"text": (255,255,255)},
}

# ── Validators ───────────────────────────────────────────────────────────────
def valid_name(s):  return bool(re.fullmatch(r"[A-Za-z ]{2,40}", s.strip()))
def valid_phone(s):
    s = s.replace(" ","").replace("-","")
    return bool(re.fullmatch(r"(\+91)?[6-9][0-9]{9}", s))
def valid_email(s): return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s))
def fmt_phone(s):
    s = s.replace(" ","").replace("-","")
    return s if s.startswith("+91") else "+91"+s

# ── Helpers ──────────────────────────────────────────────────────────────────
def theme_keyboard():
    keys = list(THEMES.items())
    rows = [[InlineKeyboardButton(v["label"], callback_data=f"theme_{k}") for k,v in keys[i:i+2]]
            for i in range(0, len(keys), 2)]
    return InlineKeyboardMarkup(rows)

def load_font(size):
    for name in ["arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]:
        try: return ImageFont.truetype(name, size)
        except: pass
    return ImageFont.load_default()

def draw_text_fit(draw, xy, text, max_width, start_size, color):
    """Draw text, shrinking font size until it fits within max_width."""
    size = start_size
    while size > 18:
        font = load_font(size)
        if draw.textlength(text, font=font) <= max_width:
            break
        size -= 3
    draw.text(xy, text, font=load_font(size), fill=color)

# ── Card Generation ──────────────────────────────────────────────────────────
def make_card(data):
    W, H = 1200, 660
    theme = THEMES[data.get("theme", "ocean")]
    c1, c2 = theme["bg"]
    accent, tcol = theme["accent"], theme["text"]

    # Gradient background
    card = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(card)
    for y in range(H):
        t = y / H
        draw.line([(0,y),(W,y)], fill=tuple(int(c1[i]+(c2[i]-c1[i])*t) for i in range(3)))

    # Soft decorative circles (RGBA overlay)
    ov = Image.new("RGBA", (W,H), (0,0,0,0))
    od = ImageDraw.Draw(ov)
    for cx,cy,cr,a in [(1050,-60,320,22),(1180,560,250,15),(-60,440,200,18)]:
        od.ellipse([cx-cr,cy-cr,cx+cr,cy+cr], fill=(*accent,a))
    card = Image.alpha_composite(card.convert("RGBA"), ov).convert("RGB")
    draw = ImageDraw.Draw(card)

    # ── QR Code (right side) ────────────────────────────────
    vcard = "\n".join(filter(None, [
        "BEGIN:VCARD","VERSION:3.0",
        f"N:{data['last']};{data['first']};;;",
        f"FN:{data['first']} {data['last']}",
        f"ORG:{data['org']}"   if data.get("org")   else "",
        f"TITLE:{data['title']}" if data.get("title") else "",
        f"TEL;TYPE=CELL:{data['phone']}",
        f"EMAIL:{data['email']}",
        "END:VCARD"
    ]))
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr.add_data(vcard); qr.make(fit=True)
    qr_img = qr.make_image(
        fill_color="#{:02x}{:02x}{:02x}".format(*accent), back_color="white"
    ).convert("RGB")

    QR = 400
    qr_img = qr_img.resize((QR, QR), Image.LANCZOS)

    # Logo inside QR
    if data.get("logo"):
        data["logo"].seek(0)
        lg = Image.open(data["logo"]).convert("RGBA")
        ls = int(QR * 0.22)
        lg = ImageOps.fit(lg, (ls,ls), Image.LANCZOS)
        bs = ls + 16
        bg = Image.new("RGBA",(bs,bs),(255,255,255,255))
        bm = Image.new("L",(bs,bs),0); ImageDraw.Draw(bm).ellipse((0,0,bs,bs),fill=255)
        qi = qr_img.convert("RGBA")
        qi.paste(bg,((QR-bs)//2,(QR-bs)//2),bm)
        lm = Image.new("L",(ls,ls),0); ImageDraw.Draw(lm).ellipse((0,0,ls,ls),fill=255)
        qi.paste(lg,((QR-ls)//2,(QR-ls)//2),lm)
        qr_img = qi.convert("RGB")

    # Paste QR with white border
    pad = 14
    qr_x, qr_y = W - QR - 65, (H - QR) // 2
    card.paste(Image.new("RGB",(QR+pad*2,QR+pad*2),(255,255,255)), (qr_x-pad, qr_y-pad))
    card.paste(qr_img, (qr_x, qr_y))
    draw.text((qr_x + QR//2, qr_y+QR+8), "Scan to Save", font=load_font(24), fill=tcol, anchor="mt")

    # ── Text (left side) ────────────────────────────────────
    LX = 60                         # left margin
    MAX = qr_x - LX - 30           # max text width — never overlaps QR

    # Optional logo top-left
    tx = LX
    if data.get("logo"):
        data["logo"].seek(0)
        lc = Image.open(data["logo"]).convert("RGBA")
        lc = ImageOps.fit(lc,(120,120),Image.LANCZOS)
        m = Image.new("L",(120,120),0); ImageDraw.Draw(m).ellipse((0,0,120,120),fill=255)
        card.paste(lc,(LX,60),m)
        tx = LX + 140
        MAX -= 140                  # shrink max width so text never goes under logo area

    # Name
    draw_text_fit(draw, (tx, 65), f"{data['first']} {data['last']}", MAX, 66, tcol)

    # Accent line
    draw.rectangle([LX, 210, LX+MAX+(140 if tx==LX else 0), 213], fill=accent)

    # Title + Org
    y = 228
    if data.get("title"):
        draw_text_fit(draw, (LX, y), data["title"], MAX+140, 36, accent); y += 48
    if data.get("org"):
        draw_text_fit(draw, (LX, y), data["org"],   MAX+140, 34, tcol);   y += 50

    # Phone & Email
    y = max(y + 10, 335)
    for icon, val in [("📱", data["phone"]), ("📧", data["email"])]:
        draw.text((LX, y), icon, font=load_font(32), fill=accent)
        draw_text_fit(draw, (LX+52, y+4), val, MAX+88, 32, tcol)
        y += 54

    # Bottom accent strip
    draw.rectangle([0, H-6, W, H], fill=accent)

    out = BytesIO(); out.name = "card.png"
    card.save(out, "PNG"); out.seek(0)
    return out

# ── Conversation ─────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "💼 *Business Card Bot*\n\nType /cancel anytime.\n\n✏️ Enter your *First Name*:",
        parse_mode=ParseMode.MARKDOWN)
    return FIRST

async def step_first(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not valid_name(t):
        await update.message.reply_text("❌ Letters only, 2–40 chars.\nRe-enter *First Name*:", parse_mode=ParseMode.MARKDOWN)
        return FIRST
    context.user_data["first"] = t
    await update.message.reply_text("✏️ Enter your *Last Name*:", parse_mode=ParseMode.MARKDOWN)
    return LAST

async def step_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not valid_name(t):
        await update.message.reply_text("❌ Letters only, 2–40 chars.\nRe-enter *Last Name*:", parse_mode=ParseMode.MARKDOWN)
        return LAST
    context.user_data["last"] = t
    await update.message.reply_text("📱 Enter *Phone* (10 digits or +91 format):", parse_mode=ParseMode.MARKDOWN)
    return PHONE

async def step_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not valid_phone(t):
        await update.message.reply_text(
            "❌ Invalid.\nExample: `9876543210` or `+919876543210`\nRe-enter:", parse_mode=ParseMode.MARKDOWN)
        return PHONE
    context.user_data["phone"] = fmt_phone(t)
    await update.message.reply_text("📧 Enter your *Email*:", parse_mode=ParseMode.MARKDOWN)
    return EMAIL

async def step_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not valid_email(t):
        await update.message.reply_text("❌ Invalid email.\nExample: `you@example.com`\nRe-enter:", parse_mode=ParseMode.MARKDOWN)
        return EMAIL
    context.user_data["email"] = t
    await update.message.reply_text("🏢 Enter *Organization* (or `skip`):", parse_mode=ParseMode.MARKDOWN)
    return ORG

async def step_org(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    context.user_data["org"] = "" if t.lower() == "skip" else t
    await update.message.reply_text("🎯 Enter *Job Title* (or `skip`):", parse_mode=ParseMode.MARKDOWN)
    return TITLE

async def step_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    context.user_data["title"] = "" if t.lower() == "skip" else t
    await update.message.reply_text("🖼 Upload your *Logo* (photo) or type `skip`:", parse_mode=ParseMode.MARKDOWN)
    return LOGO

async def step_logo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() == "skip":
        context.user_data["logo"] = None
    elif update.message.photo:
        f = await update.message.photo[-1].get_file()
        bio = BytesIO(); await f.download_to_memory(bio); bio.seek(0)
        context.user_data["logo"] = bio
    else:
        await update.message.reply_text("❌ Please send a photo or type `skip`:", parse_mode=ParseMode.MARKDOWN)
        return LOGO
    await update.message.reply_text("🎨 Choose a *Theme*:", parse_mode=ParseMode.MARKDOWN, reply_markup=theme_keyboard())
    return THEME

async def step_theme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["theme"] = q.data.replace("theme_","")
    d = context.user_data
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Generate!", callback_data="gen"),
        InlineKeyboardButton("🔄 Restart",  callback_data="restart"),
    ]])
    await q.edit_message_text(
        f"📋 *Confirm Details*\n\n"
        f"👤 {d['first']} {d['last']}\n"
        f"🎯 {d.get('title') or '—'}\n"
        f"🏢 {d.get('org') or '—'}\n"
        f"📱 {d['phone']}\n"
        f"📧 {d['email']}\n"
        f"🎨 {THEMES[d['theme']]['label']}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    return CONFIRM

async def step_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "restart":
        context.user_data.clear()
        await q.edit_message_text("🔄 Restarted. Type /start to begin.")
        return ConversationHandler.END
    await q.edit_message_text("⏳ Generating your card...")
    card = make_card(context.user_data)
    await q.message.reply_document(document=card, caption="🎉 Your Business Card!\n\nScan the QR to save contact.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled. Type /start to try again.")
    return ConversationHandler.END

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ Unknown command. Use /start to create a card.")

# ── Run ──────────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            FIRST:   [MessageHandler(filters.TEXT & ~filters.COMMAND, step_first)],
            LAST:    [MessageHandler(filters.TEXT & ~filters.COMMAND, step_last)],
            PHONE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, step_phone)],
            EMAIL:   [MessageHandler(filters.TEXT & ~filters.COMMAND, step_email)],
            ORG:     [MessageHandler(filters.TEXT & ~filters.COMMAND, step_org)],
            TITLE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, step_title)],
            LOGO:    [MessageHandler(filters.TEXT | filters.PHOTO, step_logo)],
            THEME:   [CallbackQueryHandler(step_theme, pattern="^theme_")],
            CONFIRM: [CallbackQueryHandler(step_confirm, pattern="^(gen|restart)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    print("✅ Bot running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
