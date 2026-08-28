# LapBase v1.0.28

LapBase читает разрешённые новостные каналы Discord, очищает служебную разметку,
переводит английский текст на русский через Groq и публикует результат в Telegram.
Проект хранит техническое состояние и связь Discord → Telegram в Supabase PostgreSQL.

## Быстрый старт

### Windows 10/11

1. Распакуйте проект в обычную папку без прав администратора.
2. Скопируйте `.env.example` в `.env` и заполните секреты/ID.
3. Запустите `start.bat` двойным кликом.

### Ubuntu Linux

```bash
cp .env.example .env
# заполните .env
chmod +x start.sh
./start.sh
```

Первый запуск требует интернет. Launcher сам загружает **строго uv 0.12.2**, проверяет
SHA-256 до исполнения, устанавливает локальный **Python 3.14.7**, создаёт `.venv` и
синхронизирует зависимости. Системный Python/pip не используются.

При обычном повторном запуске runtime и зависимости не переустанавливаются. Launcher
сравнивает dependency fingerprint и синхронизирует environment только если изменились
`pyproject.toml`/`uv.lock` или environment повреждён.

## Portable Mode

Целевой режим: **PORTABLE-L2**.

- `.runtime/` — локальный uv, Python и cache;
- `.venv/` — локальные Python-зависимости;
- `.1kds/state/` — fingerprints и служебное состояние без секретов;
- `logs/` — application/bootstrap logs;
- `backups/` — проверяемые логические backups Supabase.

Launcher не изменяет системный PATH, не устанавливает глобальные Python packages и не
переходит на system Python при ошибке локального runtime.

Поддерживаемые launcher-платформы: Windows x64, Linux x64 и Linux arm64. macOS не входит
в согласованный scope проекта, поэтому `start.command` намеренно отсутствует.

## Зависимости

Единственный dependency manifest — `pyproject.toml`. `requirements.txt` удалён как
дублирующий источник истины. Прямые runtime-зависимости закреплены точными версиями.

`uv.lock` является обязательным production lock-файлом. Если архив был получен до
генерации lock-файла, первый launcher создаст его один раз при доступе к PyPI, после чего
его следует добавить в Git. Последующие sync выполняются с `--frozen`.

## Конфигурация

Секреты хранятся только в `.env` и не должны попадать в Git. Шаблон находится в
`.env.example`. Ключевые настройки:

- `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_IDS`;
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`;
- `GROQ_API_KEY`, `GROQ_MODEL`;
- `SUPABASE_DB_URL`;
- таймауты `GROQ_TIMEOUT_SECONDS`, `TELEGRAM_TIMEOUT_SECONDS`,
  `DISCORD_API_TIMEOUT_SECONDS`, `DISCORD_READY_TIMEOUT_SECONDS`,
  `DB_COMMAND_TIMEOUT_SECONDS`.

## Поведение автопоста

Автопубликация использует Telegram `send_message` с HTML:

```text
Источник официальный DISCORD: #имя-канала

Переведённый текст с сохранёнными переносами.

