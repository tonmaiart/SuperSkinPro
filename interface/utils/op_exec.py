"""Shared Operator.execute() body for Domain Registry-routed operators.

Used by operators/ops_weight_apply.py, clipboard/ops.py, auto_block_weight/ops.py,
bone_picker/ops.py, and multi_color_preview/ops.py. All execution is routed
through CoreFacade → DomainRegistry → FeatureDomain.

As of the Unified Component Architecture refactor, new code should prefer
``run_domain_via_unified()`` which routes through ``UnifiedRegistry``.
"""

import bpy


def run_domain(context, action: str):
    """Shared execute body for legacy Domain Registry-routed operators.

    Uses ``DomainRegistry.execute`` by action string. Prefer
    ``run_domain_via_unified()`` for new code.
    """
    from ..registry import DomainRegistry
    from ...core.facade import CoreFacade
    context.scene.superskin_internal_transaction = True
    try:
        facade = CoreFacade(context)
        result = DomainRegistry.execute(action, context, facade)
        if result.get("status") == "CANCELLED":
            return {'CANCELLED'}
        return {'FINISHED'}
    except ValueError:
        return {'CANCELLED'}
    finally:
        context.scene.superskin_internal_transaction = False


def run_domain_via_unified(context, domain_id: str, action: str):
    """Shared execute body for Unified Registry-routed operators.

    Routes through ``UnifiedRegistry.execute`` by domain_id + action.
    """
    from ..registry.register_api import UnifiedRegistry
    from ...core.facade import CoreFacade
    context.scene.superskin_internal_transaction = True
    try:
        facade = CoreFacade(context)
        result = UnifiedRegistry.execute(domain_id, action, context, facade)
        if result.get("status") == "CANCELLED":
            return {'CANCELLED'}
        return {'FINISHED'}
    except ValueError:
        return {'CANCELLED'}
    finally:
        context.scene.superskin_internal_transaction = False
