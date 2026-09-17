"""Configuration and sampling logic, kept independent from GTK for testing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import json
import math
import os
from pathlib import Path
import random
import tempfile


APP_DIR_NAME = "pushpushpush"


@dataclass(slots=True)
class Settings:
    interval_minutes: int = 30
    mean_pushups: int = 10
    variance: int = 9
    enabled: bool = True

    def validated(self) -> "Settings":
        return Settings(
            interval_minutes=min(480, max(1, int(self.interval_minutes))),
            mean_pushups=min(500, max(1, int(self.mean_pushups))),
            variance=min(10_000, max(0, int(self.variance))),
            enabled=bool(self.enabled),
        )


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    completed_at: str
    count: int


def daily_pushup_totals(
    entries: list[HistoryEntry],
    days: int = 14,
    end_date: date | None = None,
) -> list[tuple[date, int]]:
    """Return local-calendar-day totals ending on ``end_date`` (today by default)."""
    if days < 1:
        raise ValueError("days must be at least one")

    last_day = end_date or datetime.now().astimezone().date()
    first_day = last_day - timedelta(days=days - 1)
    totals = {first_day + timedelta(days=offset): 0 for offset in range(days)}
    for entry in entries:
        completed_day = datetime.fromisoformat(entry.completed_at).astimezone().date()
        if completed_day in totals:
            totals[completed_day] += entry.count
    return list(totals.items())


def config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_DIR_NAME / "settings.json"


def history_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_DIR_NAME / "history.json"


def load_settings(path: Path | None = None) -> Settings:
    path = path or config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Settings(
            interval_minutes=raw.get("interval_minutes", 30),
            mean_pushups=raw.get("mean_pushups", 10),
            variance=raw.get("variance", 9),
            enabled=raw.get("enabled", True),
        ).validated()
    except (
        AttributeError,
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        OverflowError,
        TypeError,
        ValueError,
    ):
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    """Atomically persist settings so interruption cannot leave invalid JSON."""
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(settings.validated()), indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=".settings-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def load_history(path: Path | None = None) -> list[HistoryEntry]:
    path = path or history_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        entries: list[HistoryEntry] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            timestamp = str(item["completed_at"])
            datetime.fromisoformat(timestamp)
            count = int(item["count"])
            if count >= 1:
                entries.append(HistoryEntry(timestamp, count))
        return entries
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        OSError,
        OverflowError,
        TypeError,
        ValueError,
    ):
        return []


def save_history(entries: list[HistoryEntry], path: Path | None = None) -> None:
    path = path or history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps([asdict(entry) for entry in entries], indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=".history-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def record_completion(
    count: int,
    path: Path | None = None,
    completed_at: datetime | None = None,
) -> HistoryEntry:
    if count < 1:
        raise ValueError("a completed set must contain at least one push-up")
    path = path or history_path()
    instant = completed_at or datetime.now().astimezone()
    entry = HistoryEntry(instant.isoformat(timespec="seconds"), int(count))
    entries = load_history(path)
    entries.append(entry)
    save_history(entries, path)
    return entry


def sample_pushups(settings: Settings, rng: random.Random | None = None) -> int:
    """Sample a whole-number set from N(mean, variance), with a floor of one."""
    rng = rng or random
    settings = settings.validated()
    value = rng.gauss(settings.mean_pushups, math.sqrt(settings.variance))
    return max(1, round(value))
