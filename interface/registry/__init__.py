"""Registry sub-package for the Interface subsystem.

Unified Component Architecture:
    UnifiedFeatureExtension — single-class contract for feature domains
    UnifiedRegistry           — central registry for actions + UI + persistence
    SUPERSKIN_OT_execute_action — universal proxy operator

Legacy (still defined but no longer consumed at runtime):
    PrefsExtensionSpec / PrefsExtensionRegistry — UI + persistence registry
"""

from importlib import reload

from . import prefs_extension_registry
from . import register_api

for _mod in (prefs_extension_registry, register_api):
    try:
        reload(_mod)
    except Exception:
        pass

from .prefs_extension_registry import PrefsExtensionRegistry, PrefsExtensionSpec
from .register_api import (
    UnifiedFeatureExtension,
    UnifiedRegistry,
    SUPERSKIN_OT_execute_action,
    register_operator,
    unregister_operator,
)
