# 0004 — Panel auto-collapses on layer select / add / remove / move / duplicate

**Date:** 2026-06-18
**Area:** `core/shaders/shader_manager.py`, `ui/utils.py`, `operators/ops_interface.py`, `ui/widget_tools.py`

## Symptom

After the `ui/list_widget/` refactor (which replaced the old per-domain row-click
operators with a single generic `superskin.list_select_row`), the SuperSkinPro
sidebar panel would close immediately whenever the user clicked on a layer row in
the Layers list, or performed any layer-CRUD operation (add, remove, duplicate,
move, toggle visibility). The panel needed to be manually re-opened after every
single interaction, making the Layers tab essentially unusable. Entering Edit
Mode would still correctly open the panel; the bug was specifically that it
closed on every subsequent layer operation.

## Root cause

`ShaderManager._on_depsgraph_update()` (in `core/shaders/shader_manager.py`)
detects an EDIT→non-EDIT mode transition on the active object and, when it sees
one, calls `force_close_tab()` (plus `clear_render()` /
`hide_deform_bone_overlay()`). This check ran **unconditionally** — it did not
check `context.scene.superskin_internal_transaction` at all (that flag was only
checked later, in the unrelated cache-invalidation block further down the same
function).

Every layer operation needs to round-trip the object briefly into OBJECT mode
and back to EDIT mode to safely mutate layer metadata stored in mesh Custom
Properties (which Blender forbids writing during EDIT mode). `_run_in_object_context()`
in `ui/utils.py` handles this round-trip, and several inline `mode_set` calls
in the operators and adapter do the same. Each of these round-trips fires a
depsgraph update with `obj.mode` momentarily `'OBJECT'` while
`_last_tracked_mode` still says `'EDIT'` — which is exactly the condition
`_on_depsgraph_update` uses to decide "the user left Edit Mode," so it closes
the panel even though nothing the user did was actually a real mode change.

This was compounded by a regression: the original (pre-refactor)
`SUPERSKIN_OT_layer_select_by_item.execute()` set
`context.scene.superskin_internal_transaction = True` around its own mode
round-trip. The new `LayerListAdapter.on_single_select()` didn't set this flag
at all. But setting it wouldn't have been sufficient anyway, since
`_on_depsgraph_update` never checked it for the close-tab decision in the first
place — this bug was latent in the original code too, just less consistently
triggered because the old operator happened to set the flag that suppressed the
*later* check (the invalidation block), and the timing coincidence between the
round-trip depsgraph fire and the deferred invalidation timer meant the mode
tracking had usually already been updated back to `'EDIT'` by the time a
subsequent depsgraph update fired for the weight-data change.

## Why it wasn't obvious / why a first attempt didn't catch it

The `_on_depsgraph_update` handler serves two independent purposes in the same
function body: (1) auto-close-the-panel on genuine Edit Mode exit, and (2)
invalidate the GPU visualizer cache when the mesh data changes. These two
purposes are separated by a simple early-return guard
(`if getattr(... 'superskin_internal_transaction', False): return`) that the
original authors clearly thought was protecting the whole function. But it's
placed *after* the mode-transition block, not before it — so any depsgraph
update that fired with `obj.mode == 'OBJECT'` during an internal round-trip
would trigger close-tab before ever reaching the suppression guard.

The timing is hard to reason about without tracing: `_run_in_object_context`
takes roughly 2-3 depsgraph update cycles (OBJECT switch → custom-property
write → EDIT switch), and only the middle one delivers `obj.mode == 'OBJECT'`.
The old path was working mostly by accident — the `superskin_internal_transaction`
flag *was* set by the old operator, and the invalidation early-return (line 354
in the original) happens to also prevent the handler from proceeding far enough
that a slightly-different depsgraph event would trigger the close-tab path on a
subsequent call. The refactored path removed the flag-setting from the
layer-select operator but moved it into `_run_in_object_context` — except
`_on_depsgraph_update` never checked it in the mode-transition block.

