"""Compatibility shim — all implementations have moved to shared/list_widget/.

Maintained so that existing imports in ui/ continue to resolve without
modification.  The canonical _adapter_registry lives in shared/list_widget/
select_ops.py; importing via this shim routes to the same singleton.
"""

from importlib import reload

from SuperSkinPro.shared.list_widget import base_list, select_ops, layout
from SuperSkinPro.shared.list_widget import (
    SuperSkinListMixin,
    draw_list_with_sidebar,
    ListSelectionAdapter,
    register_adapter,
    get_adapter,
    resolve_row_click_selection,
)

for mod in (base_list, select_ops, layout):
    try:
        reload(mod)
    except Exception:
        pass


def register():
    pass  # per-domain operators are registered by their owning feature domains


def unregister():
    pass
