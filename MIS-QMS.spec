# -*- mode: python ; coding: utf-8 -*-
"""Рецепт однофайловой сборки MIS-QMS (наряд `0040` §3, задача QMS-030).

Собирается **одной командой** из корня репо:

    .venv\\Scripts\\python.exe -m PyInstaller --noconfirm MIS-QMS.spec

На выходе `dist/MIS-QMS.exe`. Сам артефакт в git не кладётся — `build/` и `dist/`
уже в `.gitignore`; коммитится рецепт, потому что воспроизводимость даёт он, а не
файл.

**Что здесь неочевидно и почему.**

*Миграции — данные, а не модули.* `migrations/versions/*.py` никто не импортирует
по имени: их находит Alembic, читая каталог. Анализатор PyInstaller ходит по
импортам и потому не видит их вовсе — если не положить каталог **данными**,
сборка получится без единой миграции и на чистой машине не поднимет схему.
`alembic.ini` кладётся туда же и по той же причине.

*Куда они попадают.* В каталог распаковки (`sys._MEIPASS`), который создаётся при
старте и **стирается при выходе**. Это верно для ресурсов и смертельно для базы —
поэтому база берёт свой корень у `paths.work_root()` и живёт рядом с `.exe`
(§1 наряда).

*`console=False`.* Приложение оконное; консоль под ним — чёрный прямоугольник за
окном на всё время работы. Следствие, которое надо помнить: после упаковки печать
в консоль не видна никому, и единственный видимый признак необработанного сбоя —
окно `ui/crash.py`. Что оно доехало до сборки, доказывает Д-2 наряда, а не эта
строка.
"""

from PyInstaller.utils.hooks import collect_submodules

datas = [
    # (что положить, куда внутри сборки) — корень распаковки обозначается '.'
    ("alembic.ini", "."),
    ("migrations", "migrations"),
]

hiddenimports = [
    # Alembic грузит свой шаблон окружения и диалекты не по прямому импорту.
    *collect_submodules("alembic"),
    # Драйвер SQLite у SQLAlchemy выбирается по имени URL, а не импортом.
    "sqlalchemy.dialects.sqlite",
    # **`migrations/env.py` лежит данными, и его импорты анализатор не видит.**
    # Это не теория: первая же сборка запустилась, создала пустой файл базы и
    # упала на `from logging.config import fileConfig` —
    # `ModuleNotFoundError: No module named 'logging.config'`. Ни один тест
    # этого не показал бы, и чтение `.spec` тоже: поймал запуск (Д-1 наряда
    # `0040`, §9а.20 — у механизма, обязанного доехать до экрана, критерий
    # приёмки это запуск, а не чтение рецепта).
    #
    # `logging.config` тянет за собой `logging.handlers` — `fileConfig`
    # разбирает секции обработчиков по имени класса, тоже без импорта.
    "logging.config",
    "logging.handlers",
]

a = Analysis(
    ["src/app.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Тяжёлое и ненужное в поставке: тестовый бегунок и сборщик самого себя.
    excludes=["pytest", "PyInstaller", "tkinter"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MIS-QMS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
