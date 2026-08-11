# Наряд 0001 — S1 · Фундамент данных

- **Задача / цель:** **QMS-011** (спринт **S1** плана Этапа 1, [[ROADMAP_MIS-QMS]] §S1). На
  выходе — работающий слой хранения MIS-QMS: SQLAlchemy-модели всех таблиц модели,
  baseline-миграция Alembic, генератор человекочитаемых бизнес-номеров, сид справочников,
  синтетический датасет и тесты. Это фундамент, на который в S2+ ложатся UI, ETL, карточка
  и поиск. Кода приложения (Qt), парсинга Excel и генерации документов в этом наряде **нет**.

- **Вход (читать перед работой):**
  - `docs/model/_overview.md` — канон-вход: глоссарий, акторы, сквозной процесс (9 шагов), save flow §6.
  - `docs/model/Item.md`, `Characteristic.md`, `CharacteristicGroup.md`, `Deviation.md`,
    `Finding.md`, `Inspection.md`, `DeviationCard.md`, `Search.md`, `Import-Workflow.md` — сущности,
    поля, инварианты.
  - `docs/model/reference/reference-data.md`, `reference/output-document.md` — справочники и
    карта полей документа (нужна для полноты набора полей, чтобы заполнение бланка было
    copy-from-card; сам документ в S1 не генерим).
  - `docs/architecture.md` — стек и **§5 «Физическая схема (rev 0.1)»** — прямой источник
    таблиц/ключей/связей. §7 — что вне scope Этапа 1.
  - `docs/decisions.md` — R1 (спящий `state_depending`), R2 (маппинг ранний), R3 (CG по ходу),
    границы области базы.

