# 0022 — Deform Bones list stuck showing only "Mask" despite real vertex groups existing

**Date:** 2026-07-02
**Area:** `features/deform_bone_viewer/ui.py`, `interface/utils/utils.py`

## Symptom

`Deform Bones List` panel showed only the virtual "Mask" row — no real bones —
even though the active object had real vertex groups (`Bone.L`, `Bone.R`)
matching real deform bones on a linked Armature, and `ss_layers_meta` already
had a layer entry for the object. Debug log confirmed the mirror collection
(`obj.superskin_bones_collection`) genuinely only had 1 row:

```
[SSP:BONE_ID] draw_influence_list_system(): obj='Cube' superskin_bones_collection
has 1 rows, mask_rows=['Mask'], filter_mode='NONE'
```

Switching `bone_list_filter_mode` between `NONE` / `INFLUENCE` / `ORPHAN`, and
clicking the Mask row itself, changed nothing — ruling out a `filter_items`
draw-time issue, since the mirror collection itself never grew past 1 row
across any of those interactions.

## Root cause

`sync_bones_to_ui_collection()` (`interface/utils/utils.py`) — the function
that actually populates `obj.superskin_bones_collection` from the real
`vertex_groups` — is write-only and by design is called from exactly two
places: `_superskin_layers_depsgraph_handler` (`depsgraph_update_post`) and
`_superskin_layers_load_handler` (`load_post`). Neither fired during this
session:

- **F3 → Reload Scripts does not trigger `load_post`.** It only reloads
  Python modules; it is not equivalent to opening the `.blend` file. So the
  unconditional per-object sync in `_superskin_layers_load_handler` never ran.
- **Pure UI interaction (selecting a row, switching filter mode) does not
  trigger `depsgraph_update_post`** — no mesh or armature data actually
  changed, so there was nothing for the handler to react to.

`draw_influence_list_system()` (`features/deform_bone_viewer/ui.py`) has a
self-heal fallback for exactly this class of problem: a one-shot
`bpy.app.timers` callback (`_force_bones_resync`) that calls
`sync_bones_to_ui_collection()` outside the draw cycle. But the trigger
condition was:

```python
if ("ss_layers_meta" in obj.data and not mask_rows
        and not _bones_resync_pending):
    ...schedule resync...
```

`not mask_rows` only detects a **completely empty / mask-less** mirror
collection — the bootstrap case (fresh layer system, addon just installed,
mirror collection never built once). It does not detect "the Mask row exists
but every real bone row is missing," which is exactly the state this session
was stuck in (the Mask row had presumably been synced once, earlier, before
the real vertex groups existed on the object). Since `mask_rows` was
non-empty, the self-heal condition was never `True`, so the timer was never
scheduled, and the stale 1-row collection persisted indefinitely.

Two related-but-secondary staleness gaps were also found and hardened while
tracing this, in case a similar-smelling report comes in again:

1. `_get_cached_display_order()`'s cache key was `(mesh_name, arm_name,
   len(deform_bones))` — a bone-**count**-based key. Deleting one deform bone
   and adding a differently-named one (net count unchanged) would return a
   stale cached name list missing the new bone, even on a session where the
   depsgraph handler *did* fire correctly. Changed to
   `frozenset(deform_bones)` so identity changes, not just count changes,
   invalidate the cache.
2. `_superskin_layers_depsgraph_handler` only reacts to `depsgraph.updates`
   whose `update.id` is a Mesh-type `Object` — an Armature-only edit (e.g.
   toggling a bone's `use_deform`, or an "apply armature preset" operator)
   tags the Armature ID, not the Mesh, so the handler's `MESH` branch never
   fires and the mesh's bones mirror never resyncs. Added a second branch
   that detects Armature-type updates and re-syncs every mesh with an
   `ARMATURE` modifier pointing at it.

Neither (1) nor (2) was the actual blocker in this report — the debug log
showed `_get_display_order_impl()` (added mid-investigation) never fired at
all during the session, meaning `sync_bones_to_ui_collection()` itself was
never called, which only the self-heal gap (main fix, below) explains.

## Why it wasn't obvious

The natural first hypotheses (checked and partially true, see above) were
"the bone filtering logic is dropping the VG" (cache staleness,
`use_deform` mismatch) or "the depsgraph handler didn't fire for the right
reason" (Armature vs Mesh ID). Both looked plausible and were real gaps
worth closing, but neither explained why the collection was stuck at exactly
1 row across *any* further interaction in the session, including operators
that should have forced a resync. The actual blocker only became clear after
adding a debug log directly inside `_get_display_order_impl()` (the function
one level below the cache) and observing that it **never printed at all** —
proving the bug was upstream of any bone-filtering logic, in whether
`sync_bones_to_ui_collection()` was being invoked in the first place.

## Fix

**`features/deform_bone_viewer/ui.py` → `draw_influence_list_system()`**
Broadened the self-heal trigger condition from "Mask row missing" to
"Mask row missing OR collection has only the Mask row while the object has
at least one real vertex group" (`only_mask_present = len(col) <= 1 and
vg_count > 0`). Added a per-object `_bones_resync_attempted_vg_count` guard
keyed on the live vertex-group count so a mesh with genuinely zero
deform-matching vertex groups doesn't get the timer re-scheduled on every
redraw — it only re-attempts when the vertex-group count actually changes
from what was last attempted.

**`interface/utils/utils.py`**
- `_get_cached_display_order()`: cache key changed from
  `len(deform_bones)` to `frozenset(deform_bones)`.
- `_superskin_layers_depsgraph_handler()`: added an Armature-update branch
  that re-syncs every mesh with a matching `ARMATURE` modifier.

## How it was diagnosed

1. Reproduced with `bone_list_filter_mode` cycled through all three values —
   ruled out `filter_items` (draw-time) since the mirror collection's own row
   count never changed.
2. Read `sync_bones_to_ui_collection()` and `_get_display_order_impl()`
   (`interface/utils/utils.py`) to find where a real VG could get dropped
   from the `order` list before it's mirrored into the collection.
3. Added a temporary `DebugLogService.log("bone_id", ...)` call inside
   `_get_display_order_impl()` printing `arm_obj`, `deform_bones`, and
   `vg_names` — the decisive step. It never printed across the entire
   session, which eliminated every bone-filtering hypothesis and pointed
   directly at the call site (`sync_bones_to_ui_collection` never invoked)
   instead.
4. User-provided screenshots (Armature modifier panel, Deform Bones list,
   Vertex Groups list, `ss_bone_uuid_map`/`ss_layers_meta` custom properties,
   Armature outliner) confirmed the real VGs and bones existed and matched
   by name, ruling out a data-identity mismatch and narrowing the bug to
   "sync never ran" rather than "sync ran but filtered the bone out."

## General lesson

A "self-heal on next draw" fallback timer is only as good as its staleness
detection. Here the detection reused a narrower signal ("is the bootstrap
row present") to stand in for a broader one ("is the mirror collection in
sync with the live vertex groups"), which is a common shortcut when the
narrow signal is cheap to check and was sufficient for the original bug it
was written for (see the mirror-collection refactor referenced in
`features/deform_bone_viewer/README.md`). When adding a self-heal/backfill
gate like this, re-check periodically whether the cheap proxy condition
still covers every way the underlying state can go stale — new call paths
(an F3 reload skipping `load_post`, an Armature-only edit skipping the
Mesh-ID branch) keep expanding the ways the proxy's blind spot gets hit.
