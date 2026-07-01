"""SuperSkinPro weight-tools drawing stub.

The Layer List UIList, adapter, row-click operator, and draw function that
previously lived here have been relocated to
``features/layer_viewer/ui.py`` as part of the LAYER tab domain extraction
(2026-06 architecture refactor).

The Deform Bone List previously imported here via
``from .widget_deform_bones import draw_influence_list_system`` has been
relocated to ``features/deform_bone_viewer/ui.py``.

Both domains register via ``PrefsExtensionRegistry`` and are drawn by
``ui/widget_preferences.py`` as the first entries in their respective tabs.

This module is retained as an empty stub to avoid breaking any import
paths that still reference ``ui.widget_tools``.
"""


def register():
    pass


def unregister():
    pass
