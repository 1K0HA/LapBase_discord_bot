@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem ============================================================
rem Обертка: всегда оставляет окно открытым после завершения рабочей части.
rem ============================================================
if /I "%~1"=="--core" goto :core_entry

cmd /d /c call "%~f0" --core %*
set "PUBLISH_RC=%ERRORLEVEL%"

echo.
echo ============================================================
echo Работа LapBase GitHub Publisher завершена.
echo Код завершения: %PUBLISH_RC%
echo ============================================================
echo.
pause
exit /b %PUBLISH_RC%


:core_entry
shift
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem Отключаем интерактивные pager'ы Git/GitHub, чтобы BAT не "зависал" на экране less.
set "GIT_PAGER=cat"
set "GH_PAGER=cat"
set "PAGER=cat"
set "LESS=FRX"

set "MODE=interactive"
if /I "%~1"=="--check" set "MODE=check"
if /I "%~1"=="--dry-run" set "MODE=dry-run"

title LapBase - Публикация в GitHub

call :header
call :preflight
set "RC=!ERRORLEVEL!"

if /I "!MODE!"=="check" exit /b !RC!
if /I "!MODE!"=="dry-run" goto :dry_run

if not "!RC!"=="0" (
    echo.
    echo [ИНФО] Предварительная проверка обнаружила блокирующие проблемы.
    echo [ИНФО] Меню остаётся доступным, чтобы можно было исправить настройки.
)

goto :menu


:header
echo ============================================================
echo              LapBase - Публикация в GitHub
echo ============================================================
echo Проект:
echo   %CD%
echo.
echo Безопасность:
echo   - force push запрещён
echo   - hard reset запрещён
echo   - автоматический rebase запрещён
echo   - .env / runtime / venv не публикуются
echo ============================================================
exit /b 0


:menu
echo.
echo ============================================================
echo                          МЕНЮ
echo ============================================================
echo 1. Проверка / диагностика
echo 2. Исправить .gitignore
echo 3. Создать или подключить GitHub-репозиторий
echo 4. Commit и push
echo 5. Создать GitHub Release
echo 6. Выход
echo ============================================================
choice /c 123456 /n /m "Выбор: "
if errorlevel 6 exit /b 0
if errorlevel 5 goto :menu_release
if errorlevel 4 goto :menu_push
if errorlevel 3 goto :menu_setup
if errorlevel 2 goto :menu_repair_ignore
if errorlevel 1 goto :menu_preflight
goto :menu


:menu_preflight
call :preflight
goto :menu


:menu_repair_ignore
call :repair_gitignore
goto :menu


:menu_setup
call :repo_setup
goto :menu


:menu_push
call :commit_push
goto :menu


:menu_release
call :release_flow
goto :menu


:preflight_failed
echo.
echo [BLOCKED] Preflight failed. Fix the items above and run again.
exit /b !RC!


:preflight
set "FAIL=0"
set "IS_REPO=0"
set "HAS_ORIGIN=0"
set "CURRENT_BRANCH="
set "GIT_NAME="
set "GIT_EMAIL="
set "GH_REPO="
set "GH_PERMISSION="

echo.
echo ============================================================
echo ПРЕДВАРИТЕЛЬНАЯ ПРОВЕРКА (ТОЛЬКО ЧТЕНИЕ)
echo ============================================================

where git >nul 2>nul
if errorlevel 1 goto :pf_no_git
for /f "delims=" %%V in ('git --version 2^>nul') do echo [READY] %%V
goto :pf_git_done

:pf_no_git
echo [БЛОКИРОВКА] Git не найден в PATH.
set "FAIL=1"

:pf_git_done
where gh >nul 2>nul
if errorlevel 1 goto :pf_no_gh
for /f "tokens=1,2,3" %%A in ('gh --version 2^>nul ^| findstr /b /c:"gh version"') do echo [READY] GitHub CLI %%C
goto :pf_gh_done

:pf_no_gh
echo [БЛОКИРОВКА] GitHub CLI gh не найден в PATH.
set "FAIL=1"

:pf_gh_done
where git >nul 2>nul
if errorlevel 1 goto :pf_identity_done

for /f "usebackq delims=" %%N in (`git config --get user.name 2^>nul`) do set "GIT_NAME=%%N"
for /f "usebackq delims=" %%E in (`git config --get user.email 2^>nul`) do set "GIT_EMAIL=%%E"

