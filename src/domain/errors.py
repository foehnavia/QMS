"""Ошибки бизнес-правил.

Текст сообщения пишется **для оператора** — UI показывает его как есть, не
переформулируя. Сырые `IntegrityError` до оператора не доходят.
"""

from __future__ import annotations


class DomainError(Exception):
    """Нарушено бизнес-правило. Сообщение годится для показа оператору."""


class DuplicateValue(DomainError):
    """Значение с таким ключом уже есть (UNIQUE)."""


class ProtectedValue(DomainError):
    """Структурный дефолт — правке и удалению не подлежит (`General`)."""


class ValueInUse(DomainError):
    """На значение справочника ссылаются записи — удалять нельзя."""


class InvariantViolation(DomainError):
    """Нарушен инвариант модели (напр. находка не принадлежит детали отклонения)."""


class ValidationError(DomainError):
    """Ввод не прошёл проверку (пусто, не число, отрицательный индекс…)."""
