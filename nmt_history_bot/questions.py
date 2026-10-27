"""Завантаження та перевірка банку питань (questions.json).

Типи завдань (як на НМТ):
  single — одна правильна відповідь із 4: options, answer (індекс)
  match  — відповідність 4 → 5: left (4), right (5), answer (індекс у right для кожного left)
  order  — хронологічна послідовність: items (4, у правильному порядку), dates (необов'язково)
  multi  — три правильні з 7: options (7), answer (3 індекси)
"""

import json
from pathlib import Path

PATH = Path(__file__).with_name("questions.json")
TYPES = {"single": "Одна правильна відповідь", "match": "Відповідність", "order": "Послідовність", "multi": "Три з семи"}
MAX_SCORE = {"single": 1, "match": 4, "order": 3, "multi": 3}


def validate(q: dict, topics: dict) -> list[str]:
    """Повертає список помилок у питанні (порожній — питання коректне)."""
    errors = []
    kind = q.get("type")
    if kind not in TYPES:
        return [f"невідомий тип {kind!r}"]
    if q.get("topic") not in topics:
        errors.append(f"невідома тема {q.get('topic')!r}")
    if not str(q.get("question", "")).strip():
        errors.append("порожній текст питання")
    ans = q.get("answer")
    if kind == "single":
        opts = q.get("options", [])
        if len(opts) != 4 or len(set(opts)) != 4:
            errors.append("потрібно 4 різні варіанти")
        if not isinstance(ans, int) or not 0 <= ans < 4:
            errors.append("answer — індекс 0–3")
    elif kind == "match":
        left, right = q.get("left", []), q.get("right", [])
        if len(left) != 4 or len(right) != 5 or len(set(right)) != 5:
            errors.append("потрібно 4 елементи зліва і 5 різних справа")
        if not isinstance(ans, list) or len(ans) != 4 or len(set(ans)) != 4 or not all(0 <= a < 5 for a in ans):
            errors.append("answer — 4 різні індекси 0–4")
    elif kind == "order":
        items = q.get("items", [])
        if len(items) != 4 or len(set(items)) != 4:
            errors.append("потрібно 4 різні події")
        if q.get("dates") and len(q["dates"]) != 4:
            errors.append("dates має містити 4 значення")
    elif kind == "multi":
        opts = q.get("options", [])
        if len(opts) != 7 or len(set(opts)) != 7:
            errors.append("потрібно 7 різних варіантів")
        if not isinstance(ans, list) or len(set(ans)) != 3 or not all(0 <= a < 7 for a in ans):
            errors.append("answer — 3 різні індекси 0–6")
    return errors


def load(path: Path = PATH) -> tuple[dict[str, str], dict[str, dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    topics = data["topics"]
    questions = {}
    for q in data["questions"]:
        errors = validate(q, topics)
        if errors:
            raise ValueError(f"{q.get('id')}: {'; '.join(errors)}")
        if q["id"] in questions:
            raise ValueError(f"дубль id {q['id']}")
        questions[q["id"]] = q
    return topics, questions


TOPICS, QUESTIONS = load()
