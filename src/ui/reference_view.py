"""Экран справочников — все 6 словарей: добавить / переименовать / удалить.

Защиты (`domain.reference`) поднимаются сюда сообщением, а не отказом молча:
занятое по FK значение и структурный дефолт `General` остаются на месте.

Наряд 0007 закрывает здесь находки прогона В-1…В-4: подпись справочника стоит
рядом со своим полем, подсказка изолирована и **зависит от выбранного словаря**,
а воздух между списком и подсказкой распределён.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
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
    PROTECTED_NAMES,
    REFERENCE_TITLES,
    add_value,
    delete_value,
    is_protected,
    list_values,
    rename_value,
    usage_count,
)

from .common import directional, iso, show_error

#: Общая часть подсказки — верна для всех шести словарей.
IN_USE_HINT = "A value referenced by records cannot be deleted."

#: Про `General` говорим **только там, где он есть** (находка прогона В-3):
#: на «Item type» структурного дефолта нет, и текст был не про этот экран.
GENERAL_HINT = (
    "“General” is a structural default: it is neither renamed nor deleted. "
)


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
        # Значения справочников бывают ивритскими: направление строки — по её
        # содержимому, а не по окну (наряд 0007, §4а).
        directional(self.values)
        self.hint = QLabel()
        self.hint.setWordWrap(True)

        self.add_button = QPushButton(iso("Add…"))
        self.rename_button = QPushButton(iso("Rename…"))
        self.delete_button = QPushButton("Delete")
        self.add_button.clicked.connect(self.add)
        self.rename_button.clicked.connect(self.rename)
        self.delete_button.clicked.connect(self.delete)

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.rename_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)

        # Подпись и её поле — одной строкой формы (находка прогона В-1): раньше
        # подпись стояла отдельным виджетом над списком и прижималась к одному
        # краю, а поле — к другому.
        picker_form = QFormLayout()
        picker_form.addRow("Reference list:", self.picker)

        # Подсказка идёт сразу за списком, кнопки — внизу (находка прогона В-4):
        # прежде подсказка была прижата к нижнему краю через ряд кнопок, и взгляд
        # шёл к ней через пустое поле.
        layout = QVBoxLayout(self)
        layout.addLayout(picker_form)
        layout.addWidget(self.values, 1)
        layout.addWidget(self.hint)
        layout.addLayout(buttons)

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
                    label += "  · default"
                if used:
                    label += f"  · references: {used}"

                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, name)
                self.values.addItem(item)

        self.hint.setText(iso(self._hint_for(model)))

    @staticmethod
    def _hint_for(model: type) -> str:
        """Текст подсказки под выбранный словарь, а не «вообще»."""
        if PROTECTED_NAMES.get(model):
            return GENERAL_HINT + IN_USE_HINT
        return IN_USE_HINT

    def _selected_name(self) -> str | None:
        item = self.values.currentItem()
        if item is None:
            QMessageBox.information(
                self, "Nothing selected", "Select a value in the list first."
            )
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    # --- действия -------------------------------------------------------------

    def add(self) -> None:
        name, accepted = QInputDialog.getText(
            self, "New value", f"{REFERENCE_TITLES[self.model]} — name:"
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
        name, accepted = QInputDialog.getText(self, "Rename", "New name:", text=current)
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
            self, "Delete value", f"Delete “{current}” from this reference list?"
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            with session_scope(self._engine) as session:
                value = self._fetch(session, current)
                delete_value(session, self.model, value)
        except Exception as error:
            show_error(self, error, title="Not deleted")
            return
        self.reload()

    def _fetch(self, session, name: str):
        from sqlalchemy import select

        return session.scalar(select(self.model).where(self.model.name == name))
