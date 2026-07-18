"""OverlayColorFeature — Unified Component Architecture implementation for
the overlay_color domain.

Merges what used to be two separate domains, `vgcolor` (weight/mask ramp
customization) and `multi_color_preview` (Alt+3 rainbow per-bone preview) —
both are "SuperSkinPro draws its own color on top of Blender's native
viewport instead of leaving it alone" mechanisms, and both needed to
coordinate to avoid visually stacking (see `native_sync.py`'s "Yields to
Multi Color Preview" note), which is much simpler to do inside one domain
than across two with the project's "Zero Cross-Imports" rule between
features. Renamed from `vgcolor` to `overlay_color` to reflect that
broader identity — it was never really about "VG color" specifically.

Owns:
  - Two customizable color ramps (`edit_ramp` for normal weight editing,
    `mask_ramp` for mask editing), edited through Blender's own native
    ColorRamp widget (see `_ramp_io.py`) and pushed into Blender's native
    weight-color pipeline by `native_sync.py` while the addon's own "Edit
    Layer Weight" mode is active.
  - Multi Color Preview (`multi_color_draw.py`), the Alt+3 toggle that
    blends all bone colors per vertex via a temp mesh color attribute +
    native Solid/Attribute shading.
  - Action dispatch: `start_multi_color` / `stop_multi_color` /
    `toggle_multi_color` (multi_color_draw.py); the ramps need no actions
    of their own, Blender's native ColorRamp widget already has its own
    add/remove/drag UI built in.
"""

import bpy
import os

from ...interface.registry.register_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade
from . import _ramp_io
from . import multi_color_draw

_DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "default_config.json")


def _migrate_legacy_vgcolor_key() -> None:
    """One-time migration: this domain used to be `vgcolor` (before merging
    with `multi_color_preview` and renaming to `overlay_color`). Anyone who
    had already customized their ramps has that data sitting in their
    per-machine ``user.json`` under the OLD key ``"vgcolor"`` --
    ``PreferencesService.load()`` only ever looks under this domain's
    *current* ``json_path`` (``("overlay_color",)``), so without this
    migration that customization would silently stop being read at all
    (falling back to bare `default_config.json` values, which looks like
    "my config disappeared" even though the data is still sitting right
    there in the file under the old name). Idempotent -- does nothing once
    the key has already been renamed once.
    """
    try:
        from ...core_subsystems.preferences import io
        path = io.user_json_path()
        data = io.load_json_safe(path)
        if "vgcolor" in data and "overlay_color" not in data:
            data["overlay_color"] = data.pop("vgcolor")
            io.save_json(path, data)
    except Exception:
        pass


# ==============================================================================
# Live-edit auto-save watcher
# ==============================================================================
# Native ColorRampElement properties have no addon-attachable `update=`
# callback (unlike a custom PropertyGroup field), so dragging a stop in the
# UI can't call CoreFacade.save_prefs() directly the way every other
# domain's fields do. Instead this polls both ramps' current stops (cheap --
# a handful of floats) and saves whenever they differ from the last-saved
# snapshot, the same poll-based reactivity pattern used elsewhere in this
# addon (see native_sync.py / multi_color_draw.py's watchers) for state
# nothing pushes a change notification for.

_WATCH_INTERVAL = 0.5
_watch_timer_registered = False
_last_saved_signature = None


def _current_signature():
    edit_tex = _ramp_io.get_or_create_ramp_texture("edit")
    mask_tex = _ramp_io.get_or_create_ramp_texture("mask")
    if edit_tex is None or mask_tex is None:
        raise RuntimeError("overlay_color ramp textures not available yet")
    return (
        tuple(_ramp_io.read_stops(edit_tex.color_ramp)),
        tuple(_ramp_io.read_stops(mask_tex.color_ramp)),
    )


def _watch_tick():
    global _last_saved_signature
    try:
        sig = _current_signature()
    except Exception:
        return _WATCH_INTERVAL
    if sig != _last_saved_signature:
        _last_saved_signature = sig
        CoreFacade.save_prefs()
    return _WATCH_INTERVAL


# ==============================================================================
# OverlayColorFeature — UnifiedFeatureExtension
# ==============================================================================