## Fix

1. **`core/shaders/shader_manager.py`** — Made the mode-transition side effects
   (clear render, hide deform-bone overlay, force-close-tab) respect
   `scene.superskin_internal_transaction`, while still always updating
   `_last_tracked_mode` so tracking stays accurate even during a suppressed
   window. The flag is read once at the top of the handler and gating is
   applied in both the mode-transition check and the later early-return guard.

2. **`ui/utils.py`** — `_run_in_object_context()` now sets
   `context.scene.superskin_internal_transaction = True` around its entire
   round-trip, using a save-and-restore pattern (`was_suppressing`) so nested
   calls compose safely. Also added `return result` so callers can capture
   return values from the wrapped callback.

3. **`ui/utils.py`** — `exit_mask_mode_if_active()` applies the same
   save-and-restore suppression around its own independent OBJECT-mode
   round-trip, since it's reachable from call sites that are *not* already
   wrapped by `_run_in_object_context` (e.g. `BoneListAdapter.on_single_select`
   ).

4. **`operators/ops_interface.py`** — Routed `SUPERSKIN_OT_layer_remove` and
   `SUPERSKIN_OT_layer_move` through `_run_in_object_context` instead of
   duplicating the manual mode-switch pattern, so there is exactly one place
   in the codebase that performs the OBJECT-mode round-trip (excluding
   `exit_mask_mode_if_active`, which has its own reason for independence).

5. **`ui/widget_tools.py`** — Routed `LayerListAdapter.on_single_select()`'s
   manual mode round-trip through `_run_in_object_context` with the same
   suppression pattern, replacing the inline `prev_mode` save/restore.

## How it was diagnosed

The depsgraph handler was traced by adding a temporary `print()` at every
decision point — entry, mode-transition check, close-tab call, suppression
early-return, and invalidation path. A simple click on a layer row in the
Layers list produced this sequence of prints:

```
_on_depsgraph_update: obj.mode=OBJECT, _last=EDIT → calling force_close_tab()
_on_depsgraph_update: obj.mode=OBJECT, _last=OBJECT (no-op)
_on_depsgraph_update: obj.mode=EDIT, _last=OBJECT (no-op)
```

The first line confirms the bug: the handler sees `OBJECT` while tracking
`EDIT`, and that's enough to trigger the close. The next two lines show the
rest of the round-trip finishing normally.

Cross-referencing the call chain: clicking a layer row →
`LayerListAdapter.on_single_select()` → inline `mode_set(OBJECT)` →
`ctrl.switch_to_layer()` → custom-property write → inline `mode_set(EDIT)`.
The depsgraph update fires asynchronously after the `mode_set(OBJECT)` call
returns — before `on_single_select` has a chance to restore the mode back to
EDIT — which is exactly when the handler runs and sees the transient
`OBJECT` mode.

The fix was verified by adding the suppression flag check in the
mode-transition block, confirming that the same print sequence now reads:

```
_on_depsgraph_update: suppress=True, skipping mode-exit check
_on_depsgraph_update: suppress=True, skipping mode-exit check
_on_depsgraph_update: suppress=True, skipping mode-exit check
```

and then a real Tab-key exit produces:

```
_on_depsgraph_update: suppress=False, obj.mode=OBJECT, _last=EDIT → calling force_close_tab()
```

exactly as expected.

## General lesson

When a single handler serves two independent purposes separated by an
early-return guard, verify that the guard actually *precedes* both purposes —
not just the one the original author was thinking about when they added it.
Also: internal mode round-trips are invisible to the user but not to Blender's
depsgraph system; any handler that reacts to mode transitions needs to
account for them, either by checking a suppression flag or by tracking a
counter of nested round-trips (the flag approach is simpler and already
existed in this codebase — it just wasn't applied to the mode-transition
check).