#autopost@lapbase
```

Строка источника выводится жирным. Discord channel artifacts, `@everyone`, `@here`
и Discord custom emoji очищаются. Все URL в обычном тексте удаляются до перевода;
URL внутри code blocks/inline code сохраняются. Строки с просьбой дать обратную связь
и вопросы к аудитории о мнении/ответе удаляются до отправки в Groq.

Если Discord post содержит изображения, URL первой картинки передаётся Telegram отдельно
через `LinkPreviewOptions.url`. Сам CDN URL в `text` не вставляется. Telegram запрашивается
показать крупный preview под текстом. Если изображений несколько, используется только первое.

## Очередь и retry

Обработка последовательная: один Discord post за раз. Временная ошибка блокирует более
новые posts до retry. По умолчанию максимум 5 попыток через 5 минут.

Retry выполняется только для временных сетевых/server/rate-limit ошибок. Ошибки
валидации, Telegram Bad Request и другие постоянные ошибки сразу переходят в `failed`.

## Админ-команды

В Telegram admin command menu и `/help` синхронно отображаются все 20 поддерживаемых команд:
`/start`, `/stop`, `/restart`, `/pause`, `/resume`, `/status`, `/health`, `/stats`,
`/queue`, `/failed`, `/retry`, `/delete`, `/republish`, `/sync`, `/logs`, `/backup`,
`/cleardb`, `/post`, `/cancel`, `/help`.

Права администратора по-прежнему проверяются через `TELEGRAM_ADMIN_USER_ID`, а Telegram
command menu устанавливается для `TELEGRAM_ADMIN_CHAT_ID`.

Опасные операции требуют подтверждения. `/cleardb` перед удалением данных автоматически
создаёт и проверяет backup. Уже опубликованные Telegram messages физически не удаляются
при `/cleardb`.

## База и migrations

Миграции находятся в `migrations/` и регистрируются в `schema_migrations`. Автоматическое
применение разрешено только если состояние БД является линейным префиксом локальной
истории. Неизвестная/расходящаяся история останавливает запуск вместо скрытого repair.

После миграций выполняется schema-contract check обязательных полей `posts`. Дополнительные
additive-колонки разрешены. Repository не использует `SELECT *` для создания `PostRecord`,
поэтому будущая дополнительная колонка сама по себе не должна ломать старую модель.

## Backup и восстановление

Backup создаётся в `backups/lapbase_*.json.gz` и содержит `posts`, `stats_events`,
`system_state`, `admin_confirmations`, `schema_migrations`. Перед признанием успешным файл
повторно открывается и проверяется. Запись выполняется через temporary file + atomic replace.

Ручной backup:

```bash
.venv/bin/python scripts/backup_db.py
```

Восстановление — отдельная осознанная операция:

```bash
.venv/bin/python scripts/restore_backup.py backups/<file>.json.gz
```

## Логи и диагностика

- `logs/lapbase.log` — application log;
- `logs/bootstrap.log` — installer/launcher bootstrap log.

`start.bat` и `start.sh` показывают одну и ту же проектную информацию:
версию из `pyproject.toml`, платформу, `Portable L2` и `UTF-8`.
Bootstrap-ошибка и ошибка уже запущенного приложения различаются отдельными сообщениями.

Python terminal streams запускаются с `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8` и
`PYTHONUNBUFFERED=1`. Windows launcher дополнительно включает code page 65001.
Linux launcher использует существующую UTF-8 locale, не меняя системные настройки.

`/health` показывает состояние `Queue worker` (`RUNNING`, `PAUSED`, `FAILED`, `STOPPED`)
и последнюю ошибку worker, если она есть. На Windows окно после ошибки launcher остаётся
открытым.

## systemd

Пример: `deploy/lapbase.service`. После копирования проекта в `/opt/lapbase` настройте
пользователя/права и включите unit стандартными средствами systemd.

## Проверки разработки

После подготовки dev environment:

```bash
./start.sh --prepare-only --dev
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app tests
.venv/bin/python -m mypy app
.venv/bin/python -m compileall -q app
```

CI: `.github/workflows/ci.yml`, Windows + Linux.

Фактический Portable Proof после подготовки environment:

```bash
.venv/bin/python scripts/portable_proof.py
```

На Windows используйте `.venv\Scripts\python.exe scripts\portable_proof.py`.

## Обновление

Перед заменой файлов **полностью остановите старый LapBase**, затем замените source-файлы,
не перезаписывая `.env`, и запустите `start.bat`/`start.sh` заново.

Начиная с v1.0.28 приложение удерживает cross-platform instance lock в
`.1kds/state/lapbase.lock`. Второй экземпляр завершается с exit code `73` **до подключения
к БД и миграций**. Сам lock-файл может оставаться на диске как metadata — активность
определяется OS file lock, а не наличием файла.

Важно для первого перехода v1.0.27 → v1.0.28: v1.0.27 ещё не умеет держать этот lock,
поэтому старый процесс необходимо остановить вручную до обновления.

Launcher обновит только изменившийся слой: runtime при изменении runtime manifest,
dependencies при изменении fingerprint, environment при повреждении.

## Удаление

Portable runtime/environment удаляются вместе с каталогом проекта. Supabase — внешний
persistent storage и не удаляется при удалении локальной папки. Перед удалением проекта
при необходимости выполните `/backup`.

## Известное ограничение текущей сборки

В среде сборки v1.0.23 отсутствовал сетевой доступ Package Registry и локальный Python 3.14.7,
поэтому фактический `uv.lock` не удалось сгенерировать и проверить здесь. Это препятствует
заявлению полного соответствия 1KDS-DEP-002 до первого успешного lock/sync и добавления
полученного `uv.lock` в Git. Остальные проверки перечисляются в итоговом отчёте сборки.

## Статус 1KDS

Подробный отчёт: `1KDS_REPORT.md`.

До генерации и commit `uv.lock` проект **не объявляется полностью DONE по 1KDS**.


## Исправление Portable bootstrap в v1.0.23

Текущий pinned runtime использует `uv 0.12.2` и Python `3.14.7`.
Причина изменения: managed CPython `3.14.7` появился начиная с `uv 0.12.2`,
поэтому предыдущая связка `uv 0.12.1 + Python 3.14.7` не могла пройти first-install.

При ошибке `start.bat` и `start.sh` показывают последние 20 строк
`logs/bootstrap.log`, чтобы техническая причина была видна сразу.


## Исправление Windows bootstrap в v1.0.24

Исправлен этап определения пути к managed Python после установки:

- `start.bat` больше не запускает `uv python find` внутри `FOR /F`;
- результат `uv python find` сначала записывается в `.1kds/state/python-path.tmp`,
  затем безопасно читается как обычная строка;
- временный файл удаляется после чтения;
- `UV_PYTHON_INSTALL_BIN=0` и `--no-bin` запрещают создание новых Python executable-links
  вне project root;
- `UV_PYTHON_NO_REGISTRY=1` и `--no-registry` запрещают Windows registry discovery/registration;
- хвост `bootstrap.log` читается PowerShell с `-Encoding UTF8`.

Уже созданные внешние executable-links автоматически не удаляются: изменение файлов
вне project root требует отдельного согласования.


## Очистка автопостов в v1.0.25

- все URL удаляются из обычного текста;
- URL внутри code blocks/inline code сохраняются;
- `[полезный текст](https://...)` превращается в `полезный текст`;
- feedback-призывы и вопросы к аудитории удаляются до Groq;
- Discord CDN URL изображений больше не добавляются в Telegram `send_message`.

При текущем режиме `send_message` изображения нативно не прикрепляются.


## Native media в v1.0.26

Автопост с изображениями публикуется как одна логическая Telegram-публикация:

```text
1 изображение:
[send_photo]
[send_message с полным HTML-текстом]

2–10 изображений:
[send_media_group]
[send_message с полным HTML-текстом]
```

Discord CDN URL используются только как внутренний источник media и не вставляются в текст.

Для mapping используются:
- `telegram_message_id` — ID текстового сообщения;
- `telegram_media_message_ids BIGINT[]` — ID фото/альбома.

При edit/republish создаётся новый bundle, затем старый bundle удаляется best-effort.
При delete удаляются все сохранённые media ID и text ID.

Миграция `004_telegram_media_messages.sql` additive и не удаляет существующие данные.
Старые backup без поля `telegram_media_message_ids` восстанавливаются с пустым списком.


## CDN link preview в v1.0.27

Текущая модель снова: **один Discord post → один Telegram message**.

- без картинки: обычный `send_message`;
- с картинкой: тот же `send_message` + `LinkPreviewOptions.url=image_urls[0]`;
- `prefer_large_media=True`;
- `show_above_text=False`;
- CDN URL отсутствует в тексте сообщения;
- при нескольких изображениях используется только первое;
- edit обновляет тот же Telegram message и новый preview;
- если картинка при edit исчезла, старый preview явно отключается.

Миграция `004_telegram_media_messages.sql` не удаляется и не откатывается. Поле
`telegram_media_message_ids` больше не является новым mapping-контрактом; оно сохраняется
для совместимости backup/схемы и временной очистки сообщений, созданных v1.0.26.


### Уточнение отображения preview

По явному подтверждению пользователя сборка v1.0.27 пересобрана без повышения версии:
preview первой Discord-картинки теперь запрашивается **под текстом**
через `show_above_text=False`.


## Reliability hardening v1.0.28

Исправлен класс ошибки, при котором новая additive-колонка БД могла вызвать
`PostRecord.__init__() got an unexpected keyword argument ...` в уже работающем процессе.

Защиты v1.0.28:
- explicit column contract вместо `SELECT *` в Repository;
- fail-fast schema check обязательных полей после migrations;
- cross-platform single-instance lock до DB connect/migrate;
- состояния QueueWorker: `STOPPED/RUNNING/PAUSED/FAILED`;
- ограниченный retry только для временных infrastructure errors;
- logic/contract error переводит worker в `FAILED` и уведомляет администратора;
- `worker.stop()` больше не повторно выбрасывает старое исключение task;
- `/restart` и системный shutdown могут восстановиться после worker crash;
- `/health` показывает состояние worker и последнюю ошибку;
- `systemd` не входит в restart-loop при exit code `73`.
