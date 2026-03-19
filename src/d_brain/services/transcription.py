"""Deepgram transcription service."""

import logging
from dataclasses import dataclass

from deepgram import AsyncDeepgramClient

logger = logging.getLogger(__name__)


@dataclass
class Utterance:
    speaker: int
    text: str


# ---------------------------------------------------------------------------
# Diarization utilities (shared between bot handler and web portal)
# ---------------------------------------------------------------------------


def identify_user_speaker(utterances: list[Utterance]) -> tuple[int, bool]:
    """Pick the speaker with the most words as the likely user.

    Returns (speaker_id, is_confident).
    Confident when top speaker has >= 1.5x words of the next speaker.
    """
    if not utterances:
        return 0, True

    word_counts: dict[int, int] = {}
    for u in utterances:
        word_counts[u.speaker] = word_counts.get(u.speaker, 0) + len(u.text.split())

    ranked = sorted(word_counts, key=word_counts.__getitem__, reverse=True)
    top = ranked[0]

    if len(ranked) == 1:
        return top, True

    ratio = word_counts[top] / max(word_counts[ranked[1]], 1)
    return top, ratio >= 1.5


def format_diarized(utterances: list[Utterance], user_speaker: int) -> str:
    """Format utterances as labelled dialogue."""
    lines: list[str] = []
    for u in utterances:
        label = "Ты" if u.speaker == user_speaker else "Собеседник"
        lines.append(f"[{label}]: {u.text}")
    return "\n".join(lines)


def first_examples(utterances: list[Utterance], speaker: int, n: int = 2) -> list[str]:
    """Return first N utterance texts for a given speaker."""
    return [u.text for u in utterances if u.speaker == speaker][:n]


def build_confidence_note(
    utterances: list[Utterance], user_speaker: int
) -> str:
    """Build a note to show when speaker identification is uncertain."""
    parts: list[str] = []
    for sp in sorted({u.speaker for u in utterances}):
        label = "Ты" if sp == user_speaker else "Собеседник"
        examples = first_examples(utterances, sp)
        if examples:
            parts.append(f"[{label}]: «{examples[0]}»")
    return (
        "\n\n⚠️ Не уверен, кто есть кто. Примеры фраз:\n"
        + "\n".join(parts)
        + "\n\nЕсли неверно — скажи «поменять спикеров»."
    )


# ---------------------------------------------------------------------------
# Transcriber
# ---------------------------------------------------------------------------


class DeepgramTranscriber:
    """Service for transcribing audio using Deepgram Nova-3."""

    def __init__(self, api_key: str) -> None:
        self.client = AsyncDeepgramClient(api_key=api_key)

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes to text."""
        logger.info("Starting transcription, audio size: %d bytes", len(audio_bytes))

        response = await self.client.listen.v1.media.transcribe_file(
            request=audio_bytes,
            model="nova-3",
            language="ru",
            punctuate=True,
            smart_format=True,
        )

        transcript = (
            response.results.channels[0].alternatives[0].transcript
            if response.results
            and response.results.channels
            and response.results.channels[0].alternatives
            else ""
        )

        logger.info("Transcription complete: %d chars", len(transcript))
        return transcript

    async def transcribe_diarized(self, audio_bytes: bytes) -> list[Utterance]:
        """Transcribe audio with speaker diarization."""
        logger.info(
            "Starting diarized transcription, audio size: %d bytes", len(audio_bytes)
        )

        response = await self.client.listen.v1.media.transcribe_file(
            request=audio_bytes,
            model="nova-3",
            language="ru",
            punctuate=True,
            smart_format=True,
            diarize=True,
        )

        words = (
            response.results.channels[0].alternatives[0].words
            if response.results
            and response.results.channels
            and response.results.channels[0].alternatives
            else []
        )

        if not words:
            return []

        utterances: list[Utterance] = []
        current_speaker: int = words[0].speaker
        current_words: list[str] = []

        for word in words:
            if word.speaker == current_speaker:
                current_words.append(word.word)
            else:
                if current_words:
                    utterances.append(
                        Utterance(
                            speaker=current_speaker, text=" ".join(current_words)
                        )
                    )
                current_speaker = word.speaker
                current_words = [word.word]

        if current_words:
            utterances.append(
                Utterance(speaker=current_speaker, text=" ".join(current_words))
            )

        num_speakers = len({u.speaker for u in utterances})
        logger.info(
            "Diarized transcription: %d utterances, %d speaker(s)",
            len(utterances),
            num_speakers,
        )
        return utterances
