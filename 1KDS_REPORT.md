# LapBase 1.0.28 — отчёт 1KDS

## Статус

**Статус: частично соответствует 1KDS v1.0.0; полный статус DONE пока не заявляется.**

Обязательный production lock-файл `uv.lock` не был корректно сгенерирован в среде сборки:
в ней нет доступа к реестру зависимостей и отсутствует подготовленный локальный Python 3.14.7.
Подделывать lock-файл запрещено. Launcher умеет создать его на первой подготовке окружения,
а `publish.bat` блокирует публикацию, пока `uv.lock` отсутствует.


## Gate v1.0.28 — отказоустойчивость, терминалы и Telegram-команды

### Причина изменения

На Linux был зафиксирован реальный отказ:

```text
TypeError: PostRecord.__init__() got an unexpected keyword argument
'telegram_media_message_ids'
```

Исключение завершало `QueueWorker`, после чего `worker.stop()` повторно получал ошибку
уже завершённой task. Из-за этого ломались `/restart`, `/stop` и системный shutdown.

### Реализованные защиты

- Repository создаёт `PostRecord` только из явного списка `POST_RECORD_COLUMNS`;
- `SELECT * FROM posts` исключён из runtime Repository-контракта;
- дополнительная additive-колонка не передаётся в dataclass автоматически;
- после migrations выполняется fail-fast проверка обязательных колонок `posts`;
- extra-колонки разрешены;
- перед DB connect/migrate приложение получает OS-level single-instance lock;
- второй экземпляр получает exit code `73`;
- `start.bat` и `start.sh` одинаково обрабатывают exit code `73`;
- systemd использует `RestartPreventExitStatus=73`;
- QueueWorker имеет состояния `STOPPED`, `RUNNING`, `PAUSED`, `FAILED`;
- временные инфраструктурные ошибки получают только ограниченный retry;
- logic/contract error переводит QueueWorker в `FAILED` и сохраняет последнюю причину;
- `worker.stop()` безопасно потребляет завершившуюся с ошибкой/cancellation task;
- Runtime различает здоровье Discord и QueueWorker;
- при живом Discord и FAILED worker можно восстановить только worker;
- `/health` показывает состояние worker и последнюю ошибку;
- `/restart` использует безопасный stop → start;
- системный shutdown больше не должен повторно выбрасывать старую ошибку QueueWorker.

### Version / UTF-8 / launcher parity

Единственный источник project version — `pyproject.toml`.

Удалён устаревший второй источник:

```text
app/__init__.py: __version__ = "1.0.0"
```

`start.bat`, `start.sh` и `publish.bat` читают версию из `pyproject.toml`.

Windows и Linux launcher показывают:

```text
LapBase v1.0.28
Платформа: ...
Режим: Portable L2
Кодировка: UTF-8
```

Для Python terminal I/O устанавливаются:
- `PYTHONUTF8=1`;
- `PYTHONIOENCODING=utf-8`;
- `PYTHONUNBUFFERED=1`.

Windows дополнительно использует `chcp 65001`.
Linux выбирает уже существующую UTF-8 locale без изменения системных настроек.
Python logging явно reconfigure stdout/stderr на UTF-8.

Bootstrap и application errors теперь различаются:
- `[ОШИБКА] Не удалось подготовить LapBase.`
- `[ОШИБКА] LapBase завершился с ошибкой.`

### Telegram command menu

Единый `ADMIN_COMMAND_SPECS` является источником для Telegram menu и `/help`.

Проверены все 20 команд:
`/start`, `/stop`, `/restart`, `/pause`, `/resume`, `/status`, `/health`, `/stats`,
`/queue`, `/failed`, `/retry`, `/delete`, `/republish`, `/sync`, `/logs`, `/backup`,
`/cleardb`, `/post`, `/cancel`, `/help`.

Telegram command scope использует `TELEGRAM_ADMIN_CHAT_ID`.
Авторизация административных действий остаётся по `TELEGRAM_ADMIN_USER_ID`.

### Фактически выполнено в текущей среде

- `pytest`: **86 passed**;
- `python -m compileall -q app scripts tests`: **OK**;
- `bash -n start.sh`: **OK**;
- статическая проверка `start.bat`: **15 labels / 5 refs / missing 0**;
- статическая проверка `publish.bat`: **96 labels / 95 refs / missing 0**;
- BAT CRLF: **OK**;
- SH/service LF и UTF-8 decode: **OK**;
- version single source `1.0.28`: **OK**;
- Telegram admin menu: **20/20**;
- regression: extra DB column → `PostRecord` не ломается: **OK**;
- regression: missing required DB column → fail-fast: **OK**;
- regression: QueueWorker logic error → `FAILED`: **OK**;
- regression: stop после crashed/cancelled worker task: **OK**;
- Linux OS-level second-instance lock test: **OK**;
- instance lock расположен до DB connect/migrations: **OK**;
- migrations v1.0.27 → v1.0.28 не изменены: **OK**.

### Не считается проверенным

