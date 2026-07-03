"""SuperSkinPro status panel.

Always shown in the 3D Viewport sidebar (Super Skin Pro tab), first in the
tab. Hosts version info, the addon update checker, license status, and a
Settings shortcut into the addon's own Preferences page. Sorts above
VIEW3D_PT_superskin_main (default bl_order vs. that panel's
bl_order = 1000000).

Unlike the old activation-gate design, this panel does NOT disappear once a
valid license is active — it stays and just switches its status box from
"Locked" to "Activated". VIEW3D_PT_superskin_main's own poll() still
requires activation, so before activation this is the only panel visible in
the tab; afterward both panels coexist, Status first.
"""

import bpy
import tomllib
from pathlib import Path

from .. import addon_updater_ops
from .. import ADDON_PACKAGE
from ..core.facade import CoreFacade

_cached_version = None


def _addon_version() -> str:
    """Read the version string from blender_manifest.toml, cached after first read."""
    global _cached_version
    if _cached_version is None:
        manifest_path = Path(__file__).parent.parent / "blender_manifest.toml"
        with open(manifest_path, "rb") as fh:
            manifest = tomllib.load(fh)
        _cached_version = manifest.get("version", "unknown")
    return _cached_version


class _LayoutShim:
    """Minimal stand-in for a Panel instance, exposing only `.layout`.

    addon_updater_ops.update_notice_box_ui(self, context) draws into
    `self.layout` unconditionally (no explicit layout/element parameter,
    unlike update_settings_ui_condensed) -- passing this instead of the real
    Panel lets its output land inside our nested collapsible body instead of
    always falling back to the panel's top-level layout.
    """
    def __init__(self, layout):
        self.layout = layout


class VIEW3D_PT_superskin_gate(bpy.types.Panel):
    bl_idname = "VIEW3D_PT_superskin_gate"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Super Skin Pro'
    bl_label = "Status"

    def draw(self, context):
        layout = self.layout
        prefs = context.window_manager.superskin_prefs
        lic = prefs.license
        activated = CoreFacade.is_system_activated()

        # Two distinct panel_id strings (not a shared id + a runtime
        # default_closed flip) so the collapse state genuinely resets the
        # moment activation state changes -- layout.panel()'s
        # default_closed only seeds the *first* draw of a given id; once
        # Blender has any remembered state for that id, further
        # default_closed changes are ignored. Activating (or resetting
        # activation) switches to an id that has never been drawn in this
        # area before, so the "collapsed after activation / expanded while
        # locked" default always applies on the state that actually matters.
        panel_id = "superskin_gate_activated" if activated else "superskin_gate_locked"
        header, body = layout.panel(panel_id, default_closed=activated)
        if activated:
            header.label(text="Status: Activated", icon='CHECKMARK')
        else:
            header.label(text="Status: Locked", icon='LOCKED')

        if body is None:
            return

        body.label(text=f"Version {_addon_version()}")

        if activated:
            if lic.status_message:
                body.label(text=lic.status_message)
        else:
            body.prop(lic, "license_key", text="License Key")
            body.operator("superskin.activate_license", text="Activate", icon='UNLOCKED')
            if lic.status_message:
                body.label(text=lic.status_message)

        row = body.row()
        settings_op = row.operator("preferences.addon_show", text="Settings", icon='PREFERENCES')
        settings_op.module = ADDON_PACKAGE

        body.separator()
        addon_updater_ops.update_notice_box_ui(_LayoutShim(body), context)
        addon_updater_ops.update_settings_ui_condensed(None, context, element=body.box())


def register():
    bpy.utils.register_class(VIEW3D_PT_superskin_gate)


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_superskin_gate)
