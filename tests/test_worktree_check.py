"""Входной контроль второго рода: зафиксировано ли то, поверх чего идёт наряд.

Разбор и вердикт проверяются **чистыми функциями**, без временных репозиториев:
предмет проверки -- классификация путей и порядок диагнозов, а не умение git отдавать
статус. Интеграция закрыта одним тестом, который зовёт `main()` на настоящем репо и
следит, чтобы тот ничего не менял.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

from tools.worktree_check import group, layer_of, main, parse_status, report

REPO_ROOT = Path(__file__).resolve().parents[1]

HEAD_HASH = "sha256:" + "a" * 64
OTHER_HASH = "sha256:" + "b" * 64


def _verdict(paths, head=HEAD_HASH, worktree=HEAD_HASH) -> tuple[int, str]:
    stream = io.StringIO()
    code = report(paths, head, worktree, stream=stream)
    return code, stream.getvalue()


# --- Слои -------------------------------------------------------------------------


def test_canon_is_separated_from_the_rest_of_the_cowork_layer() -> None:
    """`docs/model/` -- стоп-условие, остальной `docs/` -- нет.

    Наряд, приехавший в `docs/worklog/`, работе не мешает: он её и заказывает.
    Движущийся канон мешает, потому что против него сверяются зеркало и тесты.
    """
    assert layer_of("docs/model/_overview.md") == "canon"
    assert layer_of("docs/model/reference/reference-data.md") == "canon"
    assert layer_of("docs/worklog/0023-mirror-body-hash.md") == "docs"
    assert layer_of("docs/decisions.md") == "docs"
    assert layer_of("tools/build_mirror.py") == "code"
    assert layer_of("build/mirror/CONCEPT_full_rev1.00_EN.md") == "other"


def test_paths_are_grouped_and_sorted() -> None:
    grouped = group(["tools/b.py", "docs/model/Search.md", "tools/a.py"])

    assert grouped == {"canon": ["docs/model/Search.md"], "code": ["tools/a.py", "tools/b.py"]}


# --- Разбор статуса ----------------------------------------------------------------


def test_parse_status_reads_modified_and_untracked() -> None:
    payload = " M docs/model/_overview.md\0?? tools/new.py\0"

    assert parse_status(payload) == ["docs/model/_overview.md", "tools/new.py"]


def test_parse_status_takes_the_new_path_of_a_rename() -> None:
    """Переименование приходит двумя записями; на диске лежит первая.

    Разбирается `-z` именно ради этого места и ради имён с не-ASCII символами: обычный
    вывод git их цитирует и экранирует, а в репозитории такие имена штатны.
    """
    payload = "R  docs/model/New.md\0docs/model/Old.md\0 M tools/build_mirror.py\0"

    assert parse_status(payload) == ["docs/model/New.md", "tools/build_mirror.py"]


def test_parse_status_survives_an_empty_tree() -> None:
    assert parse_status("") == []


# --- Вердикты ----------------------------------------------------------------------


def test_a_clean_tree_is_ok() -> None:
    code, output = _verdict([])

    assert code == 0
    assert "VERDICT: OK" in output
    assert "uncommitted paths: none" in output


def test_an_uncommitted_canon_file_stops_the_work() -> None:
    """Сегодняшний случай: наряд 0023 шёл поверх правки `_overview.md`."""
    code, output = _verdict(["docs/model/_overview.md"], head=HEAD_HASH, worktree=OTHER_HASH)

    assert code == 1
    assert "VERDICT: CANON MOVED" in output
    assert "VERDICT: OK" not in output
    # Оба хеша печатаются: расхождение надо объяснять, а не констатировать.
    assert f"canon hash HEAD     : {HEAD_HASH}" in output
    assert f"canon hash worktree : {OTHER_HASH}" in output


def test_own_unfinished_work_does_not_stop_anything() -> None:
    """Своя незавершённая полоса посреди наряда -- норма, а не расхождение."""
    code, output = _verdict(["tools/build_mirror.py", "tests/test_build_mirror.py"])

    assert code == 0
    assert "VERDICT: OK" in output
    # Но перечислить её всё равно надо -- иначе отчёт будет о неполном дереве.
    assert "- tools/build_mirror.py" in output


def test_a_naryad_arriving_is_not_a_stop_condition() -> None:
    code, output = _verdict(["docs/worklog/0024-next.md"])

    assert code == 0
    assert "VERDICT: OK" in output


def test_a_canon_hash_that_moved_without_git_seeing_it_is_caught() -> None:
    """Правка канона мимо git -- отдельный диагноз, список путей её не объясняет."""
    code, output = _verdict(["tools/build_mirror.py"], head=HEAD_HASH, worktree=OTHER_HASH)

    assert code == 1
    assert "outside git's view" in output


# --- Печать и интеграция ------------------------------------------------------------


def test_printed_strings_are_ascii_only() -> None:
    """Консоль рабочей машины -- cp1255; не-ASCII в печати роняет прогон.

    То же правило, что у `build_mirror.py`, и держится оно так же тестом, а не памятью.
    """
    source = (REPO_ROOT / "tools" / "worktree_check.py").read_text(encoding="utf-8")
    offenders = [
        (piece.lineno, piece.value)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print"
        for piece in ast.walk(node)
        if isinstance(piece, ast.Constant)
        and isinstance(piece.value, str)
        and not piece.value.isascii()
    ]

    assert offenders == []


def test_main_reads_the_real_repo_and_writes_nothing(capsys) -> None:
    """Проверку зовут посреди работы -- она обязана быть безопасной.

    Ветка не переключается принципиально: канон HEAD достаётся распаковкой во
    временный каталог. Проверка, двигающая ветку под исполнителем, была бы хуже
    дефекта, который она ищет.
    """
    model = REPO_ROOT / "docs" / "model"
    before = {path: path.read_bytes() for path in model.rglob("*.md")}

    code = main([])

    assert code in (0, 1)
    assert "VERDICT: " in capsys.readouterr().out
    assert {path: path.read_bytes() for path in model.rglob("*.md")} == before
