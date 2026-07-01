"""Shared list-widget infrastructure — moved from ui/list_widget/ so that
feature domains under features/ can import the base classes and helpers
without creating cross-package ui/ dependencies.

Exports (public):
    SuperSkinListMixin          - mixin for concrete bpy.types.UIList subclasses
    draw_list_with_sidebar      - layout helper (template_list + search + side buttons)
    register_adapter            - register a ListSelectionAdapter for a domain
    resolve_row_click_selection - pure function: modifier-key range-select / toggle logic
    ListSelectionAdapter        - ABC for domain-specific multi-select state
    get_adapter                 - retrieve a registered adapter by domain key

The canonical _adapter_registry lives in select_ops.py here; ui/list_widget/
re-exports from this package so all consumers share the same singleton.
"""

from importlib import reload

from . import base_list
from . import select_ops
from . import layout

from .base_list import SuperSkinListMixin
from .layout import draw_list_with_sidebar
from .select_ops import (
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