if not defined GIT_NAME goto :pf_no_name
echo [ГОТОВО] Git user.name: !GIT_NAME!
goto :pf_name_done

:pf_no_name
echo [БЛОКИРОВКА] Git user.name не настроен.
set "FAIL=1"

:pf_name_done
if not defined GIT_EMAIL goto :pf_no_email
echo [ГОТОВО] Git user.email: !GIT_EMAIL!
goto :pf_identity_done

:pf_no_email
echo [БЛОКИРОВКА] Git user.email не настроен.
set "FAIL=1"

:pf_identity_done
where gh >nul 2>nul
if errorlevel 1 goto :pf_repo
gh auth status -h github.com >nul 2>nul
if errorlevel 1 goto :pf_no_auth
echo [ГОТОВО] Авторизация GitHub: OK
goto :pf_repo

:pf_no_auth
echo [БЛОКИРОВКА] GitHub CLI не авторизован.
echo           Выполни: gh auth login
set "FAIL=1"

:pf_repo
git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 goto :pf_not_repo

set "IS_REPO=1"
echo [ГОТОВО] Локальный Git-репозиторий найден

for /f "delims=" %%B in ('git symbolic-ref --short -q HEAD 2^>nul') do set "CURRENT_BRANCH=%%B"
if not defined CURRENT_BRANCH goto :pf_detached
echo [ГОТОВО] Текущая ветка: !CURRENT_BRANCH!
goto :pf_conflicts

:pf_detached
echo [БЛОКИРОВКА] Не удалось определить текущую ветку или обнаружен detached HEAD.
set "FAIL=1"
goto :pf_conflicts

:pf_not_repo
echo [ПРЕДУПРЕЖДЕНИЕ] Локальный Git-репозиторий ещё не создан.
goto :pf_project

:pf_conflicts
if exist ".git\MERGE_HEAD" goto :pf_merge
if exist ".git\CHERRY_PICK_HEAD" goto :pf_cherry
if exist ".git\REVERT_HEAD" goto :pf_revert
if exist ".git\rebase-merge" goto :pf_rebase
if exist ".git\rebase-apply" goto :pf_rebase
goto :pf_conflict_files

:pf_merge
echo [БЛОКИРОВКА] Обнаружен незавершённый merge.
set "FAIL=1"
goto :pf_conflict_files

:pf_cherry
echo [БЛОКИРОВКА] Обнаружен незавершённый cherry-pick.
set "FAIL=1"
goto :pf_conflict_files

:pf_revert
echo [БЛОКИРОВКА] Обнаружен незавершённый revert.
set "FAIL=1"
goto :pf_conflict_files

:pf_rebase
echo [БЛОКИРОВКА] Обнаружен незавершённый rebase.
set "FAIL=1"

:pf_conflict_files
set "CONFLICT_FILE="
for /f "delims=" %%C in ('git --no-pager diff --name-only --diff-filter^=U 2^>nul') do set "CONFLICT_FILE=%%C"
if not defined CONFLICT_FILE goto :pf_origin
echo [БЛОКИРОВКА] Неразрешённый конфликт: !CONFLICT_FILE!
set "FAIL=1"

:pf_origin
git remote get-url origin >nul 2>nul
if errorlevel 1 goto :pf_no_origin

set "HAS_ORIGIN=1"
for /f "delims=" %%R in ('git remote get-url origin 2^>nul') do set "ORIGIN_URL=%%R"
echo [ГОТОВО] origin: !ORIGIN_URL!

where gh >nul 2>nul
if errorlevel 1 goto :pf_project
gh auth status -h github.com >nul 2>nul
if errorlevel 1 goto :pf_project

for /f "delims=" %%R in ('gh repo view --json nameWithOwner -q ".nameWithOwner" 2^>nul') do set "GH_REPO=%%R"
for /f "delims=" %%P in ('gh repo view --json viewerPermission -q ".viewerPermission" 2^>nul') do set "GH_PERMISSION=%%P"

if defined GH_REPO echo [ГОТОВО] Репозиторий GitHub: !GH_REPO!
if defined GH_PERMISSION echo [ГОТОВО] Права GitHub: !GH_PERMISSION!
goto :pf_project

:pf_no_origin
echo [ПРЕДУПРЕЖДЕНИЕ] Remote origin не настроен.

:pf_project
if exist ".gitignore" goto :pf_gitignore_ok
echo [БЛОКИРОВКА] Файл .gitignore отсутствует.
set "FAIL=1"
goto :pf_sensitive

