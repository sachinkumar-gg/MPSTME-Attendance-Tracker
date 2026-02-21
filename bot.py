import math
from datetime import datetime
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from db.connection import get_connection

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

conn = get_connection()
cursor = conn.cursor()

# -------------------------------------------------
# START
# -------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    cursor.execute(
        "INSERT OR IGNORE INTO users (telegram_id, name) VALUES (?, ?)",
        (user.id, user.first_name)
    )
    conn.commit()

    await update.message.reply_text(
        "👋 Welcome to Attendance Tracker\n\n"
        "Available Commands:\n\n"
        "/preset_cyber - Auto-add Cybersecurity Sem 2 timetable\n"
        "/addsubject - Add subject manually\n"
        "/setattendance - Add existing attendance (mid-sem)\n\n"
        "/mark - Mark attendance\n"
        "/undo - Undo last entry\n\n"
        "/status - View attendance\n"
        "/canimiss - Safe bunk calculator\n"
        "/leaveplanner - Estimate leave impact\n"
    )
# -------------------------------------------------
# ADD SUBJECT
# -------------------------------------------------
async def addsubject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["step"] = "name"

    await update.message.reply_text(
        "📘 Enter subject name:"
    )
async def addsubject_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Guard: run ONLY during add-subject flow
    if context.user_data.get("step") not in {
        "name", "class_type", "cpw", "weeks"
    }:
        return

    step = context.user_data.get("step")

    # 1️⃣ Subject name
    if step == "name":
        context.user_data["subject_name"] = update.message.text.strip()
        context.user_data["step"] = "class_type"

        await update.message.reply_text(
            "Select class type:",
            reply_markup=ReplyKeyboardMarkup(
                [["Theory", "Tutorial", "Lab"]],
                one_time_keyboard=True
            )
        )

    # 2️⃣ Class type (theory / tutorial / lab)
    elif step == "class_type":
        class_type = update.message.text.lower()

        if class_type not in {"theory", "tutorial", "lab"}:
            await update.message.reply_text("❌ Please choose Theory, Tutorial, or Lab.")
            return

        context.user_data["class_type"] = class_type
        context.user_data["step"] = "cpw"

        await update.message.reply_text(
            "How many classes per week?"
        )

    # 3️⃣ Classes per week
    elif step == "cpw":
        try:
            cpw = int(update.message.text)
            if cpw <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Enter a valid positive number.")
            return

        context.user_data["classes_per_week"] = cpw
        context.user_data["step"] = "weeks"

        await update.message.reply_text(
            "Total weeks? (usually 15)"
        )

    # 4️⃣ Final insert
    elif step == "weeks":
        try:
            weeks = int(update.message.text)
            if weeks <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Enter a valid positive number.")
            return

        data = context.user_data

        total_classes = data["classes_per_week"] * weeks
        required_classes = math.ceil(0.8 * total_classes)
        lab_hours = 2 if data["class_type"] == "lab" else 0

        cursor.execute("""
        INSERT INTO user_subjects
        (telegram_id, subject_name, class_type,
         classes_per_week, total_weeks,
         total_classes, required_classes,
         lab_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            update.effective_user.id,
            data["subject_name"],
            data["class_type"],
            data["classes_per_week"],
            weeks,
            total_classes,
            required_classes,
            lab_hours
        ))

        conn.commit()
        context.user_data.clear()

        await update.message.reply_text(
            f"✅ {data['subject_name']} ({data['class_type'].title()}) added successfully!"
        )
# -------------------------------------------------
# MARK ATTENDANCE
# -------------------------------------------------
async def mark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute(
        "SELECT subject_name FROM user_subjects WHERE telegram_id = ?",
        (update.effective_user.id,)
    )
    subjects = [[row["subject_name"]] for row in cursor.fetchall()]

    if not subjects:
        await update.message.reply_text("❌ No subjects found.")
        return

    context.user_data.clear()
    context.user_data["step"] = "mark_subject"

    await update.message.reply_text(
        "Select subject:",
        reply_markup=ReplyKeyboardMarkup(subjects, one_time_keyboard=True)
    )

async def mark_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("step") not in {"mark_subject", "mark_status"}:
        return  # NOT in mark flow

    step = context.user_data.get("step")

    if step == "mark_subject":
        context.user_data["subject"] = update.message.text
        context.user_data["step"] = "mark_status"
        await update.message.reply_text(
            "Present or Absent?",
            reply_markup=ReplyKeyboardMarkup(
                [["Present", "Absent"]], one_time_keyboard=True
            )
        )

    elif step == "mark_status":
        subject = context.user_data["subject"]
        status = update.message.text.lower()

        cursor.execute("""
        UPDATE user_subjects
        SET conducted = conducted + 1,
            attended = attended + ?
        WHERE telegram_id = ? AND subject_name = ?
        """, (
            1 if status == "present" else 0,
            update.effective_user.id,
            subject
        ))

        cursor.execute("""
        INSERT INTO attendance_logs (telegram_id, subject_name, status)
        VALUES (?, ?, ?)
        """, (update.effective_user.id, subject, status))

        conn.commit()
        context.user_data.clear()

        await update.message.reply_text(
            f"✅ {subject}: {status.upper()}"
        )
# -------------------------------------------------
# UNDO
# -------------------------------------------------
async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
    SELECT id, subject_name, status
    FROM attendance_logs
    WHERE telegram_id = ?
    ORDER BY timestamp DESC
    LIMIT 1
    """, (update.effective_user.id,))
    row = cursor.fetchone()

    if not row:
        await update.message.reply_text("❌ Nothing to undo.")
        return

    cursor.execute("""
    UPDATE user_subjects
    SET conducted = conducted - 1,
        attended = attended - ?
    WHERE telegram_id = ? AND subject_name = ?
    """, (
        1 if row["status"] == "present" else 0,
        update.effective_user.id,
        row["subject_name"]
    ))

    cursor.execute("DELETE FROM attendance_logs WHERE id = ?", (row["id"],))
    conn.commit()

    await update.message.reply_text(f"↩️ Undid last entry for {row['subject_name']}")

