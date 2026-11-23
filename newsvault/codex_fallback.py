"""Last-resort local Codex CLI fallback when AI Hub and direct Ollama both fail."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

# Codex out of quota ("You've hit your usage limit ...") fails identically on every later
# call, so it is switched off for the rest of the process.
_DISABLED_REASON = ""
_STDERR_TAIL_CHARS = 800
_SLOTS = threading.BoundedSemaphore(max(1, int(os.environ.get("CODEX_MAX_PARALLEL", "4"))))


def model() -> str:
    return os.environ.get("CODEX_MODEL", "gpt-6-luna")


def is_disabled() -> bool:
    return bool(_DISABLED_REASON)


def disabled_reason() -> str:
    return _DISABLED_REASON


def reset_disabled() -> None:
    global _DISABLED_REASON
    _DISABLED_REASON = ""


def enabled() -> bool:
    """Env switch NEWSVAULT_CODEX_FALLBACK (default on; 0/false/off/no disables)."""
    return os.environ.get("NEWSVAULT_CODEX_FALLBACK", "1").strip().lower() not in (
        "0", "false", "off", "no", "",
    )


def _stderr_tail(stderr: str, limit: int = _STDERR_TAIL_CHARS) -> str:
    lines = [ln.rstrip() for ln in stderr.splitlines() if ln.strip()]
    while lines and lines[0].startswith((
        "OpenAI Codex", "-----", "workdir:", "model:", "provider:", "approval:",
        "sandbox:", "reasoning effort:", "reasoning summaries:", "session id:",
    )):
        lines.pop(0)
    return "\n".join(lines)[-limit:]


def _configured_codex_path() -> Path | None:
    config_path = Path.home() / ".codex" / "config.toml"
    if not config_path.is_file():
        return None
    try:
        text = config_path.read_text(encoding="utf-8")
        configured = tomllib.loads(text).get("CODEX_CLI_PATH")
        if not isinstance(configured, str):
            match = re.search(r'^\s*CODEX_CLI_PATH\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
            configured = match.group(1) if match else None
        if isinstance(configured, str) and configured.strip():
            candidate = Path(configured.strip()).expanduser()
            if candidate.is_file():
                return candidate
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logger.warning("[codex-fallback] cannot read %s: %s", config_path, exc)
    return None


def _find_codex_executable() -> Path | None:
    configured = _configured_codex_path()
    if configured:
        return configured
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates = list((Path(local_app_data) / "OpenAI" / "Codex" / "bin").glob("*/codex.exe"))
        if candidates:
            return max(candidates, key=lambda path: path.stat().st_mtime)
    on_path = shutil.which("codex")
    return Path(on_path) if on_path else None


def is_usable() -> bool:
    """Flag on, not quota-disabled, and an executable can be found."""
    if not enabled() or is_disabled():
        return False
    try:
        return _find_codex_executable() is not None
    except OSError:
        return False


def codex_fallback(prompt: str, timeout: int = 300) -> str | None:
    """Run Codex CLI and return its saved output text, or None on failure."""
    global _DISABLED_REASON
    if _DISABLED_REASON:
        return None
    try:
        codex_exe = _find_codex_executable()
    except OSError as exc:
        logger.warning("[codex-fallback] cannot locate Codex CLI: %s", exc)
        return None
    if not codex_exe:
        logger.warning("[codex-fallback] codex.exe not found")
        return None

    output_path: Path | None = None
    try:
        fd, output_name = tempfile.mkstemp(prefix="newsvault-codex-", suffix=".txt")
        os.close(fd)
        output_path = Path(output_name)
        output_path.unlink(missing_ok=True)
        repo_root = Path(__file__).resolve().parents[1]
        command = [
            str(codex_exe), "exec", "-C", str(repo_root), "-s", "read-only",
            "--skip-git-repo-check", "-m", model(),
            "-c", 'model_reasoning_effort="low"', "-o", str(output_path),
        ]
        try:
            with _SLOTS:
                completed = subprocess.run(
                    command, input=prompt.encode("utf-8"), capture_output=True, timeout=timeout,
                )
        except subprocess.TimeoutExpired:
            logger.warning("[codex-fallback] Codex CLI timeout after %ss", timeout)
            return None
        except OSError as exc:
            logger.warning("[codex-fallback] cannot run Codex CLI: %s", exc)
            return None

        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            tail = _stderr_tail(stderr)
            logger.warning("[codex-fallback] Codex CLI exit %s: %s", completed.returncode, tail)
            if "usage limit" in stderr.lower():
                _DISABLED_REASON = tail[-200:] or "usage limit"
                logger.warning("[codex-fallback] usage limit hit; disabled for this process")
            return None
        if not output_path.is_file():
            logger.warning("[codex-fallback] Codex CLI produced no output file")
            return None
        output = output_path.read_text(encoding="utf-8").strip()
        if not output:
            logger.warning("[codex-fallback] Codex CLI output empty")
            return None
        return output
    except OSError as exc:
        logger.warning("[codex-fallback] cannot read Codex output: %s", exc)
        return None
    finally:
        if output_path:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
