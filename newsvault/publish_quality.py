"""Final, provider-independent guard before untrusted summaries reach the archive."""

from __future__ import annotations

import re

_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


def publishable_text(value: object, *, minimum: int = 80) -> bool:
    """Accept useful Vietnamese-oriented prose and reject empty/truncated CJK output.

    This is deliberately a final safety net, not a translation detector.  Upstream
    pipelines retain rejected rows for provider retry and diagnostics.
    """
    if not isinstance(value, str):
        return False
    text = value.strip()
    return len(text) >= minimum and not _CJK.search(text)
