from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import math
from db.connection import get_connection

TOKEN = "PASTE_YOUR_BOT_TOKEN"

conn = get_connection()
cursor = conn.cursor()

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    cursor.execute(
        "INSERT OR IGNORE INTO users (telegram_id, name) VALUES (?, ?)",
        (user.id, user.first_name)
    )
    conn.commit()

    await update.message.reply_text(
        "👋 Welcome to Attendance Tracker\n\n"
        "Use /addsubject to add your subjects.\n"
        "Then use /mark to mark attendance.\n"
        "Check /status anytime."
    )

# ---------------- ADD SUBJECT ----------------
async def addsubject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["step"] = "name"
    await update.message.reply_text("📘 Enter subject name:")

async def addsubject_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")

    if step == "name":
        context.user_data["subject_name"] = update.message.text
        context.user_data["step"] = "lab"
        kb = [["Theory", "Lab"]]
        await update.message.reply_text(
            "Is this a lab?",
            reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)
        )

    elif step == "lab":
        is_lab = update.message.text.lower() == "lab"
        context.user_data["is_lab"] = is_lab
        context.user_data["step"] = "cpw"
        await update.message.reply_text("How many classes per week?")

    elif step == "cpw":
        cpw = int(update.message.text)
        context.user_data["classes_per_week"] = cpw
        context.user_data["step"] = "weeks"
        await update.message.reply_text("Total weeks? (usually 15)")

    elif step == "weeks":
        weeks = int(update.message.text)
        data = context.user_data

        total_classes = data["classes_per_week"] * weeks
        required = math.ceil(0.8 * total_classes)

        cursor.execute("""
        INSERT INTO user_subjects
        (telegram_id, subject_name, classes_per_week, total_weeks,
         total_classes, required_classes, is_lab, lab_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            update.effective_user.id,
            data["subject_name"],
            data["classes_per_week"],
            weeks,
            total_classes,
            required,
            data["is_lab"],
            2 if data["is_lab"] else 0
        ))

        conn.commit()
        context.user_data.clear()

        await update.message.reply_text(
            f"✅ {data['subject_name']} added successfully!"
        )

# ---------------- MARK ATTENDANCE ----------------
async def mark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute(
        "SELECT subject_name FROM user_subjects WHERE telegram_id = ?",
        (update.effective_user.id,)
    )
    subjects = [[row["subject_name"]] for row in cursor.fetchall()]

    if not subjects:
        await update.message.reply_text("No subjects found. Add with /addsubject")
        return

    context.user_data["step"] = "mark_subject"
    await update.message.reply_text(
        "Select subject:",
        reply_markup=ReplyKeyboardMarkup(subjects, one_time_keyboard=True)
    )

async def mark_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        await update.message.reply_text(f"✅ Marked {status} for {subject}")

# ---------------- STATUS ----------------
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
    SELECT subject_name, attended, conducted, required_classes, total_classes
    FROM user_subjects WHERE telegram_id = ?
    """, (update.effective_user.id,))

    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("No subjects found.")
        return

    msg = "📊 Attendance Status\n\n"
    for r in rows:
        percent = (r["attended"] / r["conducted"] * 100) if r["conducted"] else 100
        msg += (
            f"{r['subject_name']}\n"
            f"{r['attended']}/{r['conducted']} → {percent:.1f}%\n\n"
        )

    await update.message.reply_text(msg)

# ---------------- MAIN ----------------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addsubject", addsubject))
app.add_handler(CommandHandler("mark", mark))
app.add_handler(CommandHandler("status", status))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, addsubject_flow))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mark_flow))

print("Bot running...")
app.run_polling()