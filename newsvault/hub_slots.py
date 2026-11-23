"""Cross-process concurrency slots for the shared MK1 AI Hub (ollama backend).

The ollama account behind the hub caps concurrent requests account-wide, so every
project on this machine (news-hunter, x-pulse, youtube-summarizer, news-vault,
facebook-digest, substack-digest) must share one pool of slots. Each slot is a
lock file under %LOCALAPPDATA%\\mk1-ai-hub; holding an OS byte-lock on it means
holding the slot. Locks are released automatically if the process dies.

Keep this file identical across projects.

Usage:
    with hub_slot():
        resp = http_post(...)

Env:
    AI_HUB_MAX_CONCURRENCY  number of slots (default 3)
    AI_HUB_SLOT_WAIT_S      max seconds to wait for a slot (default 600)
    AI_HUB_SLOT_DIR         override the lock directory (tests)
"""
from __future__ import annotations

import contextlib
import os
import random
import re
import time
from pathlib import Path
from typing import Iterator

_RESET_RE = re.compile(r"reset after\s+(\d+)\s*s", re.IGNORECASE)


def _slot_dir() -> Path:
    override = os.environ.get("AI_HUB_SLOT_DIR")
    if override:
        base = Path(override)
    else:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "mk1-ai-hub"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _max_slots() -> int:
    try:
        return max(1, int(os.environ.get("AI_HUB_MAX_CONCURRENCY", "3")))
    except ValueError:
        return 3


def _try_lock(fh) -> bool:
    try:
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fh) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


class SlotTimeout(RuntimeError):
    """No hub slot became free within AI_HUB_SLOT_WAIT_S."""


@contextlib.contextmanager
def hub_slot(wait_s: float | None = None) -> Iterator[int]:
    """Hold one shared hub slot for the duration of the block. Yields the slot index."""
    if wait_s is None:
        try:
            wait_s = float(os.environ.get("AI_HUB_SLOT_WAIT_S", "600"))
        except ValueError:
            wait_s = 600.0
    directory = _slot_dir()
    n = _max_slots()
    deadline = time.monotonic() + wait_s
    while True:
        for idx in random.sample(range(n), n):
            fh = open(directory / f"slot-{idx}.lock", "a+b")
            if _try_lock(fh):
                try:
                    yield idx
                finally:
                    _unlock(fh)
                    fh.close()
                return
            fh.close()
        if time.monotonic() >= deadline:
            raise SlotTimeout(f"no free AI Hub slot after {wait_s:.0f}s ({n} slots)")
        time.sleep(0.5 + random.random())


def reset_after_seconds(message: str, default: float = 30.0, cap: float = 60.0) -> float:
    """Parse '(reset after 42s)' from an ollama 429 body; returns seconds to sleep."""
    m = _RESET_RE.search(message or "")
    secs = float(m.group(1)) + 1 if m else default
    return min(secs, cap)


def is_concurrency_429(status: int, body: str) -> bool:
    return status == 429 and "too many concurrent" in (body or "").lower()


def is_retired_model(status: int, body: str) -> bool:
    return status == 410 and "retired" in (body or "").lower()
