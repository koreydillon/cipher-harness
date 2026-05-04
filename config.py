"""
config.py — Central configuration loader for Cipher.

Reads settings from environment variables (or a .env file via python-dotenv).
Import this module early (before any other cipher module) so that all
os.environ lookups see the populated values.

Usage:
    from config import cfg          # access typed settings
    import config; config.load()   # explicit (re)load, e.g. in tests
"""
from __future__ import annotations

import os
from pathlib import Path


def load(env_file: str | Path | None = None) -> None:
    """Load a .env file into the environment (no-op if python-dotenv is absent).

    Priority (highest → lowest):
        1. Values already in the real environment (never overwritten).
        2. Values in *env_file* (defaults to .env in the current directory).
    """
    try:
        from dotenv import load_dotenv  # type: ignore[import]
    except ImportError:
        return  # python-dotenv not installed — rely on the shell environment

    path = Path(env_file) if env_file else Path(".env")
    if path.exists():
        load_dotenv(dotenv_path=path, override=False)


def _bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").lower()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    return default


def _int(key: str, default: int) -> int:
    try:
        return int(os.environ[key])
    except (KeyError, ValueError):
        return default


def _float(key: str, default: float | None) -> float | None:
    try:
        return float(os.environ[key])
    except (KeyError, ValueError):
        return default


class _Config:
    """Typed, lazy view over os.environ.

    All attributes are properties so they reflect any runtime changes to
    os.environ (e.g., from test fixtures) without needing a reload.
    """

    # ── Anthropic ──────────────────────────────────────────────────────────────
    @property
    def anthropic_api_key(self) -> str | None:
        return os.environ.get("ANTHROPIC_API_KEY")

    # ── Model ──────────────────────────────────────────────────────────────────
    @property
    def model(self) -> str:
        return os.environ.get("CIPHER_DEFAULT_MODEL", "claude-sonnet-4-6")

    @property
    def max_tokens(self) -> int:
        return _int("CIPHER_MAX_TOKENS", 8096)

    # ── Local / Ollama ─────────────────────────────────────────────────────────
    @property
    def local_model(self) -> bool:
        return _bool("LOCAL_MODEL", False)

    @property
    def cipher_model(self) -> str:
        """Name of the local Ollama model to use."""
        return os.environ.get("CIPHER_MODEL", "cipher")

    @property
    def ollama_url(self) -> str:
        return os.environ.get("OLLAMA_URL", "http://localhost:11434/v1")

    # ── Plugins ────────────────────────────────────────────────────────────────
    @property
    def plugin_dir(self) -> str:
        return os.environ.get("CIPHER_PLUGIN_DIR", "~/.cipher/plugins")

    # ── Budget ─────────────────────────────────────────────────────────────────
    @property
    def budget(self) -> float | None:
        return _float("CIPHER_BUDGET", None)

    # ── Logging / session ──────────────────────────────────────────────────────
    @property
    def log_dir(self) -> str:
        return os.environ.get("CIPHER_LOG_DIR", ".cipher/sessions")

    # ── Auto-compact ───────────────────────────────────────────────────────────
    @property
    def compact_threshold(self) -> float:
        """Fraction of the context window that triggers auto-compact (0–1)."""
        try:
            v = float(os.environ.get("CIPHER_COMPACT_THRESHOLD", "0.85"))
            return max(0.1, min(1.0, v))
        except ValueError:
            return 0.85

    # ── Autonomous mode ────────────────────────────────────────────────────────
    @property
    def auto_mode(self) -> bool:
        return _bool("CIPHER_AUTO_MODE", False)

    def __repr__(self) -> str:  # pragma: no cover
        key = self.anthropic_api_key
        key_repr = f"{key[:8]}…" if key else "not set"
        return (
            f"<Config model={self.model!r} max_tokens={self.max_tokens} "
            f"local_model={self.local_model} budget={self.budget} "
            f"anthropic_api_key={key_repr}>"
        )


# Singleton — import and use everywhere as `from config import cfg`
cfg = _Config()