- **Что сделать:**

  1. **Окружение.** Работать в существующем venv `C:\MIS-QMS\.venv` (SQLAlchemy 2.x + Alembic
     проверены в Ф1, `docs/architecture.md` §9). Раскладку пакета `src/` выбираешь сам;
     предложение — `src/db/` (base, models, session), `src/db/ids.py` (бизнес-номера),
     `src/seed/`, `tests/`. Фактическую раскладку зафиксируй в отчёте. SQLite-файл — `app.sqlite`
     (источник истины), `PRAGMA foreign_keys=ON`.

  2. **SQLAlchemy-модели — все таблицы по `architecture.md` §5.** Суррогатный целочисленный PK
     везде; для `deviation` и `inspection` — плюс человекочитаемый бизнес-номер (UNIQUE).

     **Core (8):**
     - `item` — PK `item_id`; `item_number` UNIQUE NOT NULL; FK `item_type_id`, `connection_type_id`,
       `size_id` (два последних — с дефолтом `General`, см. п. 5). Инвариант: у детали ≥1
       характеристика к моменту существования; при создании детали сеются только CG-размеры
       (не-CG создаются при первом отклонении — это логика S2, здесь только схема это допускает).
     - `characteristic` — PK; FK `item_id`; `local_number`; **UNIQUE(`item_id`,`local_number`)**;
       nullable self-FK `state_depending_id` → characteristic (**спящее поле R1**, по умолчанию NULL,
       в S1 не заполняется, но в схеме присутствует).
     - `characteristic_group` — PK `cg_id`; `name`.
     - `g_position` — PK; FK `cg_id`; `g_index` INT; `nominal` REAL; `tol_plus` REAL; `tol_minus` REAL.
     - `mapping` — (characteristic → g_position), **0..1 на характеристику**: FK `characteristic_id`
       **UNIQUE**, FK `g_position_id` nullable. Требование кода 99 — см. заметку А ниже.
     - `deviation` — PK; `dev_number` UNIQUE NOT NULL (формат `DEV-YYMMDD-NNNN`); FK `item_id`;
       `wo` (`פק"ע`, строка); `machine` NULL; `quantity` INT; `date`; `ncr` NULL (может прийти позже
       решения); `decision_date` (дефолт — системное время); `decision_dev` — словарь из 4 значений
       `approved`/`rejected`/`sorting`/`repair`; `explanation` (свободный текст, всегда);
       `attachment` NULL (ссылки на файлы в сетевой папке, **не блобы**). Целостность — на уровне
       отклонения.
     - `finding` — PK; FK `deviation_id`; FK `characteristic_id`; `direction` (`+`/`−`); `value` REAL NULL;
       `dimension_point` INT NULL; `comment` NULL; FK `zone_id` NULL; FK `deviation_type_id` NULL.
       Решения и количества **не несёт**.
     - `inspection` — PK; `insp_number` UNIQUE NOT NULL (формат `INSP-YYMMDD-NNN`); FK `deviation_id`;
       FK `finding_id`; FK `type_id` → ref_inspection_type; `decision_insp` — **бинарный**
       `approved`/`not_approved` (независим от `decision_dev`); `protocol` (ссылка на документ).
       Item выводится из deviation/finding, отдельно не хранится.

     **Reference (6, контролируемые словари, каждая PK + `name`):**
     `ref_item_type`, `ref_connection_type`, `ref_size`, `ref_zone`, `ref_deviation_type`,
     `ref_inspection_type`.

  3. **Alembic baseline.** Инициализировать Alembic на SQLite; одна baseline-миграция создаёт всю
     схему (14 таблиц). Должна применяться на **чистой** БД с нуля (`upgrade head`) и чисто
     откатываться (`downgrade base`).

  4. **Генерация бизнес-номеров.** `DEV-YYMMDD-NNNN` (счётчик суток, 4 знака) и `INSP-YYMMDD-NNN`
     (3 знака). `YYMMDD` — из даты записи (зафиксируй правило: от `date`/`decision_date`/системной
     даты — обоснуй выбор); `NNNN`/`NNN` — сквозной счётчик в пределах суток, с ведущими нулями.
     Уникальность гарантируется UNIQUE-констрейнтом + логикой присвоения; пакетная вставка в один
     день не должна давать дублей (одна машина/один пользователь — гонок почти нет, но присвоение
     детерминированное).

  5. **Сид справочников (идемпотентный).** `General`-дефолты для `ref_connection_type` и `ref_size`.
     Стартовые значения: connection_type `{C1, V3, IntHex, LYNX, General}`; size `{NP, SP, WP, General}`;
     deviation_type `{thread burr, thread length, inner diameter, cutting-edge width, angle}` (стартовый
     набор, расширяемо оператором); inspection_type `{Solidworks assembly, Implantation torque test}`
     (стартовый); zone — пусто или 1–2 примера (заполняется оператором); item_type — 2–3 примера
     (`implant`/`abutment`/`drill`) либо пусто. Повторный прогон сида дублей не плодит.

  6. **Синтетический датасет.** Скрипт, наполняющий БД правдоподобными данными, покрывающими
     инварианты (можно неsensitive реальные и вымышленные значения, в т.ч. иврит — [[RULES]] §5 /
     `decisions.md` 2026-08-10 «отдельные значения не sensitive»):
     - ≥2 детали (Item) с классификаторами;
     - у одной — засеянные CG-размеры + маппинг на g-позиции; у другой — не-CG характеристика;
     - хотя бы один маппинг с **кодом 99** («позиция рассмотрена, отсутствует»);
     - ≥1 CharacteristicGroup с несколькими g-позициями (номинал + допуск);
     - ≥3 отклонения с разными `decision_dev` (включая `approved` и `rejected`); у одного — несколько
       findings (1..N) с разными направлениями `±`, у части — заполнены zone / deviation_type;
     - ≥1 исследование (Inspection), привязанное к deviation + finding, с `decision_insp`;
     - бизнес-номера присвоены и уникальны.

  7. **Тесты (pytest).** Против критериев приёмки ниже; прогон на чистой БД.

  8. **Git.** Коммитить осмысленными порциями (модели / миграция / сид+синтетика / тесты); сообщение —
     что и зачем + ссылка на **QMS-011 / наряд 0001**. `.gitignore`: не коммитить `app.sqlite`,
     `.venv/`, синтетические БД-файлы.

- **Критерии приёмки (проверяемые):**
  1. `alembic upgrade head` на чистой БД создаёт все **14** таблиц; `downgrade base` чисто откатывает.
  2. **FK и UNIQUE держат** (`PRAGMA foreign_keys=ON`): падают — finding с несуществующим
     `characteristic_id`; дубль `item_number`; дубль `dev_number` / `insp_number`; второй `mapping`
     на ту же характеристику.
  3. **Бизнес-номера:** формат `DEV-YYMMDD-NNNN` / `INSP-YYMMDD-NNN`, уникальны, человекочитаемы;
     пакет из N отклонений за один день — последовательные, без дублей.
  4. **Round-trip:** весь граф (item→characteristic→mapping→g_position; deviation→finding→inspection;
     справочники) пишется и читается назад без потерь, связи навигируются. Тест зелёный.
  5. **Сид идемпотентен**; `General`-дефолты присутствуют.

