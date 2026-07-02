---
name: superskinpro-core-debug
description: Use this skill when debugging, auditing, or understanding any bug or behavior rooted inside SuperSkinPro's core/ or core_subsystems/ layers — NOT feature domains. Trigger on symptoms like: shader/visualizer not updating, weight flatten wrong, layer metadata corrupted, undo/redo broken, bone locks not syncing, Edit Mode weight ops not persisting, GPU draw errors, temp VG bridge issues, or any traceback originating from core/ files. Also trigger when the user says "core bug", "core issue", "debug core", "check core", or names a specific core file (shader_manager, pipeline, ui_controller, storage_service, etc.). Do NOT trigger for feature domain issues — use superskinpro-domain skill instead.
---
 
# SuperSkinPro — Core Debug Skill
 
This skill governs how to read, diagnose, and reason about bugs in
`core/` and `core_subsystems/`. The central discipline: **read minimum
files, stay focused, escalate to subsystems only when necessary.**

For anything outside the fixed reading order below (e.g. a specific
`features/` file, or a folder not covered by the Subsystem Deep-Dives),
invoke `superskinpro-locate` first rather than exploring ad hoc.
 
---
 
## Reading Protocol (Strict)
 
### Layer 1 — Always read first
Start every debug session with these two references. There is no separate
external "debug guide" file — the symptom → subsystem map lives inline in
this skill (Layer 2 table below + Subsystem Deep-Dives section).
 
| Reference | Purpose |
|---|---|
| Layer 2 table below (this file) | Symptom → subsystem map. Use it to identify which subsystem is relevant before opening any source. |
| `docs/bug-history/README.md` | Check whether this symptom has been seen before. |
 
### Layer 2 — Subsystem-targeted reads
Use the symptom table below to identify the minimum set of files to read.
**Read only those files.** Do not open unrelated core modules.
 
```
Symptom → symptom table below → relevant subsystem files ONLY
```
 
The six subsystems and their trigger symptoms:
 
| Subsystem | Trigger symptoms |
|---|---|
| **Bone Lock** | Lock toggle has no effect, native VG lock diverges from SuperSkin metadata |
| **Layer Metadata** | Names, visibility, bone-selection, active-bone lost or not restored on layer switch |
| **Weight Flatten / Compositor** | Weights in viewport don't match storage, wrong normalization, missing bones |
| **Temp VG Bridge** | Edit Mode weight ops don't persist, undo/redo corrupts active-layer data |
| **Bone Identity / Orphan** | Bones appear orphaned after rename/delete, weight data references missing VGs |
| **GPU Visualizer / Shader** | Overlay doesn't update, wrong colors, draw error in console |
 
### Layer 3 — core_subsystems (escalate only when necessary)
`core/` re-exports several things from `core_subsystems/`. Do NOT read
`core_subsystems/` files preemptively.
 
Only open a `core_subsystems/` file when:
- The traceback originates there, OR
- A core file you already read explicitly imports from it and the
  bug behavior is in that import
**What each subsystem covers (for targeted escalation):**
 
| Package / file | What it owns |
|---|---|
| `rust_weight_engine/rust_weight_engine.py` | Binary loading, dispatch, `RustWeightEngine`, `RustUnavailableError` |
| `rust_weight_engine/flat_array_bridge.py` | CSR/flat array FFI conversion |
| `rust_weight_engine/data_bridge.py` | Int/string-keyed layer dict conversion for FFI |
| `layer_compositor/layer_compositor.py` + `codec.py` | Layer metadata CRUD, compositing entry point, encode/decode |
| `topology_cache_manager/` (`topology_cache_manager.py`, `proximity_analyzer.py`) | VG-index mapping cache, mesh-neighbor topology, bone proximity/display-order |
| `context_selection_service/` | Viewport selection, mask-context detection, `normalize_weights` |
| `license_gateway/license_gateway.py` | `LicenseGateway` — Gumroad verification, Pro-tier gating — escalate only for license/activation bugs |
| `preferences/` (legacy, retained pending migration) | `PreferencesService`, ramp stops, palette — escalate only if prefs-related data is the bug source |
 
If you escalate to `core_subsystems/`, read only the one relevant file,
not the entire package.
 
### What never to read (unless explicitly requested)
- `features/*` — feature domains are out of scope for core debugging (use `superskinpro-domain` instead)
- `interface/*` — N-panel widgets/registry are out of scope unless the bug is a draw callback clearly registered from an `interface/` file. Note: there is no top-level `ui/` or `operators/` package anymore — panel/widget code lives in `interface/`, and operator shells live per-domain in `features/<domain>/ops.py`.
---
 
## Core Architecture Quick Reference
 
