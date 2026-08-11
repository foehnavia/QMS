"""Экран справочников — все 6 словарей: добавить / переименовать / удалить.

Защиты (`domain.reference`) поднимаются сюда сообщением, а не отказом молча:
занятое по FK значение и структурный дефолт `General` остаются на месте.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine

from db.models import REFERENCE_MODELS
from db.session import session_scope
from domain.reference import (
    REFERENCE_TITLES,
    add_value,
    delete_value,
    is_protected,
    list_values,
    rename_value,
    usage_count,
)

from .common import iso, show_error


class ReferenceView(QWidget):
    """Список значений выбранного справочника + правка."""

    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine

        self.picker = QComboBox()
        for model in REFERENCE_MODELS:
            self.picker.addItem(REFERENCE_TITLES[model], model)
        self.picker.currentIndexChanged.connect(self.reload)

        self.values = QListWidget()
        self.hint = QLabel()
        self.hint.setWordWrap(True)

        self.add_button = QPushButton(iso("Добавить…"))
        self.rename_button = QPushButton(iso("Переименовать…"))
        self.delete_button = QPushButton("Удалить")
        self.add_button.clicked.connect(self.add)
        self.rename_button.clicked.connect(self.rename)
        self.delete_button.clicked.connect(self.delete)

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.rename_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Справочник:"))
        layout.addWidget(self.picker)
        layout.addWidget(self.values, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.hint)

        self.reload()

    # --- данные ---------------------------------------------------------------

    @property
    def model(self) -> type:
        return self.picker.currentData()

    def reload(self) -> None:
        """Перечитать выбранный справочник из БД."""
        model = self.model
        self.values.clear()
        with session_scope(self._engine) as session:
            for value in list_values(session, model):
                name = value.name
                used = usage_count(session, model, value)
                protected = is_protected(model, name)

                label = name
                if protected:
                    label += "  · дефолт"
                if used:
                    label += f"  · ссылок: {used}"

                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, name)
                self.values.addItem(item)

        self.hint.setText(
            "«General» — структурный дефолт: не переименовывается и не удаляется. "
            "Значение, на которое ссылаются записи, удалить нельзя."
        )

    def _selected_name(self) -> str | None:
        item = self.values.currentItem()
        if item is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите значение в списке.")
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    # --- действия -------------------------------------------------------------

    def add(self) -> None:
        name, accepted = QInputDialog.getText(
            self, "Новое значение", f"{REFERENCE_TITLES[self.model]} — название:"
        )
        if not accepted:
            return
        try:
            with session_scope(self._engine) as session:
                add_value(session, self.model, name)
        except Exception as error:  # доменная ошибка показывается как есть
            show_error(self, error)
            return
        self.reload()

    def rename(self) -> None:
        current = self._selected_name()
        if current is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Переименовать", "Новое название:", text=current
        )
        if not accepted:
            return
        try:
            with session_scope(self._engine) as session:
                value = self._fetch(session, current)
                rename_value(session, self.model, value, name)
        except Exception as error:
            show_error(self, error)
            return
        self.reload()

    def delete(self) -> None:
        current = self._selected_name()
        if current is None:
            return
        confirmed = QMessageBox.question(
            self, "Удалить значение", f"Удалить «{current}» из справочника?"
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            with session_scope(self._engine) as session:
                value = self._fetch(session, current)
                delete_value(session, self.model, value)
        except Exception as error:
            show_error(self, error, title="Не удалено")
            return
        self.reload()

    def _fetch(self, session, name: str):
        from sqlalchemy import select

        return session.scalar(select(self.model).where(self.model.name == name))