# -------------------------------------------------
# STATUS
# -------------------------------------------------
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
    SELECT subject_name, class_type, attended, conducted
    FROM user_subjects
    WHERE telegram_id = ?
    ORDER BY class_type
    """, (update.effective_user.id,))

    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("❌ No subjects found.")
        return

    sections = {
        "theory": "📘 *Theory*",
        "tutorial": "📗 *Tutorial*",
        "lab": "🧪 *Lab*"
    }

    msg = "📊 *Attendance Status*\n\n"
    current_type = None

    for r in rows:
        if r["class_type"] != current_type:
            current_type = r["class_type"]
            msg += f"\n{sections[current_type]}\n"

        if r["conducted"] == 0:
            percent = 100.0
        else:
            percent = (r["attended"] / r["conducted"]) * 100

        if percent < 75:
            flag = "❌"
        elif percent < 80:
            flag = "⚠️"
        else:
            flag = "✅"

        msg += (
            f"{r['subject_name']} → "
            f"{r['attended']}/{r['conducted']} "
            f"({percent:.1f}%) {flag}\n"
        )

    await update.message.reply_text(msg, parse_mode="Markdown")
# -------------------------------------------------
# CAN I MISS
# -------------------------------------------------
async def canimiss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
    SELECT subject_name, class_type,
           total_classes, required_classes,
           conducted, attended
    FROM user_subjects
    WHERE telegram_id = ?
    """, (update.effective_user.id,))

    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("❌ No subjects found.")
        return

    msg = "🧮 *Safe Bunk Status*\n\n"

    for r in rows:
        max_absent = r["total_classes"] - r["required_classes"]
        current_absent = r["conducted"] - r["attended"]
        remaining = max_absent - current_absent

        # Tutorial logic (STRICT)
        if r["class_type"] == "tutorial":
            if r["conducted"] == 0:
                msg += f"📗 {r['subject_name']}: ✅ Safe for now\n"
            elif (r["attended"] / r["conducted"]) * 100 < 80:
                msg += (
                    f"📗 {r['subject_name']}: ❌ *CRITICAL* "
                    "(Tutorial attendance low)\n"
                )
            else:
                msg += f"📗 {r['subject_name']}: ⚠️ Avoid bunking\n"
            continue

        # Theory / Lab logic
        if remaining <= 0:
            msg += f"{r['subject_name']}: ❌ NO more bunks\n"
        else:
            msg += f"{r['subject_name']}: ✅ {remaining} bunks left\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

# -------------------------------------------------
# LEAVE PLANNER (simple & honest)
# -------------------------------------------------
async def leaveplanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["step"] = "days"
    await update.message.reply_text("How many days will you be absent?")

async def leaveplanner_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("step") != "leave_days":
        return

    days = int(update.message.text)

    cursor.execute("""
    SELECT subject_name, classes_per_week
    FROM user_subjects WHERE telegram_id = ?
    """, (update.effective_user.id,))

    msg = f"📅 Leave impact for {days} days\n\n"
    for r in cursor.fetchall():
        approx = math.ceil((r["classes_per_week"] / 5) * days)
        msg += f"{r['subject_name']}: ~{approx} classes missed\n"

    context.user_data.clear()
    await update.message.reply_text(msg)
# -------------------------------------------------
# Set-Attendance Flow
# -------------------------------------------------
async def setattendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute(
        "SELECT subject_name FROM user_subjects WHERE telegram_id = ?",
        (update.effective_user.id,)
    )
    subjects = [[row["subject_name"]] for row in cursor.fetchall()]

    if not subjects:
        await update.message.reply_text("❌ No subjects found.")
        return

    context.user_data.clear()
    context.user_data["step"] = "set_subject"

    await update.message.reply_text(
        "Select subject to set existing attendance:",
        reply_markup=ReplyKeyboardMarkup(subjects, one_time_keyboard=True)
    )
