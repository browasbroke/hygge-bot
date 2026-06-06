"""
Hygge Kafé — Telegram Bot
Меню, бронирование со статусами, ИИ-ответы, админ-панель.
"""

import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes,
)
from menu import MENU, get_menu_text, get_category_items
import re
from db import init_db, add_booking, get_booking, update_status, get_upcoming, delete_booking

load_dotenv()

BOT_TOKEN  = os.getenv("BOT_TOKEN")
ADMIN_ID   = int(os.getenv("ADMIN_CHAT_ID"))
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ============================================================
#  Валидация даты и времени
# ============================================================

MONTHS = {
    'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,
    'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12
}

def parse_date(text: str):
    """Возвращает красивую строку даты или None если невалидно."""
    t = text.strip()

    # «15 июня» или «15 июня 2026»
    m = re.match(r'^(\d{1,2})\s+([а-яёА-ЯЁ]+)(\s+\d{4})?$', t, re.I)
    if m:
        day, month_word = int(m.group(1)), m.group(2).lower()
        month = MONTHS.get(month_word)
        if month and 1 <= day <= 31:
            year = m.group(3).strip() if m.group(3) else ""
            return f"{day} {m.group(2)}{' ' + year if year else ''}"

    # «15.06» / «15.06.2026» / «15/06»
    m = re.match(r'^(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?$', t)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        if 1 <= day <= 31 and 1 <= month <= 12:
            month_name = list(MONTHS.keys())[month - 1]
            year = f" {m.group(3)}" if m.group(3) else ""
            return f"{day} {month_name}{year}"

    return None  # невалидная дата

def parse_time(text: str):
    """Возвращает «ЧЧ:ММ» или None если невалидно."""
    t = text.strip().replace('.', ':').replace('-', ':')

    m = re.match(r'^(\d{1,2}):(\d{2})$', t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"

    # «1400» → «14:00»
    m = re.match(r'^(\d{2})(\d{2})$', t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"

    return None


# ---- Conversation states ----
NAME, PHONE, DATE, TIME, GUESTS, COMMENT = range(6)


# ============================================================
#  Клавиатуры
# ============================================================

MINI_APP_URL = os.getenv("MINI_APP_URL", "")

def kb_main():
    menu_btn = (
        InlineKeyboardButton("📋 Меню", web_app=__import__('telegram').WebAppInfo(url=MINI_APP_URL))
        if MINI_APP_URL else
        InlineKeyboardButton("📋 Меню", callback_data="menu")
    )
    return InlineKeyboardMarkup([
        [menu_btn],
        [InlineKeyboardButton("🗓 Забронировать стол",   callback_data="book")],
        [InlineKeyboardButton("📍 Адрес и часы работы",  callback_data="info")],
    ])

def kb_categories():
    cats = list(MENU.keys())
    rows = []
    for i in range(0, len(cats), 2):
        row = [InlineKeyboardButton(c, callback_data=f"cat:{c}") for c in cats[i:i+2]]
        rows.append(row)
    rows.append([InlineKeyboardButton("← Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)

def kb_guests():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1",  callback_data="g:1"),
            InlineKeyboardButton("2",  callback_data="g:2"),
            InlineKeyboardButton("3",  callback_data="g:3"),
        ],
        [
            InlineKeyboardButton("4",  callback_data="g:4"),
            InlineKeyboardButton("5",  callback_data="g:5"),
            InlineKeyboardButton("6+", callback_data="g:6+"),
        ],
    ])

def kb_skip():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Пропустить →", callback_data="skip_comment")]
    ])

def kb_back():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("← На главную", callback_data="back_main")]
    ])

def kb_admin_booking(booking_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{booking_id}"),
            InlineKeyboardButton("❌ Отменить",    callback_data=f"cancel:{booking_id}"),
        ],
        [
            InlineKeyboardButton("🗑 Удалить",     callback_data=f"delete:{booking_id}"),
        ]
    ])




# ============================================================
#  Основные хэндлеры
# ============================================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Гость"
    await update.message.reply_text(
        f"Привет, {name}! Добро пожаловать в Hygge Kafé 🤍\n\n"
        "Я помогу посмотреть меню, ответить на вопросы о блюдах "
        "и забронировать столик.\n\n"
        "Или просто напишите вопрос — отвечу!",
        reply_markup=kb_main(),
    )