:pf_gitignore_ok
echo [ГОТОВО] .gitignore найден

:pf_sensitive
call :check_ignore_rule ".env" ".env"
if errorlevel 1 set "FAIL=1"
call :check_ignore_rule ".venv" ".venv/"
if errorlevel 1 set "FAIL=1"
call :check_ignore_rule ".runtime" ".runtime/"
if errorlevel 1 set "FAIL=1"
call :check_ignore_rule ".portable" ".portable/"
if errorlevel 1 set "FAIL=1"

if not "!IS_REPO!"=="1" goto :pf_inventory

call :check_tracked ".env"
if errorlevel 1 set "FAIL=1"
call :check_tracked "*.pem"
if errorlevel 1 set "FAIL=1"
call :check_tracked "*.key"
if errorlevel 1 set "FAIL=1"
call :check_tracked "*.p12"
if errorlevel 1 set "FAIL=1"
call :check_tracked "*.pfx"
if errorlevel 1 set "FAIL=1"

:pf_inventory
if not "!IS_REPO!"=="1" goto :pf_result
echo.
echo --- Точный список изменений ---
git --no-pager status --short
echo --- Конец списка ---

:pf_result
echo.
if "!FAIL!"=="0" goto :pf_ready
echo ПРОВЕРКА: БЛОКИРОВКА
exit /b 13

:pf_ready
echo ПРОВЕРКА: ГОТОВО
exit /b 0


:check_ignore_rule
set "IGNORE_PATH=%~1"
set "IGNORE_RULE=%~2"

rem First validate the project policy directly from .gitignore.
rem This works even before git init, keeping preflight read-only.
findstr /x /l /c:"!IGNORE_RULE!" ".gitignore" >nul 2>nul
if errorlevel 1 goto :cir_missing_rule

rem If the path does not exist yet, the rule itself is sufficient.
if not exist "!IGNORE_PATH!" goto :cir_rule_ok

rem Before git init, git check-ignore has no repository context.
if not "!IS_REPO!"=="1" goto :cir_rule_ok

rem Once a repository exists, verify that Git resolves the rule as expected.
git check-ignore -q -- "!IGNORE_PATH!" >nul 2>nul
if errorlevel 1 goto :cir_git_mismatch

:cir_rule_ok
echo [ГОТОВО] Проверка ignore: !IGNORE_PATH! ^(!IGNORE_RULE!^)
exit /b 0

:cir_missing_rule
echo [БЛОКИРОВКА] В .gitignore отсутствует правило: !IGNORE_RULE!
exit /b 1

:cir_git_mismatch
echo [БЛОКИРОВКА] Git не игнорирует !IGNORE_PATH! хотя правило !IGNORE_RULE! существует.
exit /b 1


:check_tracked
set "TRACKED_BAD="
for /f "delims=" %%F in ('git ls-files "%~1" 2^>nul') do set "TRACKED_BAD=%%F"
if not defined TRACKED_BAD exit /b 0
if /I "!TRACKED_BAD!"==".env.example" exit /b 0
echo [БЛОКИРОВКА] Git уже отслеживает чувствительный файл: !TRACKED_BAD!
exit /b 1


:dry_run
echo.
echo ============================================================
echo DRY-RUN
echo ============================================================
echo Файлы Git, refs, настройки репозитория и объекты GitHub не изменялись.
echo.
echo Планируемый процесс:
echo   1. Предварительная проверка только для чтения.
echo   2. Проверка точного списка изменений.
echo   3. Подтверждение staging.
echo   4. Проверка staged-файлов.
echo   5. Подтверждение commit.
echo   6. Fetch и проверка расхождений.
echo   7. Подтверждение push.
echo   8. Проверка SHA commit на GitHub.
echo ============================================================
exit /b 0


:repair_gitignore
echo.
echo ============================================================
echo ИСПРАВЛЕНИЕ .GITIGNORE
echo ============================================================
echo Это действие только добавляет отсутствующие защитные правила в .gitignore.
echo Оно не выполняет git init, staging, commit или push.
echo.
echo Необходимые правила:
echo   .env
echo   .venv/
echo   .runtime/
echo   .portable/
echo   dist/
echo.
set "ANSWER="
set /p "ANSWER=Введи YES, чтобы добавить отсутствующие правила: "
if /I not "!ANSWER!"=="YES" (
    echo [ОТМЕНЕНО] .gitignore не изменён.
    exit /b 0
)

