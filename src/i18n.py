"""
Internationalization bootstrap for grainsize_measure.

Call setup() ONCE, immediately after QApplication() is constructed
and before any GUI widgets are created. After that, every module can do:

    from i18n import _

and use _("English source string") throughout.

Locale detection uses QLocale.system().name() which is reliable on all
platforms (Windows NLS API / Linux LANG env var / macOS System Prefs).
Falls back to English (NullTranslations = identity) if no .mo file is
found for the detected locale.
"""
from __future__ import annotations

import gettext
import os
from pathlib import Path

# Locale files live at src/locales/<lang>/LC_MESSAGES/messages.mo
_LOCALE_DIR = Path(__file__).parent / "locales"
_DOMAIN = "messages"

# Module-level holder; setup() replaces this with a GNUTranslations instance.
_current_translation: gettext.NullTranslations = gettext.NullTranslations()


def setup() -> None:
    """Detect system locale via QLocale and install the best matching translation.

    Must be called after QApplication() is constructed.
    Falls back to English if no .mo file is found for the detected locale.
    """
    global _current_translation
    from PyQt6.QtCore import QLocale  # QApplication must exist before this

    # GRAINSIZE_LANG env var overrides system locale — useful for testing.
    # On Windows QLocale ignores LANG/LANGUAGE, so this is the portable override.
    # Example: set GRAINSIZE_LANG=en && uv run src/grainsize_measure.py
    env_lang = os.environ.get("GRAINSIZE_LANG", "").strip()
    if env_lang:
        locale_name = env_lang
    else:
        locale_name = QLocale.system().name()      # e.g. "ja_JP", "en_US", "zh_CN"
    lang_code = locale_name.split("_")[0]           # e.g. "ja", "en"
    candidates = [locale_name, lang_code]           # ["ja_JP", "ja"] — first match wins

    try:
        _current_translation = gettext.translation(
            _DOMAIN,
            localedir=str(_LOCALE_DIR),
            languages=candidates,
        )
    except FileNotFoundError:
        # No .mo for this locale → English source strings displayed as-is
        _current_translation = gettext.NullTranslations()


def _(message: str) -> str:
    """Translate *message* using the currently installed locale."""
    return _current_translation.gettext(message)