async def btn_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "back_main":
        await q.edit_message_text("Чем могу помочь?", reply_markup=kb_main())

    elif data == "menu":
        await q.edit_message_text("Выберите раздел меню:", reply_markup=kb_categories())

    elif data.startswith("cat:"):
        cat = data[4:]
        items = get_category_items(cat)
        if not items:
            await q.edit_message_text("Раздел пуст.", reply_markup=kb_categories())
            return
        lines = [f"{cat}\n"]
        for item in items:
            lines.append(f"• {item['name']} — {item['price']} ₽\n  {item['desc']}")
        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("← Все разделы",     callback_data="menu")],
                [InlineKeyboardButton("🗓 Забронировать",  callback_data="book")],
            ]),
        )

    elif data == "info":
        await q.edit_message_text(
            "📍 Уфа, ул. Бакалинская, 27\n"
            "ТЦ «Ультра», 3 этаж\n"
            "Вход со стороны «Лента»\n\n"
            "📞 +7 (937) 849-23-18\n\n"
            "🍳 Завтраки:\n"
            "   Будни: 10:00–12:00\n"
            "   Выходные: 10:00–14:00\n\n"
            "🎨 Мастер-классы и детский лагерь «Зайцбург» — уточняйте по телефону",
            reply_markup=kb_back(),
        )

    elif data.startswith("delete:"):
        if update.effective_user.id != ADMIN_ID:
            await q.answer("Нет доступа.", show_alert=True)
            return
        booking_id = int(data.split(":")[1])
        booking = get_booking(booking_id)
        if booking:
            delete_booking(booking_id)
            await q.edit_message_text(
                q.message.text + "\n\n🗑 Бронь удалена из базы."
            )
        else:
            await q.edit_message_text("Бронь не найдена.")

    elif data.startswith("confirm:") or data.startswith("cancel:"):
        if update.effective_user.id != ADMIN_ID:
            await q.answer("Нет доступа.", show_alert=True)
            return

        action, booking_id = data.split(":", 1)
        booking_id = int(booking_id)
        booking = get_booking(booking_id)

        if not booking:
            await q.edit_message_text("Бронь не найдена.")
            return

        table_line = f"🪑 Стол №{booking['table_number']}\n" if booking.get("table_number") else ""

        if action == "confirm":
            update_status(booking_id, "confirmed")
            status_text = "✅ Бронь подтверждена!"
            guest_text = (
                f"✅ Ваша бронь подтверждена!\n\n"
                f"📅 {booking['date']} в {booking['time']}\n"
                f"👥 {booking['guests']} чел.\n"
                f"{table_line}"
                f"\nЖдём вас в Hygge Kafé!\n"
                f"📍 ТЦ Ультра, 3 этаж"
            )
        else:
            update_status(booking_id, "cancelled")
            status_text = "❌ Бронь отменена."
            guest_text = (
                f"К сожалению, мы не сможем принять вашу бронь "
                f"на {booking['date']} в {booking['time']}.\n\n"
                f"Для уточнений позвоните: +7 (937) 849-23-18"
            )

        new_text = q.message.text + f"\n\n{status_text}"
        await q.edit_message_text(new_text)

        try:
            await ctx.bot.send_message(
                chat_id=booking["user_id"],
                text=guest_text,
                reply_markup=kb_main(),
            )
        except Exception as e:
            log.error(f"Не удалось уведомить гостя: {e}")


# ============================================================
#  Бронирование (ConversationHandler)
# ============================================================

async def book_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data.clear()
    await q.edit_message_text(
        "Отлично! Давайте забронируем столик 🗓\n\n"
        "Как вас зовут?\n"
        "(Чтобы отменить — напишите /cancel)"
    )
    return NAME

async def book_start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "Отлично! Давайте забронируем столик 🗓\n\n"
        "Как вас зовут?\n"
        "(Чтобы отменить — напишите /cancel)"
    )
    return NAME

