"""Генерация человекочитаемых бизнес-номеров: `DEV-YYMMDD-NNNN`, `INSP-YYMMDD-NNN`.

Правило `YYMMDD` (заметка А/Б наряда 0001): берётся **системная дата в момент
присвоения** номера, а не `date` события и не `decision_date`.

* `decision_date` на момент регистрации ещё не существует — решение принимается
  на шаге 8 процесса, а отклонение регистрируется на шаге 3;
* `date` события может приходить задним числом (импорт S6), что ломало бы
  монотонность номеров и заставляло дописываться в уже израсходованный
  суточный счётчик.

Номер идентифицирует **запись**, а не физическое событие. Дату можно передать
явно (`on_date=`) — этого достаточно для тестов и для будущего импорта.

Счётчик — сквозной в пределах суток, выводится из максимума уже выданных
номеров того же дня (нулевая набивка делает лексикографический максимум равным
числовому). Уникальность гарантируется UNIQUE-констрейнтом на колонке.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from .models import Deviation, Inspection

DEV_PREFIX = "DEV"
DEV_WIDTH = 4
INSP_PREFIX = "INSP"
INSP_WIDTH = 3


class NumberSpaceExhausted(RuntimeError):
    """За сутки исчерпан суточный счётчик (99 999 отклонений/999 исследований)."""


def _next_number(
    session: Session,
    column: ColumnElement[str],
    *,
    prefix: str,
    width: int,
    on_date: date_type | None,
) -> str:
    day = (on_date or datetime.now().date()).strftime("%y%m%d")
    stem = f"{prefix}-{day}-"
    # Автофлаш до SELECT делает видимыми ранее добавленные в эту же сессию записи,
    # поэтому пакетная вставка за один день не даёт дублей.
    last = session.execute(
        select(func.max(column)).where(column.like(f"{stem}%"))
    ).scalar_one_or_none()
    seq = 1 if last is None else int(last[len(stem) :]) + 1
    if seq >= 10**width:
        raise NumberSpaceExhausted(f"{stem}: the daily counter is exhausted")
    return f"{stem}{seq:0{width}d}"


def next_dev_number(session: Session, on_date: date_type | None = None) -> str:
    """Следующий номер отклонения `DEV-YYMMDD-NNNN`.

    Вызывать **до** создания объекта Deviation: номер обязателен (NOT NULL), а
    незаполненный объект в сессии сорвал бы автофлаш перед SELECT.
    """
    return _next_number(
        session, Deviation.dev_number, prefix=DEV_PREFIX, width=DEV_WIDTH, on_date=on_date
    )


def next_insp_number(session: Session, on_date: date_type | None = None) -> str:
    """Следующий номер исследования `INSP-YYMMDD-NNN`."""
    return _next_number(
        session,
        Inspection.insp_number,
        prefix=INSP_PREFIX,
        width=INSP_WIDTH,
        on_date=on_date,
    )
