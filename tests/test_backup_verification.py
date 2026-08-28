from __future__ import annotations

import gzip
import json

import pytest

from app.services.backup import BACKUP_FORMAT, BackupService, REQUIRED_TABLES


def _write(path, payload):
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)


def test_backup_verification_accepts_complete_payload(tmp_path):
    path = tmp_path / "ok.json.gz"
    _write(path, {"format": BACKUP_FORMAT, "tables": {name: [] for name in REQUIRED_TABLES}})
    BackupService.verify_backup(path)


def test_backup_verification_rejects_missing_table(tmp_path):
    path = tmp_path / "bad.json.gz"
    tables = {name: [] for name in REQUIRED_TABLES if name != "posts"}
    _write(path, {"format": BACKUP_FORMAT, "tables": tables})
    with pytest.raises(RuntimeError):
        BackupService.verify_backup(path)
