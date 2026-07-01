"""Registry package for SuperSkinPro.

Unified Component Architecture (new):
    UnifiedFeatureExtension — single-class contract for feature domains
    UnifiedRegistry           — central registry for actions + UI + persistence
    SUPERSKIN_OT_execute_action — universal proxy operator

Legacy (still supported during migration):
    BaseDomain / DomainRegistry            — action-only registry
    PrefsExtensionSpec / PrefsExtensionRegistry — UI + persistence registry
"""

from importlib import reload

# Explicit bottom-up reload of every source file in this package so
# ``F3 > Reload Scripts`` picks up the latest class definitions even
# when ``sys.modules`` still holds stale bytecode.
from . import base_domain
from . import domain_registry
from . import prefs_extension_registry
from . import unified_feature_api

for _mod in (base_domain, domain_registry, prefs_extension_registry, unified_feature_api):
    try:
        reload(_mod)
    except Exception:
        pass

from .base_domain import BaseDomain
from .domain_registry import DomainRegistry
from .prefs_extension_registry import PrefsExtensionRegistry, PrefsExtensionSpec
from .unified_feature_api import (
    UnifiedFeatureExtension,
    UnifiedRegistry,
    SUPERSKIN_OT_execute_action,
    register_operator,
    unregister_operator,
)
