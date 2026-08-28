from __future__ import annotations

from functools import lru_cache
import tomllib

from app.config import ROOT_DIR


@lru_cache(maxsize=1)
def get_version() -> str:
    """Возвращает версию приложения из единственного источника — pyproject.toml."""
    with (ROOT_DIR / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    return str(project["version"])
