"""SuperSkinPro Preferences — core coordinator.

Bridges core_subsystems/preferences (pure I/O + PropertyGroups) with the
Blender lifecycle hooks and temp-VG recovery logic that must live in core
because they depend on core/layer_storage.
"""

import bpy

from ...core_subsystems.preferences import PreferencesService
from ...core_subsystems.preferences import property_groups


@bpy.app.handlers.persistent
def _superskin_prefs_load_handler(dummy):
    """Re-populate WindowManager.superskin_prefs from user.json after every
    file load. ``superskin_prefs`` is SKIP_SAVE (see
    core_subsystems/preferences/property_groups.py), so opening any .blend
    file hands it a brand-new WindowManager ID-block whose PointerProperty
    starts out at type-defaults — without this handler, every file open/new
    would silently blank out the user's customized Preferences until the addon
    is disabled and re-enabled.
    """
    PreferencesService.load()
    _recover_orphaned_temp_vgs()


def _recover_orphaned_temp_vgs():
    """If a .blend was saved mid-Edit with temp VGs present, bake them back."""
    try:
        from ..layer_storage.temp_vg_bridge import (
            has_temp_vgs, read_temp_vgs_to_layer, delete_temp_vgs
        )
        from ..layer_storage.storage_service import LayerStorageService

        for obj in bpy.data.objects:
            if obj.type != 'MESH' or not has_temp_vgs(obj):
                continue
            storage = LayerStorageService(obj.data)
            if not storage.has_layer_system():
                delete_temp_vgs(obj)
                continue
            layer_dict, mask_dict, active_idx = read_temp_vgs_to_layer(obj)
            storage.write_layer_dict(active_idx, layer_dict)
            if mask_dict:
                storage.write_mask_dict(active_idx, mask_dict)
            delete_temp_vgs(obj)
    except Exception as e:
        print(f"[SuperSkinPro] Warning: temp VG recovery failed: {e}")


def register():
    property_groups.register()
    # Initial PreferencesService.load() is deferred to the root __init__.py
    # register() — after features.register() has run so all PrefsExtension
    # specs are in place before the first load attempt.
    bpy.app.handlers.load_post.append(_superskin_prefs_load_handler)


def unregister():
    try:
        bpy.app.handlers.load_post.remove(_superskin_prefs_load_handler)
    except Exception:
        pass
    property_groups.unregister()
