"""Доменный слой MIS-QMS — правила поверх `src/db`, **без зависимости от UI**.

`architecture.md` §4: ядро UI-независимо, UI — единственный сменный слой.
Поэтому здесь не должно появляться импортов PySide6 (проверяется тестом).
Наряды 0002 / QMS-012 и 0003 / QMS-013.
"""

from .characteristics import get_or_create_characteristic
from .errors import (
    DomainError,
    DuplicateValue,
    InvariantViolation,
    ProtectedValue,
    ValidationError,
    ValueInUse,
)
from .findings import ensure_finding_target, make_finding
from .groups import (
    GPositionSpec,
    add_position,
    create_group,
    list_groups,
    position_usage,
    remove_position,
    set_drawing,
    update_group,
    update_position,
)
from .items import create_item, groups_of, list_items, seed_cg_characteristics
from .mappings import (
    PositionState,
    binding_state,
    bind,
    clear,
    is_complete,
    items_by_position,
    mark_absent,
)
from .reference import add_value, delete_value, list_values, rename_value, usage_count

__all__ = [
    "DomainError",
    "DuplicateValue",
    "GPositionSpec",
    "InvariantViolation",
    "PositionState",
    "ProtectedValue",
    "ValidationError",
    "ValueInUse",
    "add_position",
    "add_value",
    "bind",
    "binding_state",
    "clear",
    "create_group",
    "create_item",
    "delete_value",
    "ensure_finding_target",
    "get_or_create_characteristic",
    "groups_of",
    "is_complete",
    "items_by_position",
    "list_groups",
    "list_items",
    "list_values",
    "make_finding",
    "mark_absent",
    "position_usage",
    "remove_position",
    "rename_value",
    "seed_cg_characteristics",
    "set_drawing",
    "update_group",
    "update_position",
    "usage_count",
]
