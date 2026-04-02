"""Additive CSV reporter for OpenCode plugin test outcomes.

Appends test results to a shared CSV file so that multiple runs
(different models, different configurations) accumulate in one place.
"""

import csv
import time
from dataclasses import dataclass, field
from pathlib import Path


RESULTS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "test_results" / "opencode_plugin"
)
DEFAULT_CSV = RESULTS_DIR / "test_outcomes.csv"

CSV_COLUMNS = [
    "timestamp",
    "model",
    "plugin_enabled",
    "test_class",
    "test_name",
    "status",
    "duration_s",
    "tool_calls_count",
    "autobe_calls_count",
    "files_generated",
    "error_message",
    "session_id",
    "work_dir",
    "notes",
]


@dataclass
class OutcomeRecord:
    """Single test outcome record."""

    model: str
    plugin_enabled: bool
    test_class: str
    test_name: str
    status: str  # "pass", "fail", "error", "skip"
    duration_s: float = 0.0
    tool_calls_count: int = 0
    autobe_calls_count: int = 0
    files_generated: int = 0
    error_message: str = ""
    session_id: str = ""
    work_dir: str = ""
    notes: str = ""
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

    def to_row(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "plugin_enabled": str(self.plugin_enabled),
            "test_class": self.test_class,
            "test_name": self.test_name,
            "status": self.status,
            "duration_s": f"{self.duration_s:.2f}",
            "tool_calls_count": str(self.tool_calls_count),
            "autobe_calls_count": str(self.autobe_calls_count),
            "files_generated": str(self.files_generated),
            "error_message": self.error_message,
            "session_id": self.session_id,
            "work_dir": self.work_dir,
            "notes": self.notes,
        }


def append_outcome(outcome: OutcomeRecord, csv_path: Path = DEFAULT_CSV) -> None:
    """Append a single test outcome to the CSV, creating it if needed."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0

    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(outcome.to_row())


def append_outcomes(
    outcomes: list[OutcomeRecord], csv_path: Path = DEFAULT_CSV
) -> None:
    """Append multiple test outcomes."""
    for o in outcomes:
        append_outcome(o, csv_path)


def read_outcomes(csv_path: Path = DEFAULT_CSV) -> list[dict]:
    """Read all outcomes from the CSV."""
    if not csv_path.exists():
        return []
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))