class OverlayColorFeature(UnifiedFeatureExtension):
    """Unified extension owning SuperSkinPro's overlay color modes."""

    # ── Configuration (class attributes) ──────────────────────────────────

    domain_id = "overlay_color"
    actions = ["start_multi_color", "stop_multi_color", "toggle_multi_color"]
    section_title = "Overlay Color"
    draw_tab = "PREFERENCE"
    defaults_path = _DEFAULTS_PATH
    supports_dev_override = True

    # ── Action dispatch ───────────────────────────────────────────────────

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        try:
            if action == "toggle_multi_color":
                multi_color_draw.toggle()
                core_facade.invalidate_and_redraw()
            elif action == "start_multi_color":
                multi_color_draw.start()
                core_facade.invalidate_and_redraw()
            elif action == "stop_multi_color":
                multi_color_draw.stop()
                core_facade.invalidate_and_redraw()
            else:
                return {"status": "CANCELLED", "message": f"Unknown action: {action}"}
        except Exception as e:
            return {"status": "CANCELLED", "message": str(e)}
        return {"status": "FINISHED"}

    # ── UI layout ─────────────────────────────────────────────────────────

    def draw_section(self, layout, context) -> None:
        """Both ramps (Blender's own native ColorRamp widget) plus a
        one-line pointer to the Alt+3 Multi Color Preview toggle, which has
        no other configurable settings of its own.

        The ramps apply while editing through this addon -- see
        ``native_sync.py`` for which one is actually live at any given
        moment (edit-weight ramp normally, mask ramp while the active row
        is the Mask row) -- and are suppressed entirely while Multi Color
        Preview is on (see ``native_sync.py``'s "Yields to Multi Color
        Preview" note).
        """
        edit_tex = _ramp_io.get_or_create_ramp_texture("edit")
        mask_tex = _ramp_io.get_or_create_ramp_texture("mask")

        if edit_tex is None or mask_tex is None:
            layout.label(text="Color ramps not ready yet -- reopen this panel.", icon='INFO')
        else:
            layout.label(text="Edit Weight Colors", icon='COLOR')
            layout.template_color_ramp(edit_tex, "color_ramp", expand=True)

            layout.separator(factor=0.4)

            layout.label(text="Mask Colors", icon='MOD_MASK')
            layout.template_color_ramp(mask_tex, "color_ramp", expand=True)

        layout.separator(factor=0.4)
        layout.label(text="Multi Color Preview: hold Alt+3 to toggle", icon='COLORSET_10_VEC')

    # ── JSON persistence ──────────────────────────────────────────────────

    def populate(self, data: dict) -> None:
        """Rebuild both ramp textures' ColorRamps from the merged JSON dict."""
        for ramp_id, field in (("edit", "edit_ramp"), ("mask", "mask_ramp")):
            stops_raw = data.get(field, {}).get("stops", [])
            stops = [(float(s[0]), tuple(float(c) for c in s[1])) for s in stops_raw]
            if not stops:
                continue
            tex = _ramp_io.get_or_create_ramp_texture(ramp_id)
            if tex is None:
                continue
            _ramp_io.write_stops(tex.color_ramp, stops)

        global _last_saved_signature
        try:
            _last_saved_signature = _current_signature()
        except Exception:
            pass

    def serialize_into(self, full_dict: dict) -> None:
        """Write current ramp texture values into full_dict at the correct JSON path.

        No-op (leaves any prior "overlay_color" entry in full_dict
        untouched) if the ramp textures aren't available yet -- see
        ``_ramp_io.get_or_create_ramp_texture()``'s docstring.
        """
        edit_tex = _ramp_io.get_or_create_ramp_texture("edit")
        mask_tex = _ramp_io.get_or_create_ramp_texture("mask")
        if edit_tex is None or mask_tex is None:
            return
        full_dict["overlay_color"] = {
            "edit_ramp": {
                "stops": [[p, list(c)] for p, c in _ramp_io.read_stops(edit_tex.color_ramp)]
            },
            "mask_ramp": {
                "stops": [[p, list(c)] for p, c in _ramp_io.read_stops(mask_tex.color_ramp)]
            },
        }


# ==============================================================================
# Registration (called from __init__.py)
# ==============================================================================

def register():
    """Migrate any legacy user.json data, create the ramp textures, register
    the extension, start the auto-save watcher."""
    _migrate_legacy_vgcolor_key()
    _ramp_io.get_or_create_ramp_texture("edit")
    _ramp_io.get_or_create_ramp_texture("mask")
    UnifiedRegistry.register(OverlayColorFeature())

    global _watch_timer_registered
    if not _watch_timer_registered:
        bpy.app.timers.register(_watch_tick, first_interval=_WATCH_INTERVAL, persistent=True)
        _watch_timer_registered = True


def unregister():
    """Stop the auto-save watcher and unregister the extension.

    Deliberately does NOT remove the ramp textures (``_ramp_io.
    remove_ramp_textures()`` still exists but is no longer called from
    here) -- `unregister()` fires on every F3 Reload Scripts, not just a
    genuine addon uninstall (Blender gives no way to tell the two apart),
    so destroying and recreating them here made every reload depend on
    `populate()` successfully repopulating them from JSON to avoid a
    visible reset. Leaving the textures alone across reloads is simpler
    and strictly safer -- worst case an old install leaves one small,
    hidden, fake-user Texture datablock behind, which is a fully acceptable
    trade against silently losing a user's ramp customization on every
    script reload.
    """
    global _watch_timer_registered
    if _watch_timer_registered and bpy.app.timers.is_registered(_watch_tick):
        bpy.app.timers.unregister(_watch_tick)
    _watch_timer_registered = False

    UnifiedRegistry.unregister("overlay_color")
