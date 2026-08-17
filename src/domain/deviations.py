"""Отклонение — регистрация, решение, список, удаление (наряд 0004).

Порядок канона: **регистрация — шаг 3, решение — шаг 8** (`_overview.md` §7).
Поэтому `register` создаёт запись с пустым решением (`decision_dev` nullable —
ратификация S1 №2), а `set_decision` — отдельное действие, которое выполняется
после изучения прецедентов. Разводить их по разным функциям — не формальность:
форма регистрации, предлагающая выбрать исход, толкала бы принять решение до
шага 6.

Область базы кончается решением (`Deviation.md`, scope boundary): судьба деталей
после него (сортировка → QC, повторные циклы, комитет) здесь не моделируется.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.ids import next_dev_number
from db.models import DECISION_DEV, Deviation, Finding, Inspection, Item

from .errors import ValidationError

#: Значение `quantity`, которым импорт (S6) помечает выборку `X מתוך Y`.
#: В ручном вводе — обычное число, отдельного флага не заводим (заметка А).
SAMPLING_QUANTITY = 9999


@dataclass(frozen=True)
class DeviationRow:
    """Строка списка отклонений — всё, что рисует экран, одним запросом.

    Счётчики считаются агрегатом, а не обходом коллекций: список открывается
    на каждом входе в раздел, а находки и исследования там не нужны целиком.
    """

    deviation_id: int
    dev_number: str
    item_number: str
    wo: str
    date: date_type
    quantity: int
    decision_dev: str | None
    findings: int
    inspections: int


def register(
    session: Session,
    *,
    item: Item,
    wo: str,
    quantity: int,
    date: date_type,
    machine: str | None = None,
    ncr: str | None = None,
    attachment: str | None = None,
) -> Deviation:
    """Зарегистрировать отклонение **без решения** (шаг 3 процесса).

    Находки добавляются отдельно (`findings.make_finding`); инвариант «находок
    `1..N`» держит форма ввода — в домене отклонение рождается пустым, иначе
    регистрацию нельзя было бы разложить на два шага.
    """
    if item is None:
        raise ValidationError("Деталь обязательна: отклонение без детали не адресуемо.")

    wo = (wo or "").strip()
    if not wo:
        raise ValidationError('Номер WO (פק"ע) обязателен.')

    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise ValidationError("Количество должно быть целым числом.")
    if quantity < 1:
        raise ValidationError("Количество деталей в отклонении должно быть не меньше 1.")

    if date is None:
        raise ValidationError("Дата отклонения обязательна.")
    if date > datetime.now().date():
        raise ValidationError(f"Дата отклонения {date:%d.%m.%Y} — в будущем.")

    # Номер берётся до создания объекта: он NOT NULL, и незаполненный Deviation
    # в сессии сорвал бы автофлаш перед SELECT счётчика (`db.ids`).
    deviation = Deviation(
        dev_number=next_dev_number(session),
        item=item,
        wo=wo,
        machine=_clean(machine),
        quantity=quantity,
        date=date,
        ncr=_clean(ncr),
        attachment=_clean(attachment),
    )
    session.add(deviation)
    session.flush()
    return deviation


def update_registration(
    session: Session,
    deviation: Deviation,
    *,
    wo: str,
    quantity: int,
    date: date_type,
    machine: str | None,
    ncr: str | None,
    attachment: str | None,
) -> Deviation:
    """Заменить шапку отклонения **целиком** (правило S3).

    Решения и детали не касается: исход меняется `set_decision`, а перенос
    отклонения на другую деталь осиротил бы находки — размеры принадлежат
    прежней детали (`Characteristic.md`), поэтому деталь после регистрации
    неизменна.
    """
    wo = (wo or "").strip()
    if not wo:
        raise ValidationError('Номер WO (פק"ע) обязателен.')
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise ValidationError("Количество должно быть целым числом.")
    if quantity < 1:
        raise ValidationError("Количество деталей в отклонении должно быть не меньше 1.")
    if date is None:
        raise ValidationError("Дата отклонения обязательна.")
    if date > datetime.now().date():
        raise ValidationError(f"Дата отклонения {date:%d.%m.%Y} — в будущем.")

    deviation.wo = wo
    deviation.quantity = quantity
    deviation.date = date
    deviation.machine = _clean(machine)
    deviation.ncr = _clean(ncr)
    deviation.attachment = _clean(attachment)
    session.flush()
    return deviation


def set_decision(
    session: Session,
    deviation: Deviation,
    *,
    decision: str,
    explanation: str,
    ncr: str | None = None,
    decision_date: datetime | None = None,
) -> Deviation:
    """Внести или сменить решение по отклонению (шаг 8 процесса).

    Смысл `None` у двух необязательных аргументов **разный**, и это намеренно:

    * `decision_date=None` — проставить системное время (решение принимается
      сейчас); повторный вызов перезаписывает дату, потому что она относится к
      действующему решению, а не к первому;
    * `ncr=None` — **не трогать** существующий NCR. Номер приходит от QA и может
      прийти позже решения (`Deviation.md`), а вводится он и на регистрации, и
      здесь; «не передали» обязано означать «оставить», иначе внесение решения
      стирало бы номер, введённый при регистрации. Снять номер явно — передать
      пустую строку.
    """
    if decision not in DECISION_DEV:
        raise ValidationError(
            f"Неизвестный исход «{decision}»: допустимы {', '.join(DECISION_DEV)}."
        )

    explanation = (explanation or "").strip()
    # Отложенная с S1 доменная валидация (ратификация №3): на одобрении
    # обоснование уходит в `אישור חריגה` (DS-QC.2-2) и пустым быть не может.
    if decision == "approved" and not explanation:
        raise ValidationError(
            "Одобрение требует обоснования: текст уходит в אישור חריגה."
        )

    deviation.decision_dev = decision
    deviation.explanation = explanation
    deviation.decision_date = decision_date or datetime.now()
    if ncr is not None:
        deviation.ncr = _clean(ncr)
    session.flush()
    return deviation


def list_deviations(session: Session, *, item: Item | None = None) -> list[DeviationRow]:
    """Строки списка отклонений, свежие сверху; `item` сужает до одной детали."""
    findings = (
        select(Finding.deviation_id, func.count().label("n"))
        .group_by(Finding.deviation_id)
        .subquery()
    )
    inspections = (
        select(Inspection.deviation_id, func.count().label("n"))
        .group_by(Inspection.deviation_id)
        .subquery()
    )

    query = (
        select(
            Deviation.deviation_id,
            Deviation.dev_number,
            Item.item_number,
            Deviation.wo,
            Deviation.date,
            Deviation.quantity,
            Deviation.decision_dev,
            func.coalesce(findings.c.n, 0),
            func.coalesce(inspections.c.n, 0),
        )
        .join(Item, Deviation.item_id == Item.item_id)
        .outerjoin(findings, findings.c.deviation_id == Deviation.deviation_id)
        .outerjoin(inspections, inspections.c.deviation_id == Deviation.deviation_id)
        .order_by(Deviation.date.desc(), Deviation.dev_number.desc())
    )
    if item is not None:
        query = query.where(Deviation.item_id == item.item_id)

    return [DeviationRow(*row) for row in session.execute(query)]


def delete_deviation(session: Session, deviation: Deviation) -> None:
    """Удалить отклонение вместе с находками и исследованиями.

    Каскад уже описан связями (`Deviation.findings` / `.inspections`), поэтому
    здесь нет ни ручного обхода, ни защиты: подтверждение спрашивает UI —
    единица целостности и есть отклонение целиком (`Deviation.md`).
    """
    session.delete(deviation)
    session.flush()


def _clean(value: str | None) -> str | None:
    """Пустая строка и пробелы — это отсутствие значения, а не значение."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