- **Чего не трогать:**
  - `docs/model/**`, `docs/architecture.md`, `docs/decisions.md`, `docs/staging.md`, `docs/_INDEX.md`
    — **канон / авторский слой Cowork**. Не править. Расхождение канона со схемой не чинить молча —
    вынести в «Отклонения / вопросы Cowork».
  - Волт (подключён read-only) — не писать.
  - **Вне scope S1, не реализовывать:** UI/PySide6, ETL-парсинг Excel/regex, карточка-представление
    и поиск L1/L2, генерация `אישור חריגה` / PDF, типы измерения + квалитет, вычисление `value` из
    пинов, дедуп автовыгрузки, судьба деталей после решения (`architecture.md` §7, `staging.md`).
  - `mcp__claude_ai_FHA*` — запрещено (`deny` в репо `.claude/settings.json`).

- **Заметки исполнителю (не блокеры; решение зафиксировать в отчёте):**
  - **А. Код 99.** Нужен способ явно хранить «позиция рассмотрена, отсутствует» — отличать от
    «маппинга ещё нет». Варианты: сентинел-`g_position` с `g_index=99` в служебном CG; либо булев
    флаг `absent` на `mapping`. Выбери и обоснуй. По коду 99 поиск не ведётся (не ключ поиска).
  - **Б. `decision_date`** — дефолт системное время; учесть, что при импорте (S6) может приходить
    извне. В S1 достаточно дефолта.
  - **В. `direction`** — знак `+`/`−`, согласован со знаковой конвенцией ETL (`−` ниже min, `+` выше max).
  - **Г. `state_depending`** — поле в схеме есть, спящее (R1); в S1 не заполнять.

---
## Отчёт исполнителя (заполняет Claude Code)

- **Сделано:** слой хранения собран и работает. 14 SQLAlchemy-моделей по
  `architecture.md` §5; baseline-миграция Alembic (создаёт схему с нуля, чисто
  откатывается); генератор бизнес-номеров; идемпотентный сид справочников;
  синтетический датасет, покрывающий инварианты; CLI `tools/seed_db.py`; 34 pytest-теста
  против критериев приёмки. Рабочая `app.sqlite` на машине создана и засеяна
  справочниками (в git не попадает — `.gitignore`). Кода приложения, ETL и генерации
  документов, как и задано, нет.

- **Раскладка `src/`:**

  ```
  src/db/base.py       Declarative Base + соглашение об именовании констрейнтов
  src/db/models.py     14 моделей + словари DECISION_DEV/DECISION_INSP/Direction + ALL_TABLES
  src/db/session.py    движок, PRAGMA foreign_keys=ON, session_scope; URL из QMS_DB_URL / app.sqlite
  src/db/ids.py        next_dev_number / next_insp_number
  src/seed/reference.py  REFERENCE_SEED, seed_reference(), ref() — доступ к General-дефолтам
  src/seed/synthetic.py  build_synthetic()
  alembic.ini · migrations/versions/baseline_schema_rev_0_1.py   (revision id `baseline`)
  tools/seed_db.py     CLI: --synthetic, --url
  pytest.ini           pythonpath=src, SAWarning как ошибка
  tests/               conftest + 5 файлов по критериям приёмки
  ```

  Импорт пакета — через `pythonpath = src` (pytest) и `sys.path`-вставку (alembic `env.py`,
  `tools/`), без установки пакета в venv. БД: `QMS_DB_URL`, иначе `app.sqlite` в корне.

