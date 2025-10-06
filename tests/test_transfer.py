from __future__ import annotations

import pytest

from email_transferrer.config import AppConfig, DestinationConfig, SourceConfig
from email_transferrer.state import StateStore
from email_transferrer.transfer import EmailTransferrer, TransferResult


class FakeTime:
    def __init__(self) -> None:
        self.current = 0.0

    def monotonic(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds

    def sleep(self, seconds: float) -> None:  # pragma: no cover - helper for completeness
        self.advance(seconds)


@pytest.fixture
def fake_time(monkeypatch: pytest.MonkeyPatch) -> FakeTime:
    from email_transferrer import transfer as transfer_module

    fake = FakeTime()
    monkeypatch.setattr(transfer_module, "time", fake)
    return fake


@pytest.fixture
def sample_config(tmp_path) -> AppConfig:
    destination = DestinationConfig(
        host="dest.example.com",
        port=993,
        username="dest",
        password="secret",
        folder="INBOX",
    )

    source_fast = SourceConfig(
        name="fast",
        protocol="imap",
        host="imap.fast.example.com",
        port=993,
        username="fast_user",
        password="fast_pass",
        destination=destination,
        poll_interval=120,
    )

    source_slow = SourceConfig(
        name="slow",
        protocol="imap",
        host="imap.slow.example.com",
        port=993,
        username="slow_user",
        password="slow_pass",
        destination=destination,
        poll_interval=None,
    )

    return AppConfig(
        sources=[source_fast, source_slow],
        poll_interval_seconds=300,
        state_file=tmp_path / "state.json",
    )


@pytest.fixture
def transferrer(sample_config: AppConfig, fake_time: FakeTime) -> EmailTransferrer:
    state = StateStore(sample_config.state_file)
    transfer = EmailTransferrer(sample_config, state)
    return transfer


def test_run_once_respects_per_source_intervals(monkeypatch: pytest.MonkeyPatch, transferrer: EmailTransferrer, fake_time: FakeTime) -> None:
    calls: list[str] = []

    def fake_process(self, source: SourceConfig) -> TransferResult:
        calls.append(source.name)
        return TransferResult(source=source.name, transferred=1, deleted=0)

    monkeypatch.setattr(EmailTransferrer, "_process_imap_source", fake_process)

    # Initial run should process all sources immediately.
    results = transferrer.run_once()
    assert sorted(result.source for result in results) == ["fast", "slow"]
    assert calls == ["fast", "slow"]

    calls.clear()

    # Without advancing time nothing should run again.
    assert transferrer.run_once() == []
    assert calls == []

    # Advance time past the fast interval but not the slow/global interval.
    fake_time.advance(150)
    results = transferrer.run_once()
    assert [result.source for result in results] == ["fast"]
    assert calls == ["fast"]

    calls.clear()

    # Advance to a point where both sources are due again.
    fake_time.advance(150)
    results = transferrer.run_once()
    assert sorted(result.source for result in results) == ["fast", "slow"]
    assert calls == ["fast", "slow"]


def test_time_until_next_run_uses_earliest_schedule(transferrer: EmailTransferrer, fake_time: FakeTime) -> None:
    # After first run, next run times should be scheduled.
    transferrer.run_once()

    wait = transferrer._time_until_next_run()
    assert wait == pytest.approx(120)

    fake_time.advance(100)
    wait = transferrer._time_until_next_run()
    assert wait == pytest.approx(20)

    fake_time.advance(25)
    wait = transferrer._time_until_next_run()
    assert wait == pytest.approx(0)
