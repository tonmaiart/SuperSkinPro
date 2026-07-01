"""UI package loader for SuperSkinPro.

Imports from the modular UI files:
  - utils.py               Shared helpers, caches, matchers
  - panel_main.py          Master sidebar layout (poll: OBJECT + EDIT_MESH)
  - widget_deform_bones.py Stub — Bone List moved to features/deform_bone_viewer/
  - widget_tools.py        Stub — Layer List moved to features/layer_viewer/
  - widget_preferences.py  Mode-split sidebar draw (no bpy.types classes of its own)
  - addon_preferences.py   Blender native Add-on Preferences (System/Customize settings)
  - list_widget/           Compatibility shim — canonical code in shared/list_widget/
"""

from importlib import reload

from . import utils
from . import panel_main
from . import widget_deform_bones
from . import widget_tools
from . import widget_preferences
from . import addon_preferences
from . import list_widget

for mod in (utils, panel_main, widget_deform_bones, widget_tools,
            widget_preferences, addon_preferences, list_widget):
    try:
        reload(mod)
    except Exception:
        pass


def register():
    utils.register()
    list_widget.register()
    addon_preferences.register()
    panel_main.register()
    # widget_deform_bones and widget_tools are stubs — nothing to register here;
    # their classes are now owned by features/deform_bone_viewer/ and
    # features/layer_viewer/ respectively.


def unregister():
    panel_main.unregister()
    addon_preferences.unregister()
    list_widget.unregister()
    utils.unregister()