```
Blender Operator
    ↓
CoreFacade (core/facade/__init__.py)
    — CoreFacade IS the sole ctrl type; UIController no longer exists as a
      separate class. get_ctrl() just `return self`.
    ├── ReadFacadeMixin (read.py)       — active layer dict, masks, vg state
    ├── WriteFacadeMixin (write.py)     — write_layer_dict, write_mask_dict, finish()
    └── VisualizerFacadeMixin (visualizer.py) — invalidate, toast notifications
    ↓ delegates to private ui_controller/ sub-modules (never imported outside core/)
    ├── pipeline.py        — finish(), flatten_to_mesh_edit(), save/restore state
    ├── layer_crud.py      — CRUD, bone locks, layer switch, active bone
    ├── operations.py      — mirror macro, normalize_weights bridge
    └── undo_manager.py    — undo/redo orchestration
    ↓
LayerStorageService (core/layer_storage/storage_service.py)
    — single authority for ss_layer_N, ss_mask_N, ss_layers_meta
    ↓
LayerCompositor (core_subsystems/layer_compositor/layer_compositor.py)
    — pure-data metadata CRUD + composite pipeline entry point
    ↓
codec._composite_layers() (core_subsystems/layer_compositor/codec.py)
    — decode, coerce int keys, dispatch to Rust FFI
    ↓
RustWeightEngine (core_subsystems/rust_weight_engine/)
    — rust_composite_layers FFI call, top-down alpha blend
    ↓
ShaderManager (core/shaders/shader_manager.py)
    — GPU redraw invalidation, HUD toast, deform-generation bump
```
 
**Key invariants to check during debugging:**
 
```
INVARIANT: LayerStorageService is the only writer of ss_layer_N / ss_layers_meta
INVARIANT: bump_deform_generation() MUST be called after any weight flatten
INVARIANT: In Edit Mode, active layer lives in __ssp_* temp VGs (NOT ss_layer_N)
INVARIANT: ss_layers_meta is always written back after mutating a meta dict
INVARIANT: @bpy.app.handlers.persistent is MANDATORY innermost decorator on handlers
INVARIANT: active bone → superskin_storage.last_clicked_index (NOT vertex_groups.active_index)
INVARIANT: undo_manager.push() / sync_checksum() are no-op stubs — never call in new code
INVARIANT: core/preferences/ is a thin stub; the real PreferencesService lives in core_subsystems/preferences/ (legacy-flagged but still authoritative)
```
 
---
 
## Subsystem Deep-Dives
 
### Bone Lock Subsystem
 
**Source of truth:** `ss_layers_meta` field `bone_locks: {bone_name: bool}`  
Native `VertexGroup.lock_weight` is NOT authoritative — it is a UI mirror only.
 
**Write path:** `ctrl.set_bone_locks(locks)` → `layer_crud.set_bone_locks()` → `storage.write_meta_list()`  
**Sync path:** `apply_bone_locks(ctrl)` syncs metadata → `superskin_bones_collection` → UI
 
**Common failure:** Operator wrote to native `vg.lock_weight` and never updated
`superskin_bones_collection`. The UI shows no change; native VG list shows lock.
 
---
 
### Layer Metadata Subsystem
 
**Source of truth:** `mesh["ss_layers_meta"]` (JSON string)  
Fields per layer: `name`, `index`, `visible`, `bone_locks`, `mask_default`, `bone_selection`, `active_bone`
 
**Write rule:** `LayerCompositor` metadata methods return a **new list** — they
do NOT write. The caller MUST call `ctrl.storage.write_meta_list(meta)` afterward.
 
**Restore path:** `pipeline.restore_layer_state()` syncs metadata → `superskin_bones_collection`
on every layer switch. If UI state is stale after a switch, check this function.
 
---
 
### Weight Flatten / Compositor Subsystem
 
**Pipeline:**
```
storage.harvest_layer_data_map()  +  harvest_mask_data_map()
    ↓
LayerCompositor.composite_layers()  (core_subsystems/layer_compositor/layer_compositor.py)
    ↓
codec._composite_layers()  (core_subsystems/layer_compositor/codec.py)
    — decodes stored blobs, coerces int keys, dispatches to Rust FFI
    ↓
RustWeightEngine.call("rust_composite_layers", ...)
    ↓
flatten.flatten_visible_layers_to_mesh()  →  writes VertexGroup weights
    ↓
mesh.update() + obj.update_tag() + bump_deform_generation()
```
 
**Edit Mode path:** `pipeline.flatten_to_mesh_edit()` composites temp VGs
(`__ssp_*`) with other layers from `ss_layer_N`. The active layer is read
from the live BMesh deform layer, NOT from `ss_layer_N`.
 
