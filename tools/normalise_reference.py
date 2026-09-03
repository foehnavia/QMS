"""Свести близнецов по регистру в справочниках базы — доменной операцией.

Наряд 0021. Инструмент **ничего не решает сам**: вся логика в
`domain.reference.normalise_all`, здесь только открыть базу, позвать её и
показать оператору, что сделано с его данными (§4.3).

Тем же путём пойдёт импорт `.xlsx` на S6, где регистр придёт из чужой таблицы.

    python tools/normalise_reference.py [путь-к-базе]

Перед правкой рядом с базой кладётся копия `<имя>.before-0021.sqlite`: работа
идёт с данными прогона, и откат должен быть возможен без git.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from db.session import create_db_engine, session_scope  # noqa: E402
from domain.reference import normalise_all  # noqa: E402


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "data" / "qms016.sqlite"
    if not target.exists():
        print(f"База не найдена: {target}")
        return 1

    backup = target.with_suffix(".before-0021.sqlite")
    shutil.copyfile(target, backup)
    print(f"Копия до правки: {backup.name}")

    engine = create_db_engine(f"sqlite:///{target.as_posix()}")
    with session_scope(engine) as session:
        report = normalise_all(session)
    engine.dispose()

    print()
    print(f"{'список':22} {'выжило':22} {'снято':22} {'перевешено':>10}")
    total = 0
    for table, rows in report.items():
        for keep, drop, moved in rows:
            print(f"{table:22} {keep:22} {drop:22} {moved:>10}")
            total += moved
    if not any(report.values()):
        print("(близнецов не найдено)")
    print()
    print(f"перевешено записей: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
