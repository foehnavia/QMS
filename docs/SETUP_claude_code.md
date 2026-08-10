# Настройка VS Code + Claude Code для репо MIS-QMS

> Одноразовая установка на машине. Конфиги уже лежат в репо (`.claude/settings.json`,
> `.mcp.json`, `MIS-QMS.code-workspace`, корневой `CLAUDE.md`). Порядок ниже сводит
> установку к «поставить расширения + открыть workspace + проверить». Работает и на
> рабочей (`C:`), и на домашней (`D:`) машине — пути в конфигах относительные
> (`../Vault_01/...`), т.е. репо и волт должны лежать рядом: `X:\MIS-QMS` и `X:\Vault_01`.

## 0. Предпосылки (уже есть после QMS-009)

- VS Code **1.94+**.
- Python **3.13** + venv `C:\MIS-QMS\.venv` (стек проверен, QMS-009 §9).
- Git + remote `github.com/foehnavia/QMS`.
- Установленный Word/Office (для docx→PDF) — проверен.

## 1. Расширения VS Code

`Ctrl+Shift+X` → установить:

- **Claude Code** (`anthropic.claude-code`).
- **Python** (`ms-python.python`).

Оба уже в `recommendations` workspace-файла — VS Code предложит их при открытии.

## 2. Открыть workspace (а не папку)

```powershell
code C:\MIS-QMS\MIS-QMS.code-workspace
```

В Explorer должно появиться **три корня**:

- `MIS-QMS (repo · read-write)` — репо, полный доступ.
- `Vault · _system (read-only)` — правила/терминология/инфраструктура волта.
- `Vault · 90_Shared (read-only)` — общая зона волта.

Файлы под волтом открываются **только на чтение** (замок в заголовке вкладки) —
`files.readonlyInclude`. Остальные домены волта (`10_…`, `20_…`, `30_…`, `40_VA`,
`50_MIS-QMS`) **намеренно не подключены**: канон MIS-QMS Claude Code читает из репо
`docs/model/`, а не из волта.

## 3. Интерпретатор Python

Если не подхватился автоматически: `Ctrl+Shift+P` → **Python: Select Interpreter** →
`.venv\Scripts\python.exe` в корне репо.

## 4. Проверка Claude Code

Открыть панель Claude Code. Убедиться:

1. Прочитан корневой `CLAUDE.md` (конституция исполнителя) — спроси у Claude Code
   «какова твоя роль по CLAUDE.md», ответ должен ссылаться на «руки + локальный диагност».
2. `/mcp` → серверов **нет** (FHA исключён по решению INFRA-013 — это правильно).
3. Границы: Claude Code **читает** `_system/RULES.md` из волта — ок; попытка записать/
   изменить любой файл под `Vault_01/` — **запрещена** (`deny` в `.claude/settings.json`).
   Это можно проверить, попросив Claude Code отредактировать любой файл волта — он должен
   отказаться.

## 5. Git (ответственность Claude Code)

Первый коммит подхватывает новые файлы, созданные дизайн-сессией:

```powershell
cd C:\MIS-QMS
git add CLAUDE.md .claude/settings.json .mcp.json MIS-QMS.code-workspace `
        docs/worklog/README.md docs/SETUP_claude_code.md docs/architecture.md docs/decisions.md
git commit -m "INFRA-013: операционная модель Cowork <-> Claude Code (конституция, наряды, конфиги VS Code)"
git push
```

(`docs/architecture.md` / `docs/decisions.md` — если ещё не закоммичены с QMS-009.)

## 6. Что дальше

Рабочий цикл — через наряды `docs/worklog/` (см. `docs/worklog/README.md`):
Cowork пишет наряд → Claude Code исполняет + коммитит + пишет отчёт → Cowork ревьюит.
Первый боевой наряд — блок QMS-010 (валидация схемы: DDL + модели + синтетика).

## Приложение — что в каких файлах

| Файл | Роль |
|---|---|
| `CLAUDE.md` | конституция Claude Code (роль, карта, наряд, git, границы, запреты) |
| `.claude/settings.json` | доступ к волту read-only-подсетом (`_system`, `90_Shared`) + deny на запись |
| `.mcp.json` | MCP пуст (FHA не подключается) |
| `MIS-QMS.code-workspace` | 3 корня (репо rw + 2 волт-подсета ro), интерпретатор, рекомендации |
| `docs/worklog/README.md` | протокол нарядов + шаблон |
