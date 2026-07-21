"""End-user license acceptance and first-use gating.

Acceptance is recorded once per license version under the per-user application
data directory (see :mod:`stegosuite.paths`), so the prompt appears only once.
The CLI, GUI and API all funnel through the helpers here.

Overrides:
    STEGOSUITE_ACCEPT_LICENSE=1   accept non-interactively (CI / automation)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from . import __version__
from .paths import app_home
from .i18n import t

# Bump when the license terms change materially: forces re-acceptance.
EULA_VERSION = "1.0"
ACCEPT_FILENAME = "eula_accepted.json"
ENV_ACCEPT = "STEGOSUITE_ACCEPT_LICENSE"

_YES = {"y", "yes", "i", "igen"}


def acceptance_path() -> Path:
    """Location of the acceptance record inside the app data directory."""
    return app_home() / ACCEPT_FILENAME


def _load() -> dict:
    path = acceptance_path()
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


def _env_accept() -> bool:
    return os.environ.get(ENV_ACCEPT, "").strip().lower() in {"1", "true", "yes"}


def is_accepted() -> bool:
    """True if the current license version was accepted (or env override set)."""
    if _env_accept():
        return True
    return _load().get("eula_version") == EULA_VERSION


def reset_acceptance() -> bool:
    """Delete the acceptance record. Returns True if a record was removed."""
    path = acceptance_path()
    if path.is_file():
        path.unlink()
        return True
    return False


def record_acceptance(method: str) -> Path:
    """Persist acceptance for the current license version. Returns the file path."""
    path = acceptance_path()
    data = {
        "eula_version": EULA_VERSION,
        "app_version": __version__,
        "accepted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "method": method,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def status_text() -> str:
    data = _load()
    if data.get("eula_version") == EULA_VERSION:
        return t("eula.status.accepted",
                 version=data.get("app_version", "?"),
                 when=data.get("accepted_at", "?"),
                 method=data.get("method", "?"))
    return t("eula.status.not_accepted")


def summary_text() -> str:
    """The short, human-readable terms shown in prompts/dialogs."""
    return t("eula.intro", version=__version__) + "\n\n" + t("eula.terms")


def license_file() -> Path | None:
    """Locate the bundled LICENSE file in both dev and frozen builds."""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "LICENSE")
    candidates.append(Path(__file__).resolve().parents[2] / "LICENSE")
    for path in candidates:
        if path.is_file():
            return path
    return None


def license_text() -> str:
    path = license_file()
    if path is None:
        return summary_text()
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return summary_text()


def ensure_accepted_cli(accept_flag: bool = False) -> bool:
    """Gate CLI usage on acceptance.

    Returns True if the user may proceed. Records acceptance when granted via
    flag, env override, or an interactive prompt. Prints guidance and returns
    False when acceptance is missing and cannot be obtained.
    """
    if is_accepted():
        return True
    if accept_flag or _env_accept():
        path = record_acceptance("flag" if accept_flag else "env")
        print(t("eula.accepted", version=__version__, path=path))
        return True
    if sys.stdin is not None and sys.stdin.isatty():
        print(summary_text())
        print()
        try:
            answer = input(t("eula.prompt")).strip().lower()
        except EOFError:
            answer = ""
        if answer in _YES:
            path = record_acceptance("prompt")
            print(t("eula.accepted", version=__version__, path=path))
            return True
        print(t("eula.declined"), file=sys.stderr)
        return False
    print(t("eula.required"), file=sys.stderr)
    return False


__all__ = [
    "EULA_VERSION",
    "ENV_ACCEPT",
    "acceptance_path",
    "is_accepted",
    "record_acceptance",
    "reset_acceptance",
    "status_text",
    "summary_text",
    "license_file",
    "license_text",
    "ensure_accepted_cli",
]
