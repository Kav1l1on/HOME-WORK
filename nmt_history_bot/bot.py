"""Телеграм-бот для підготовки до НМТ з історії України (2027)."""

import asyncio
import logging
import os
import random
import sqlite3
from datetime import date

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from questions import QUESTIONS, TOPICS

LETTERS = "АБВГ"
TEST_SIZE = 10
DB_PATH = os.getenv("DB_PATH", "stats.db")
NMT_DATE = date(2027, 5, 20)  # орієнтовна дата початку основної сесії; уточніть на testportal.gov.ua

dp = Dispatcher()
# user_id -> {"queue": [(topic, idx), ...], "current": (topic, idx), "correct": int, "total": int}
sessions: dict[int, dict] = {}


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS answers ("
        "user_id INTEGER, topic TEXT, idx INTEGER, correct INTEGER)"
    )
    return conn


def save_answer(user_id: int, topic: str, idx: int, correct: bool) -> None:
    with db() as conn:
        conn.execute("INSERT INTO answers VALUES (?, ?, ?, ?)", (user_id, topic, idx, int(correct)))


def mistakes(user_id: int) -> list[tuple[str, int]]:
    """Питання, на які остання відповідь користувача була хибною."""
    with db() as conn:
        rows = conn.execute(
            "SELECT topic, idx, correct FROM answers WHERE user_id = ? ORDER BY rowid", (user_id,)
        ).fetchall()
    last = {(t, i): c for t, i, c in rows}
    return [k for k, c in last.items() if not c and k[0] in QUESTIONS and k[1] < len(QUESTIONS[k[0]])]


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Тест (10 питань)", callback_data="mode:random")],
        [InlineKeyboardButton(text="📚 Тест за темою", callback_data="mode:topics")],
        [InlineKeyboardButton(text="🔁 Робота над помилками", callback_data="mode:mistakes")],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="mode:stats")],
    ])


def topics_menu() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"topic:{key}")] for key, name in TOPICS.items()]
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="mode:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def days_left() -> str:
    days = (NMT_DATE - date.today()).days
    return f"До НМТ-2027 орієнтовно {days} дн." if days > 0 else "НМТ-2027 вже розпочалося — успіхів!"


async def start_test(message: Message, user_id: int, queue: list[tuple[str, int]]) -> None:
    random.shuffle(queue)
    sessions[user_id] = {"queue": queue[:TEST_SIZE], "correct": 0, "total": 0}
    await send_question(message, user_id)


async def send_question(message: Message, user_id: int) -> None:
    s = sessions[user_id]
    if not s["queue"]:
        pct = round(100 * s["correct"] / s["total"]) if s["total"] else 0
        await message.answer(
            f"🏁 Тест завершено: {s['correct']}/{s['total']} ({pct}%).",
            reply_markup=main_menu(),
        )
        sessions.pop(user_id)
        return
    topic, idx = s["current"] = s["queue"].pop()
    q = QUESTIONS[topic][idx]
    s["order"] = random.sample(range(len(q["o"])), len(q["o"]))  # перемішуємо варіанти
    n = s["total"] + 1
    text = f"<b>Питання {n}</b> · <i>{TOPICS[topic]}</i>\n\n{q['q']}\n\n" + "\n".join(
        f"{LETTERS[pos]}) {q['o'][orig]}" for pos, orig in enumerate(s["order"])
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LETTERS[i], callback_data=f"ans:{i}") for i in range(len(q["o"]))],
        [InlineKeyboardButton(text="⏹ Завершити", callback_data="mode:stop")],
    ])
    await message.answer(text, reply_markup=kb)


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привіт! 👋 Я допоможу підготуватися до <b>НМТ з історії України 2027</b>.\n\n"
        f"У базі {sum(map(len, QUESTIONS.values()))} питань з {len(TOPICS)} тем — від стародавньої "
        f"історії до сучасності.\n{days_left()}\n\nОбери режим:",
        reply_markup=main_menu(),
    )


@dp.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Обери режим:", reply_markup=main_menu())


@dp.callback_query(F.data.startswith("mode:"))
async def on_mode(cb: CallbackQuery) -> None:
    mode = cb.data.split(":", 1)[1]
    uid = cb.from_user.id
    await cb.answer()
    if mode == "random":
        await start_test(cb.message, uid, [(t, i) for t, qs in QUESTIONS.items() for i in range(len(qs))])
    elif mode == "topics":
        await cb.message.answer("Обери тему:", reply_markup=topics_menu())
    elif mode == "mistakes":
        queue = mistakes(uid)
        if not queue:
            await cb.message.answer("Помилок поки немає 🎉", reply_markup=main_menu())
        else:
            await start_test(cb.message, uid, queue)
    elif mode == "stats":
        await cb.message.answer(stats_text(uid), reply_markup=main_menu())
    elif mode == "stop":
        sessions.pop(uid, None)
        await cb.message.answer("Тест зупинено.", reply_markup=main_menu())
    else:
        await cb.message.answer("Обери режим:", reply_markup=main_menu())


@dp.callback_query(F.data.startswith("topic:"))
async def on_topic(cb: CallbackQuery) -> None:
    topic = cb.data.split(":", 1)[1]
    await cb.answer()
    if topic in QUESTIONS:
        await start_test(cb.message, cb.from_user.id, [(topic, i) for i in range(len(QUESTIONS[topic]))])


@dp.callback_query(F.data.startswith("ans:"))
async def on_answer(cb: CallbackQuery) -> None:
    uid = cb.from_user.id
    s = sessions.get(uid)
    if not s or "current" not in s:
        await cb.answer("Тест неактивний. Почни новий через /menu", show_alert=True)
        return
    order = s["order"]
    choice = order[int(cb.data.split(":", 1)[1])]
    topic, idx = s.pop("current")
    q = QUESTIONS[topic][idx]
    ok = choice == q["a"]
    s["total"] += 1
    s["correct"] += ok
    save_answer(uid, topic, idx, ok)
    verdict = "✅ Правильно!" if ok else f"❌ Неправильно. Правильна відповідь: {LETTERS[order.index(q['a'])]}) {q['o'][q['a']]}"
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(f"{verdict}\n\n💡 {q['e']}")
    await send_question(cb.message, uid)


def stats_text(user_id: int) -> str:
    with db() as conn:
        rows = conn.execute(
            "SELECT topic, COUNT(*), SUM(correct) FROM answers WHERE user_id = ? GROUP BY topic", (user_id,)
        ).fetchall()
    if not rows:
        return "Статистики ще немає — пройди перший тест!"
    total = sum(r[1] for r in rows)
    correct = sum(r[2] for r in rows)
    lines = [f"📊 Усього відповідей: {total}, правильних: {correct} ({round(100 * correct / total)}%)\n"]
    for topic, n, c in sorted(rows, key=lambda r: r[2] / r[1]):
        lines.append(f"• {TOPICS.get(topic, topic)}: {c}/{n} ({round(100 * c / n)}%)")
    lines.append("\nТеми зверху — найслабші, почни з них.")
    return "\n".join(lines)


async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("Вкажіть токен бота у змінній середовища BOT_TOKEN")
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