if not exist ".gitignore" (
    type nul > ".gitignore"
)

call :append_ignore_rule ".env"
call :append_ignore_rule ".venv/"
call :append_ignore_rule ".runtime/"
call :append_ignore_rule ".portable/"
call :append_ignore_rule "dist/"

echo.
echo [OK] Защитные правила .gitignore добавлены.
echo.
type ".gitignore"
exit /b 0


:append_ignore_rule
set "RULE=%~1"
findstr /x /l /c:"!RULE!" ".gitignore" >nul 2>nul
if not errorlevel 1 exit /b 0
>>".gitignore" echo !RULE!
exit /b 0


:repo_setup
call :preflight
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" goto :setup_preflight_failed

if "!IS_REPO!"=="1" goto :setup_repo_exists

echo.
echo ПЛАН: создать локальный Git-репозиторий в:
echo   %CD%
set "ANSWER="
set /p "ANSWER=Введи YES, чтобы выполнить git init: "
if /I not "!ANSWER!"=="YES" exit /b 0

git init
if errorlevel 1 goto :setup_git_init_failed

set "NEW_BRANCH="
set /p "NEW_BRANCH=Имя основной ветки [main]: "
if not defined NEW_BRANCH set "NEW_BRANCH=main"

git branch -M "!NEW_BRANCH!"
if errorlevel 1 goto :setup_branch_failed
echo [OK] Локальный репозиторий создан.
goto :setup_remote

:setup_repo_exists
echo [READY] Local repository already существует.

:setup_remote
git remote get-url origin >nul 2>nul
if not errorlevel 1 goto :setup_origin_exists

echo.
echo 1. Подключить существующий GitHub-репозиторий
echo 2. Создать новый GitHub-репозиторий через gh
echo 3. Отмена
choice /c 123 /n /m "Выбор: "
if errorlevel 3 exit /b 0
if errorlevel 2 goto :setup_create_gh
if errorlevel 1 goto :setup_connect_existing
exit /b 0

:setup_connect_existing
set "REMOTE_URL="
set /p "REMOTE_URL=URL GitHub-репозитория: "
if not defined REMOTE_URL exit /b 20

echo Будет добавлен remote:
echo   origin = !REMOTE_URL!
set "ANSWER="
set /p "ANSWER=Введи YES, чтобы добавить origin: "
if /I not "!ANSWER!"=="YES" exit /b 0

git remote add origin "!REMOTE_URL!"
if errorlevel 1 goto :setup_remote_failed
echo [OK] origin добавлен.
exit /b 0

:setup_create_gh
where gh >nul 2>nul
if errorlevel 1 goto :setup_no_gh
gh auth status -h github.com >nul 2>nul
if errorlevel 1 goto :setup_no_auth

set "REPO_NAME="
set /p "REPO_NAME=Название репозитория: "
if not defined REPO_NAME exit /b 20

echo 1. private
echo 2. public
choice /c 12 /n /m "Видимость: "
if errorlevel 2 set "VISIBILITY=public"
if errorlevel 1 set "VISIBILITY=private"

echo.
echo ПЛАН:
echo   репозиторий: !REPO_NAME!
echo   видимость: !VISIBILITY!
echo   remote: origin
set "ANSWER="
set /p "ANSWER=Type YES to create GitHub репозиторий: "
if /I not "!ANSWER!"=="YES" exit /b 0

gh repo create "!REPO_NAME!" --"!VISIBILITY!" --source "." --remote origin
if errorlevel 1 goto :setup_gh_create_failed

echo [OK] GitHub-репозиторий создан.
exit /b 0

:setup_origin_exists
echo [ГОТОВО] origin уже существует:
git remote get-url origin
exit /b 0

:setup_preflight_failed
echo [БЛОКИРОВКА] Настройка заблокирована предварительной проверкой.
echo [ИНФО] Если проблема в .gitignore, сначала используй пункт меню 2.
exit /b !RC!

:setup_git_init_failed
echo [ОШИБКА] git init завершился ошибкой.
exit /b 20

:setup_branch_failed
echo [ОШИБКА] Не удалось установить ветку.
exit /b 20

:setup_remote_failed
echo [ОШИБКА] Не удалось добавить origin.
exit /b 20

:setup_no_gh
echo [ОШИБКА] GitHub CLI gh отсутствует.
exit /b 10

