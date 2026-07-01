# Registry — Unified Component Architecture

This package provides the registration and dispatch layer for all feature
domains in SuperSkinPro. The **Unified Component Architecture** collapses the
previous dual-registry system into a single cohesive interface.

## Quick Start

Create a new feature domain in 3 steps:

### 1. Create `features/<name>/<name>_feature.py`

```python
import bpy
import os

from ...registry.unified_feature_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade

_DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "default_config.json")


class MyFeature(UnifiedFeatureExtension):
    """Unified extension for the MyFeature domain."""

    # ── Identity ──

    def get_id(self) -> str:
        return "my_feature"                       # stable domain identifier

    def get_actions(self) -> list[str]:
        return ["my_action"]                       # action strings this domain handles

    # ── UI metadata ──

    def get_section_title(self) -> str:
        return "My Feature"                        # label in collapsible header

    def get_draw_tab(self) -> str:
        return "SKINNING"                          # 'LAYER', 'SKINNING', or 'CUSTOMIZE'

    def get_defaults_path(self) -> str | None:
        return _DEFAULTS_PATH                      # return None for no persistence

    def is_collapsible(self) -> bool:
        return True                                # False for full-width viewer domains

    # ── Action dispatch ──

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        if action == "my_action":
            # ... do work via core_facade ...
            return {"status": "FINISHED"}
        return {"status": "CANCELLED", "message": f"Unknown action: {action}"}

    # ── UI layout ──

    def draw_section(self, layout, context) -> None:
        """Draw the section body. Called inside the collapsible wrapper."""
        layout.label(text="Hello from MyFeature")
        layout.operator("superskin.execute_action",
                        text="Run Action").domain_id = "my_feature"

    # ── JSON persistence ──

    def populate(self, data: dict) -> None:
        """Write data from user.json into live PropertyGroups."""

    def serialize_into(self, full_dict: dict) -> None:
        """Write live values back into full_dict for save."""


# ── Registration ──

def register():
    """Register PropertyGroups, UnifiedRegistry, and legacy compat."""
    # Register any Blender PropertyGroup classes here
    UnifiedRegistry.register(MyFeature())
    _register_legacy()


def unregister():
    """Reverse registration order."""
    _unregister_legacy()
    UnifiedRegistry.unregister("my_feature")
    # Unregister PropertyGroups here


def _register_legacy():
    """Register with legacy registries for backward compatibility."""
    try:
        from ...registry import DomainRegistry, BaseDomain, PrefsExtensionRegistry, PrefsExtensionSpec

        class _Domain(BaseDomain):
            def get_id(self): return "my_feature"
            def get_actions(self): return ["my_action"]
            def execute(self, action, context, core_facade):
                return MyFeature().execute(action, context, core_facade)
        DomainRegistry.register(_Domain())

        PrefsExtensionRegistry.register(PrefsExtensionSpec(
            json_key="my_feature",
            json_path=("my_feature",),
            section_title="My Feature",
            draw_tab="SKINNING",
            draw_section_fn=lambda layout: MyFeature().draw_section(layout, bpy.context),
            populate_fn=MyFeature().populate,
            serialize_into_fn=MyFeature().serialize_into,
            defaults_path=_DEFAULTS_PATH,
        ))
    except Exception:
        pass


def _unregister_legacy():
    try:
        from ...registry import PrefsExtensionRegistry
        PrefsExtensionRegistry.unregister("my_feature")
    except Exception:
        pass
```

### 2. Wire up `features/<name>/__init__.py`

```python
from importlib import reload

from . import <name>_feature
# ... other imports (logic, ops, draw, keymap, etc.) ...

for mod in (<name>_feature,):
    try:
        reload(mod)
    except Exception:
        pass


def register():
    <name>_feature.register()
    # ... register operators, keymaps, etc. ...


def unregister():
    # ... unregister in reverse order ...
    <name>_feature.unregister()
```

