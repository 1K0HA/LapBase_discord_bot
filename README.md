# LapBase v1.0.4

LapBase watches selected Discord text channels, translates English posts to Russian with Groq,
preserves supported formatting/images, and publishes them to a Telegram channel. It also provides a
private Telegram control plane for the main administrator.

## Current architecture

- Private project-managed Python 3.14 via `uv` (system Python is not required)
- `discord.py 2.7.1`
- `aiogram 3.30.0` / Telegram Rich Messages
- `groq 1.6.0`, default model `openai/gpt-oss-120b`
- Supabase PostgreSQL via `asyncpg`
- Windows 10/11 and Ubuntu 22.04+
- `systemd` for production auto-start/restart

## Security

Never put bot tokens, API keys or DB passwords in source code. Copy `.env.example` to `.env` and fill
it locally. `.env` is ignored by Git.

The source file used to design `/post` contained a Telegram bot token. That token is intentionally NOT
copied into this project; rotate it in BotFather before using this build.

All admin functions are restricted by `TELEGRAM_ADMIN_USER_ID`. The supplied default is `335707167`.

## Setup

1. Create a Supabase project.
2. Copy `.env.example` -> `.env` and fill all required values.
3. Enable Discord **Message Content Intent** and give the bot `View Channel` + `Read Message History`.
4. Add the Telegram bot as an administrator of the destination channel with permission to post/edit/delete.
5. Windows: run `start.bat`.
6. Linux: `chmod +x start.sh && ./start.sh`.
7. On the first launch the launcher installs a private `uv`, private Python 3.14, `.venv`, and project dependencies automatically. The application applies SQL migrations automatically at startup.


### Private Python runtime

LapBase does **not** depend on the system Python. The launchers install and use a project-local runtime:

```text
.runtime/
├── uv-bin/       # private uv executable
├── python/       # private managed Python 3.14
├── python-bin/
└── cache/

.venv/            # project virtual environment using that Python 3.14
.python-version   # pins 3.14
```

The first launch requires internet access. Existing system Python versions (including Python 3.15+) are ignored.
`start.bat` stays open after an error until `CLOSE` is entered. `start.sh` does the same in an interactive terminal, but exits normally under `systemd` so restart policies continue to work.

### Supabase connection

For a persistent VPS, use a Direct connection when the network can reach it. On IPv4-only VPS without
the IPv4 add-on, use the Supavisor **Session Pooler** connection string on port 5432.

## Discord channels

Only IDs from `.env` are accepted:

```env
DISCORD_CHANNEL_IDS=111111111111111111,222222222222222222
```

The channel name is read from Discord at processing time and is added to the Telegram post as:

```text
**Источник официальный DISCORD:** #updates
```

## Main pipeline

1. `MESSAGE_CREATE` is persisted in Supabase as `queued`.
2. A single worker (`concurrency=1`) processes the oldest queued event.
3. Discord links, `@everyone`, `@here`, custom Discord emoji and unsupported attachments are removed.
4. User/role mentions are converted to plain `@name` text.
5. Code, URLs and mentions are protected from translation.
6. Groq translates EN -> RU and corrects Russian grammar without changing meaning/facts.
7. Telegram Rich Message publishes text plus all supported static images in one message.
8. Discord edit -> existing Telegram message is updated.
9. Discord delete -> mapped Telegram message is deleted when Telegram permits it. Telegram Bot API's
   `deleteMessage` has time/permission restrictions; a refused deletion follows normal retry/failure handling.

Retries: 5 total processing attempts with a 5-minute delay. While the oldest item is waiting for retry,
later posts stay blocked to preserve queue order. After the final failure it becomes `failed`, admin is
notified, and the queue continues.

At startup, unfinished jobs are recovered and Discord history from the last 24 hours is checked for
missing message IDs. History is queued oldest -> newest.

## Telegram commands (admin only)

- `/start` - admin panel / start core when stopped
- `/stop` - stop Discord + worker, keep Telegram admin bot online (confirmation required)
- `/restart` - restart the core (confirmation required)
- `/pause`, `/resume`
- `/status`, `/health`, `/stats`, `/queue`, `/failed`
- `/retry <discord_message_id>`
- `/delete <discord_message_id>` (confirmation required)
- `/republish <discord_message_id>` (confirmation required)
- `/sync`
- `/logs [N]` - default 50, max 200
- `/backup`
- `/cleardb` — после подтверждения полностью очищает данные LapBase из `posts`, `stats_events`, `admin_confirmations` и `system_state`; схема БД сохраняется
- `/post` - manual photo/text/button publishing wizard
- `/cancel`
- `/help`

Regular users only receive a bilingual `/start` message explaining that the bot has no user-facing
functionality outside LapBaseApp.

## Data policy

Supabase stores only operational metadata: Discord channel/message IDs, Telegram message ID, status,
retry counters/timestamps, statistics, system state and pending confirmations. Original/translated
post text and images are not stored.

Temporary statistics are cleaned every 48 hours (retention 48h). Critical Discord <-> Telegram mappings
are never auto-deleted. Local logs are retained for approximately 3 days.

Backups: a portable compressed `.json.gz` snapshot of LapBase-owned persistent tables every 24 hours;
keep the latest 3. `/backup` creates one manually. This works on Windows and Linux without `pg_dump`.
Restore while LapBase is stopped with `.venv\Scripts\python.exe scripts\restore_backup.py backups\<file>.json.gz` on Windows or `.venv/bin/python scripts/restore_backup.py backups/<file>.json.gz` on Linux.

## Production systemd

Copy the project to `/opt/lapbase`, adjust `User=` in `deploy/lapbase.service`, then:

```bash
sudo cp deploy/lapbase.service /etc/systemd/system/lapbase.service
sudo systemctl daemon-reload
sudo systemctl enable --now lapbase
```

## Tests

```bash
.venv/bin/python -m pytest
# Windows:
.venv\Scripts\python.exe -m pytest
```

### Discord text cleanup
- Discord routing labels such as `Last Asylum: Plague <#channel_id>:` are removed on any line, and remaining raw `<#channel_id>` mentions are removed everywhere.
- Original line breaks and paragraph spacing are protected during translation.

### Launcher
LapBase uses a project-local `uv` runtime and Python 3.14. `start.bat` / `start.sh` synchronize `requirements.txt` into `.venv` on every launch before starting the app.

### Auto-post format
Automatic Telegram publications use the Rich Markdown heading:
`# **Источник официальный DISCORD: #channel-name**`

Discord line breaks and blank lines are preserved exactly through translation.
Every automatic publication ends with:
`#autopost@lapbase`

## GitHub publish

На Windows используется `publish.bat`. Скрипт следует GitHub Publish Contract:

- при открытии сначала выполняет read-only preflight;
- проверяет Git, GitHub CLI `gh`, Git identity, GitHub auth, repository/branch/upstream/remote и conflicts;
- проверяет `.gitignore` и sensitive files;
- показывает exact change inventory до staging;
- поддерживает меню `diagnose`, `init/connect`, `commit+push`, `GitHub Release`;
- поддерживает `publish.bat --check` и `publish.bat --dry-run`;
- не устанавливает prerequisites глобально, не использует force push, hard reset или автоматический rebase;
- commit/push/tag/release выполняются только после отдельного подтверждения;
- после успешной публикации сохраняет receipt в `.portable/state/publish/`.

Для работы `publish.bat` должны быть заранее установлены и настроены Git и GitHub CLI.