async def web_app_book(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Entry point из Mini App — получает стол если выбран."""
    import json
    try:
        data = json.loads(update.message.web_app_data.data)
    except Exception:
        return ConversationHandler.END

    if data.get("action") != "book":
        return ConversationHandler.END

    ctx.user_data.clear()
    tables = data.get("tables") or ([data["table"]] if data.get("table") else [])
    if tables:
        ctx.user_data["table"] = ", ".join(str(t) for t in tables)

    table_text = f"Столики {ctx.user_data['table']} выбраны! " if tables else ""
    await update.message.reply_text(
        f"{table_text}Давайте оформим бронь 🗓\n\n"
        "Как вас зовут?\n"
        "(Чтобы отменить — напишите /cancel)"
    )
    return NAME

async def got_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Ваш номер телефона?")
    return PHONE

async def got_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["phone"] = update.message.text.strip()
    await update.message.reply_text("На какую дату? (например: 15 июня или 15.06)")
    return DATE

async def got_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    date = parse_date(update.message.text)
    if not date:
        await update.message.reply_text(
            "Не понял дату 🤔 Напишите, например:\n"
            "• 15 июня\n"
            "• 15.06\n"
            "• 15/06/2026"
        )
        return DATE
    ctx.user_data["date"] = date
    await update.message.reply_text("На какое время? (например: 14:00 или 19.30)")
    return TIME

async def got_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    time = parse_time(update.message.text)
    if not time:
        await update.message.reply_text(
            "Не понял время 🤔 Напишите, например:\n"
            "• 14:00\n"
            "• 19:30\n"
            "• 1000"
        )
        return TIME
    ctx.user_data["time"] = time
    await update.message.reply_text(
        "Сколько гостей будет?",
        reply_markup=kb_guests(),
    )
    return GUESTS

async def got_guests(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["guests"] = q.data.split(":")[1]
    await q.edit_message_text(
        "Есть пожелания? (аллергии, детский праздник, особые пожелания...)\n"
        "Или нажмите «Пропустить».",
        reply_markup=kb_skip(),
    )
    return COMMENT

async def got_guests_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["guests"] = update.message.text.strip()
    await update.message.reply_text(
        "Есть пожелания?\n"
        "Или напишите «нет».",
    )
    return COMMENT

async def got_comment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        ctx.user_data["comment"] = ""
    else:
        ctx.user_data["comment"] = update.message.text.strip()

    await _finish_booking(update, ctx)
    return ConversationHandler.END

async def _finish_booking(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = ctx.user_data
    user = update.effective_user
    table = d.get("table", "")
    table_line = f"🪑 Стол №{table}\n" if table else ""

    booking_id = add_booking(
        user_id=user.id,
        username=user.username or "",
        name=d["name"],
        phone=d["phone"],
        date=d["date"],
        time=d["time"],
        guests=d["guests"],
        comment=d.get("comment", ""),
        table_number=table,
    )
    log.info(f"[БРОНЬ #{booking_id}] {d['name']} — {d['date']} {d['time']}"
             + (f" стол №{table}" if table else ""))

    admin_msg = (
        f"🗓 Новая бронь #{booking_id}\n\n"
        f"👤 {d['name']}\n"
        f"📞 {d['phone']}\n"
        f"📅 {d['date']} в {d['time']}\n"
        f"👥 {d['guests']} чел.\n"
        f"{table_line}"
        f"💬 {d.get('comment', '—') or '—'}\n\n"
        f"Telegram: @{user.username or '—'} (id: {user.id})"
    )
    try:
        await ctx.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_msg,
            reply_markup=kb_admin_booking(booking_id),
        )
    except Exception as e:
        log.error(f"Ошибка уведомления админа: {e}")

    confirm = (
        f"Заявка принята, {d['name']}! 🤍\n\n"
        f"📅 {d['date']} в {d['time']}\n"
        f"👥 {d['guests']} чел.\n"
        f"{table_line}"
        f"\nМы скоро подтвердим бронь — ждите сообщения от бота.\n"
        f"Вопросы: +7 (937) 849-23-18"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(confirm, reply_markup=kb_main())
    else:
        await update.message.reply_text(confirm, reply_markup=kb_main())

async def cancel_booking(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Бронирование отменено.", reply_markup=kb_main())
    return ConversationHandler.END


# ============================================================
#  Список броней для админа
# ============================================================

async def cmd_bookings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bookings = get_upcoming()
    if not bookings:
        await update.message.reply_text("Активных броней нет 👌")
        return

    STATUS = {"pending": "⏳ Ожидает", "confirmed": "✅ Подтверждена", "cancelled": "❌ Отменена"}
    await update.message.reply_text(f"📋 Броней: {len(bookings)}")

    for b in bookings:
        status = STATUS.get(b["status"], b["status"])
        table_line = f"🪑 Стол №{b['table_number']}\n" if b.get("table_number") else ""
        text = (
            f"{status} · #{b['id']}\n\n"
            f"👤 {b['name']}\n"
            f"📞 {b['phone']}\n"
            f"📅 {b['date']} в {b['time']}\n"
            f"👥 {b['guests']} чел.\n"
            f"{table_line}"
            f"💬 {b['comment'] or '—'}"
        )
        await update.message.reply_text(
            text,
            reply_markup=kb_admin_booking(b["id"]),
        )


async def free_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Чем могу помочь? Выберите раздел 👇\n\n"
        "По вопросам звоните: +7 (937) 849-23-18",
        reply_markup=kb_main(),
    )


# ============================================================
#  Запуск
# ============================================================

def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    booking = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(book_start, pattern="^book$"),
            CommandHandler("book", book_start_cmd),
            MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_book),
        ],
        states={
            NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, got_name)],
            PHONE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_phone)],
            DATE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, got_date)],
            TIME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, got_time)],
            GUESTS:  [
                CallbackQueryHandler(got_guests, pattern=r"^g:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_guests_text),
            ],
            COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_comment),
                CallbackQueryHandler(got_comment, pattern="^skip_comment$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_booking),
            CommandHandler("start",  cancel_booking),
        ],
        allow_reentry=True,
        per_message=False,
    )

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("bookings", cmd_bookings, filters=filters.User(ADMIN_ID)))
    app.add_handler(CommandHandler("book",     book_start_cmd))
    app.add_handler(booking)
    app.add_handler(CallbackQueryHandler(btn_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text))

    log.info("Hygge Kafé Bot запущен ✅")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
