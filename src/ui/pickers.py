"""Мелкие выборщики: «какую деталь» / «какую группу» — общие для разделов."""

from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QWidget


def _pick(parent: QWidget | None, title: str, prompt: str, rows: list[tuple[int, str]]) -> int | None:
    labels = [label for _key, label in rows]
    choice, accepted = QInputDialog.getItem(parent, title, prompt, labels, 0, False)
    if not accepted:
        return None
    return next(key for key, label in rows if label == choice)


def pick_item(parent: QWidget | None, items: list[tuple[int, str]]) -> int | None:
    """Выбрать деталь из списка `(item_id, item_number)`."""
    return _pick(parent, "Выбор детали", "Деталь:", items)


def pick_group(parent: QWidget | None, groups: list[tuple[int, str]]) -> int | None:
    """Выбрать группу характеристик из списка `(cg_id, name)`."""
    return _pick(parent, "Выбор группы", "Группа характеристик:", groups)