- Ruff: модуль `ruff` отсутствует в среде сборки;
- mypy: модуль `mypy` отсутствует в среде сборки;
- `uv audit --frozen --no-dev`: `uv.lock`/подготовленный Portable runtime отсутствуют;
- реальный `start.bat` на Windows;
- реальный `start.sh --prepare-only --dev` на целевой Ubuntu с Portable runtime;
- GitHub Actions Windows/Linux;
- live Discord/Groq/Telegram/Supabase E2E;
- реальное отображение Discord CDN preview в Telegram.

Эти пункты не объявляются успешно пройденными.

### Первый переход с v1.0.27

v1.0.27 ещё не удерживает новый instance lock. Поэтому перед первым обновлением
`v1.0.27 → v1.0.28` старый процесс необходимо **полностью остановить**, и только затем
заменять файлы и запускать новый release.

Новых DB migrations и новых dependencies в v1.0.28 нет.

Полный статус `DONE` по 1KDS по-прежнему не заявляется.

## Согласованный scope

Функциональность LapBase v1.0.21 сохранена:
- Discord → очередь → Groq → Telegram;
- Telegram `send_message`;
- Supabase PostgreSQL;
- admin-команды, `/post`, `/cleardb`;
- backup/restore;
- edit/delete публикаций;
- sync за 24 часа.

Изменена инженерная основа: Portable L2, launchers, зависимости, versioning,
retry/timeout, миграции, backup verification, CI и документация.

## Реализовано

### Portable L2
- Python `3.14.7`.
- uv `0.12.2`.
- runtime: `.runtime/`.
- environment: `.venv/`.
- `.venv` создаётся только локальным managed Python.
- fallback на system Python/PIP отсутствует.
- uv-артефакт выбирается по OS/архитектуре.
- SHA-256 проверяется до запуска скачанного uv.
- dependency sync запускается только при первом install/repair или изменении fingerprint.
- служебный state: `.1kds/state/`.
- `.env` не перезаписывается.
- системный PATH не изменяется.

### Launcher state
Поддерживаются состояния:
`FIRST_INSTALL`, `NORMAL_START`, `DEPENDENCY_CHANGE`, `RUNTIME_CHANGE`,
`BROKEN_ENVIRONMENT`, `CONFIG_ERROR`, `MIGRATION_REQUIRED`, `APPLICATION_ERROR`.

### Зависимости
Единый dependency source — `pyproject.toml`.
Прямые зависимости зафиксированы точными версиями.
`requirements.txt` удалён как дублирующий источник истины.
После появления `uv.lock` sync выполняется через `--frozen`, а fingerprint строится
из `pyproject.toml` + `uv.lock`.

### Ошибки и сеть
- retry только для классифицированных временных ошибок;
- постоянные ошибки сразу получают `failed`;
- Groq internal retry отключён, retry контролирует очередь;
- явные timeout для Groq, Telegram, Discord API и БД;
- технические подробности пишутся в лог, не в Telegram UI.

### БД и backup
- история миграций валидируется до применения;
- backup пишется во временный файл и атомарно заменяется;
- backup после создания открывается и валидируется;
- `/cleardb` сначала создаёт и проверяет backup;
- restore валидирует backup до восстановления.

### Язык
- новый launcher UI и пояснения на русском;
- новые комментарии/docstring на русском;
- идентификаторы остаются английскими;
- README на русском.

### CI
Windows + Ubuntu:
- Portable L2 prepare;
- pytest;
- Ruff;
- mypy;
- compileall;
- `uv audit --frozen --no-dev`;
- `bash -n start.sh` на Linux.

## Исторические проверки базовой 1KDS-сборки

- `pytest`: **40 passed**.
- `python -m compileall -q app scripts tests`: **OK**.
- `bash -n start.sh`: **OK**.
- статическая проверка BAT labels/references: **OK**.
- CRLF для BAT: **OK**.
- поиск известных fallback-patterns system Python/PIP в launchers: **OK**.
- проверка ZIP на `.env`, runtime/cache и Python bytecode: **OK**.
- базовый поиск явных секретов в исходниках: **OK**.

## Исторически не проверенные пункты

- реальный `start.bat` на Windows;
- реальный first-install uv 0.12.1 + Python 3.14.7;
- Ruff локально;
- mypy локально;
- `uv audit` локально;
- GitHub Actions CI;
- live Discord/Groq/Telegram/Supabase E2E;
- создание `uv.lock`.

Эти пункты не считаются успешно пройденными.

## Следующий обязательный Gate

На Windows с интернетом:

```bat
start.bat --prepare-only --dev
```

После успешного выполнения:
1. проверить появление `uv.lock`;
2. запустить `publish.bat`;
3. пройти CI Windows + Ubuntu;
4. провести финальный 1KDS Gate.

## Rollback

Исходный `LapBase_v1.0.21.zip` не изменён.
`.runtime`, `.venv`, `.1kds/state` восстанавливаемые.
`.env` и данные Supabase не удаляются при rollback среды.

## Portable Proof — текущий проектный статус

