from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VOICE: str = "vi-VN-HoaiMyNeural"


@dataclass(frozen=True, slots=True)
class AudioResult:
    path: Path | None
    error: str  # '' on success, 'disabled' | 'missing-dependency' | a message


def is_available() -> bool:
    """True when the optional `edge-tts` dependency can be imported."""
    try:
        import edge_tts  # noqa: F401

        return True
    except ImportError:
        return False


def synthesize_brief(
    bullets: Sequence[str],
    destination: Path,
    *,
    voice: str = DEFAULT_VOICE,
    enabled: bool = False,
    timeout: int = 120,
) -> AudioResult:
    """Render the day's brief to an mp3. Disabled by default: enabling it publishes the brief text as
    audio on a public site. Returns AudioResult(None, 'disabled') when `enabled` is False."""
    if not enabled:
        return AudioResult(None, "disabled")

    try:
        import edge_tts
    except ImportError:
        return AudioResult(None, "missing-dependency")

    # Join bullets with period and line break for voice pause
    text = ".\n".join(bullets)

    async def _run() -> None:
        communicate = edge_tts.Communicate(text, voice=voice)
        await communicate.save(str(destination))

    try:
        asyncio.run(_run())
    except Exception as e:
        return AudioResult(None, str(e))

    return AudioResult(destination, "")
