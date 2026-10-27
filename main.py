import os
import sqlite3
import logging
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "284341133"))

DB = "bonus_moyka.db"

PLATE, AMOUNT, PHOTO = range(3)

menu = ReplyKeyboardMarkup(
    [["🎁 Bonusim", "📊 Tashriflarim"], ["🔄 Yangi tashrif"]],
    resize_keyboard=True
)


def init_db():
    with sqlite3.connect(DB) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plate TEXT NOT NULL,
                amount INTEGER NOT NULL,
                photo_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                user_id INTEGER PRIMARY KEY,
                plate TEXT DEFAULT '',
                bonus INTEGER DEFAULT 0,
                completed_visits INTEGER DEFAULT 0
            )
        """)


def get_customer(user_id):
    with sqlite3.connect(DB) as con:
        con.execute(
            "INSERT OR IGNORE INTO customers(user_id) VALUES (?)",
            (user_id,)
        )
        return con.execute(
            "SELECT plate, bonus, completed_visits FROM customers "
            "WHERE user_id=?",
            (user_id,)
        ).fetchone()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_customer(update.effective_user.id)

    await update.message.reply_text(
        "🚘 BONUS MOYKA N1\n\n"
        "Moykamizning bonus dasturiga xush kelibsiz!\n\n"
        "📸 Tashrifni hisoblash uchun «🔄 Yangi tashrif»ni bosing.\n"
        "🎁 Har 10 ta tashrifdan keyin bonus hisoblanadi.",
        reply_markup=menu
    )


async def new_visit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚘 Mashinangiz davlat raqamini kiriting.\n"
        "Masalan: 50A123BC"
    )
    return PLATE


async def plate_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    plate = update.message.text.strip().upper().replace(" ", "")

    if len(plate) < 5 or len(plate) > 12:
        await update.message.reply_text(
            "Raqam noto‘g‘ri ko‘rinadi. Qayta kiriting."
        )
        return PLATE

    context.user_data["plate"] = plate

    await update.message.reply_text(
        "💵 Apparatga qancha pul tashladingiz?\n\n"
        "Faqat son kiriting: 5000, 10000, 20000 yoki 50000."
    )
    return AMOUNT


async def amount_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    try:
        amount = int(update.message.text.strip().replace(" ", ""))
    except (ValueError, AttributeError):
        await update.message.reply_text(
            "Summani faqat raqam bilan kiriting. Masalan: 10000"
        )
        return AMOUNT

    if amount not in (5000, 10000, 20000, 50000):
        await update.message.reply_text(
            "Ruxsat etilgan summalar:\n"
            "5000, 10000, 20000 yoki 50000 so‘m."
        )
        return AMOUNT

    context.user_data["amount"] = amount

    await update.message.reply_text(
        "📸 Endi apparat ekranidagi summa yoki vaqt ko‘rinadigan "
        "suratni yuboring.\n\n"
        "Suratda imkon qadar mashina raqami ham ko‘rinsin."
    )
    return PHOTO


async def photo_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user_id = update.effective_user.id
    plate = context.user_data["plate"]
    amount = context.user_data["amount"]
    photo_id = update.message.photo[-1].file_id

    with sqlite3.connect(DB) as con:
        con.execute(
            "INSERT OR IGNORE INTO customers(user_id) VALUES (?)",
            (user_id,)
        )

        con.execute("""
            INSERT INTO visits
            (user_id, plate, amount, photo_id, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            plate,
            amount,
            photo_id,
            datetime.now().isoformat(timespec="seconds")
        ))

        con.execute(
            "UPDATE customers SET plate=? WHERE user_id=?",
            (plate, user_id)
        )

        total = con.execute(
            "SELECT COUNT(*) FROM visits WHERE user_id=?",
            (user_id,)
        ).fetchone()[0]

        cycle_visits = (total - 1) % 10 + 1

        recent = con.execute("""
            SELECT amount FROM visits
            WHERE user_id=?
            ORDER BY id DESC LIMIT 10
        """, (user_id,)).fetchall()

        bonus = 0

        if cycle_visits == 10:
            bonus = sum(row[0] for row in recent) // 10
            con.execute(
                "UPDATE customers SET bonus=bonus+?, "
                "completed_visits=completed_visits+1 WHERE user_id=?",
                (bonus, user_id)
            )

        current_bonus = con.execute(
            "SELECT bonus FROM customers WHERE user_id=?",
            (user_id,)
        ).fetchone()[0]

    await update.message.reply_text(
        f"✅ Tashrif qayd etildi!\n\n"
        f"🚘 Mashina: {plate}\n"
        f"💵 Kiritilgan summa: {amount:,} so‘m\n"
        f"🔢 Joriy 10 talik davr: {cycle_visits}/10\n"
        + (
            f"\n🎉 Bonus hisoblandi: {bonus:,} so‘m!"
            if bonus else ""
        )
        + f"\n🎁 Jami hisoblangan bonus: {current_bonus:,} so‘m\n\n"
        "Eslatma: bonus apparatdan bepul pul chiqishini anglatmaydi. "
        "Bonusdan foydalanish moyxona qoidalariga bog‘liq.",
        reply_markup=menu
    )

    # Admin uchun ma'lumot va surat
    try:
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_id,
            caption=(
                "📸 Yangi tashrif\n"
                f"Telegram ID: {user_id}\n"
                f"Mashina: {plate}\n"
                f"Yozilgan summa: {amount:,} so‘m"
            )
        )
    except Exception:
        logging.exception("Admin xabarini yuborib bo‘lmadi")

    context.user_data.clear()
    return ConversationHandler.END


async def my_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    customer = get_customer(update.effective_user.id)
    bonus = customer[1]

    await update.message.reply_text(
        f"🎁 Sizning hisoblangan bonusingiz: {bonus:,} so‘m",
        reply_markup=menu
    )


async def my_visits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    with sqlite3.connect(DB) as con:
        total = con.execute(
            "SELECT COUNT(*) FROM visits WHERE user_id=?",
            (user_id,)
        ).fetchone()[0]

    await update.message.reply_text(
        f"📊 Jami tashriflaringiz: {total}\n"
        f"🔢 Keyingi bonusgacha: {10 - total % 10} ta",
        reply_markup=menu
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Bekor qilindi.", reply_markup=menu
    )
    return ConversationHandler.END


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN sozlanmagan!")

    init_db()

    app = Application.builder().token(TOKEN).build()

    conversation = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^🔄 Yangi tashrif$"),
                new_visit
            )
        ],
        states={
            PLATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, plate_received)
            ],
            AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, amount_received)
            ],
            PHOTO: [
                MessageHandler(filters.PHOTO, photo_received)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(conversation)
    app.add_handler(
        MessageHandler(filters.Regex("^🎁 Bonusim$"), my_bonus)
    )
    app.add_handler(
        MessageHandler(filters.Regex("^📊 Tashriflarim$"), my_visits)
    )

    app.run_polling()


if __name__ == "__main__":
    main()
