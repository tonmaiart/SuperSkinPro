# 📦 Developer Guide: Adding a New Extra Domain (Unified Component Architecture)

SuperSkinPro uses a strict decoupled plugin architecture. Core modules never import from feature packages. Instead, feature packages self-register a single `UnifiedFeatureExtension` instance into `UnifiedRegistry` (`interface/registry/register_api.py`), which owns action dispatch, UI layout, and JSON persistence for that domain.

```
[UI Layout Click] → SUPERSKIN_OT_execute_action (domain_id, action_id)
                  → UnifiedRegistry.get_by_id(domain_id).execute(action_id, ctx, facade)
```

### 📖 Strict Feature Documentation Rule (The README Invariant)
Every single feature package under `features/` MUST own and continuously maintain a local `README.md`. Documentation is treated as structural code; out-of-sync or missing documentation is considered a breaking regression.

1. **Mandatory Creation:** When creating a new feature domain, a local `README.md` MUST be generated during Step 1 before writing any execution logic.
2. **Continuous Synchronization (On Edit):** Whenever you modify, expand, or refactor files inside a feature package (e.g., adding a new action string to `<name>_feature.py`, changing PropertyGroup fields, or editing math loops in `logic.py`), you MUST immediately update the local `README.md` in the same execution/commit to reflect those architectural changes.
3. **Minimum README Specifications:** Every local `README.md` must strictly contain:
   * **Domain Identity:** Clearly state the exact `domain_id` string and its actionable commands.
   * **Architecture & Dataflow:** A clear textual map or visual flow of how data travels from the Blender Operator, through the domain, into the `CoreFacade`.
   * **File Manifest:** A scannable breakdown of what each file inside the package is specifically responsible for.
   * **Guardrails & Invariants:** Document any side-effects, technical boundary conditions, or specific constraints (e.g., undo gates, float rounding, context suppression) that the domain enforces.

Before concluding any feature modification task, re-read the updated local `README.md` side-by-side with your code to guarantee 100% synchronization.

**Always Register the Extension Lifecycle:** Double-check that your package-level `__init__.py` invokes `<name>_feature.register()`. Omitting this step will prevent the collapsible section from rendering inside the master modular panel.

---

## 🏛️ The 5-Step Component Blueprint

To seamlessly plug a new feature domain (e.g., `my_feature`) into the system with zero side effects, follow this blueprint exactly.

```
[Blender Register Chain] → features/__init__.py → my_feature/__init__.py → UnifiedRegistry.register()
```

### Step 1: Establish the Package Directory
Create a dedicated package under `features/`. Every domain must be entirely self-contained:
```
features/my_feature/
├── __init__.py            # Package lifecycle manager
├── default_config.json    # Factory fallback preferences
├── my_feature_feature.py  # Single entry point: PropertyGroups, action dispatch, UI, persistence
├── logic.py                # Computational math & Rust FFI gateway
├── ops.py                  # Thin Blender Operator shells
└── README.md                # Local domain specification for agents
```

### Step 2: Implement the Feature Class (`my_feature_feature.py`)
Inherit from `UnifiedFeatureExtension` (`interface/registry/register_api.py`). You MUST interact with core datasets exclusively through `CoreFacade`. Direct imports from `core/*` sub-modules are forbidden.

