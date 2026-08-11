"""CLI: сид справочников и (опционально) синтетический датасет.

    python tools/seed_db.py                    # только справочники (идемпотентно)
    python tools/seed_db.py --synthetic        # + синтетика (ожидает чистую БД)
    python tools/seed_db.py --url sqlite:///demo.sqlite

Схему создаёт Alembic (`alembic upgrade head`), не этот скрипт.
Наряд 0001 / QMS-011.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Консоль целевой машины — cp1255 (иврит): без этого падает печать и кириллицы,
# и ивритских значений из БД.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from db.session import create_db_engine, default_db_url, session_scope  # noqa: E402
from seed import build_synthetic, seed_reference  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=None, help="URL БД (по умолчанию QMS_DB_URL / app.sqlite)")
    parser.add_argument(
        "--synthetic", action="store_true", help="дополнительно налить синтетический датасет"
    )
    args = parser.parse_args(argv)

    url = args.url or default_db_url()
    engine = create_db_engine(url)
    print(f"БД: {url}")

    with session_scope(engine) as session:
        inserted = seed_reference(session)
        for table, count in inserted.items():
            print(f"  справочник {table}: вставлено {count}")
        if args.synthetic:
            data = build_synthetic(session)
            print(
                f"  синтетика: деталей {len(data['items'])}, "
                f"отклонений {len(data['deviations'])}, "
                f"исследований {len(data['inspections'])}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
