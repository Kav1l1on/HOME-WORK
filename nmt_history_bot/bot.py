"""Телеграм-бот для підготовки до НМТ з історії України (2027)."""

import asyncio
import logging
import os
import random
import sqlite3
from datetime import date
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from questions import MAX_SCORE, QUESTIONS, TOPICS, TYPES

LETTERS = "АБВГД"
TEST_SIZE = 10
# Структура тесту НМТ з історії України: 20 + 4 + 3 + 3 = 30 завдань, максимум 54 бали
NMT_PLAN = {"single": 20, "match": 4, "order": 3, "multi": 3}
DB_PATH = os.getenv("DB_PATH", "stats.db")
NMT_DATE = date(2027, 5, 20)  # орієнтовна дата початку основної сесії; уточніть на testportal.gov.ua

dp = Dispatcher()
# user_id -> {"queue": [qid, ...], "score": int, "max": int, "n": int, "cur": {...}, "title": str}
sessions: dict[int, dict] = {}


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS results ("
        "user_id INTEGER, qid TEXT, topic TEXT, score INTEGER, max_score INTEGER)"
    )
    return conn


def save_result(user_id: int, q: dict, score: int) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO results VALUES (?, ?, ?, ?, ?)", (user_id, q["id"], q["topic"], score, MAX_SCORE[q["type"]])
        )


def mistakes(user_id: int) -> list[str]:
    """Питання, на які остання відповідь користувача була не повністю правильною."""
    with db() as conn:
        rows = conn.execute(
            "SELECT qid, score, max_score FROM results WHERE user_id = ? ORDER BY rowid", (user_id,)
        ).fetchall()
    last = {qid: score < mx for qid, score, mx in rows}
    return [qid for qid, wrong in last.items() if wrong and qid in QUESTIONS]


def button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("🎯 Симуляція НМТ (30 завдань)", "mode:nmt")],
        [button("🎲 Швидкий тест (10 завдань)", "mode:random")],
        [button("📚 За темою", "mode:topics"), button("🧩 За типом", "mode:types")],
        [button("🔁 Робота над помилками", "mode:mistakes")],
        [button("📊 Моя статистика", "mode:stats")],
    ])