```python
import bpy
import os

from ...interface.registry.register_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade

_DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "default_config.json")


def _on_changed(self, context):
    from ...core.facade import CoreFacade
    CoreFacade.save_prefs()


class SSPrefMyFeature(bpy.types.PropertyGroup):
    setting_multiplier: bpy.props.FloatProperty(name="Value", default=0.5, update=_on_changed)


class MyFeatureFeature(UnifiedFeatureExtension):
    domain_id = "my_feature"
    actions = ["my_action_string"]
    section_title = "My Feature"
    draw_tab = "SKINNING"  # 'LAYER' | 'SKINNING' | 'PREFERENCE'
    defaults_path = _DEFAULTS_PATH

    def execute(self, action, context, core_facade: CoreFacade) -> dict:
        if action == "my_action_string":
            # layer_dict = core_facade.read_active_layer()
            return {"status": "FINISHED"}
        return {"status": "CANCELLED"}

    def draw_section(self, layout, context) -> None:
        prefs = context.window_manager.superskin_my_feature_prefs
        layout.prop(prefs, "setting_multiplier")

    def populate(self, data: dict) -> None:
        ...

    def serialize_into(self, full_dict: dict) -> None:
        ...


def register():
    bpy.utils.register_class(SSPrefMyFeature)
    bpy.types.WindowManager.superskin_my_feature_prefs = bpy.props.PointerProperty(
        type=SSPrefMyFeature, options={'SKIP_SAVE'},
    )
    UnifiedRegistry.register(MyFeatureFeature())


def unregister():
    UnifiedRegistry.unregister("my_feature")
    del bpy.types.WindowManager.superskin_my_feature_prefs
    bpy.utils.unregister_class(SSPrefMyFeature)
```

### Step 3: Define Fallback Properties (`default_config.json`)
Declare initial configuration scalars. This structure is loaded via `defaults_path` and mirrored automatically across local file systems.

```json
{
  "setting_multiplier": 0.5,
  "enable_debug_overlay": false
}
```

### Step 4: Encapsulate Local Lifecycles (`__init__.py`)
Wire up internal scripts within your package, following the Deep Matrix Reload Rule (see project `CLAUDE.md`). If your feature requires keymaps or drawing viewport shaders, encapsulate them inside `keymap.py` or `draw.py` and invoke them inside these hooks.

```python
from importlib import reload
from . import logic, ops, my_feature_feature

for mod in (logic, ops, my_feature_feature):
    try:
        reload(mod)
    except Exception:
        pass


def register():
    my_feature_feature.register()
    ops.register()


def unregister():
    ops.unregister()
    my_feature_feature.unregister()
```

### Step 5: Connect to the Main Core Socket (`features/__init__.py`)
Activate the package by adding it to the `_modules` tuple inside the root feature module. Registration order controls insertion order within each tab.

```python
# features/__init__.py
from . import my_feature

_modules = (
    layer_viewer,
    deform_bone_viewer,
    weight_apply,
    auto_block_weight,
    mirror,
    clipboard,
    bone_picker,
    weight_transfer,
    multi_color_preview,
    circle_tool_adjust,
    controller,
    my_feature,  # append here
)
```

---

## 🗂️ Current Domain Registry

| Domain ID | Package | Actions | Tab |
|---|---|---|---|
| `layer_viewer` | `features/layer_viewer/` | *(viewer, non-collapsible)* | `LAYER` |
| `deform_bone_viewer` | `features/deform_bone_viewer/` | *(viewer, non-collapsible)* | `SKINNING` |
| `weight_apply` | `features/weight_apply/` | `add`, `scale`, `smooth`, `sharpen` | `SKINNING` |
| `auto_block` | `features/auto_block_weight/` | `auto` | `SKINNING` |
| `mirror` | `features/mirror/` | `mirror` | `SKINNING` |
| `clipboard` | `features/clipboard/` | `copy`, `cut`, `paste_add`, `paste_subtract`, `paste_replace`, `select_affected` | `SKINNING` |
| `circle_tool_adjust` | `features/circle_tool_adjust/` | `adjust_radius_interactive` | `SKINNING` |
| `controller` | `features/controller/` | *(cross-cutting, no actions)* | `SKINNING` |
| `bone_picker` | `features/bone_picker/` | `start_bone_picker`, `stop_bone_picker`, `clear_multi_selection` | `PREFERENCE` |
| `multi_color_preview` | `features/multi_color_preview/` | `start_multi_color`, `stop_multi_color`, `toggle_multi_color` | `PREFERENCE` |
| `weight_transfer` | `features/weight_transfer/` | `transfer_weight_maya` (also owns Export/Import Weight JSON, self-contained operators, merged in from the former `data_io` domain) | `LAYER` |

See each package's local `README.md` for domain-specific dataflow, file manifests, and guardrails.