**Common failure:** `bump_deform_generation()` not called after flatten →
visualizer's deform-generation cache key doesn't change → GPU overlay shows
pre-op shape. Fixed by ensuring `pipeline.finish()` is called (it bumps
automatically), or calling `shader_mgr.bump_deform_generation()` directly on
lower-level paths.
 
---
 
### Temp VG Bridge Subsystem
 
**Rule:** In EDIT mode, active layer data lives in `__ssp_*` vertex groups.
`ss_layer_N` is NOT updated until the user exits Edit Mode.
 
**Read path (Edit Mode):**
```python
bm = bmesh.from_edit_mesh(mesh)
layer_dict, mask_dict, active_idx = read_temp_vgs_from_bm(bm, obj)
```
 
**Write path (Edit Mode):**
```python
write_layer_to_temp_vgs_bm(obj, mesh, layer_str, id_to_bone, mask_dict)
```
 
**Bake path (on Exit Edit Mode):**
`read_temp_vgs_to_layer()` → `storage.write_layer_dict()` → `delete_temp_vgs()`
 
**Common failure:** Weight op called `storage.read_active_layer_dict()` in Edit
Mode instead of `read_temp_vgs_from_bm()` → reads stale `ss_layer_N` data,
ignoring all in-session Edit Mode changes. See `docs/bug-history/0018`.
 
**Undo restore:** `_undo_restore_in_progress` flag prevents `ShaderManager`
from mistaking BMesh undo's transient EDIT→OBJECT→EDIT bounce for a real mode
exit. Checked via `is_undo_restore_in_progress()` in `undo_manager.py`.
 
---
 
### GPU Visualizer Subsystem
 
**Three-cache architecture:**
 
| Cache | Invalidated by | Rebuilds |
|---|---|---|
| `topo_cache` | topology/deform change (deform-generation bump) | wireframe, triangle indices, world-space coords |
| `sel_cache` | topo change OR selection change | selected/unselected point batches |
| `col_cache` | topo change OR weight-data change | color triangle batch |
 
**Invalidation methods:**
- `shader_mgr.invalidate_color_only()` — clears `col_cache` only (fast path, weight ops)
- `shader_mgr.invalidate_and_redraw()` — clears all three caches (full rebuild)
- `shader_mgr.bump_deform_generation()` — flags deform change so topo/sel/col all rebuild next draw
**`_deferred_invalidate`:** `ShaderManager._on_depsgraph_update` fires a deferred
`invalidate_color_only()` on object/mesh update. If it fires on EVERY update
(even non-weight-related), check the trigger_ids filter — a regression here
caused the full-invalidation lag in `docs/bug-history/0007`.
 
**`_bone_color_map` in `BoneMode`:** Computed once per mesh name and cached.
Reset only by `invalidate_color_cache()`. If colors are wrong on first session,
check whether `_bone_color_map` was `None` when first compute was attempted
(PreferencesService not yet loaded → palette was empty → color map was empty dict
and never repopulated). See `docs/bug-history` for this pattern.
 
**First-session color bug pattern:**
`BoneMode._bone_color_map` is a class-level attribute set to `None`.
`_compute_bone_colors_map()` assigns it. But if it ran with an empty palette
(preferences not loaded yet), the assignment sticks as `{}` (not `None`),
so subsequent draws skip recomputation even after preferences load.
Fix: check `if not cls._bone_color_map` (truthy check), not `if cls._bone_color_map is None`.
 
---
 
## Diagnosis Workflow
 
```
1. Use the Layer 2 symptom table above → identify which subsystem
2. Check docs/bug-history/README.md → has this exact symptom appeared before?
3. Read ONLY the listed subsystem files
4. Check relevant INVARIANT (list above)
5. If traceback goes into core_subsystems/ → escalate only that one file
6. Propose fix → state which file and which line changes
7. Do NOT open feature or interface files unless the traceback clearly starts there
```
 
---
 
## Output Format for Bug Reports
 
When asked to diagnose or audit a core bug, structure findings as:
 
```
SUBSYSTEM: <name>
ROOT CAUSE: <one sentence>
INVARIANT VIOLATED: <which invariant from the list above, if any>
FILE: <path>:<approximate line>
FIX: <what to change>
REGRESSION RISK: <what else could break if this is changed>
BUG HISTORY: <does this match a known pattern in docs/bug-history/>
```
 
---
 
## Escalation Decision Tree
 
```
Does the traceback mention core_subsystems/?
  YES → read only that one file in core_subsystems/
  NO  → stay in core/ only
 
Is the issue clearly in a feature domain (features/)?
  YES → switch to superskinpro-domain skill
  NO  → stay here
 
Is the issue in an N-panel widget (interface/)?
  YES → read only if draw callback is clearly registered from interface/
  NO  → do not open interface/ files
```
