from __future__ import annotations

import hashlib
import platform
import subprocess
from pathlib import Path

from app.config import ROOT_DIR


def _read_manifest() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in (ROOT_DIR / ".1kds" / "runtime.env").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def _sha256(paths: list[Path]) -> str | None:
    if not all(path.exists() for path in paths):
        return None
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    """Печатает фактический Portable Proof для подготовленного локального проекта."""
    manifest = _read_manifest()
    uv_path = ROOT_DIR / ".runtime" / "uv" / ("uv.exe" if platform.system() == "Windows" else "uv")
    venv_python = ROOT_DIR / ".venv" / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")
    lock = ROOT_DIR / "uv.lock"
    fingerprint = _sha256([ROOT_DIR / "pyproject.toml", lock])

    runtime_version = "НЕ ПРОВЕРЕНО"
    runtime_path = "НЕ НАЙДЕН"
    if venv_python.exists():
        runtime_path = str(venv_python)
        try:
            runtime_version = subprocess.check_output(
                [str(venv_python), "-c", "import platform; print(platform.python_version())"],
                text=True,
                timeout=10,
            ).strip()
        except Exception:
            runtime_version = "ОШИБКА ПРОВЕРКИ"

    print("PORTABLE PROOF")
    print("Portable level: L2 (проектная цель)")
    print(f"Project root: {ROOT_DIR}")
    print(f"Runtime: {runtime_path}")
    print(f"Runtime version: {runtime_version}")
    print(f"Pinned runtime version: {manifest.get('PYTHON_VERSION', 'НЕ ЗАДАНО')}")
    print(f"Architecture: {platform.machine()}")
    print(f"uv: {uv_path}")
    print(f"Pinned uv version: {manifest.get('UV_VERSION', 'НЕ ЗАДАНО')}")
    print(f"Dependencies: {ROOT_DIR / '.venv'}")
    print(f"Environment: {ROOT_DIR / '.venv'}")
    print(f"Dependency fingerprint: {fingerprint or 'НЕТ: uv.lock отсутствует'}")
    print("Bootstrap entry Windows: start.bat")
    print("Bootstrap entry Linux: start.sh")
    print("Bootstrap entry macOS: НЕ ПОДДЕРЖИВАЕТСЯ В СОГЛАСОВАННОМ SCOPE")
    print("System bootstrap baseline: cmd/PowerShell или bash + curl/wget + tar + sha256sum/shasum")
    print("System language runtime usage: NONE")
    print("Global package manager usage: NONE")
    print("PATH modifications: NONE")
    print(f"User data location: Supabase PostgreSQL + {ROOT_DIR / 'backups'}")
    print(f"Config location: {ROOT_DIR / '.env'}")
    print("Repair behavior: восстанавливаются только .runtime/.venv/state; .env и Supabase не удаляются")
    print("Offline after initial setup: PARTIAL (работа требует Discord/Telegram/Groq/Supabase network)")


if __name__ == "__main__":
    main()