async def setattendance_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")

    # Guard: ONLY handle setattendance flow
    if not step or not step.startswith("set_"):
        return

    # 1️⃣ Subject selected
    if step == "set_subject":
        context.user_data["subject"] = update.message.text
        context.user_data["step"] = "set_conducted"

        await update.message.reply_text(
            "Enter total classes conducted till now:"
        )

    # 2️⃣ Conducted
    elif step == "set_conducted":
        try:
            conducted = int(update.message.text)
            if conducted < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Enter a valid number.")
            return

        context.user_data["conducted"] = conducted
        context.user_data["step"] = "set_attended"

        await update.message.reply_text(
            "Enter classes attended till now:"
        )

    # 3️⃣ Attended
    elif step == "set_attended":
        try:
            attended = int(update.message.text)
            if attended < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Enter a valid number.")
            return

        conducted = context.user_data["conducted"]
        if attended > conducted:
            await update.message.reply_text(
                "❌ Attended cannot be greater than conducted."
            )
            return

        subject = context.user_data["subject"]

        cursor.execute("""
        UPDATE user_subjects
        SET conducted = ?, attended = ?
        WHERE telegram_id = ? AND subject_name = ?
        """, (
            conducted,
            attended,
            update.effective_user.id,
            subject
        ))

        conn.commit()
        context.user_data.clear()

        percent = (attended / conducted * 100) if conducted else 100

        await update.message.reply_text(
            f"✅ Attendance updated for {subject}\n"
            f"{attended}/{conducted} → {percent:.1f}%"
        )

# -------------------------------------------------
# For CyberSec SEM-II
# -------------------------------------------------
async def preset_cyber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["step"] = "cyber_batch"

    await update.message.reply_text(
        "🎓 *B.Tech Cybersecurity – Sem 2*\n\nSelect your batch:",
        reply_markup=ReplyKeyboardMarkup(
            [["K1", "K2"]],
            one_time_keyboard=True
        ),
        parse_mode="Markdown"
    )
async def preset_cyber_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("step") != "cyber_batch":
        return

    batch = update.message.text.strip().upper()
    if batch not in {"K1", "K2"}:
        await update.message.reply_text("❌ Please select K1 or K2.")
        return

    telegram_id = update.effective_user.id
    TOTAL_WEEKS = 15

    # ---------------- THEORY (COMMON) ----------------
    theory_subjects = [
        ("LADE", 3),
        ("QP", 3),
        ("PEM", 3),
        ("WT", 2),
        ("PP", 2),
        ("PR", 2),
        ("IKS", 1),
        ("EOB", 2),  # EOB theory is COMMON
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
        """, (
            telegram_id, name,
            cpw, TOTAL_WEEKS,
            total, required
        ))

    # ---------------- EOB TUTORIAL (BATCH-SPECIFIC) ----------------
    # K1 → Monday tutorial
    # K2 → Tuesday tutorial
    total = TOTAL_WEEKS
    required = math.ceil(0.8 * total)

    cursor.execute("""
    INSERT INTO user_subjects
    (telegram_id, subject_name, class_type,
     classes_per_week, total_weeks,
     total_classes, required_classes)
    VALUES (?, ?, 'tutorial', 1, ?, ?, ?)
    """, (
        telegram_id,
        "EOB Tutorial",
        TOTAL_WEEKS,
        total,
        required
    ))

    # ---------------- LABS (ROTATIONAL, COUNT = 1/WEEK) ----------------
    labs = [
        "WT Lab",
        "PP Lab",
        "QP Lab",
        "PR Lab",
        "LADE Lab",
    ]

    for lab in labs:
        total = TOTAL_WEEKS
        required = math.ceil(0.8 * total)

        cursor.execute("""
        INSERT INTO user_subjects
        (telegram_id, subject_name, class_type,
         classes_per_week, total_weeks,
         total_classes, required_classes, lab_hours)
        VALUES (?, ?, 'lab', 1, ?, ?, ?, 2)
        """, (
            telegram_id,
            lab,
            TOTAL_WEEKS,
            total,
            required
        ))

    conn.commit()
    context.user_data.clear()

    await update.message.reply_text(
        f"✅ *Cybersecurity Sem 2 preset added!*\n\n"
        f"Batch: *{batch}*\n\n"
        "You can now use:\n"
        "/mark\n"
        "/status\n"
        "/canimiss",
        parse_mode="Markdown"
    )
# -------------------------------------------------
# MAIN
# -------------------------------------------------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addsubject", addsubject))
app.add_handler(CommandHandler("mark", mark))
app.add_handler(CommandHandler("undo", undo))
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("canimiss", canimiss))
app.add_handler(CommandHandler("leaveplanner", leaveplanner))
app.add_handler(CommandHandler("preset_cyber", preset_cyber))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, preset_cyber_flow))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, addsubject_flow))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mark_flow))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, leaveplanner_flow))
app.add_handler(CommandHandler("setattendance", setattendance))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, setattendance_flow))

print("Bot running...")
app.run_polling()