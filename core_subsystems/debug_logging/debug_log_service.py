"""DebugLogService -- always-on, category-tagged debug console output.

Replaces ad-hoc print("[SSP-DBG]...") statements that are normally hand-inserted
and hand-removed during a debugging session (see docs/bug-history/0020, 0021).

As of the debug_console redesign, capture is unconditional: every category is
always printed and buffered (see ``is_enabled()``). The per-category
Preferences checkboxes (``SSPrefDebug``, drawn by the ``debug_console``
feature domain -- see ``features/debug_console/README.md``) no longer gate
whether a category is captured; they are a pure *display* filter for which
categories the console's log view currently shows. This guarantees the
buffer's history is always complete regardless of which categories are
currently visible in the panel.

``_log_buffer`` (the in-memory history used by the debug console's live log
view) is a plain module global -- a session-scoped runtime buffer, not a
UI-backed setting, so resetting on F3 Reload Scripts is acceptable and
expected (the reload re-executes this module, giving a fresh empty list).
"""

import time

CATEGORIES = (
    "temp_vg",
    "core_pipeline",
    "rust_ffi",
    "viewport_viz",
    "bone_id",
    "feature_domains",
)

_MAX_LOG_LINES = 200
_log_buffer: list[dict] = []


class DebugLogService:
    """Unconditional capture + query surface for the runtime debug-log buffer."""

    CATEGORIES = CATEGORIES

    @staticmethod
    def is_enabled(category: str) -> bool:
        """Always returns True -- debug-log capture is unconditional.

        Historically gated whether ``log()`` printed/buffered at all, keyed
        off the per-category Preferences checkboxes. Since the debug_console
        redesign those checkboxes only filter what the console's log view
        *displays*; they no longer control capture, so every category is
        always printed and buffered. Kept as a stable call site for the
        existing ``if DebugLogService.is_enabled(...):`` guards elsewhere in
        ``core/`` and ``interface/`` (now harmless always-true checks) so
        those call sites did not need to be touched.

        Args:
            category: Unused, kept for call-site compatibility.
        """
        return True

    @staticmethod
    def log(category: str, message: str) -> None:
        """Print *message* prefixed with its category, only if enabled.

        Also appends the entry to the in-memory ``_log_buffer`` (capped at
        ``_MAX_LOG_LINES``, oldest entries dropped first) so the debug
        console's live log view has something to read.

        Args:
            category: One of the strings in CATEGORIES.
            message: The text to print.
        """
        if DebugLogService.is_enabled(category):
            _log_buffer.append({
                "timestamp": time.strftime("%H:%M:%S"),
                "category": category,
                "message": message,
            })
            if len(_log_buffer) > _MAX_LOG_LINES:
                del _log_buffer[0]
            print(f"[SSP:{category.upper()}] {message}")

    @staticmethod
    def get_logs(category_filter: str | None = None, search: str = "") -> list[dict]:
        """Return buffered log entries, optionally filtered.

        Args:
            category_filter: One of CATEGORIES, or ``None``/``"ALL"`` for no
                category filtering.
            search: Case-insensitive substring match against the entry's
                message. Empty string matches everything.

        Returns:
            A new list of ``{"timestamp", "category", "message"}`` dicts, in
            the original append order (oldest first).
        """
        needle = search.lower()
        return [
            entry for entry in _log_buffer
            if (category_filter in (None, "ALL") or entry["category"] == category_filter)
            and (not needle or needle in entry["message"].lower())
        ]

    @staticmethod
    def clear_logs() -> None:
        """Discard all buffered log entries."""
        _log_buffer.clear()