- **Решения по заметкам (А код 99 · Б decision_date · В direction · Г state_depending):**

  - **А. Код 99 → булев флаг `is_absent` на `mapping`** (не сентинел-`g_position`).
    Код 99 — утверждение о факте маппинга («позиция рассмотрена, отсутствует»), а не
    геометрия. Сентинел-позиция засорила бы канон-слой фиктивной записью без
    номинала/допуска и, главное, стала бы ложным ключом join'а: поиск по `(cg, g_index)`
    начал бы схлопывать между собой 99-е разных деталей. С флагом три состояния
    различаются на уровне схемы: строки нет = маппинга ещё нет (в т.ч. исключение R2
    «срочный WO»); `g_position_id` заполнен = привязан; `g_position_id IS NULL AND
    is_absent` = код 99. Поиск такие строки не видит естественно — джойнить нечего, что
    и требует канон («не ключ поиска»). CHECK `ck_mapping_target_xor_absent` запрещает и
    «привязан и отсутствует» одновременно, и пустую строку.
  - **Б. `decision_date`** — Python-side `default=datetime.now` (локальное наивное
    время), не `server_default CURRENT_TIMESTAMP`: в SQLite это UTC, смешивать семантики
    в одной колонке нельзя. Python-дефолт перекрывается явным значением — импорт S6
    просто передаст своё.
    Отдельно зафиксировано правило `YYMMDD` в номере: **системная дата в момент
    присвоения** (перекрывается параметром `on_date`). Номер идентифицирует запись, а не
    физическое событие: `decision_date` на шаге регистрации ещё не существует (решение —
    шаг 8, регистрация — шаг 3), а `date` события может приходить задним числом из
    импорта, что ломало бы монотонность и заставляло дописываться в уже израсходованный
    суточный счётчик.
  - **В. `direction`** — `NOT NULL` + CHECK `IN ('+','-')`, хранится **ASCII-дефис**
    (канон в прозе пишет типографский `−`, U+2212). Константы `Direction.PLUS/MINUS` —
    единая точка для парсера S6 и UI, чтобы знак не размножался литералами.
  - **Г. `state_depending`** — nullable self-FK `characteristic.state_depending_id →
    characteristic.characteristic_id`. В схеме есть, кодом/сидом/синтетикой **не
    заполняется**; тест проверяет наличие self-FK через инспектор и NULL по умолчанию.

- **Коммиты:**
  - `461823b` feat(db): SQLAlchemy-модели 14 таблиц + сессия SQLite + генератор бизнес-номеров
  - `8d4af79` feat(db): baseline-миграция Alembic (14 таблиц, SQLite)
  - `6ef1db9` feat(seed): идемпотентный сид справочников + синтетический датасет + CLI
  - `bf66cfb` test: pytest-набор против критериев приёмки 1-5
  - `6f0bf22` chore: строка решения QMS-010 (роадмап в волте) + allowlist диагностических команд
    — авторская правка Cowork в `docs/decisions.md` лежала незакоммиченной, залил без
    изменения содержимого (репо ведёт Claude Code, `CLAUDE.md` §4)
  - последний — `docs(worklog): наряд 0001 + отчёт исполнителя` (сам этот текст)

- **Проверки:** `pytest` — **34 passed**, плюс ручной прогон на `app.sqlite`. Схему в
  тестах поднимает **та же baseline-миграция**, что и в production (не параллельный
  `create_all`), поэтому критерий 1 проверяется на каждом тесте.

  1. **Миграция.** `alembic upgrade head` на чистой БД → 14 таблиц, лишнего нет (кроме
     `alembic_version`); `downgrade base` → остаётся только `alembic_version`; цикл
     up→down→up повторяем. Прогнано и в тестах, и вживую на `app.sqlite`.
  2. **FK и UNIQUE.** `PRAGMA foreign_keys` = 1 проверен явно. Падают с `IntegrityError`:
     finding с несуществующим `characteristic_id`; дубль `item_number`; дубль
     `dev_number`; дубль `insp_number`; второй `mapping` на ту же характеристику; дубль
     `(item_id, local_number)`. Проходит (и должно): одинаковый `local_number` у разных
     деталей. Дополнительно держат словарные CHECK — `decision_dev`, `direction`,
     `decision_insp` — и xor-инвариант маппинга (заметка А, 3 теста).
  3. **Бизнес-номера.** Формат `DEV-YYMMDD-NNNN` / `INSP-YYMMDD-NNN` (regex), ведущие
     нули; пакет из 25 отклонений за одни сутки — строго последовательный, без дублей;
     счётчик посуточный (новый день → `0001`) и переживает перезапуск, т.к. выводится из
     БД, а не из памяти процесса.
  4. **Round-trip.** Синтетика пишется, соединение закрывается, читается на новом
     движке: `item → characteristic → mapping → g_position → cg` (включая номинал/допуск
     и код 99), `deviation → finding → inspection`, справочники, обратная навигация
     `finding → deviation → item`, ивритский `explanation` — без потерь. Отдельно
     проверено, что справочные значения общие, а не скопированные.
  5. **Сид.** Повторный прогон вставляет 0 строк; частично заполненный справочник
     досеивается без дублей; `General` присутствует в `ref_connection_type` и `ref_size`.

  **Средовая диагностика (RULES §16), два реальных упора:**
  - Локаль машины — **cp1255** (иврит). Alembic читает `alembic.ini` с
    `encoding="locale"`, поэтому не-ASCII в ini падает с `UnicodeDecodeError`. Решение:
    `alembic.ini` и `pytest.ini` держим ASCII-only, пометка стоит в самих файлах.
  - Консоль тоже cp1255 — печать кириллицы (и ивритских данных из БД) падает с
    `UnicodeEncodeError`. Решение: CLI перенастраивает `stdout/stderr` на UTF-8 при
    старте. Для будущих CLI/скриптов — то же правило.
  - `pytest 9.1.1` доустановлен в venv, `requirements.txt` перефиксирован (`pip freeze`).

