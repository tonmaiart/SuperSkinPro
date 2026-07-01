# 📦 Developer Guide: Adding a New Extra Domain (Plugin Architecture)

SuperSkinPro uses a strict decoupled Pointer-Plugin Architecture. Core modules never import from feature packages. Instead, feature packages self-register into pre-existing functional sockets via registries.

### 📖 Strict Feature Documentation Rule (The README Invariant)
Every single feature package under `features/` MUST own and continuously maintain a local `README.md`. Documentation is treated as structural code; out-of-sync or missing documentation is considered a breaking regression.

1. **Mandatory Creation:** When creating a new feature domain, a local `README.md` MUST be generated during Step 1 before writing any execution logic.
2. **Continuous Synchronization (On Edit):** Whenever you modify, expand, or refactor files inside a feature package (e.g., adding a new action string to `*_domain.py`, changing property blocks in `prefs.py`, or editing math loops in `logic.py`), you MUST immediately update the local `README.md` in the same execution/commit to reflect those architectural changes.
3. **Minimum README Specifications:** Every local `README.md` must strictly contain:
   * **Domain Identity:** Clearly state the exact `domain_id` string and its actionable commands.
   * **Architecture & Dataflow:** A clear textual map or visual flow of how data travels from the Blender Operator, through the Domain, into the `CoreFacade`.
   * **File Manifest:** A scannable breakdown of what each file inside the package is specifically responsible for.
   * **Guardrails & Invariants:** Document any side-effects, technical boundary conditions, or specific constraints (e.g., undo gates, float rounding, context suppression) that the domain enforces.

Before concluding any feature modification task, re-read the updated local `README.md` side-by-side with your code to guarantee 100% synchronization.

**Always Register Prefs Lifecycles:** Double-check that your package level `__init__.py` invokes `prefs.register()`. Omitting this step will prevent the collapsible section from rendering inside the master modular panel.

---

## 🏛️ The 6-Step Component Blueprint

To seamlessly plug a new feature domain (e.g., `my_feature`) into the system with zero side effects, follow this blueprint exactly.

[Blender Register Chain] -> features/init.py -> my_feature/init.py -> Self-Registration Sockets


### Step 1: Establish the Package Directory
Create a dedicated package under `features/`. Every domain must be entirely self-contained:
features/my_feature/
├── init.py           # Package lifecycle manager
├── default_config.json   # Factory fallback preferences
├── my_feature_domain.py  # Logic & Action execution bridge
├── logic.py              # Computational math & Rust FFI gateway
├── ops.py                # Thin Blender Operator shells
├── prefs.py              # PropertyGroups & UI drawing descriptors
└── README.md             # Local domain specification for agents


### Step 2: Implement the Logic Socket (`my_feature_domain.py`)
Inherit from `BaseDomain` to register functional action strings. You MUST interact with core datasets exclusively through `CoreFacade`. Direct imports from `core/*` sub-modules are forbidden.

```python
from ...registry import BaseDomain, DomainRegistry
from ...core.facade import CoreFacade

class MyFeatureDomain(BaseDomain):
    def get_id(self) -> str: 
        return "my_feature" # Must match Domain ID string

    def get_actions(self) -> list[str]: 
        return ["my_action_string"]

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        if action == "my_action_string":
            # 1. Enforce transactional state baseline
            core_facade.push_undo(gate="checksum")
            
            # 2. Extract mapped data structures from Facade
            # layer_dict = core_facade.get_active_layer_dict()
            
            # 3. Dispatch to local computational logic
            return {"status": "FINISHED"}
        return {"status": "CANCELLED"}

# Register instance automatically at import time
DomainRegistry.register(MyFeatureDomain())
Step 3: Define Fallback Properties (default_config.json)
Declare initial configuration scalars. This structure is mirrored automatically across local file systems.

JSON
{
  "setting_multiplier": 0.5,
  "enable_debug_overlay": false
}
Step 4: Inject Preferences & UI (prefs.py)
Bind persistent variables to a SKIP_SAVE PropertyGroup on WindowManager. Register the specification via PrefsExtensionRegistry so the core PreferencesService handles I/O routing out-of-the-box.

Python
import bpy
import os
from ...registry.prefs_extension_registry import PrefsExtensionRegistry, PrefsExtensionSpec

class SSPrefMyFeature(bpy.types.PropertyGroup):
    setting_multiplier: bpy.props.FloatProperty(name="Value", default=0.5)

def draw_section(layout):
    # Pure UI layout instructions using the WindowManager pointer
    pass

# Mandatory data lifecycle mapping hooks
def populate(data: dict): ...
def serialize_into(full_dict: dict): ...

def register():
    bpy.utils.register_class(SSPrefMyFeature)
    bpy.types.WindowManager.superskin_my_feature_prefs = bpy.props.PointerProperty(
        type=SSPrefMyFeature, options={'SKIP_SAVE'}
    )
    PrefsExtensionRegistry.register(PrefsExtensionSpec(
        json_key="my_feature",
        json_path=("my_feature",),
        section_title="My Feature Header",
        draw_tab="SKINNING", # Tab choice: 'SKINNING' | 'CUSTOMIZE' | 'SYSTEM'
        draw_section_fn=draw_section,
        populate_fn=populate,
        serialize_into_fn=serialize_into,
        defaults_path=os.path.join(os.path.dirname(__file__), "default_config.json"),
    ))

def unregister():
    PrefsExtensionRegistry.unregister("my_feature")
    del bpy.types.WindowManager.superskin_my_feature_prefs
    bpy.utils.unregister_class(SSPrefMyFeature)
Step 5: Encapsulate Local Lifecycles (__init__.py)
Wire up internal scripts within your package. If your feature requires keymaps or drawing viewport shaders, encapsulate them inside keymap.py or draw.py and invoke them inside these hooks.

Python
from importlib import reload
from . import prefs, ops, my_feature_domain

# Force-evict runtime cache lines from bottom to top
for mod in (prefs, logic, ops, my_feature_domain):
    try:
        reload(mod)
    except Exception:
        pass

def register():
    prefs.register()
    ops.register()

def unregister():
    ops.unregister()
    prefs.unregister()
Step 6: Connect to the Main Core Socket (features/__init__.py)
Activate the package by appending it to the cascading registration execution sequence inside the root feature module.

Python
# features/__init__.py
def register():
    weight_apply.register()
    auto_block_weight.register()
    # ...
    my_feature.register() # Plug your module switch here