### 3. Import in `features/__init__.py`

```python
from . import <name>
```

Add `<name>` to the `_modules` tuple (order matters for tab rendering).

---

## API Reference

### `UnifiedFeatureExtension` (ABC)

Abstract base class that every feature domain must implement.

| Method | Returns | Description |
|---|---|---|
| `get_id()` | `str` | Stable domain identifier (e.g. `"mirror"`). Also used as JSON persistence key. |
| `get_actions()` | `list[str]` | All action strings handled by this domain. Return `[]` for viewer-only domains. |
| `get_section_title()` | `str` | Label text shown in the collapsible section header. |
| `get_draw_tab()` | `str` | Target tab: `'LAYER'`, `'SKINNING'`, or `'CUSTOMIZE'`. |
| `get_json_path()` | `tuple` | JSON key path for persistence. Default: `(self.get_id(),)`. |
| `get_defaults_path()` | `str \| None` | Path to `default_config.json`. Return `None` if no preferences. |
| `is_collapsible()` | `bool` | `True` (default) wraps in collapsible panel. `False` for full-width viewers. |
| `execute(action, context, core_facade)` | `dict` | Run an action. Return `{'status': 'FINISHED'}` or `{'status': 'CANCELLED', 'message': str}`. |
| `draw_section(layout, context)` | `None` | Draw the UI section body. |
| `populate(data)` | `None` | Write JSON data into live PropertyGroups. Called on load. |
| `serialize_into(full_dict)` | `None` | Write live values into the serialization dict. Called on save. |

### `UnifiedRegistry` (class-level singleton)

| Method | Description |
|---|---|
| `register(extension)` | Register or replace a feature extension. Creates expanded-state props. |
| `unregister(domain_id)` | Remove a feature extension. |
| `get_by_id(domain_id)` | Return the extension instance or `None`. |
| `get_by_tab(tab_key)` | Return all extensions for a tab, non-collapsible first. |
| `get_all()` | Return every registered extension. |
| `execute(domain_id, action, context, core_facade)` | Forward an action to the target extension. |
| `has_action(action)` | Check if any domain handles an action. |

### `SUPERSKIN_OT_execute_action` (Universal Proxy Operator)

| Property | Type | Description |
|---|---|---|
| `bl_idname` | `"superskin.execute_action"` | Operator identifier. |
| `domain_id` | `StringProperty` | Target domain identifier. |
| `action_id` | `StringProperty` | Action to execute within the domain. |

Usage in layout code:

```python
op = layout.operator("superskin.execute_action", text="Run My Action")
op.domain_id = "my_feature"
op.action_id = "my_action"
```

---

## Migration from Legacy Registries

The old `BaseDomain` / `DomainRegistry` and `PrefsExtensionSpec` /
`PrefsExtensionRegistry` systems are still operational for backward
compatibility. New features should use `UnifiedFeatureExtension` and
`UnifiedRegistry` exclusively.

To migrate an existing feature:

1. Merge `*_domain.py` + `prefs.py` into `*_feature.py` extending `UnifiedFeatureExtension`.
2. Update `__init__.py` to import and call `*_feature.register()`.
3. Delete the old `*_domain.py` and `prefs.py` files.
4. Keep the legacy `_register_legacy()` / `_unregister_legacy()` stubs until
   all callers are migrated to `UnifiedRegistry`.

---

## Tab Assignment Convention

| Tab | Typical contents |
|---|---|
| `LAYER` | layer_viewer, data_io, weight_transfer |
| `SKINNING` | deform_bone_viewer, weight_apply, mirror, clipboard, auto_block_weight, circle_tool_adjust, controller |
| `CUSTOMIZE` | bone_picker, multi_color_preview (rendered in Add-on Preferences, not N-panel) |

Viewer domains (`is_collapsible() == False`) are rendered first in their tab
so they appear at the top of the sidebar.