- **Отклонения / вопросы Cowork:**

  1. **`state_depending` — FK против номера.** `model/Characteristic.md` описывает
     атрибут как «хранит номер связанного размера», `architecture.md` §5 и наряд — как
     nullable self-FK. Реализован **self-FK** (номер сам по себе вне детали
     неоднозначен, FK строже и не даёт повиснуть). Канон не правил — формулировку в
     `Characteristic.md` синхронизировать вам.
  2. **Item ↔ CG many-to-many не материализован.** `Item.md` говорит про связь
     «для роста» (сейчас 0..1), но `architecture.md` §5 такой таблицы не содержит, и
     наряд фиксирует ровно 14 таблиц. Сейчас принадлежность детали к CG выводится через
     `characteristic → mapping → g_position → cg`. Подтвердите, что это ок до появления
     CG второго уровня, — иначе это 15-я таблица и правка §5.
  3. **`decision_dev` сделан nullable** (наряд не оговаривал): NULL = «решение ещё не
     принято». По процессу регистрация — шаг 3, решение — шаг 8, значит отклонение
     обязано существовать без решения. CHECK допускает NULL или одно из 4 значений.
     Подтвердите.
  4. **`explanation` — NOT NULL с дефолтом `''`** (канон: «свободный текст, **всегда**»).
     На момент регистрации до решения это пустая строка. Если «всегда» означает
     «непусто на момент решения» — это доменная валидация S2, а не схема; скажите, какой
     вариант канонический.
  5. **Межтабличный инвариант не выражен в схеме:** `finding.characteristic` должен
     принадлежать `deviation.item`. В SQLite это требует либо дублирования `item_id` в
     `finding` с композитным FK, либо триггера. В S1 не enforced — предлагаю доменную
     проверку в S2 при сохранении карточки. Решение за вами (вариант с композитным FK
     меняет §5).
  6. **`direction` NOT NULL — риск на S6.** Для качественных признаков (`GO`/`מדיד`,
     пин) величины нет, но направление по канону берётся из слова max/min, поэтому
     NOT NULL корректен. Если в реальных данных встретится случай **без направления
     вовсе** — колонку придётся сделать nullable (миграция). Флажок на ETL-наряд.
  7. **`attachment` — одно текстовое поле** со ссылкой(ами) на файлы в сетевой папке.
     Если понадобятся несколько вложений с метаданными (тип, кто приложил, дата) —
     это отдельная таблица и правка §5.
  8. **`quantity = 9999`** (выборка `X מתוך Y`) хранится обычным числом, без отдельного
     флага; в синтетике такой случай есть. Если сентинел нужно отличать от реального
     количества — нужен флаг, скажите.
  9. **Для волта (INFRA):** локаль целевой машины cp1255 задаёт два правила разработки —
     конфиги configparser-типа (`*.ini`) держим ASCII-only; CLI-скрипты перенастраивают
     stdout на UTF-8. Занести в `_system/INFRASTRUCTURE` — ваше (в волт не писал).
  10. **Q-07** (`מנה` vs глоссарий) кодом не затронут: `wo` — просто строка.
