"""Path utilities for portable param JSON path handling.

Paths in param JSON files are stored as Unix-style (POSIX) strings and
relative to the JSON file's location when possible.  This module provides
helpers to create and resolve those stored strings on any platform.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path, PurePosixPath

APP_NAME = "grainsize_measure"


def read_app_version() -> str:
    """Read version string from pyproject.toml at the project root."""
    try:
        toml_path = Path(__file__).parent.parent / "pyproject.toml"
        with open(toml_path, "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except Exception:
        return "?.?.?"


def make_relative_posix_str(image_path: Path, json_path: Path) -> str:
    """Return *image_path* as a POSIX (forward-slash) string relative to *json_path*'s
    parent directory.

    Falls back to an absolute POSIX string when the two paths are on different
    drives (Windows) and a relative path cannot be computed.
    """
    try:
        rel = image_path.relative_to(json_path.parent)
        return rel.as_posix()
    except ValueError:
        # Different drives on Windows — store absolute POSIX string
        return image_path.as_posix()


def resolve_image_path(image_path_str: str, json_path: Path) -> Path:
    """Resolve a stored image-path string to a :class:`~pathlib.Path`.

    Resolution rules (applied in order):

    1. On Windows, convert Git Bash / MSYS2 Unix-style drive paths
       ``/c/...`` → ``C:/...``.
    2. If the stored string is **relative**, resolve it against
       *json_path*'s parent directory.
    3. If **absolute** and the file exists, return it as-is.
    4. If **absolute** but the file is missing, check whether
       *json_path*'s parent is a prefix of the stored path.  If so,
       strip that prefix and try the remainder as a relative path from
       *json_path*'s parent (handles the case where the entire project
       folder was moved and the stored absolute path shares the same
       sub-directory structure).
    5. Return the resolved ``Path`` regardless — the caller is
       responsible for handling a missing file.
    """
    s = image_path_str

    # 1. Git Bash / MSYS2 drive-letter paths on Windows: /c/foo -> C:/foo
    if sys.platform == "win32":
        m = re.match(r"^/([a-zA-Z])(/.*)?$", s)
        if m:
            drive = m.group(1).upper()
            rest = m.group(2) or "/"
            s = f"{drive}:{rest}"

    # Normalise forward slashes from old Windows param files
    p = Path(s)

    # 2. Relative path → resolve against JSON directory (primary interpretation)
    #    Falls back to CWD-relative for compatibility with older param files that
    #    stored paths relative to the working directory rather than the JSON file.
    if not p.is_absolute():
        candidate_json = json_path.parent / p
        if candidate_json.exists():
            return candidate_json
        candidate_cwd = Path.cwd() / p
        if candidate_cwd.exists():
            return candidate_cwd
        return candidate_json  # preferred interpretation even if missing

    # 3. Absolute and the file exists
    if p.exists():
        return p

    # 4. Absolute but missing — try stripping json_dir prefix
    json_dir = json_path.parent
    try:
        rel = p.relative_to(json_dir)
        candidate = json_dir / rel
        if candidate.exists():
            return candidate
    except ValueError:
        pass

    # 5. Give up; return the computed path (caller handles the error)
    return p
