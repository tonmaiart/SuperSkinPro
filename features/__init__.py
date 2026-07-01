"""SuperSkinPro — Extra Domains Package Initializer.

This module acts as the central registry gateway for all feature domains.
Every domain folder under features/ must register its lifecycle here.

As of the Unified Component Architecture refactor, each feature domain
owns a ``*_feature.py`` file containing a ``UnifiedFeatureExtension``
subclass. The domain's ``__init__.py`` calls ``<name>_feature.register()``
which registers with ``UnifiedRegistry`` (and legacy registries for
backward compatibility).

Registration order controls insertion order within each tab.
The viewer domains must be first so they render at the top of their tabs:

  LAYER tab   : layer_viewer (first, non-collapsible) → data_io → weight_transfer
  SKINNING tab: deform_bone_viewer (first, non-collapsible) → weight_apply → mirror → clipboard → auto_block → circle_tool_adjust
  CUSTOMIZE   : bone_picker → multi_color_preview (hosted under SYSTEM tab)
"""

from importlib import reload

# Viewer domains — must register before any other spec in their tabs
from . import layer_viewer         # LAYER tab — first (non-collapsible)
from . import deform_bone_viewer   # SKINNING tab — first (non-collapsible)

# Standard feature domains
from . import weight_apply
from . import auto_block_weight
from . import mirror
from . import clipboard
from . import bone_picker
from . import weight_transfer      # LAYER tab
from . import data_io              # LAYER tab
from . import multi_color_preview
from . import circle_tool_adjust

# Cross-cutting control domain (scene-mode gate, pie menu, safe-shrink)
from . import controller

_modules = (
    layer_viewer,
    deform_bone_viewer,
    weight_apply,
    auto_block_weight,
    mirror,
    clipboard,
    bone_picker,
    weight_transfer,
    data_io,
    multi_color_preview,
    circle_tool_adjust,
    controller,
)

for mod in _modules:
    try:
        reload(mod)
    except Exception:
        pass


def register():
    """Register all extra domain lifecycles sequentially."""
    for mod in _modules:
        if hasattr(mod, "register"):
            mod.register()


def unregister():
    """Unregister all extra domain lifecycles in reverse order."""
    for mod in reversed(_modules):
        if hasattr(mod, "unregister"):
            mod.unregister()
