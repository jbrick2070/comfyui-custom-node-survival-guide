"""Cross-platform env-var reader.

The OTR sprint script that this addon is extracted from used
``winreg.OpenKey(HKEY_CURRENT_USER, "Environment")`` directly to read
fresh values. That works on Windows (catches User-scope vars set via
``setx`` without requiring a shell restart) but breaks on Linux / WSL /
RunPod / macOS.

This module tries the Windows path first, falls back to ``os.environ``
on every other platform — so the same code runs everywhere a custom
node author might be developing.
"""

from __future__ import annotations

import os
import sys


def read_env_var(name: str, expected_prefix: str | None = None) -> str:
    """Return the value of ``name`` from the current user's environment.

    On Windows we read the User-scope ``HKCU\\Environment`` key directly,
    so values set via ``setx NAME value`` are picked up without a shell
    restart. On other platforms we fall back to ``os.environ`` (the
    standard interpreter inheritance path).

    If ``expected_prefix`` is given, the value is sanity-checked against
    it (e.g. ``sk-`` for OpenAI keys) and a clear error is raised if the
    prefix doesn't match — usually this means the wrong key was pasted.

    Raises:
        RuntimeError: if the var is missing, empty, or fails the prefix
            check. The message tells the user how to set the var.
    """
    value: str | None = None

    if sys.platform == "win32":
        try:
            import winreg  # type: ignore
        except ImportError:
            winreg = None  # type: ignore
        else:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, "Environment"
                ) as k:
                    try:
                        value, _ = winreg.QueryValueEx(k, name)
                    except FileNotFoundError:
                        value = None
            except OSError:
                value = None

    if not value:
        # POSIX fallback (and Windows path-not-found fallback). Honors
        # whatever the parent process exported, including `.env` style
        # files that the parent has already loaded.
        value = os.environ.get(name)

    if not value:
        if sys.platform == "win32":
            how_to_set = (
                f'`setx {name} "your-key-here"` (User scope) and open '
                f"a fresh shell, OR `$env:{name} = 'your-key-here'` for "
                f"the current process only."
            )
        else:
            how_to_set = (
                f'`export {name}="your-key-here"` in your shell, or set '
                f"it in your `.env` / systemd unit / pod env."
            )
        raise RuntimeError(
            f"{name} is not set. To configure it: {how_to_set}"
        )

    if expected_prefix and not value.startswith(expected_prefix):
        raise RuntimeError(
            f"{name} does not start with expected prefix "
            f"{expected_prefix!r} (got first 4 chars: {value[:4]!r}). "
            f"Probably the wrong key was pasted."
        )

    return value