```text
PORTABLE PROOF
Portable level: L2 (реализация; первый bootstrap ещё не подтверждён на целевых ОС)
Project root: вычисляется из расположения launcher
Runtime: PROJECT/.runtime/python/...
Runtime version: 3.14.7
Architecture: Windows x86_64; Linux x86_64/aarch64
Dependencies: PROJECT/.venv
Environment: PROJECT/.venv
Dependency fingerprint: SHA-256(pyproject.toml + uv.lock)
Bootstrap entry Windows: start.bat
Bootstrap entry Linux: start.sh
Bootstrap entry macOS: UNSUPPORTED (macOS не входит в согласованные платформы)
System bootstrap baseline: Windows cmd.exe + PowerShell; Linux sh/bash + curl/wget + tar + sha256sum/shasum
System language runtime usage: NONE по статическому анализу launchers
Global package manager usage: NONE
PATH modifications: NONE
User data location: Supabase/Telegram/Discord; локальные backup в PROJECT/backups
Config location: PROJECT/.env
Repair behavior: восстанавливает runtime/environment/cache/state; .env и бизнес-данные не сбрасывает
Offline after initial setup: PARTIAL
Validated platforms: Linux syntax/static; Windows BAT static only
```

Полный Portable Proof возможен только после реального bootstrap smoke на Windows и Linux.


## Исправление bootstrap v1.0.23

Текущий pinned bootstrap:
- uv `0.12.2`;
- Python `3.14.7`.

Причина: версия uv 0.12.2 добавила managed CPython 3.14.7; uv 0.12.1 была
выпущена раньше и не могла установить этот runtime.

Официальные SHA-256:
- Windows x64: `01442d8ce5c7124151a73e697c836d252c6da853c18c73206d3cc4c2378a91d2`
- Linux x64: `d66e96b5f1ca3b99806eee283a8125d33a0bd669e6e6d9bc4ab7ffda63c41bf4`
- Linux arm64: `19b7f1f66895261fbaa07f8ea91da0f86337ad4e47efa594e87641c1718ffc52`

Полный 1KDS DONE по-прежнему не заявляется до реального first-install smoke,
создания `uv.lock`, Ruff/mypy/audit и CI.


## Исправление Windows bootstrap v1.0.24

На реальном Windows first-install выявлена ошибка quoting `cmd.exe` при использовании
`FOR /F` с командой `uv python find`. Сам Python 3.14.7 устанавливался успешно, но
launcher не мог прочитать найденный путь.

Исправление:
- поиск managed Python через временный файл внутри `.1kds/state/`;
- без command substitution `FOR /F`;
- `UV_PYTHON_INSTALL_BIN=0`;
- `UV_PYTHON_NO_REGISTRY=1`;
- установка Python с `--no-bin --no-registry`;
- UTF-8 чтение диагностического лога.

Полный 1KDS DONE по-прежнему не заявляется до успешного Windows prepare,
создания `uv.lock`, Ruff/mypy/audit и CI.


## Очистка автопостов v1.0.25

Согласованное изменение поведения:
- URL обычного текста удаляются до Groq;
- URL внутри code сохраняются;
- feedback calls и audience opinion questions удаляются построчно до Groq;
- Discord image attachment URLs больше не добавляются в `send_message`.

БД, очередь, admin-команды и API-контракты не изменялись.


## Native media v1.0.26

Согласованное R2-изменение:
- Telegram native `send_photo` / `send_media_group`;
- полный текст остаётся отдельным `send_message`;
- additive migration `telegram_media_message_ids BIGINT[]`;
- edit/republish заменяет весь логический bundle;
- delete удаляет весь bundle;
- при ошибке текста после успешного media publisher выполняет compensating cleanup;
- старые backup без media ID остаются восстанавливаемыми.

Остаточный риск:
Telegram API и PostgreSQL не образуют общую транзакцию. Если новая публикация полностью
создана и старый bundle удалён, но запись нового mapping в БД затем упадёт, возможен
orphan Telegram bundle. Outbox/transaction coordinator сознательно не добавлялся как
избыточная сложность для текущего scope.

Live Telegram/Supabase E2E не считается проверенным до реального запуска.


## CDN link preview v1.0.27

Согласованное изменение заменяет native-media bundle v1.0.26 на один `send_message`:
- первая Discord image URL передаётся через `LinkPreviewOptions.url`;
- URL не добавляется в HTML-текст;
- запрашивается large preview под текстом;
- edit меняет text + preview в существующем message;
- delete снова работает по одному `telegram_message_id`;
- migration 004 остаётся additive schema residue и не удаляется;
- legacy `telegram_media_message_ids` используется только для переходной очистки
  уже созданных v1.0.26 media-сообщений и затем очищается в БД.

Фактическое отображение preview конкретного Discord CDN URL зависит от Telegram и должно
быть подтверждено live-тестом. Оно не считается проверенным в среде сборки.


## Повторная сборка v1.0.27: preview снизу

По явному выбору пользователя версия не повышалась, несмотря на изменение содержимого сборки.
Это сознательное отклонение от обычной практики неизменяемости SemVer-артефактов.

Функциональное изменение:
- `show_above_text=False`;
- preview первой Discord-картинки запрашивается под текстом;
- остальные контракты v1.0.27 не менялись.
