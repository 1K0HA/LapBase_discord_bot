from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bat_and_sh_show_same_version_source_and_utf8_contract():
    bat = (ROOT / "start.bat").read_text(encoding="utf-8")
    sh = (ROOT / "start.sh").read_text(encoding="utf-8")

    for text in (bat, sh):
        assert "APP_VERSION" in text
        assert "pyproject.toml" in text
        assert "PYTHONUTF8" in text
        assert "PYTHONIOENCODING" in text
        assert "PYTHONUNBUFFERED" in text
        assert "LapBase v" in text
        assert "Portable L2" in text
        assert "Кодировка: UTF-8" in text

    assert "Windows x64" in bat
    assert "Linux x86_64" in sh
    assert "Linux arm64" in sh


def test_bat_and_sh_distinguish_bootstrap_and_application_errors():
    bat = (ROOT / "start.bat").read_text(encoding="utf-8")
    sh = (ROOT / "start.sh").read_text(encoding="utf-8")

    assert ":BOOT_FAIL" in bat
    assert ":APP_FAIL" in bat
    assert "Не удалось подготовить LapBase" in bat
    assert "LapBase завершился с ошибкой" in bat

    assert "bootstrap_fail()" in sh
    assert "application_fail()" in sh
    assert "Не удалось подготовить LapBase" in sh
    assert "LapBase завершился с ошибкой" in sh


def test_duplicate_instance_exit_is_handled_on_both_platforms():
    bat = (ROOT / "start.bat").read_text(encoding="utf-8")
    sh = (ROOT / "start.sh").read_text(encoding="utf-8")
    service = (ROOT / "deploy/lapbase.service").read_text(encoding="utf-8")

    assert '"%APP_EXIT%"=="73"' in bat
    assert '[ "$code" -eq 73 ]' in sh
    assert "RestartPreventExitStatus=73" in service


def test_version_has_no_second_hardcoded_source():
    init = (ROOT / "app/__init__.py").read_text(encoding="utf-8")
    version = (ROOT / "app/version.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '__version__ = "1.0.0"' not in init
    assert "pyproject.toml" in version
    assert 'version = "1.0.28"' in pyproject


def test_publish_bat_shows_project_version_and_utf8():
    source = (ROOT / "publish.bat").read_text(encoding="utf-8")
    assert "LapBase v!APP_VERSION!" in source
    assert "pyproject.toml" in source
    assert "PYTHONUTF8=1" in source
    assert "UTF-8" in source
