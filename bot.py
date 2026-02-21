import os
import math
import sqlite3
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================= ENV & DB =================

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

conn = sqlite3.connect("attendance.db", check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    cursor.execute(
        "INSERT OR IGNORE INTO users (telegram_id, name) VALUES (?, ?)",
        (user.id, user.first_name)
    )
    conn.commit()

    await update.message.reply_text(
        "👋 Welcome to Attendance Tracker\n\n"
        "Commands:\n"
        "/preset_cyber – Auto-add Cybersecurity Sem 2 timetable\n"
        "/addsubject – Add subject manually\n"
        "/setattendance – Add existing attendance\n\n"
        "/mark – Mark attendance\n"
        "/status – View attendance\n"
        "/canimiss – Safe bunk calculator\n"
    )

# ================= ADD SUBJECT =================

async def addsubject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["flow"] = "addsubject"
    context.user_data["step"] = "name"
    await update.message.reply_text("Enter subject name:")

async def addsubject_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")

    if step == "name":
        context.user_data["subject"] = update.message.text
        context.user_data["step"] = "type"
        await update.message.reply_text(
            "Select class type:",
            reply_markup=ReplyKeyboardMarkup(
                [["Theory", "Tutorial", "Lab"]],
                one_time_keyboard=True
            )
        )

    elif step == "type":
        context.user_data["class_type"] = update.message.text.lower()
        context.user_data["step"] = "cpw"
        await update.message.reply_text("Classes per week?")

    elif step == "cpw":
        context.user_data["cpw"] = int(update.message.text)
        context.user_data["step"] = "weeks"
        await update.message.reply_text("Total weeks? (usually 15)")

    elif step == "weeks":
        weeks = int(update.message.text)
        cpw = context.user_data["cpw"]
        total = cpw * weeks
        required = math.ceil(0.8 * total)
        lab_hours = 2 if context.user_data["class_type"] == "lab" else 0

        cursor.execute("""
        INSERT INTO user_subjects
        (telegram_id, subject_name, class_type,
         classes_per_week, total_weeks,
         total_classes, required_classes, lab_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            update.effective_user.id,
            context.user_data["subject"],
            context.user_data["class_type"],
            cpw, weeks, total, required, lab_hours
        ))

        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ Subject added.")

# ================= PRESET CYBER =================

async def preset_cyber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["flow"] = "preset_cyber"
    context.user_data["step"] = "batch"

    await update.message.reply_text(
        "Select your batch:",
        reply_markup=ReplyKeyboardMarkup([["K1", "K2"]], one_time_keyboard=True)
    )

async def preset_cyber_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    TOTAL_WEEKS = 15
    uid = update.effective_user.id

    # -------- THEORY (ONLY AFTER BREAK) --------
    theory_subjects = [
        ("LADE", 3),
        ("PEM", 3),
        ("WT", 1),
        ("PP", 1),
        ("PR", 1),
        ("QP", 2),
        ("IKS", 1),
        ("EOB", 2),
    ]

    for name, cpw in theory_subjects:
        total = cpw * TOTAL_WEEKS
        required = math.ceil(0.8 * total)
        cursor.execute("""
        INSERT INTO user_subjects
        (telegram_id, subject_name, class_type,
         classes_per_week, total_weeks,
         total_classes, required_classes)
        VALUES (?, ?, 'theory', ?, ?, ?, ?)
        """, (uid, name, cpw, TOTAL_WEEKS, total, required))

    # -------- EOB TUTORIAL --------
    total = TOTAL_WEEKS
    required = math.ceil(0.8 * total)
    cursor.execute("""
    INSERT INTO user_subjects
    (telegram_id, subject_name, class_type,
     classes_per_week, total_weeks,
     total_classes, required_classes)
    VALUES (?, 'EOB Tutorial', 'tutorial', 1, ?, ?, ?)
    """, (uid, TOTAL_WEEKS, total, required))

    # -------- LABS (8–10 ONLY) --------
    labs = ["WT Lab", "PP Lab", "QP Lab", "PR Lab", "LADE Lab"]

    for lab in labs:
        cursor.execute("""
        INSERT INTO user_subjects
        (telegram_id, subject_name, class_type,
         classes_per_week, total_weeks,
         total_classes, required_classes, lab_hours)
        VALUES (?, ?, 'lab', 1, ?, ?, ?, 2)
        """, (uid, lab, TOTAL_WEEKS, TOTAL_WEEKS, math.ceil(0.8 * TOTAL_WEEKS)))

    conn.commit()
    context.user_data.clear()
    await update.message.reply_text("✅ Cybersecurity Sem 2 preset added.")

# ================= MARK =================

async def mark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute(
        "SELECT subject_name FROM user_subjects WHERE telegram_id = ?",
        (update.effective_user.id,)
    )
    subs = [[r["subject_name"]] for r in cursor.fetchall()]

    context.user_data.clear()
    context.user_data["flow"] = "mark"
    context.user_data["step"] = "subject"

    await update.message.reply_text(
        "Select subject:",
        reply_markup=ReplyKeyboardMarkup(subs, one_time_keyboard=True)
    )

async def mark_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")

    if step == "subject":
        context.user_data["subject"] = update.message.text
        context.user_data["step"] = "status"
        await update.message.reply_text(
            "Present or Absent?",
            reply_markup=ReplyKeyboardMarkup(
                [["Present", "Absent"]],
                one_time_keyboard=True
            )
        )

    elif step == "status":
        attended = 1 if update.message.text.lower() == "present" else 0
        subject = context.user_data["subject"]

        cursor.execute("""
        UPDATE user_subjects
        SET conducted = conducted + 1,
            attended = attended + ?
        WHERE telegram_id = ? AND subject_name = ?
        """, (attended, update.effective_user.id, subject))

        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ Attendance marked.")

# ================= SET ATTENDANCE =================

async def setattendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute(
        "SELECT subject_name FROM user_subjects WHERE telegram_id = ?",
        (update.effective_user.id,)
    )
    subs = [[r["subject_name"]] for r in cursor.fetchall()]

    context.user_data.clear()
    context.user_data["flow"] = "setattendance"
    context.user_data["step"] = "subject"

    await update.message.reply_text(
        "Select subject:",
        reply_markup=ReplyKeyboardMarkup(subs, one_time_keyboard=True)
    )

async def setattendance_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")

    if step == "subject":
        context.user_data["subject"] = update.message.text
        context.user_data["step"] = "conducted"
        await update.message.reply_text("Classes conducted till now?")

    elif step == "conducted":
        context.user_data["conducted"] = int(update.message.text)
        context.user_data["step"] = "attended"
        await update.message.reply_text("Classes attended till now?")

    elif step == "attended":
        subject = context.user_data["subject"]
        conducted = context.user_data["conducted"]
        attended = int(update.message.text)

        cursor.execute("""
        UPDATE user_subjects
        SET conducted = ?, attended = ?
        WHERE telegram_id = ? AND subject_name = ?
        """, (conducted, attended, update.effective_user.id, subject))

        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ Attendance updated.")

# ================= STATUS =================

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
    SELECT subject_name, class_type, attended, conducted
    FROM user_subjects
    WHERE telegram_id = ?
    """, (update.effective_user.id,))

    rows = cursor.fetchall()
    subjects = {}

    # Group by base subject name
    for r in rows:
        name = r["subject_name"]
        base = name.replace(" Lab", "").replace(" Tutorial", "")
        subjects.setdefault(base, []).append(r)

    msg = "📊 *Your Attendance Snapshot*\n\n"

    for base, entries in subjects.items():
        msg += f"📘 *{base}*\n"

        for r in entries:
            attended = r["attended"]
            conducted = r["conducted"]
            pct = (attended / conducted * 100) if conducted else 100

            if r["class_type"] == "lab":
                emoji = "🧪"
                label = "Lab"
            elif r["class_type"] == "tutorial":
                emoji = "📓"
                label = "Tutorial"
            else:
                emoji = "📖"
                label = "Theory"

            warning = ""
            if conducted > 0 and pct < 80:
                warning = " ⚠️"

            msg += f"{emoji} {label}: {attended}/{conducted} ({pct:.0f}%){warning}\n"

        msg += "\n"

    await update.message.reply_text(msg)

# ================= CAN I MISS =================

async def canimiss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
    SELECT subject_name, class_type,
           total_classes, required_classes,
           attended, conducted
    FROM user_subjects
    WHERE telegram_id = ?
    """, (update.effective_user.id,))

    rows = cursor.fetchall()
    subjects = {}

    for r in rows:
        base = r["subject_name"].replace(" Lab", "").replace(" Tutorial", "")
        subjects.setdefault(base, []).append(r)

    msg = "🧮 *Can I Miss?*\n\n"

    for base, entries in subjects.items():
        msg += f"📘 *{base}*\n"

        for r in entries:
            max_absent = r["total_classes"] - r["required_classes"]
            current_absent = r["conducted"] - r["attended"]
            left = max_absent - current_absent

            if r["class_type"] == "lab":
                emoji = "🧪"
                label = "Lab"
            elif r["class_type"] == "tutorial":
                emoji = "📓"
                label = "Tutorial"
            else:
                emoji = "📖"
                label = "Theory"

            if r["class_type"] == "tutorial" and r["conducted"] > 0:
                pct = (r["attended"] / r["conducted"]) * 100
                if pct < 80:
                    msg += f"{emoji} {label}: 🚨 *CRITICAL*\n"
                    continue

            if left <= 0:
                msg += f"{emoji} {label}: ❌ No bunks left\n"
            else:
                msg += f"{emoji} {label}: ✅ {left} bunks left\n"

        msg += "\n"

    await update.message.reply_text(msg)
# ================= TEXT ROUTER =================

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    flow = context.user_data.get("flow")

    if flow == "addsubject":
        await addsubject_flow(update, context)
    elif flow == "preset_cyber":
        await preset_cyber_flow(update, context)
    elif flow == "mark":
        await mark_flow(update, context)
    elif flow == "setattendance":
        await setattendance_flow(update, context)

# ================= MAIN =================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addsubject", addsubject))
app.add_handler(CommandHandler("preset_cyber", preset_cyber))
app.add_handler(CommandHandler("mark", mark))
app.add_handler(CommandHandler("setattendance", setattendance))
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("canimiss", canimiss))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

print("Bot running...")
app.run_polling()