:setup_no_auth
echo [ОШИБКА] GitHub CLI не авторизован.
exit /b 12

:setup_gh_create_failed
echo [ОШИБКА] gh repo create завершился ошибкой.
exit /b 20


:commit_push
call :preflight
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" goto :push_preflight_failed
if not "!IS_REPO!"=="1" goto :push_no_repo
if not "!HAS_ORIGIN!"=="1" goto :push_no_origin

set "HAS_CHANGES="
for /f "delims=" %%S in ('git status --porcelain --untracked-files^=all 2^>nul') do set "HAS_CHANGES=1"

if defined HAS_CHANGES goto :push_review_changes
echo [ИНФО] Локальных изменений для commit нет.
goto :push_sync_only

:push_review_changes
echo.
echo ============================================================
echo ПРОВЕРКА ИЗМЕНЕНИЙ
echo ============================================================
git --no-pager status --short
echo ============================================================

call :working_sensitive_gate
if errorlevel 1 exit /b 14

set "COMMIT_MSG="
set /p "COMMIT_MSG=Сообщение Conventional Commit: "
if not defined COMMIT_MSG goto :push_no_message

call :validate_commit "!COMMIT_MSG!"
if errorlevel 1 goto :push_bad_message

echo.
echo ПЛАН:
echo   добавить в staging все показанные изменения
echo   commit: !COMMIT_MSG!
echo   ветка: !CURRENT_BRANCH!
echo   remote: origin
set "ANSWER="
set /p "ANSWER=Введи YES, чтобы добавить изменения в staging: "
if /I not "!ANSWER!"=="YES" exit /b 0

git add -A
if errorlevel 1 goto :push_stage_failed

call :staged_sensitive_gate
if errorlevel 1 exit /b 14

echo.
echo ============================================================
echo СПИСОК STAGED-ФАЙЛОВ
echo ============================================================
git --no-pager diff --cached --name-status
echo ============================================================
set "ANSWER="
set /p "ANSWER=Введи YES, чтобы создать commit: "
if /I not "!ANSWER!"=="YES" exit /b 0

git commit -m "!COMMIT_MSG!"
if errorlevel 1 goto :push_commit_failed

:push_sync_only
for /f "delims=" %%H in ('git rev-parse HEAD 2^>nul') do set "LOCAL_SHA=%%H"
if not defined LOCAL_SHA goto :push_no_head

git ls-remote --exit-code --heads origin "refs/heads/!CURRENT_BRANCH!" >nul 2>nul
if errorlevel 1 goto :push_first

echo.
echo Для проверки синхронизации требуется git fetch origin !CURRENT_BRANCH!.
set "ANSWER="
set /p "ANSWER=Введи YES, чтобы выполнить fetch и сравнение: "
if /I not "!ANSWER!"=="YES" exit /b 0

git fetch origin "!CURRENT_BRANCH!"
if errorlevel 1 goto :push_fetch_failed

set "AHEAD=0"
set "BEHIND=0"
for /f "tokens=1,2" %%A in ('git rev-list --left-right --count HEAD...FETCH_HEAD') do set "AHEAD=%%A" & set "BEHIND=%%B"

echo [ИНФО] Локальная ветка впереди на: !AHEAD!
echo [ИНФО] Локальная ветка отстаёт на: !BEHIND!
if not "!BEHIND!"=="0" goto :push_diverged
goto :push_confirm

:push_first
echo [ИНФО] Удалённая ветка ещё не существует. Это будет первый push.

:push_confirm
echo.
echo ============================================================
echo ПЛАН PUSH
echo ============================================================
echo Ветка: !CURRENT_BRANCH!
echo Commit: !LOCAL_SHA!
echo Remote: origin
echo Force: НЕТ
echo ============================================================
set "ANSWER="
set /p "ANSWER=Введи YES, чтобы выполнить push: "
if /I not "!ANSWER!"=="YES" exit /b 0

git rev-parse --abbrev-ref --symbolic-full-name @{u} >nul 2>nul
if errorlevel 1 goto :push_with_upstream

git push origin "!CURRENT_BRANCH!"
if errorlevel 1 goto :push_failed
goto :push_verify

:push_with_upstream
git push -u origin "!CURRENT_BRANCH!"
if errorlevel 1 goto :push_failed

:push_verify
set "REMOTE_SHA="
for /f "tokens=1" %%H in ('git ls-remote origin "refs/heads/!CURRENT_BRANCH!" 2^>nul') do set "REMOTE_SHA=%%H"

