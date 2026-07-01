"""Registry sub-package for the Interface subsystem.

Unified Component Architecture:
    UnifiedFeatureExtension — single-class contract for feature domains
    UnifiedRegistry           — central registry for actions + UI + persistence
    SUPERSKIN_OT_execute_action — universal proxy operator

Legacy (still supported during migration):
    BaseDomain / DomainRegistry            — action-only registry
    PrefsExtensionSpec / PrefsExtensionRegistry — UI + persistence registry
"""

from importlib import reload

from . import base_domain
from . import domain_registry
from . import prefs_extension_registry
from . import register_api

for _mod in (base_domain, domain_registry, prefs_extension_registry, register_api):
    try:
        reload(_mod)
    except Exception:
        pass

from .base_domain import BaseDomain
from .domain_registry import DomainRegistry
from .prefs_extension_registry import PrefsExtensionRegistry, PrefsExtensionSpec
from .register_api import (
    UnifiedFeatureExtension,
    UnifiedRegistry,
    SUPERSKIN_OT_execute_action,
    register_operator,
    unregister_operator,
)
