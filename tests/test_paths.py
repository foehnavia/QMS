"""Два корня приложения — чистыми функциями, на любой платформе (наряд `0040`, Д-3).

Свойство, которое проверяется, живёт **только внутри замороженной сборки**, а
сравнения «до/после» на ней не существует: до наряда `0040` `.exe` не собирался
ни разу. Поэтому оно вынесено в чистую функцию и проверяется подменой `sys`
(`CLAUDE.md` §9а.14) — а что сборка действительно кладёт базу рядом с `.exe`,
доказывает Д-1 запуском, не тест.
"""

from __future__ import annotations

import sys
from pathlib import Path

import paths
from db.session import default_db_path, default_db_url


def test_out_of_the_freeze_both_roots_are_the_repository(monkeypatch) -> None:
    """Вне заморозки корни **совпадают** — и потому неразличимы на глаз.

    Это и есть причина, по которой их две, а не одна с флагом: расходятся они
    ровно в том режиме, где ошибку труднее всего заметить.
    """
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert paths.frozen() is False
    assert paths.data_root() == paths.REPO_ROOT
    assert paths.work_root() == paths.REPO_ROOT
    assert default_db_path() == paths.REPO_ROOT / "app.sqlite"


def test_under_the_freeze_the_roots_part_ways(monkeypatch, tmp_path) -> None:
    """Под заморозкой ресурсы берутся из распаковки, а база — рядом с `.exe`.

    Сторожит правило наряда `0040` §1 и решение пользователя 2026-09-10: база
    живёт рядом с исполняемым файлом, чтобы «бэкап = копия одного файла»
    оставалось буквально верным.

    Если бы обе величины считались от каталога распаковки, база легла бы в папку,
    которую PyInstaller **стирает при выходе**, и всё введённое исчезало бы
    вместе с ней — молча, без единого сообщения.
    """
    unpacked = tmp_path / "_MEI12345"
    beside_exe = tmp_path / "app-folder"
    unpacked.mkdir()
    beside_exe.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(unpacked), raising=False)
    monkeypatch.setattr(sys, "executable", str(beside_exe / "MIS-QMS.exe"))

    assert paths.frozen() is True
    assert paths.data_root() == unpacked
    assert paths.work_root() == beside_exe
    assert paths.data_root() != paths.work_root(), (
        "корни совпали под заморозкой — база легла бы в стираемый каталог"
    )
    assert default_db_path() == beside_exe / "app.sqlite"


def test_a_frozen_build_without_unpacking_reads_beside_the_executable(
    monkeypatch, tmp_path
) -> None:
    """Однопапочная сборка: распаковывать нечего, ресурсы лежат рядом с `.exe`."""
    beside_exe = tmp_path / "onedir"
    beside_exe.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "executable", str(beside_exe / "MIS-QMS.exe"))

    assert paths.data_root() == beside_exe
    assert paths.work_root() == beside_exe


def test_the_env_override_still_wins(monkeypatch, tmp_path) -> None:
    """`QMS_DB_URL` остаётся официальным способом увести базу в другое место."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "MIS-QMS.exe"))
    monkeypatch.setenv("QMS_DB_URL", "sqlite:///C:/elsewhere/other.sqlite")

    assert default_db_url() == "sqlite:///C:/elsewhere/other.sqlite"


def test_the_freeze_is_read_from_sys_frozen_not_guessed(monkeypatch) -> None:
    """Признак заморозки — `sys.frozen`, а не наличие `_MEIPASS` (§9а.24).

    Наблюдать надо нужную величину, а не её удобный признак: `_MEIPASS` может
    оказаться выставленным чем угодно, а вопрос «заморожены ли мы» задаётся
    тому, кто на него отвечает.
    """
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(Path.cwd()), raising=False)

    assert paths.frozen() is False
    assert paths.data_root() == paths.REPO_ROOT