if /I not "!REMOTE_SHA!"=="!LOCAL_SHA!" goto :push_verify_failed

echo [OK] Push подтверждён.
echo [OK] Удалённый SHA: !REMOTE_SHA!
exit /b 0

:push_preflight_failed
echo [БЛОКИРОВКА] Commit/push заблокирован предварительной проверкой.
exit /b !RC!

:push_no_repo
echo [ОШИБКА] Локальный Git-репозиторий отсутствует.
exit /b 13

:push_no_origin
echo [ОШИБКА] Remote origin отсутствует.
exit /b 13

:push_no_message
echo [ОШИБКА] Сообщение commit обязательно.
exit /b 31

:push_bad_message
echo [ОШИБКА] Используй Conventional Commit, например:
echo         fix: preserve Telegram line breaks
exit /b 31

:push_stage_failed
echo [ОШИБКА] git add завершился ошибкой.
exit /b 30

:push_commit_failed
echo [ОШИБКА] git commit завершился ошибкой.
exit /b 31

:push_no_head
echo [ОШИБКА] HEAD commit отсутствует.
exit /b 41

:push_fetch_failed
echo [ОШИБКА] git fetch завершился ошибкой.
exit /b 40

:push_diverged
echo [БЛОКИРОВКА] На GitHub есть commit, которых нет локально.
echo Автоматический rebase, reset и force push выполняться не будут.
exit /b 40

:push_failed
echo [ОШИБКА] git push завершился ошибкой.
exit /b 41

:push_verify_failed
echo [ОШИБКА] Проверка удалённого SHA не пройдена.
exit /b 42


:working_sensitive_gate
set "BAD_PATH="
for /f "delims=" %%S in ('git status --porcelain --untracked-files^=all -- ".env" "*.pem" "*.key" "*.p12" "*.pfx" ".venv" ".runtime" ".portable" 2^>nul') do set "BAD_PATH=%%S"
if not defined BAD_PATH goto :wsg_ok
echo [БЛОКИРОВКА] В списке изменений найден чувствительный/runtime путь:
echo   !BAD_PATH!
exit /b 1

:wsg_ok
echo [ГОТОВО] Проверка чувствительных данных пройдена.
exit /b 0


:staged_sensitive_gate
set "BAD_STAGED="
for /f "delims=" %%S in ('git --no-pager diff --cached --name-only -- ".env" "*.pem" "*.key" "*.p12" "*.pfx" ".venv" ".runtime" ".portable" 2^>nul') do set "BAD_STAGED=%%S"
if not defined BAD_STAGED exit /b 0
echo [БЛОКИРОВКА] В staging найден чувствительный файл:
echo   !BAD_STAGED!
exit /b 1


