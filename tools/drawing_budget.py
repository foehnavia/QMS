"""Вес чертежей и порог по числу групп — **замер**, а не оценка (наряд `0040` §5).

Расплывчатое «база не должна расти больше ~200 МБ» заменяется правилом
«вес чертежа × число групп». От инструмента — числа; формулировку правила в канон
вносит Cowork.

Живёт в `tools/`, а не в отчёте одного наряда, ровно затем, чтобы через год не
мерить руками заново: порог пересчитывается той же командой на той же базе.

    python tools/drawing_budget.py               # рабочая app.sqlite
    python tools/drawing_budget.py путь.sqlite   # любая другая

Что печатает: размер файла базы, статистику блоба `characteristic_group.drawing`
(минимум, медиана, максимум, сумма), сколько групп всего и у скольких есть
чертёж, и при каком числе групп база достигает 200 МБ и 1 ГБ — **отдельно** по
медианному и по максимальному чертежу.

**Медиана и максимум разведены намеренно.** Порог по медиане отвечает на вопрос
«когда это случится при обычных чертежах», порог по максимуму — «когда это может
случиться раньше всего». Одно число вместо двух пришлось бы округлять в чью-то
сторону, а обе стороны нужны: первая планирует, вторая предупреждает.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from statistics import median

REPO_ROOT = Path(__file__).resolve().parents[1]

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

MB = 1024 * 1024
GB = 1024 * MB

#: Пороги, о которых спрашивает наряд. Значения — вопрос, а не норма: нормой их
#: делает канон, если Cowork так решит.
THRESHOLDS = (("200 МБ", 200 * MB), ("1 ГБ", GB))


def _human(size: float) -> str:
    if size >= GB:
        return f"{size / GB:.2f} ГБ"
    if size >= MB:
        return f"{size / MB:.2f} МБ"
    if size >= 1024:
        return f"{size / 1024:.1f} КБ"
    return f"{size:.0f} Б"


def measure(db_path: Path) -> dict:
    """Снять числа с базы. Чистая функция от пути: ничего не пишет."""
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        cursor = connection.cursor()
        groups = cursor.execute("SELECT COUNT(*) FROM characteristic_group").fetchone()[0]
        sizes = [
            row[0]
            for row in cursor.execute(
                "SELECT LENGTH(drawing) FROM characteristic_group WHERE drawing IS NOT NULL"
            )
        ]
    finally:
        connection.close()

    return {
        "db_bytes": db_path.stat().st_size,
        "groups": groups,
        "with_drawing": len(sizes),
        "sizes": sorted(sizes),
    }


def report(db_path: Path) -> int:
    if not db_path.exists():
        print(f"базы нет по пути {db_path}", flush=True)
        return 1

    data = measure(db_path)
    sizes = data["sizes"]

    print(f"база                : {db_path}")
    print(f"размер файла        : {_human(data['db_bytes'])} ({data['db_bytes']} Б)")
    print(f"групп всего         : {data['groups']}")
    print(f"из них с чертежом   : {data['with_drawing']}")

    if not sizes:
        print("\nчертежей в базе нет — считать нечего.")
        print("Порог по чертежам меряется на базе, где чертежи есть; синтетикой")
        print("досеивать не надо: число из выдуманных данных хуже честного «нечего мерить».")
        return 0

    low, mid, high = sizes[0], median(sizes), sizes[-1]
    total = sum(sizes)
    print(f"\nблоб `drawing`      : минимум {_human(low)} · медиана {_human(mid)}"
          f" · максимум {_human(high)}")
    print(f"сумма чертежей      : {_human(total)}"
          f"  ({total / data['db_bytes'] * 100:.0f} % файла базы)")

    if len(sizes) < 3:
        print(f"\n[!] Чертежей всего {len(sizes)} — медиана на таком числе величина условная.")
        print("    Числа ниже честны ровно настолько, насколько представительны эти чертежи.")

    print("\nпри каком числе групп с чертежом база достигнет порога:")
    print(f"    {'порог':8} {'по медиане':>14} {'по максимуму':>14}")
    for name, limit in THRESHOLDS:
        by_median = int(limit // mid) if mid else 0
        by_max = int(limit // high) if high else 0
        print(f"    {name:8} {by_median:>14} {by_max:>14}")
    print("\nсчитается по весу самих чертежей: прочие данные на фоне блобов пренебрежимы")
    print("(их доля видна строкой «сумма чертежей» выше).")
    return 0


def main(argv: list[str]) -> int:
    db_path = Path(argv[1]) if len(argv) > 1 else REPO_ROOT / "app.sqlite"
    return report(db_path.resolve())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
