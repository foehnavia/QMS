"""Экран справочников — все 6 словарей: добавить / переименовать / удалить.

Защиты (`domain.reference`) поднимаются сюда сообщением, а не отказом молча:
занятое по FK значение и структурный дефолт `General` остаются на месте.

Наряд 0007 закрыл здесь находки прогона В-1…В-4: подпись справочника стоит
рядом со своим полем, подсказка изолирована и **зависит от выбранного словаря**,
а воздух между списком и подсказкой распределён. Наряд 0011 перевёл экран на
`kit` — числа оформления ушли в токены, вид пришёл из одного листа стиля.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
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

from . import kit
from .common import directional, iso, joined

#: Общая часть подсказки — верна для всех шести словарей.
IN_USE_HINT = "A value referenced by records cannot be deleted."

#: Про `General` говорим **только там, где он есть** (находка прогона В-3):
#: на «Item type» структурного дефолта нет, и текст был не про этот экран.
GENERAL_HINT = (
    "“General” is a structural default: it is neither renamed nor deleted. "
)


class ReferenceView(QWidget):
    """Список значений выбранного справочника + правка."""

    statusChanged = Signal(str)

    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._summary = ""

        self.picker = QComboBox()
        for model in REFERENCE_MODELS:
            self.picker.addItem(REFERENCE_TITLES[model], model)
        self.picker.currentIndexChanged.connect(self.reload)

        self.values = QListWidget()
        # Значения справочников бывают ивритскими: направление строки — по её
        # содержимому, а не по окну (наряд 0007, §4а).
        directional(self.values)
        self.hint = kit.hint()

        self.add_button = kit.primary("Add…")
        self.rename_button = kit.secondary("Rename…")
        self.delete_button = kit.danger("Delete")
        self.add_button.clicked.connect(self.add)
        self.rename_button.clicked.connect(self.rename)
        self.delete_button.clicked.connect(self.delete)

        # Подпись и её поле — одной строкой формы (находка прогона В-1): раньше
        # подпись стояла отдельным виджетом над списком и прижималась к одному
        # краю, а поле — к другому.
        picker_form = kit.form()
        picker_form.addRow("Reference list:", self.picker)

        # Подсказка идёт сразу за списком, кнопки — внизу (находка прогона В-4):
        # прежде подсказка была прижата к нижнему краю через ряд кнопок, и взгляд
        # шёл к ней через пустое поле.
        layout = kit.screen_layout(self)
        layout.addWidget(
            kit.section_header(
                "Reference data", "Controlled vocabularies the forms pick from"
            )
        )
        layout.addLayout(picker_form)
        layout.addWidget(self.values, 1)
        layout.addWidget(self.hint)
        layout.addLayout(
            kit.button_row(self.add_button, self.rename_button, self.delete_button)
        )

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

                # Составная строка: имя значения бывает ивритским, а пометки
                # английские — каждый токен в своём изоляте, порядок за базой
                # (наряд 0007, §4а).
                label = joined(
                    name,
                    "default" if protected else "",
                    f"references: {used}" if used else "",
                )

                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, name)
                self.values.addItem(item)

        self.hint.setText(iso(self._hint_for(model)))
        self._summary = (
            f"{REFERENCE_TITLES[model]} — values: {self.values.count()}"
        )
        self.statusChanged.emit(self._summary)

    def summary_text(self) -> str:
        """Сводка экрана — её показывает **подвал окна**, а не сам экран.

        Своей строки состояния у раздела нет намеренно: подвал уже несёт
        счётчики и путь базы, и вторая такая же строка над ним была бы одним и
        тем же числом дважды на одном экране.
        """
        return self._summary

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
            kit.show_error(self, error)
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
            kit.show_error(self, error)
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
            kit.show_error(self, error, title="Not deleted")
            return
        self.reload()

    def _fetch(self, session, name: str):
        from sqlalchemy import select

        return session.scalar(select(self.model).where(self.model.name == name))