def list_menu(items: dict[str, str], prefix: str) -> InlineKeyboardMarkup:
    rows = [[button(name, f"{prefix}:{key}")] for key, name in items.items()]
    rows.append([button("⬅️ Меню", "mode:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def days_left() -> str:
    days = (NMT_DATE - date.today()).days
    return f"До НМТ-2027 орієнтовно {days} дн." if days > 0 else "НМТ-2027 вже розпочалося — успіхів!"


def pick(qids: list[str], n: int) -> list[str]:
    return random.sample(qids, min(n, len(qids)))


async def start_test(message: Message, user_id: int, queue: list[str], title: str) -> None:
    if not queue:
        await message.answer("Немає завдань для цього режиму.", reply_markup=main_menu())
        return
    sessions[user_id] = {"queue": queue, "score": 0, "max": 0, "n": 0, "title": title}
    await send_question(message, user_id)


# ---------- рендер завдань ----------

def render(q: dict, cur: dict, n: int, total: int) -> tuple[str, InlineKeyboardMarkup]:
    head = f"<b>Завдання {n}/{total}</b> · <i>{TOPICS[q['topic']]}</i> · {TYPES[q['type']]}\n\n{escape(q['question'])}\n\n"
    stop = [button("⏹ Завершити", "stop")]
    kind = q["type"]

    if kind == "single":
        body = "\n".join(f"{LETTERS[p]}) {escape(q['options'][o])}" for p, o in enumerate(cur["order"]))
        kb = [[button(LETTERS[p], f"a:{p}") for p in range(4)], stop]

    elif kind == "match":
        body = "\n".join(f"{i + 1}) {escape(t)}" for i, t in enumerate(q["left"])) + "\n\n"
        body += "\n".join(f"{LETTERS[p]}) {escape(q['right'][o])}" for p, o in enumerate(cur["order"]))
        picks = cur["picks"]
        body += "\n\nВаша відповідь: " + "  ".join(
            f"{i + 1}{LETTERS[picks[i]] if i < len(picks) else '?'}" for i in range(4)
        )
        body += f"\n<b>Оберіть відповідник для {len(picks) + 1}:</b>"
        kb = [[button(LETTERS[p], f"a:{p}") for p in range(5) if p not in picks], stop]

    elif kind == "order":
        body = "\n".join(f"{LETTERS[p]}) {escape(q['items'][o])}" for p, o in enumerate(cur["order"]))
        picks = cur["picks"]
        body += "\n\nПослідовність: " + (" → ".join(LETTERS[p] for p in picks) or "…")
        body += f"\n<b>Оберіть подію №{len(picks) + 1}:</b>"
        kb = [[button(LETTERS[p], f"a:{p}") for p in range(4) if p not in picks], stop]

    else:  # multi
        body = "\n".join(f"{p + 1}) {escape(q['options'][o])}" for p, o in enumerate(cur["order"]))
        picks = cur["picks"]
        body += f"\n\nОбрано: {', '.join(str(p + 1) for p in sorted(picks)) or '—'} (потрібно 3)"
        kb = [[button(f"{'✅' if p in picks else ''}{p + 1}", f"a:{p}") for p in range(7)]]
        if len(picks) == 3:
            kb.append([button("✔️ Готово", "done")])
        kb.append(stop)

    return head + body, InlineKeyboardMarkup(inline_keyboard=kb)


def new_state(q: dict) -> dict:
    size = {"single": 4, "match": 5, "order": 4, "multi": 7}[q["type"]]
    return {"qid": q["id"], "order": random.sample(range(size), size), "picks": []}


def grade(q: dict, cur: dict) -> tuple[int, str]:
    """Повертає бали та текст із правильною відповіддю."""
    order, picks, kind = cur["order"], cur["picks"], q["type"]
    if kind == "single":
        score = int(order[picks[0]] == q["answer"])
        right = f"{LETTERS[order.index(q['answer'])]}) {escape(q['options'][q['answer']])}"
    elif kind == "match":
        score = sum(order[picks[i]] == q["answer"][i] for i in range(4))
        right = "\n".join(
            f"{i + 1}{LETTERS[order.index(q['answer'][i])]} — {escape(q['left'][i])} → {escape(q['right'][q['answer'][i]])}"
            for i in range(4)
        )
    elif kind == "order":
        in_place = sum(order[p] == i for i, p in enumerate(picks))
        score = 3 if in_place == 4 else min(in_place, 2)  # спрощене оцінювання
        dates = q.get("dates") or [""] * 4
        right = "\n".join(
            f"{LETTERS[order.index(i)]}) {escape(t)}{f' ({escape(dates[i])})' if dates[i] else ''}"
            for i, t in enumerate(q["items"])
        )
    else:
        score = sum(order[p] in q["answer"] for p in picks)
        right = ", ".join(f"{order.index(a) + 1}) {escape(q['options'][a])}" for a in sorted(q["answer"], key=order.index))
    return score, right


async def send_question(message: Message, user_id: int) -> None:
    s = sessions[user_id]
    if not s["queue"]:
        pct = round(100 * s["score"] / s["max"]) if s["max"] else 0
        await message.answer(
            f"🏁 <b>{s['title']}</b> завершено: {s['score']}/{s['max']} балів ({pct}%).",
            reply_markup=main_menu(),
        )
        sessions.pop(user_id)
        return
    q = QUESTIONS[s["queue"].pop(0)]
    s["n"] += 1
    s["cur"] = new_state(q)
    text, kb = render(q, s["cur"], s["n"], s["n"] + len(s["queue"]))
    sent = await message.answer(text, reply_markup=kb)
    s["cur"]["msg_id"] = sent.message_id


async def finish_question(cb: CallbackQuery, s: dict, q: dict) -> None:
    score, right = grade(q, s["cur"])
    mx = MAX_SCORE[q["type"]]
    s["score"] += score
    s["max"] += mx
    save_result(cb.from_user.id, q, score)
    s.pop("cur")
    if score == mx:
        verdict = "✅ Правильно!" if mx == 1 else f"✅ Правильно! {score}/{mx}"
    else:
        verdict = f"❌ {score}/{mx}. Правильна відповідь:\n{right}"
    if q.get("explanation"):
        verdict += f"\n\n💡 {escape(q['explanation'])}"
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(verdict)
    await send_question(cb.message, cb.from_user.id)


# ---------- обробники ----------

@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привіт! 👋 Я допоможу підготуватися до <b>НМТ з історії України 2027</b>.\n\n"
        f"У базі {len(QUESTIONS)} завдань усіх чотирьох типів НМТ з {len(TOPICS)} тем.\n"
        f"{days_left()}\n\nОбери режим:",
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
    if mode == "nmt":
        queue = []
        for kind, n in NMT_PLAN.items():
            queue += pick([qid for qid, q in QUESTIONS.items() if q["type"] == kind], n)
        await start_test(cb.message, uid, queue, "Симуляцію НМТ")
    elif mode == "random":
        await start_test(cb.message, uid, pick(list(QUESTIONS), TEST_SIZE), "Тест")
    elif mode == "topics":
        await cb.message.answer("Обери тему:", reply_markup=list_menu(TOPICS, "topic"))
    elif mode == "types":
        await cb.message.answer("Обери тип завдань:", reply_markup=list_menu(TYPES, "type"))
    elif mode == "mistakes":
        queue = mistakes(uid)
        if not queue:
            await cb.message.answer("Помилок поки немає 🎉", reply_markup=main_menu())
        else:
            await start_test(cb.message, uid, pick(queue, TEST_SIZE), "Роботу над помилками")
    elif mode == "stats":
        await cb.message.answer(stats_text(uid), reply_markup=main_menu())
    else:
        await cb.message.answer("Обери режим:", reply_markup=main_menu())


@dp.callback_query(F.data.startswith("topic:") | F.data.startswith("type:"))
async def on_filter(cb: CallbackQuery) -> None:
    field, value = cb.data.split(":", 1)
    await cb.answer()
    title = f"Тест «{TOPICS.get(value) or TYPES.get(value)}»"
    qids = [qid for qid, q in QUESTIONS.items() if q[field] == value]
    await start_test(cb.message, cb.from_user.id, pick(qids, TEST_SIZE), title)


@dp.callback_query(F.data == "stop")
async def on_stop(cb: CallbackQuery) -> None:
    await cb.answer()
    s = sessions.pop(cb.from_user.id, None)
    await cb.message.edit_reply_markup(reply_markup=None)
    result = f" Набрано {s['score']}/{s['max']} балів." if s and s["max"] else ""
    await cb.message.answer(f"Тест зупинено.{result}", reply_markup=main_menu())


@dp.callback_query(F.data.startswith("a:") | (F.data == "done"))
async def on_answer(cb: CallbackQuery) -> None:
    s = sessions.get(cb.from_user.id)
    cur = s.get("cur") if s else None
    if not cur or cur["msg_id"] != cb.message.message_id:
        await cb.answer("Це завдання вже неактивне. Почни новий тест через /menu", show_alert=True)
        return
    await cb.answer()
    q = QUESTIONS[cur["qid"]]
    picks = cur["picks"]

    if cb.data == "done":
        if q["type"] == "multi" and len(picks) == 3:
            await finish_question(cb, s, q)
        return

    p = int(cb.data.split(":", 1)[1])
    if q["type"] == "multi":
        if p in picks:
            picks.remove(p)
        elif len(picks) < 3:
            picks.append(p)
        else:
            return
    elif p not in picks:
        picks.append(p)
    else:
        return

    need = {"single": 1, "match": 4, "order": 4}.get(q["type"])
    if need and len(picks) == need:
        await finish_question(cb, s, q)
    else:
        text, kb = render(q, cur, s["n"], s["n"] + len(s["queue"]))
        await cb.message.edit_text(text, reply_markup=kb)


def stats_text(user_id: int) -> str:
    with db() as conn:
        rows = conn.execute(
            "SELECT topic, COUNT(*), SUM(score), SUM(max_score) FROM results WHERE user_id = ? GROUP BY topic",
            (user_id,),
        ).fetchall()
    if not rows:
        return "Статистики ще немає — пройди перший тест!"
    n = sum(r[1] for r in rows)
    score = sum(r[2] for r in rows)
    mx = sum(r[3] for r in rows)
    lines = [f"📊 Виконано завдань: {n}, балів: {score}/{mx} ({round(100 * score / mx)}%)\n"]
    for topic, cnt, sc, m in sorted(rows, key=lambda r: r[2] / r[3]):
        lines.append(f"• {TOPICS.get(topic, topic)}: {sc}/{m} ({round(100 * sc / m)}%)")
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
