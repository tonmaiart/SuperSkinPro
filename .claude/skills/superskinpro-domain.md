---
name: superskinpro-domain
description: Use this skill for ANY task touching a SuperSkinPro feature domain under the features/ folder. This covers three modes: (1) CREATING — scaffolding a new domain package, wiring the UnifiedRegistry, writing ops/logic/the feature class; (2) RECHECKING — auditing an existing domain for architecture violations, missing files, or broken invariants; (3) VERIFYING — confirming a domain is complete and correct before code handoff or PR. Trigger on any prompt mentioning "new domain", "new feature", "add feature", "create domain", "recheck feature", "verify feature", "audit domain", "check domain", "review feature", "is this domain correct", "validate feature", or any request to inspect, scaffold, or modify files under features/. Always trigger when the task involves domain files such as ops.py, logic.py, or the `<name>_feature.py` file inside any features/ package.
---
 
# SuperSkinPro — Feature Domain Skill
 
This skill covers the full lifecycle of a SuperSkinPro Extra Domain:
creating a new one, rechecking an existing one, and verifying correctness
before handoff. Jump to the relevant mode below.

**Before opening any file:** invoke `superskinpro-locate` for the target
domain's `README.md` and the general reading-discipline rules. Read that
domain's `README.md` in full before opening `<name>_feature.py`, `ops.py`,
or `logic.py`.
 