:validate_commit
set "MSG=%~1"
echo(!MSG!| findstr /r /i /c:"^feat:" /c:"^fix:" /c:"^refactor:" /c:"^test:" /c:"^docs:" /c:"^build:" /c:"^chore:" /c:"^perf:" /c:"^ci:" /c:"^style:" /c:"^revert:" >nul 2>nul
exit /b !ERRORLEVEL!


:release_flow
call :preflight
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" goto :release_preflight_failed
if not "!IS_REPO!"=="1" goto :release_no_repo
if not "!HAS_ORIGIN!"=="1" goto :release_no_origin

set "DIRTY="
for /f "delims=" %%S in ('git status --porcelain 2^>nul') do set "DIRTY=1"
if defined DIRTY goto :release_dirty

if not exist "pyproject.toml" goto :release_no_version

set "VERSION="
for /f "usebackq delims=" %%V in (`powershell -NoProfile -Command "$m=Select-String -Path 'pyproject.toml' -Pattern '^\s*version\s*=\s*\"([^\"]+)\"' | Select-Object -First 1; if($m){$m.Matches[0].Groups[1].Value}" 2^>nul`) do set "VERSION=%%V"
if not defined VERSION goto :release_no_version

set "TAG=v!VERSION!"
echo.
echo Версия Release: !VERSION!
echo Tag: !TAG!

git tag --list "!TAG!" | findstr /x /c:"!TAG!" >nul
if not errorlevel 1 goto :release_tag_exists

git ls-remote --exit-code --tags origin "refs/tags/!TAG!" >nul 2>nul
if not errorlevel 1 goto :release_tag_exists

if not exist ".venv\Scripts\python.exe" goto :release_no_venv

echo [ПРОВЕРКА] pytest...
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 goto :release_tests_failed

echo [ПРОВЕРКА] compileall...
".venv\Scripts\python.exe" -m compileall -q app
if errorlevel 1 goto :release_compile_failed

for /f "delims=" %%H in ('git rev-parse HEAD') do set "RELEASE_SHA=%%H"

echo.
echo ПЛАН:
echo   tag: !TAG!
echo   commit: !RELEASE_SHA!
echo   создать GitHub Release после проверки tag
set "ANSWER="
set /p "ANSWER=Введи YES, чтобы создать и отправить tag: "
if /I not "!ANSWER!"=="YES" exit /b 0

git tag -a "!TAG!" "!RELEASE_SHA!" -m "Release !TAG!"
if errorlevel 1 goto :release_tag_failed

git push origin "!TAG!"
if errorlevel 1 goto :release_tag_push_failed

set "REMOTE_TAG_SHA="
for /f "tokens=1" %%H in ('git ls-remote origin "refs/tags/!TAG!^{}" 2^>nul') do set "REMOTE_TAG_SHA=%%H"
if not defined REMOTE_TAG_SHA for /f "tokens=1" %%H in ('git ls-remote origin "refs/tags/!TAG!" 2^>nul') do set "REMOTE_TAG_SHA=%%H"

if /I not "!REMOTE_TAG_SHA!"=="!RELEASE_SHA!" goto :release_tag_verify_failed

if not exist "dist" mkdir "dist"
set "ARTIFACT=dist\LapBase_!TAG!.zip"

powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $root=(Get-Location).Path; $tmp=Join-Path $env:TEMP ('lapbase_release_'+[guid]::NewGuid()); $dst=Join-Path $tmp 'LapBase'; New-Item -ItemType Directory -Path $dst -Force|Out-Null; $deny=@('.git','.env','.venv','.runtime','.portable','dist','logs','backups','__pycache__','.pytest_cache'); Get-ChildItem -Force $root|Where-Object{$deny -notcontains $_.Name}|ForEach-Object{Copy-Item $_.FullName -Destination $dst -Recurse -Force}; Compress-Archive -Path $dst -DestinationPath '!ARTIFACT!' -Force; Remove-Item $tmp -Recurse -Force"
if errorlevel 1 goto :release_artifact_failed

echo.
echo Артефакт:
echo   !ARTIFACT!
set "ANSWER="
set /p "ANSWER=Введи YES, чтобы создать GitHub Release: "
if /I not "!ANSWER!"=="YES" exit /b 0

gh release create "!TAG!" "!ARTIFACT!" --verify-tag --fail-on-no-commits --title "!TAG!" --generate-notes
if errorlevel 1 goto :release_create_failed

gh release view "!TAG!" --web >nul 2>nul
echo [OK] GitHub Release создан.
exit /b 0

:release_preflight_failed
echo [БЛОКИРОВКА] Release заблокирован предварительной проверкой.
exit /b !RC!

:release_no_repo
echo [ERROR] Local repository is missing.
exit /b 13

:release_no_origin
echo [ERROR] origin is missing.
exit /b 13

:release_dirty
echo [БЛОКИРОВКА] Перед Release рабочее дерево должно быть чистым.
exit /b 50

:release_no_version
echo [ОШИБКА] Версия не найдена в pyproject.toml.
exit /b 50

:release_tag_exists
echo [БЛОКИРОВКА] Tag !TAG! already существует.
exit /b 60

:release_no_venv
echo [ОШИБКА] .venv отсутствует. Сначала запусти start.bat.
exit /b 50

:release_tests_failed
echo [ОШИБКА] pytest завершился ошибкой.
exit /b 50

:release_compile_failed
echo [ОШИБКА] compileall завершился ошибкой.
exit /b 50

:release_tag_failed
echo [ОШИБКА] git tag завершился ошибкой.
exit /b 60

:release_tag_push_failed
echo [ОШИБКА] push tag завершился ошибкой.
exit /b 60

:release_tag_verify_failed
echo [ОШИБКА] Проверка удалённого tag не пройдена.
exit /b 60

:release_artifact_failed
echo [ОШИБКА] Не удалось создать ZIP для Release.
exit /b 50

:release_create_failed
echo [ОШИБКА] gh release create завершился ошибкой.
exit /b 60
