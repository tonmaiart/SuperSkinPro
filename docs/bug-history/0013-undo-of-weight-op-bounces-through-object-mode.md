> [STILL ACTIVE 2026-06-26] The `_undo_restore_in_progress` flag and its pre/post handler logic remain
> the active guard against shader teardown during memfile undo bounce. This mechanism is intentionally
> preserved in `undo_manager.py` and is independent of the `@skin_transaction` decorator.

# 0013 — Undo of a weight op transiently exits Edit Mode, tearing down the visualizer/panel

**Date:** 2026-06-20
**Area:** `core/shaders/shader_manager.py`, `core/ui_controller/undo_manager.py`

## Symptom

Pressing Ctrl+Z right after a weight op (Add / Scale / Smooth / Sharpen /
Mirror / Auto) appeared to "kick the user out of Edit Mode" — the custom
weight visualizer disappeared and the SuperSkinPro N-panel tab closed,
exactly as if the user had pressed Tab back to Object Mode. But `obj.mode`
read `'EDIT'` again immediately afterward; the mesh itself stayed in Edit
Mode the whole time.

## Root cause

None of the weight-op operators (`operators/ops_weight_apply.py`) switch
mode themselves — `pipeline.finish()` deliberately routes through
`bmesh.from_edit_mesh()` while in Edit Mode to avoid a mode round-trip.
The actual mode bounce happens **inside Blender's own undo system**, not
in any SuperSkinPro code:

Every weight op writes JSON-string ID Properties (`ss_layer_N`,
`ss_mask_N`, `ss_layers_meta`) onto the Mesh datablock while still in Edit
Mode. Edit-Mode's lightweight BMesh-only undo can snapshot vertex
positions, selection, and the deform (vertex-group) CustomData layer, but
it cannot snapshot arbitrary ID Properties on the Mesh ID — that's the
exact gap `LayerUndoManager`/`0001` exists to paper over on the
*storage* side. What `0001` doesn't address is what this forces on
*Blender's* side: because the operator's single Python execution mutates
both BMesh-local data and ID-level data in the same step, Blender can't
record it as a pure lightweight Edit-Mode undo step — it falls back to
recording/restoring that step via the heavier global (memfile) undo path.
Restoring a memfile step is implemented as a full database swap, which
internally exits Edit Mode, swaps the data, and re-enters Edit Mode — a
real (if brief) mode transition fires through Blender's event/depsgraph
system, even though the net effect for the user is "still in Edit Mode."

`ShaderManager._on_depsgraph_update` (`core/shaders/shader_manager.py`)
tracks `(obj.name, obj.mode)` across depsgraph updates specifically to
detect the user leaving Edit Mode by any route (native Tab, header
dropdown, etc. — see the Architecture doc's note on this), and reacts by
clearing the GPU visualizer, hiding the deform-bone overlay, and
force-closing the SuperSkinPro tab. It guards against false positives
during SuperSkinPro's *own* operators via the
`superskin_internal_transaction` scene flag — but that flag is only ever
set by SuperSkinPro's own operator wrappers (`_run_ctrl`,
`_run_in_object_context`). Native Ctrl+Z runs entirely inside Blender's C
undo system with no SuperSkinPro operator executing, so the flag is never
set during the transient EDIT→OBJECT→EDIT blip described above. The
handler saw a genuine `prev_mode == 'EDIT' and obj.mode != 'EDIT'`
transition and tore everything down — and because those teardown
side-effects don't auto-reverse themselves (re-opening the tab / re-
enabling the visualizer only happens via `mw_enter_edit_mode` or the
panel's own draw-time auto-init), the dead UI persisted even after the
mode silently snapped back to `'EDIT'` a moment later.

## Why it wasn't obvious

`obj.mode` reads `'EDIT'` both immediately before and immediately after
the Ctrl+Z — there's no Python-observable moment where the object looks
like it's in Object Mode unless you're specifically watching depsgraph
update events fire in between. The bug looks exactly like "undo exits
Edit Mode" from the user's perspective, but a check of `obj.mode` right
after pressing Ctrl+Z appears to immediately contradict that theory.

## Fix

Added a module-level `_undo_restore_in_progress` flag in
`core/ui_controller/undo_manager.py`, set `True` in `_on_undo_pre` /
`_on_redo_pre` (before Blender mutates anything) and back to `False` at
the end of `_on_undo_post` / `_on_redo_post` (after `_swap()` — which
already correctly redraws the visualizer via `_resync_object()` →
`UIController()._finish()` — has finished). `ShaderManager._on_depsgraph_update`
now checks `is_undo_restore_in_progress()` alongside the existing
`superskin_internal_transaction` check before reacting to an EDIT→non-EDIT
transition, skipping the teardown for this transient, Blender-internal
blip while still reacting normally to a real user-initiated mode exit.

## How it was diagnosed

Traced every `bpy.ops.object.mode_set` call site in the addon first and
ruled all of them out — the weight-op operators don't call any of them,
confirmed by `ops_weight_apply.py`'s own top-of-file comment about
avoiding mode round-trips. With no SuperSkinPro code switching mode, the
remaining suspect was Blender's own undo mechanics: ID Property writes
on a Mesh ID during Edit Mode are a known trigger for Blender falling
back to global/memfile undo instead of lightweight Edit-Mode undo, and
memfile-step restoration is documented to exit/re-enter edit mode as part
of the database swap. That pointed straight at
`ShaderManager._on_depsgraph_update`'s mode-transition tracker as the
piece reacting to the blip, since it's the only code in the addon that
treats *any* detected EDIT→non-EDIT transition as equivalent to the user
manually leaving Edit Mode, regardless of cause.

## General lesson

A mode-tracking handler that compares `(prev_mode, current_mode)` across
two depsgraph ticks can't distinguish "the user changed mode" from "an
external system (Blender's own undo restore) bounced through that mode
transiently while accomplishing something else." If a side-effect should
only fire on a *user-intentional* mode change, the guard needs to cover
every system capable of forcing a transient mode bounce — not just your
own code's mode-switching call sites — including ones, like memfile undo
restoration, that never show up in a grep for `mode_set`.
