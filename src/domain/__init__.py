"""Доменный слой MIS-QMS — правила поверх `src/db`, **без зависимости от UI**.

`architecture.md` §4: ядро UI-независимо, UI — единственный сменный слой.
Поэтому здесь не должно появляться импортов PySide6 (проверяется тестом).
Наряд 0002 / QMS-012.
"""

from .characteristics import get_or_create_characteristic
from .errors import DomainError, DuplicateValue, InvariantViolation, ProtectedValue, ValueInUse
from .findings import ensure_finding_target, make_finding
from .groups import GPositionSpec, create_group, list_groups
from .items import create_item, list_items, seed_cg_characteristics
from .reference import add_value, delete_value, list_values, rename_value, usage_count

__all__ = [
    "DomainError",
    "DuplicateValue",
    "GPositionSpec",
    "InvariantViolation",
    "ProtectedValue",
    "ValueInUse",
    "add_value",
    "create_group",
    "create_item",
    "delete_value",
    "ensure_finding_target",
    "get_or_create_characteristic",
    "list_groups",
    "list_items",
    "list_values",
    "make_finding",
    "rename_value",
    "seed_cg_characteristics",
    "usage_count",
]
