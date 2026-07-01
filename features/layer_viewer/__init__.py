"""LayerViewer feature package.

Anchors the Layer List at the top of the LAYER tab as a non-collapsible
viewer via LayerViewerFeature (UnifiedFeatureExtension). All UIList, adapter,
and operator classes are registered from ui.py.
"""

from importlib import reload

from . import prefs
from . import ops
from . import ui
from . import layer_viewer_feature

for mod in (prefs, ops, ui, layer_viewer_feature):
    try:
        reload(mod)
    except Exception:
        pass


def register():
    ops.register()
    ui.register()
    prefs.register()
    layer_viewer_feature.register()


def unregister():
    layer_viewer_feature.unregister()
    prefs.unregister()
    ui.unregister()
    ops.unregister()
