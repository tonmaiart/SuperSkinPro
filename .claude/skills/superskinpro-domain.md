---
name: superskinpro-domain
description: Use this skill for ANY task touching a SuperSkinPro feature domain under the features/ folder. This covers three modes: (1) CREATING — scaffolding a new domain package, wiring registry, writing operators/prefs/logic; (2) RECHECKING — auditing an existing domain for architecture violations, missing files, or broken invariants; (3) VERIFYING — confirming a domain is complete and correct before code handoff or PR. Trigger on any prompt mentioning "new domain", "new feature", "add feature", "create domain", "recheck feature", "verify feature", "audit domain", "check domain", "review feature", "is this domain correct", "validate feature", or any request to inspect, scaffold, or modify files under features/. Always trigger when the task involves domain files such as ops.py, prefs.py, logic.py, or the domain class file inside any features/ package.
---
 
# SuperSkinPro — Feature Domain Skill
 
This skill covers the full lifecycle of a SuperSkinPro Extra Domain:
creating a new one, rechecking an existing one, and verifying correctness
before handoff. Jump to the relevant mode below.
 
- **[Mode A: Create](#mode-a-create)** — Building a new domain from scratch
- **[Mode B: Recheck](#mode-b-recheck)** — Auditing an existing domain for violations
- **[Mode C: Verify](#mode-c-verify)** — Pre-handoff correctness gate
---
 
## Architecture Contract (Read First)
 
```
Blender Operator → run_domain() (shared/op_exec.py)
                 → CoreFacade → DomainRegistry
                 → FeatureDomain.execute()
                 → CoreFacade  ← ONLY entry point into core/
```
 
**Absolute rules:**
- Feature code MUST use `CoreFacade` exclusively. Never import `UIController` or any `core/*` sub-module directly.
- Never import from sibling feature packages (`features/other_feature/`).
- Operators are thin shells — no heavy mutations inside `execute()`. Use `run_domain()` from `shared/op_exec.py`.
- Never modify `bl_idname`, `bl_label`, or operator class names after registration (breaks keymaps/RNA).
- `@bpy.app.handlers.persistent` is MANDATORY as innermost decorator on all handler callbacks.
---
 
## Mode A: Create
 
6-step blueprint for building a new domain from scratch.
 
### Step 1 — Create Package Directory
 
```
features/my_feature/
├── __init__.py
├── default_config.json
├── my_feature_domain.py
├── logic.py
├── ops.py
├── prefs.py
└── README.md          ← MANDATORY, write this FIRST before any logic
```
 
**README.md minimum content:**
1. Exact `domain_id` string and list of action strings
2. Data flow: Operator → Domain → CoreFacade (what is read, what is written)
3. File manifest (one line per file)
4. Guardrails and invariants (side-effects, float handling, undo gates, etc.)
The README must stay in sync with code — update it in the same edit whenever
action strings, prefs, or math logic change.
 
---
 
### Step 2 — Domain Class (`my_feature_domain.py`)
 
```python
from ...registry import BaseDomain, DomainRegistry
from ...core.facade import CoreFacade
 
class MyFeatureDomain(BaseDomain):
    def get_id(self) -> str:
        return "my_feature"           # must be unique across all domains
 
    def get_actions(self) -> list[str]:
        return ["my_action_string"]   # all action strings this domain handles
 
    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        if action == "my_action_string":
            layer_dict = core_facade.get_active_layer_dict()
            # ... call logic.py functions ...
            core_facade.write_layer_dict(result)
            core_facade.finish()
            return {"status": "FINISHED"}
        return {"status": "CANCELLED"}
 
DomainRegistry.register(MyFeatureDomain())   # self-register at import time
```
 
---
 
### Step 3 — Factory Defaults (`default_config.json`)
 
```json
{
  "setting_multiplier": 0.5,
  "enable_debug_overlay": false
}
```
 
---
 
### Step 4 — Preferences (`prefs.py`)
 
```python
import bpy, os
from ...registry.prefs_extension_registry import PrefsExtensionRegistry, PrefsExtensionSpec
 
class SSPrefMyFeature(bpy.types.PropertyGroup):
    setting_multiplier: bpy.props.FloatProperty(name="Value", default=0.5)
 
def draw_section(layout):
    wm = bpy.context.window_manager
    prefs = wm.superskin_my_feature_prefs
    layout.prop(prefs, "setting_multiplier")
 
def populate(data: dict):
    wm = bpy.context.window_manager
    wm.superskin_my_feature_prefs.setting_multiplier = data.get("setting_multiplier", 0.5)
 
def serialize_into(full_dict: dict):
    wm = bpy.context.window_manager
    full_dict["my_feature"] = {
        "setting_multiplier": wm.superskin_my_feature_prefs.setting_multiplier,
    }
 
def register():
    bpy.utils.register_class(SSPrefMyFeature)
    bpy.types.WindowManager.superskin_my_feature_prefs = bpy.props.PointerProperty(
        type=SSPrefMyFeature, options={'SKIP_SAVE'}
    )
    PrefsExtensionRegistry.register(PrefsExtensionSpec(
        json_key="my_feature",
        json_path=("my_feature",),
        section_title="My Feature",
        draw_tab="SKINNING",          # 'SKINNING' | 'CUSTOMIZE' | 'SYSTEM'
        draw_section_fn=draw_section,
        populate_fn=populate,
        serialize_into_fn=serialize_into,
        defaults_path=os.path.join(os.path.dirname(__file__), "default_config.json"),
    ))
 
def unregister():
    PrefsExtensionRegistry.unregister("my_feature")
    del bpy.types.WindowManager.superskin_my_feature_prefs
    bpy.utils.unregister_class(SSPrefMyFeature)
```
 
---
 
### Step 5 — Package Lifecycle (`__init__.py`)
 
```python
from importlib import reload
from . import prefs, logic, ops, my_feature_domain
 
# Bottom-up reload — foundations before wrappers
for mod in (prefs, logic, ops, my_feature_domain):
    try:
        reload(mod)
    except Exception:
        pass
 
def register():
    prefs.register()
    ops.register()
    # If feature has viewport draw handlers:  draw.register()
    # If feature has keymaps:                 keymap.register()
 
def unregister():
    # If feature has keymaps:                 keymap.unregister()
    # If feature has viewport draw handlers:  draw.unregister()
    ops.unregister()
    prefs.unregister()
```
 
**Note on draw/keymap files:**
- `SpaceView3D` draw handlers → `features/<domain>/draw.py`
- Keymaps → `features/<domain>/keymap.py`
- Both must fully clean up in their own `unregister()`. Never touch
  `shader_manager.py` or `ops_shortcuts.py`.
---
 
### Step 6 — Wire into `features/__init__.py`
 
```python
# features/__init__.py  — append to existing register/unregister
from . import my_feature
 
def register():
    # ... existing domains ...
    my_feature.register()
 
def unregister():
    my_feature.unregister()
    # ... existing domains ...
```
 
Also add one row to `docs/domains/README.md`:
 
| `my_feature` | `my_feature/` | `my_action_string` | One-line summary |
 
---
 
## CoreFacade Quick Reference
 
### Read
| Method | Returns |
|---|---|
| `get_active_layer_dict()` | `{v_idx: {bone_name: weight}}` |
| `get_active_mask_dict()` | `{v_idx: float}` |
| `get_selected_verts()` | `list[int]` |
| `get_active_vg_name()` | `str` |
| `get_active_vg_id()` | `int \| None` |
| `get_obj()` | `bpy.types.Object` |
| `get_mesh()` | `bpy.types.Mesh` |
| `get_num_verts()` | `int` |
| `get_bone_locks()` | `{bone_name: bool}` |
| `get_local_mapping()` | `(bone_to_id, id_to_bone)` |
| `get_vertex_coordinates()` | `list[tuple[float,float,float]]` |
| `is_mask_context()` | `bool` |
 
### Write
| Method | Purpose |
|---|---|
| `write_layer_dict(d)` | Commit weight data to active layer |
| `write_mask_dict(d)` | Commit mask data to active layer |
| `finish()` | Reflatten + redraw (full) |
| `finish(color_only=True)` | Reflatten + redraw (color only, faster) |
| `finish_color_only()` | Shorthand for above |
| `invalidate_color_only()` | GPU color flush only (no flatten) |
| `invalidate_and_redraw()` | Full cache flush |
| `show_toast(text, duration)` | HUD notification |
| `add_vg_selected(obj, name)` | Add bone to selection pool |
| `remove_vg_selected(obj, name)` | Remove bone from selection pool |
 
**Escape hatch:** `get_ctrl()` returns raw `UIController` — use only for
orchestrations not exposed on the facade. Avoid in normal feature code.
 
---
 
## Active Bone — Critical Guardrail
 
```python
# CORRECT
active_idx = obj.superskin_storage.last_clicked_index
 
# FORBIDDEN — never read this for SuperSkin bone state
active_idx = obj.vertex_groups.active_index
```
 
See `docs/bug-history/0003` for the desync failure mode.
 
---
 
## Deform Generation Bump
 
Any path that flattens weights to the mesh MUST trigger the deform generation
bump so the GPU visualizer detects the shape change. Calling `core_facade.finish()`
handles this automatically. If calling a lower-level flatten path directly,
call `bump_deform_generation()` explicitly afterward.
 
See `docs/bug-history/0010`.
 
---
 
 
## Mode A: Create — Pre-Handoff Checklist
 
Run this after completing all 6 steps before handing off to CodeWhale.
 
- [ ] `README.md` written first; describes domain_id, actions, data flow, guardrails
- [ ] Domain class inherits `BaseDomain`, `get_id()` returns unique string
- [ ] `DomainRegistry.register(MyFeatureDomain())` called at module level in `*_domain.py`
- [ ] No imports from `core/*` sub-modules (only `core.facade.CoreFacade`)
- [ ] No imports from sibling `features/*` packages
- [ ] `prefs.py` registers `PropertyGroup` on `WindowManager` with `options={'SKIP_SAVE'}`
- [ ] `PrefsExtensionRegistry.register(...)` called in `prefs.register()`
- [ ] `__init__.py` has bottom-up reload loop before `register()`
- [ ] `prefs.register()` called inside package `register()`
- [ ] Domain row added to `docs/domains/README.md`
- [ ] `features/__init__.py` imports and calls `my_feature.register()` / `unregister()`
- [ ] Draw handlers and keymaps (if any) live in `draw.py` / `keymap.py` and clean up in own `unregister()`
- [ ] Active bone read from `superskin_storage.last_clicked_index`, not `vertex_groups.active_index`
- [ ] `finish()` called after any weight write
---
 
## Mode B: Recheck
 
Use when asked to **audit** an existing domain for architecture violations,
missing files, or broken invariants. Read the domain's files, then run through
every item below and report findings grouped by severity.
 
### B1 — File Completeness
 
Open `features/<domain>/` and confirm every required file exists:
 
| File | Required | Notes |
|---|---|---|
| `__init__.py` | ✅ | Must have reload loop + lifecycle hooks |
| `*_domain.py` | ✅ | One domain class, `DomainRegistry.register()` at module level |
| `ops.py` | ✅ | Thin operator shells only |
| `prefs.py` | ✅ | PropertyGroup on `WindowManager`, `PrefsExtensionRegistry` |
| `default_config.json` | ✅ | Keys must match what `populate_fn` reads |
| `README.md` | ✅ | Must match current code (domain_id, actions, data flow) |
| `logic.py` | ⚠️ optional | Required if domain has non-trivial computation |
| `draw.py` | ⚠️ optional | Required if domain registers draw handlers |
| `keymap.py` | ⚠️ optional | Required if domain registers keymaps |
 
### B2 — Architecture Boundary Violations
 
Grep / read for these patterns and flag every occurrence:
 
```
VIOLATION: import from core.<anything except facade>
VIOLATION: import from features.<other_domain>
VIOLATION: heavy logic inside Operator.execute() body
VIOLATION: vertex_groups.active or vertex_groups.active_index read for bone state
VIOLATION: write to native VertexGroup.lock_weight for SuperSkin lock state
VIOLATION: bpy.app.handlers callback missing @bpy.app.handlers.persistent
VIOLATION: push() or sync_checksum() called in new feature code (no-op stubs)
```
 
### B3 — Registration Integrity
 
- `__init__.py`: reload loop covers ALL sibling modules in bottom-up order
  (foundations `logic`, `prefs` before wrappers `ops`, `*_domain`)
- `prefs.register()` invoked inside package `register()`
- `DomainRegistry.register(...)` called at **module level** in `*_domain.py`,
  not inside a function
- `PrefsExtensionRegistry.register(...)` called inside `prefs.register()`
- `features/__init__.py` lists this domain in both `register()` and `unregister()`
### B4 — Write-Path Correctness
 
For every operator that modifies weight or mask data, confirm:
1. Data read via `CoreFacade` (`get_active_layer_dict`, `get_active_mask_dict`, etc.)
2. Result written back via `write_layer_dict` / `write_mask_dict`
3. `finish()` called after write (or `finish(color_only=True)` for color-only paths)
4. Active bone sourced from `obj.superskin_storage.last_clicked_index`
### B5 — README Sync
 
Compare `README.md` against actual code:
- Action strings in `get_actions()` all documented?
- Data flow description still accurate?
- Any new prefs added to `prefs.py` also documented?
- Guardrails section covers current invariants?
**Report format for Recheck:**
```
DOMAIN: <name>
SEVERITY: BLOCKER | WARNING | INFO
 
[BLOCKER] <file>:<line> — <violation description>
[WARNING] <file>:<line> — <issue description>
[INFO]    <file> — <observation>
 
SUMMARY: X blockers, Y warnings, Z info items
```
 
---
 
## Mode C: Verify
 
Use when asked to **confirm a domain is complete and correct** before a
code handoff to CodeWhale or before merging. This is a stricter pass than
Recheck — every item must be ✅ with no exceptions.
 
### Step C1 — Run Mode B Recheck first
If any BLOCKER exists → stop, report, do not proceed to handoff.
 
### Step C2 — Functional Completeness
 
Confirm the domain covers its declared scope:
- All action strings in `get_actions()` have matching `if action == ...` branches in `execute()`
- No action returns `{"status": "FINISHED"}` with an empty body (silent no-op)
- `default_config.json` keys are consumed by `populate_fn` in `prefs.py`
- `serialize_into_fn` writes back the same keys that `populate_fn` reads
### Step C3 — Operator Shell Rule
 
Each operator in `ops.py`:
- Has a unique `bl_idname` (pattern: `SUPERSKIN_OT_<domain>_<action>`)
- `execute()` delegates to `run_ctrl` or `run_domain` from `shared/op_exec.py`
- Contains no weight math, no direct `bpy.data` mutations inside `execute()`
### Step C4 — Cleanup Completeness
 
For each resource registered by the domain:
- `bpy.types.WindowManager.<prop>` registered in `prefs.register()` →
  deleted with `del` in `prefs.unregister()`
- `bpy.utils.register_class(...)` in `prefs.register()` →
  `bpy.utils.unregister_class(...)` in `prefs.unregister()`
- Draw handlers registered in `draw.register()` →
  removed in `draw.unregister()`
- Keymaps registered in `keymap.register()` →
  cleared in `keymap.unregister()`
### Step C5 — Final Sign-off
 
Only issue a "VERIFIED — ready for handoff" when all of the following hold:
- Mode B produced zero BLOCKERs
- C2, C3, C4 all pass
- README.md is in sync with current code
**If any item fails:** report as `VERIFY FAILED — <reason>` and list what
must be fixed before re-running verification.
