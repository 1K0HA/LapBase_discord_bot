from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_treats_discord_and_worker_health_independently():
    source = (ROOT / "app/runtime.py").read_text(encoding="utf-8")

    assert "def worker_operational" in source
    assert "def core_healthy" in source
    assert "self.discord_connected and self.worker_operational" in source
    assert "if self.discord_connected and self.discord is not None:" in source
    assert "await self._ensure_worker(mode)" in source


def test_restart_uses_safe_stop_then_fresh_start():
    source = (ROOT / "app/runtime.py").read_text(encoding="utf-8")

    restart = source.split("async def restart", 1)[1].split(
        "async def sync_now", 1
    )[0]
    assert "await self.stop_core()" in restart
    assert 'await self.repo.set_mode("running")' in restart
    assert "await self.start_core(sync=True)" in restart


def test_health_exposes_worker_failed_state_and_error():
    source = (ROOT / "app/telegram/admin.py").read_text(encoding="utf-8")

    assert "Queue worker: {runtime.worker_state.value}" in source
    assert "runtime.worker_last_failure" in source
    assert "Worker error:" in source
    assert "runtime.core_healthy" in source
