"""DebugLogService -- toggleable, category-gated debug console output.

Replaces ad-hoc print("[SSP-DBG]...") statements that are normally hand-inserted
and hand-removed during a debugging session (see docs/bug-history/0020, 0021).
Each category is independently switchable from the addon's Preferences panel
("Developer / Debug Tools" section) so verbose tracing can be enabled only for
the subsystem actually under investigation.

No module-level cache is kept: is_enabled() reads the live PropertyGroup on
every call. A cached dict would desync from the UI checkboxes across an F3
Reload Scripts, since PropertyGroup/RNA state survives importlib.reload() but
plain module globals do not.
"""

import bpy

CATEGORIES = (
    "temp_vg",
    "core_pipeline",
    "rust_ffi",
    "viewport_viz",
    "bone_id",
    "feature_domains",
)


class DebugLogService:
    """Stateless gate between call sites and the per-category debug toggles."""

    CATEGORIES = CATEGORIES

    @staticmethod
    def is_enabled(category: str) -> bool:
        """Return True if *category* is currently switched on in Preferences.

        Args:
            category: One of the strings in CATEGORIES.

        Returns:
            False if the preferences PropertyGroup is not registered yet
            (e.g. called during addon startup before register() has run).
        """
        prefs = getattr(bpy.context.window_manager, "superskin_prefs", None)
        if prefs is None:
            return False
        return bool(getattr(prefs.debug, category, False))

    @staticmethod
    def log(category: str, message: str) -> None:
        """Print *message* prefixed with its category, only if enabled.

        Args:
            category: One of the strings in CATEGORIES.
            message: The text to print.
        """
        if DebugLogService.is_enabled(category):
            print(f"[SSP:{category.upper()}] {message}")
