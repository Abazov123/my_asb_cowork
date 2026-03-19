"""Corrections service — transcription dictionary management.

Stores correction rules in vault/corrections.md and applies them to
transcribed text before saving.

Format in corrections.md:
    - wrong → correct (optional context note)
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_CORRECTIONS_FILE = "corrections.md"
_RULE_RE = re.compile(
    r"^-\s+(.+?)\s+[→\->]+\s+(.+?)(?:\s+\((.+?)\))?\s*$",
    re.UNICODE,
)


class CorrectionsService:
    """Service for managing and applying transcription correction rules."""

    def __init__(self, vault_path: Path | str) -> None:
        self.corrections_path = Path(vault_path) / _CORRECTIONS_FILE
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Create corrections.md with skeleton if it doesn't exist."""
        if not self.corrections_path.exists():
            self.corrections_path.write_text(
                "# Словарь исправлений транскрипций\n"
                "<!-- Формат: - неправильно → правильно (необязательный контекст) -->\n\n"
                "## Имена и люди\n\n"
                "## Проекты и сервисы\n\n"
                "## Термины\n",
                encoding="utf-8",
            )
            logger.info("Created %s", self.corrections_path)

    def load(self) -> list[dict]:
        """Load all correction rules from corrections.md.

        Returns:
            List of dicts with keys: wrong, correct, context
        """
        rules: list[dict] = []
        if not self.corrections_path.exists():
            return rules
        for line in self.corrections_path.read_text(encoding="utf-8").splitlines():
            m = _RULE_RE.match(line.strip())
            if m:
                rules.append(
                    {
                        "wrong": m.group(1).strip(),
                        "correct": m.group(2).strip(),
                        "context": (m.group(3) or "").strip(),
                    }
                )
        return rules

    def apply(self, text: str) -> tuple[str, list[str]]:
        """Apply all correction rules to text (case-insensitive exact match).

        Args:
            text: Raw transcribed text

        Returns:
            Tuple of (corrected_text, list_of_applied_corrections)
        """
        rules = self.load()
        applied: list[str] = []
        result = text
        for rule in rules:
            wrong = rule["wrong"]
            correct = rule["correct"]
            # Case-insensitive word-boundary replacement
            pattern = re.compile(r"(?<!\w)" + re.escape(wrong) + r"(?!\w)", re.IGNORECASE)
            new_result, n = pattern.subn(correct, result)
            if n > 0:
                result = new_result
                applied.append(f"{wrong} → {correct}")
        return result, applied

    def add(self, wrong: str, correct: str, context: str = "") -> None:
        """Add a new correction rule to corrections.md.

        The rule is appended in the appropriate section (Имена/Сервисы/Термины)
        or at the end of the file if no section matches.

        Args:
            wrong: Incorrect transcription
            correct: Correct form
            context: Optional explanation
        """
        rule_line = f"- {wrong} → {correct}"
        if context:
            rule_line += f" ({context})"

        content = self.corrections_path.read_text(encoding="utf-8")

        # Avoid duplicates
        if f"- {wrong} →" in content or f"- {wrong} ->" in content:
            logger.info("Correction for '%s' already exists, skipping", wrong)
            return

        # Append at end of file (before any trailing newlines)
        content = content.rstrip("\n") + "\n" + rule_line + "\n"
        self.corrections_path.write_text(content, encoding="utf-8")
        logger.info("Added correction: %s → %s", wrong, correct)

    def format_rules_summary(self) -> str:
        """Return a short human-readable summary of current rules."""
        rules = self.load()
        if not rules:
            return "Словарь пустой."
        lines = [f"• {r['wrong']} → {r['correct']}" + (f" ({r['context']})" if r["context"] else "") for r in rules]
        return "\n".join(lines)
