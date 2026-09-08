"""Перехватчик необработанных исключений: отказ обязан дойти до оператора.

**Повод — доводка 3 наряда `0030`, Д-3.3.** Двойной клик по строке исследования
падал `TypeError` внутри слота Qt. Qt печатал traceback в консоль и продолжал
работу; на экране не происходило **ничего**. Для оператора это выглядело как
«кнопка не работает».

Сейчас консоль есть, потому что приложение запускают из терминала. **После
упаковки в `.exe` (S7) консоли не будет вовсе**, и такая ошибка станет полностью
невидимой — ни окна, ни следа. Для базы качества это худший из возможных отказов:
система молчит и продолжает работать, а оператор считает, что действие выполнено.

**Зеркало QMS-021.** Там: в *тестовом* режиме `show_error` бросает, чтобы отказ не
был бесшумным в прогоне. Здесь: в *боевом* режиме любое необработанное исключение
становится окном, чтобы отказ не был бесшумным на экране. Одна болезнь, две
стороны; вторую половину закрывает этот модуль.

**Почему `sys.excepthook`, и достаточно ли его.** PySide6 не пробрасывает
исключение слота вызывающему — оно уходит именно в `sys.excepthook` (на этом же
факте стоит §9а.2 `CLAUDE.md` и фикстура `slot_errors` в тестах). Отдельный хук
Qt (`qInstallMessageHandler`) здесь не нужен и не помог бы: он перехватывает
**сообщения Qt**, а не исключения Python, и до `TypeError` из слота ему дела нет.
Установлен и `threading.excepthook` — не потому, что приложение многопоточное, а
потому, что молчащий фоновый поток и есть тот отказ, ради которого модуль написан.
"""

from __future__ import annotations

import os
import sys
import threading
import traceback
from types import TracebackType

from . import kit

#: Переменная окружения, включающая самопроверку (§7 наряда `0031`).
SELFTEST_ENV = "QMS_SELFTEST_CRASH"

#: Заголовок окна. Не «ошибка сохранения» и не «ошибка ввода»: сюда попадает
#: ровно то, чего ни один экран не предусмотрел, и называть это надо тем, что оно
#: есть, — сбоем программы.
TITLE = "Unexpected error"

#: Идёт ли показ прямо сейчас. Ошибка **внутри** показа окна об ошибке позвала бы
#: хук снова — и так до исчерпания стека, то есть до тихой смерти процесса, ровно
#: того исхода, который модуль предотвращает.
_showing = False


def install() -> None:
    """Поставить перехватчик. Зовётся один раз из `app.main()`.

    Прежние хуки **не теряются**: они зовутся первыми, поэтому в терминале
    traceback печатается как раньше. Окно добавляется к печати, а не заменяет её:
    разработчику нужен стек, оператору — знание, что произошёл сбой.
    """
    previous = sys.excepthook
    sys.excepthook = lambda kind, error, trace: _handle(previous, kind, error, trace)

    previous_thread_hook = threading.excepthook

    def thread_hook(args) -> None:
        previous_thread_hook(args)
        _report(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = thread_hook


class SelfTestCrash(Exception):
    """Исключение самопроверки — **отличимое** от настоящего сбоя.

    Свой тип, а не `RuntimeError` с приметным текстом: тот, кто увидит окно, и
    тот, кто потом будет читать журнал, обязаны различать «перехватчик работает»
    и «что-то сломалось» без вчитывания в формулировку.
    """


def arm_selftest() -> bool:
    """Взвести самопроверку, если попросили переменной окружения.

    **Зачем это вообще.** `crash.py` написан и на стенде проверен, но на живом
    приложении не проверен ни разу, и проверить его нечем: перехватчик ловит то,
    чего никто не предусмотрел, а всё найденное мы чиним. Отказ по инварианту для
    этого не годится — он **обработанный** путь и обязан показывать окно и без
    перехватчика.

    **Почему `QTimer.singleShot`, а не прямой вызов.** Нужен **настоящий слот**:
    путь до `sys.excepthook` обязан быть тем же, каким пойдёт настоящий сбой.
    Прямой вызов поднял бы исключение вызывающему — то есть проверил бы не то,
    что ломается на живом экране. Нулевая задержка ставит его первым же событием
    после показа окна.

    **Механизм постоянный, не временный.** После упаковки в `.exe` (S7) консоли
    не будет вовсе, и позвать перехватчик специально станет единственным
    способом убедиться, что он доехал до сборки, — а проверять это придётся
    после каждой сборки, а не однажды. От запуска из исходников не зависит
    ничем: переменная окружения есть и у собранного приложения.

    Без переменной — **ничего**: ни пункта меню, ни кнопки, ни строки в выводе.
    В интерфейсе самопроверки не существует, и это требование, а не экономия:
    кнопка «сломать приложение» на рабочем экране однажды будет нажата.
    """
    if os.environ.get(SELFTEST_ENV) != "1":
        return False

    from PySide6.QtCore import QTimer  # noqa: PLC0415 — только на этом пути

    QTimer.singleShot(0, _selftest_slot)
    return True


def _selftest_slot() -> None:
    """Тело самопроверки. Отдельной функцией — чтобы её имя было в трассе."""
    raise SelfTestCrash(
        f"Self-test of the crash handler ({SELFTEST_ENV}=1). "
        "Nothing is broken: this exception was raised on purpose to prove that "
        "an unhandled failure reaches you as a window. Close this and carry on."
    )


def _handle(previous, kind, error, trace) -> None:
    previous(kind, error, trace)
    _report(kind, error, trace)


def _report(
    kind: type[BaseException],
    error: BaseException | None,
    trace: TracebackType | None,
) -> None:
    """Показать окно, если это тот случай, когда окно уместно."""
    global _showing

    # `Ctrl+C` и штатный выход — не сбои: окно на них было бы шумом, а на
    # `KeyboardInterrupt` ещё и неотменяемым.
    if kind is not None and issubclass(kind, (KeyboardInterrupt, SystemExit)):
        return
    if _showing or error is None:
        return

    _showing = True
    try:
        kit.show_error(None, _wrap(kind, error, trace), title=TITLE)
    except kit.UnexpectedErrorDialog:
        # Тестовый режим `show_error`: он бросает вместо показа, и здесь, внутри
        # хука, бросать некому — исключение из `excepthook` Python проглатывает.
        # Пробрасывать нечего, тест видит вызов подменой самого `show_error`.
        raise
    except Exception:
        # Окно не собралось (нет `QApplication`, экран отвалился). Это последняя
        # линия — молчать нельзя, но и падать здесь уже некуда.
        traceback.print_exception(kind, error, trace)
    finally:
        _showing = False


def _wrap(
    kind: type[BaseException],
    error: BaseException,
    trace: TracebackType | None,
) -> Exception:
    """Собрать сообщение: **техническая правда**, без выдумывания.

    Оператор не обязан понимать traceback, но обязан знать, **что** произошёл
    сбой и **где**, — иначе ему нечего показать тому, кто чинит. Поэтому тип,
    текст и последний кадр стека: файл, строка, функция. Стек целиком в окно не
    кладём — он уходит в поток, где его прочтёт разработчик.
    """
    where = ""
    frames = traceback.extract_tb(trace)
    if frames:
        last = frames[-1]
        where = f"\n\nWhere: {last.filename}, line {last.lineno}, in {last.name}"

    return RuntimeError(
        f"The action did not complete — this is a defect, not a rejected entry.\n\n"
        f"{kind.__name__}: {error}{where}\n\n"
        "Nothing was saved by this action. Report the lines above; the work you "
        "did before it is untouched."
    )
