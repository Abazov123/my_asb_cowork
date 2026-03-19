"""Reflection service — weekly reflection state management.

Manages the "pending reflection" lifecycle:
  1. weekly.py writes a flag file after sending the digest
  2. Bot voice/text handlers append user messages to reflection.md
  3. /done or Monday 09:00 timer triggers finalization
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_PENDING_FILENAME = "{week}-reflection-pending.json"
_REFLECTION_FILENAME = "{week}-reflection.md"


class ReflectionService:
    """Service for managing weekly reflection state."""

    def __init__(self, vault_path: Path | str) -> None:
        self.summaries_dir = Path(vault_path) / "summaries"
        self.summaries_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Flag file helpers
    # ------------------------------------------------------------------

    def _flag_path(self, week: str) -> Path:
        return self.summaries_dir / _PENDING_FILENAME.format(week=week)

    def _reflection_path(self, week: str) -> Path:
        return self.summaries_dir / _REFLECTION_FILENAME.format(week=week)

    def _summary_path(self, week: str) -> Path:
        return self.summaries_dir / f"{week}-summary.md"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, week: str, deadline: datetime) -> None:
        """Create flag file to mark reflection as pending.

        Args:
            week: ISO week string like "2026-W09"
            deadline: When to auto-finalize (typically Monday 09:00)
        """
        flag = {
            "week": week,
            "deadline": deadline.isoformat(),
            "started": datetime.now().astimezone().isoformat(),
        }
        self._flag_path(week).write_text(
            json.dumps(flag, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # Create empty reflection file
        refl = self._reflection_path(week)
        if not refl.exists():
            refl.write_text(
                f"# Рефлексия недели {week}\n\n", encoding="utf-8"
            )
        logger.info("Reflection started for week %s, deadline %s", week, deadline)

    def get_pending_week(self) -> str | None:
        """Return the current pending week ID, or None if no reflection is pending."""
        for path in self.summaries_dir.glob("*-reflection-pending.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                week = data.get("week", "")
                if week:
                    return week
            except Exception:
                continue
        return None

    def is_expired(self, week: str) -> bool:
        """Return True if the reflection deadline has passed."""
        flag_path = self._flag_path(week)
        if not flag_path.exists():
            return False
        try:
            data = json.loads(flag_path.read_text(encoding="utf-8"))
            deadline_str = data.get("deadline", "")
            if not deadline_str:
                return False
            deadline = datetime.fromisoformat(deadline_str)
            # Make deadline timezone-naive for comparison if needed
            now = datetime.now()
            if deadline.tzinfo is not None:
                from datetime import timezone
                now = datetime.now(tz=timezone.utc).astimezone()
            return now >= deadline
        except Exception:
            return False

    def append_entry(self, week: str, text: str, source: str = "voice") -> None:
        """Append a user message to the reflection file.

        Args:
            week: ISO week string
            text: Message content (transcribed or typed)
            source: "voice" or "text"
        """
        refl_path = self._reflection_path(week)
        ts = datetime.now().strftime("%H:%M")
        icon = "🎤" if source == "voice" else "💬"
        entry = f"\n## {ts} [{source}]\n{text}\n"
        with refl_path.open("a", encoding="utf-8") as f:
            f.write(entry)
        logger.info("Reflection entry appended for week %s (%s)", week, icon)

    def has_content(self, week: str) -> bool:
        """Return True if the reflection file has actual user content."""
        refl_path = self._reflection_path(week)
        if not refl_path.exists():
            return False
        content = refl_path.read_text(encoding="utf-8")
        # More than just the header line means there is content
        lines = [ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
        return len(lines) > 0

    def get_reflection_path(self, week: str) -> Path:
        """Return path to the reflection file."""
        return self._reflection_path(week)

    def get_summary_path(self, week: str) -> Path:
        """Return path to the weekly summary file."""
        return self._summary_path(week)

    def clear(self, week: str) -> None:
        """Remove the pending flag file (does NOT delete the reflection content)."""
        flag = self._flag_path(week)
        if flag.exists():
            flag.unlink()
            logger.info("Reflection flag cleared for week %s", week)
