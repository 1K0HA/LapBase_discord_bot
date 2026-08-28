from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_manifest_is_exact_and_project_local():
    manifest = (ROOT / ".1kds/runtime.env").read_text(encoding="utf-8")
    assert "UV_VERSION=0.12.2" in manifest
    assert "PYTHON_VERSION=3.14.7" in manifest
    assert "UV_WINDOWS_X64_SHA256=" in manifest
    assert "UV_LINUX_X64_SHA256=" in manifest
    assert "UV_LINUX_ARM64_SHA256=" in manifest


def test_launchers_do_not_use_system_python_or_pip():
    bat = (ROOT / "start.bat").read_text(encoding="utf-8").lower()
    sh = (ROOT / "start.sh").read_text(encoding="utf-8").lower()

    forbidden = ["where python", "where pip", "command -v python", "command -v pip", "py -3", "pip install"]
    for token in forbidden:
        assert token not in bat
        assert token not in sh

    assert "uv_python_install_dir" in bat
    assert "uv_python_install_dir" in sh
    assert ".venv" in bat
    assert ".venv" in sh


def test_dependency_manifest_has_single_source_of_truth():
    assert (ROOT / "pyproject.toml").exists()
    assert not (ROOT / "requirements.txt").exists()


def test_line_endings_policy_preserves_platform_scripts():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.bat text eol=crlf" in attrs
    assert "*.sh text eol=lf" in attrs


def test_runtime_and_state_are_git_ignored():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for expected in [".env", ".venv/", ".runtime/", ".1kds/state/"]:
        assert expected in ignore



def test_uv_0122_official_artifact_hashes_are_pinned():
    manifest = (ROOT / ".1kds/runtime.env").read_text(encoding="utf-8")
    assert "UV_WINDOWS_X64_SHA256=01442d8ce5c7124151a73e697c836d252c6da853c18c73206d3cc4c2378a91d2" in manifest
    assert "UV_LINUX_X64_SHA256=d66e96b5f1ca3b99806eee283a8125d33a0bd669e6e6d9bc4ab7ffda63c41bf4" in manifest
    assert "UV_LINUX_ARM64_SHA256=19b7f1f66895261fbaa07f8ea91da0f86337ad4e47efa594e87641c1718ffc52" in manifest


def test_launchers_show_bootstrap_log_tail_on_failure():
    bat = (ROOT / "start.bat").read_text(encoding="utf-8")
    sh = (ROOT / "start.sh").read_text(encoding="utf-8")
    assert "Последние строки bootstrap.log" in bat
    assert "Get-Content -LiteralPath" in bat
    assert "Последние строки bootstrap.log" in sh
    assert "tail -n 20" in sh



def test_windows_python_find_does_not_use_for_f_command_substitution():
    bat = (ROOT / "start.bat").read_text(encoding="utf-8").lower()
    python_find_lines = [line for line in bat.splitlines() if "python find" in line]
    assert python_find_lines
    assert all("for /f" not in line for line in python_find_lines)
    assert 'set "python_path_file=%state_dir%\\python-path.tmp"' in bat
    assert 'set /p "python_exe="<"%python_path_file%"' in bat


def test_python_install_has_no_external_bin_or_registry_side_effects():
    bat = (ROOT / "start.bat").read_text(encoding="utf-8").lower()
    sh = (ROOT / "start.sh").read_text(encoding="utf-8").lower()

    for text in (bat, sh):
        assert "uv_python_install_bin=0" in text
        assert "uv_python_no_registry=1" in text
        assert "--no-bin" in text
        assert "--no-registry" in text


def test_windows_bootstrap_log_tail_is_read_as_utf8():
    bat = (ROOT / "start.bat").read_text(encoding="utf-8")
    assert "Get-Content -LiteralPath '%BOOT_LOG%' -Encoding UTF8 -Tail 20" in bat



def test_launchers_export_python_utf8_and_show_project_version():
    bat = (ROOT / "start.bat").read_text(encoding="utf-8")
    sh = (ROOT / "start.sh").read_text(encoding="utf-8")
    for text in (bat, sh):
        assert "PYTHONUTF8" in text
        assert "PYTHONIOENCODING" in text
        assert "APP_VERSION" in text
        assert "Кодировка: UTF-8" in text


def test_application_error_is_not_reported_as_bootstrap_failure():
    bat = (ROOT / "start.bat").read_text(encoding="utf-8")
    sh = (ROOT / "start.sh").read_text(encoding="utf-8")
    assert "[ОШИБКА] LapBase завершился с ошибкой." in bat
    assert "[ОШИБКА] LapBase завершился с ошибкой." in sh
