"""Multi-color preview feature domain — rainbow per-bone weight visualizer."""

from importlib import reload

from . import draw
from . import ops
from . import multi_color_preview_feature
from . import keymap

for mod in (draw, ops, multi_color_preview_feature, keymap):
    try:
        reload(mod)
    except Exception:
        pass


def register():
    multi_color_preview_feature.register()
    ops.register()
    keymap.register()
    draw.register()


def unregister():
    keymap.unregister()
    draw.unregister()
    ops.unregister()
    multi_color_preview_feature.unregister()