- **[Mode A: Create](#mode-a-create)** — Building a new domain from scratch
- **[Mode B: Recheck](#mode-b-recheck)** — Auditing an existing domain for violations
- **[Mode C: Verify](#mode-c-verify)** — Pre-handoff correctness gate
---
 
## Architecture Contract (Read First)
 
```
Blender Operator → run_domain_via_unified() (interface/utils/op_exec.py)
                 → CoreFacade → UnifiedRegistry.execute(domain_id, action, ...)
                 → UnifiedFeatureExtension.execute()
                 → CoreFacade  ← ONLY entry point into core/
```
 
**Absolute rules:**
- Feature code MUST use `CoreFacade` exclusively. Never import `core/*` sub-modules directly — `core/facade/README.md` is the sole contract doc. (`UIController` no longer exists as a separate class; `CoreFacade` absorbed it — `get_ctrl()` now just `return self`.)
- Never import from sibling feature packages (`features/other_feature/`).
- Operators are thin shells — no heavy mutations inside `execute()`. Use `run_domain_via_unified()` from `interface/utils/op_exec.py`.
- Never modify `bl_idname`, `bl_label`, or operator class names after registration (breaks keymaps/RNA).
- `@bpy.app.handlers.persistent` is MANDATORY as innermost decorator on all handler callbacks.
- A domain is a single class inheriting `UnifiedFeatureExtension` (`interface/registry/register_api.py`) — there is no separate `BaseDomain`/`DomainRegistry`/standalone `prefs.py` split anymore. Do not recreate that pattern.
---
 
## Mode A: Create
 
5-step blueprint for building a new domain from scratch (matches
`features/README.md`'s current Unified Component Architecture blueprint).
 
### Step 1 — Create Package Directory
 
```
features/my_feature/
├── __init__.py
├── default_config.json
├── my_feature_feature.py   ← single entry point: PropertyGroups, action dispatch, UI, persistence
├── logic.py
├── ops.py
└── README.md          ← MANDATORY, write this FIRST before any logic
```
 
There is no separate `prefs.py` or `*_domain.py` file — everything that
used to be split across `BaseDomain` + `prefs.py` now lives in one class
inheriting `UnifiedFeatureExtension`.
 
**README.md minimum content:**
1. Exact `domain_id` string and list of action strings
2. Data flow: Operator → `UnifiedRegistry` → Feature class → CoreFacade (what is read, what is written)
3. File manifest (one line per file)
4. Guardrails and invariants (side-effects, float handling, undo gates, etc.)
The README must stay in sync with code — update it in the same edit whenever
action strings, PropertyGroup fields, or math logic change.
 
---
 
### Step 2 — Feature Class (`my_feature_feature.py`)
 
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
    domain_id = "my_feature"          # must be unique across all domains
    actions = ["my_action_string"]    # all action strings this domain handles
    section_title = "My Feature"
    draw_tab = "SKINNING"             # 'LAYER' | 'SKINNING' | 'PREFERENCE'
    defaults_path = _DEFAULTS_PATH

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        if action == "my_action_string":
            layer_dict = core_facade.read_active_layer()
            # ... call logic.py functions ...
            core_facade.write_active_layer(result)
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
 
---
 
### Step 3 — Factory Defaults (`default_config.json`)
 
```json
{
  "setting_multiplier": 0.5,
  "enable_debug_overlay": false
}
```
 
---
 
### Step 4 — Package Lifecycle (`__init__.py`)
 
```python
from importlib import reload
from . import logic, ops, my_feature_feature
 
# Bottom-up reload — foundations before wrappers
for mod in (logic, ops, my_feature_feature):
    try:
        reload(mod)
    except Exception:
        pass
 
def register():
    my_feature_feature.register()
    ops.register()
    # If feature has viewport draw handlers:  draw.register()
    # If feature has keymaps:                 keymap.register()
 
def unregister():
    # If feature has keymaps:                 keymap.unregister()
    # If feature has viewport draw handlers:  draw.unregister()
    ops.unregister()
    my_feature_feature.unregister()
```
 
**Note on draw/keymap files:**
- `SpaceView3D` draw handlers → `features/<domain>/draw.py`
- Keymaps → `features/<domain>/keymap.py`
- Both must fully clean up in their own `unregister()`. Never touch
  `shader_manager.py` or `ops_shortcuts.py`.
---
 
### Step 5 — Wire into `features/__init__.py`
 
```python
# features/__init__.py  — append to the _modules tuple
from . import my_feature

_modules = (
    # ... existing domains ...
    my_feature,
)
```
 
Also add one row to `features/README.md`'s "Current Domain Registry" table:
 
| `my_feature` | `features/my_feature/` | `my_action_string` | `SKINNING` |
 
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
 
**Escape hatch:** `get_ctrl()` returns `self` — `CoreFacade` IS the ctrl now
(there is no separate `UIController` instance). It exists as a naming
convenience for orchestration code written before the merge; prefer the
explicit facade methods above in new feature code.

**Note:** `normalize_weights(layer_dict, vertex_index, active_vg_name)` —
per-vertex normalization (not `bone_locks`/`is_mask` kwargs).
 
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
 
Run this after completing all 5 steps before handing off.
 
- [ ] `README.md` written first; describes domain_id, actions, data flow, guardrails
- [ ] A single class inherits `UnifiedFeatureExtension` in `<name>_feature.py`; `domain_id` is a unique class attribute
- [ ] No standalone `prefs.py` or `*_domain.py` file was created (PropertyGroup + dispatch live together in `<name>_feature.py`)
- [ ] `UnifiedRegistry.register(MyFeatureFeature())` called inside `register()` in `<name>_feature.py`
- [ ] No imports from `core/*` sub-modules (only `core.facade.CoreFacade`)
- [ ] No imports from sibling `features/*` packages
- [ ] PropertyGroup registered directly on `WindowManager` as `superskin_<domain>_prefs` with `options={'SKIP_SAVE'}`
- [ ] `__init__.py` has bottom-up reload loop before `register()`
- [ ] `<name>_feature.register()` called inside package `register()`
- [ ] Domain row added to `features/README.md`'s "Current Domain Registry" table
- [ ] `features/__init__.py`'s `_modules` tuple includes the new domain
- [ ] Draw handlers and keymaps (if any) live in `draw.py` / `keymap.py` and clean up in own `unregister()`
- [ ] Active bone read from `superskin_storage.last_clicked_index`, not `vertex_groups.active_index`
- [ ] `finish()` (or `write_active_layer()`, which calls it) invoked after any weight write
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
| `<name>_feature.py` | ✅ | One class inheriting `UnifiedFeatureExtension`, PropertyGroup(s), `register()`/`unregister()` calling `UnifiedRegistry.register()`/`unregister()` |
| `ops.py` | ✅ | Thin operator shells only |
| `default_config.json` | ✅ | Keys must match what `populate()` reads |
| `README.md` | ✅ | Must match current code (domain_id, actions, data flow) |
| `logic.py` | ⚠️ optional | Required if domain has non-trivial computation |
| `draw.py` | ⚠️ optional | Required if domain registers draw handlers |
| `keymap.py` | ⚠️ optional | Required if domain registers keymaps |
| `prefs.py` / `*_domain.py` | ❌ should NOT exist | Legacy split — flag as a violation if present (see B2) |
 
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
VIOLATION: standalone prefs.py / *_domain.py file, or class inheriting BaseDomain — the legacy split was fully collapsed into UnifiedFeatureExtension; recreating it is itself a violation
```
 
### B3 — Registration Integrity
 
- `__init__.py`: reload loop covers ALL sibling modules in bottom-up order
  (foundations `logic` before wrappers `ops`, `<name>_feature`)
- `<name>_feature.register()` invoked inside package `register()`
- `UnifiedRegistry.register(MyFeatureFeature())` called inside `register()` in
  `<name>_feature.py` (not at import time / module level — it's invoked
  explicitly from `__init__.py`'s `register()`)
- PropertyGroup registered on `WindowManager` inside the same `register()`
- `features/__init__.py`'s `_modules` tuple includes this domain (controls
  both registration and tab render order)
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
code handoff or before merging. This is a stricter pass than
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
- `execute()` delegates to `run_domain_via_unified()` from `interface/utils/op_exec.py`
- Contains no weight math, no direct `bpy.data` mutations inside `execute()`
### Step C4 — Cleanup Completeness
 
For each resource registered by the domain:
- `bpy.types.WindowManager.<prop>` registered in `<name>_feature.register()` →
  deleted with `del` in `<name>_feature.unregister()`
- `bpy.utils.register_class(...)` in `<name>_feature.register()` →
  `bpy.utils.unregister_class(...)` in `<name>_feature.unregister()`
- `UnifiedRegistry.register(...)` in `<name>_feature.register()` →
  `UnifiedRegistry.unregister(domain_id)` in `<name>_feature.unregister()`
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
