"""Доменный слой MIS-QMS — правила поверх `src/db`, **без зависимости от UI**.

`architecture.md` §4: ядро UI-независимо, UI — единственный сменный слой.
Поэтому здесь не должно появляться импортов PySide6 (проверяется тестом).
Наряды 0002 / QMS-012, 0003 / QMS-013, 0004 / QMS-014, 0005 / QMS-015.
"""

from .characteristics import get_or_create_characteristic
from .deviations import (
    DeviationRow,
    delete_deviation,
    list_deviations,
    register,
    set_decision,
    update_registration,
)
from .errors import (
    DomainError,
    DuplicateValue,
    InvariantViolation,
    ProtectedValue,
    ValidationError,
    ValueInUse,
)
from .findings import (
    ensure_finding_target,
    inspection_count,
    make_finding,
    remove_finding,
    update_finding,
)
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
from .inspections import (
    create_inspection,
    inspections_for,
    remove_inspection,
    update_inspection,
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
from .precedents import (
    CANON_NEW,
    CANON_UNBOUND,
    PrecedentRow,
    canon_labels,
    canon_labels_for_item,
    precedents_descriptive,
    precedents_same_dimension,
    precedents_same_position,
)
from .reference import add_value, delete_value, list_values, rename_value, usage_count

__all__ = [
    "CANON_NEW",
    "CANON_UNBOUND",
    "DeviationRow",
    "DomainError",
    "DuplicateValue",
    "GPositionSpec",
    "InvariantViolation",
    "PositionState",
    "PrecedentRow",
    "ProtectedValue",
    "ValidationError",
    "ValueInUse",
    "add_position",
    "add_value",
    "bind",
    "binding_state",
    "canon_labels",
    "canon_labels_for_item",
    "clear",
    "create_group",
    "create_inspection",
    "create_item",
    "delete_deviation",
    "delete_value",
    "ensure_finding_target",
    "get_or_create_characteristic",
    "groups_of",
    "inspection_count",
    "inspections_for",
    "is_complete",
    "items_by_position",
    "list_deviations",
    "list_groups",
    "list_items",
    "list_values",
    "make_finding",
    "mark_absent",
    "position_usage",
    "precedents_descriptive",
    "precedents_same_dimension",
    "precedents_same_position",
    "register",
    "remove_finding",
    "remove_inspection",
    "remove_position",
    "rename_value",
    "seed_cg_characteristics",
    "set_decision",
    "set_drawing",
    "update_finding",
    "update_group",
    "update_inspection",
    "update_position",
    "update_registration",
    "usage_count",
]
