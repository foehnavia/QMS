"""UI-слой MIS-QMS (PySide6) — единственный сменный слой (`architecture.md` §4).

Виджеты не содержат бизнес-правил: всё, что можно нарушить, живёт в
`src/domain` и поднимается сюда как `DomainError` с готовым для оператора
текстом. Наряд 0002 / QMS-012.
"""

from .main_window import MainWindow

__all__ = ["MainWindow"]
