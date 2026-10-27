"""Керування банком питань.

  python manage_questions.py stats              — скільки питань за темами й типами
  python manage_questions.py validate           — перевірити questions.json
  python manage_questions.py import FILE.csv    — додати питання з однією відповіддю
  python manage_questions.py import FILE.json   — додати питання будь-якого типу

CSV (UTF-8, з заголовком): topic,question,a,b,c,d,answer,explanation
  answer — літера А/Б/В/Г (або 1–4). topic — ключ теми з questions.json (напр. rus).
JSON: список об'єктів у форматі questions.json, поле id необов'язкове.
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

from questions import PATH, TYPES, validate

LETTERS = "АБВГ"


def read_db() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def from_csv(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            ans = row["answer"].strip().upper()
            rows.append({
                "topic": row["topic"].strip(), "type": "single", "question": row["question"].strip(),
                "options": [row[k].strip() for k in "abcd"],
                "answer": LETTERS.index(ans) if ans in LETTERS else int(ans) - 1,
                "explanation": row.get("explanation", "").strip(),
            })
    return rows


def import_file(path: Path) -> None:
    db = read_db()
    new = from_csv(path) if path.suffix.lower() == ".csv" else json.loads(path.read_text(encoding="utf-8"))
    ids = {q["id"] for q in db["questions"]}
    texts = {q["question"] for q in db["questions"]}
    added, skipped = 0, 0
    for n, q in enumerate(new, 1):
        errors = validate(q, db["topics"])
        if errors:
            print(f"рядок {n}: пропущено — {'; '.join(errors)}")
            skipped += 1
            continue
        if q["question"] in texts and q.get("type") == "single":
            print(f"рядок {n}: пропущено — таке питання вже є")
            skipped += 1
            continue
        if not q.get("id") or q["id"] in ids:
            i = 1
            while f"{q['topic']}-{q['type']}-{i:03d}" in ids:
                i += 1
            q["id"] = f"{q['topic']}-{q['type']}-{i:03d}"
        q.setdefault("explanation", "")
        ids.add(q["id"])
        texts.add(q["question"])
        db["questions"].append(q)
        added += 1
    PATH.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Додано: {added}, пропущено: {skipped}")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "import" and len(sys.argv) == 3:
        import_file(Path(sys.argv[2]))
    elif cmd == "validate":
        from questions import load
        _, qs = load()
        print(f"OK: {len(qs)} питань")
    elif cmd == "stats":
        db = read_db()
        by_type = Counter(q["type"] for q in db["questions"])
        by_topic = Counter(q["topic"] for q in db["questions"])
        print(f"Усього: {len(db['questions'])}")
        for k, name in TYPES.items():
            print(f"  {name}: {by_type[k]}")
        for k, name in db["topics"].items():
            print(f"  {name}: {by_topic[k]}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
