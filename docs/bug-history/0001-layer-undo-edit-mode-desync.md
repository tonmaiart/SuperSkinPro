> [ARCHITECTURAL UPDATE 2026-06-26] `push()` and the per-mesh undo stack described here have been
> replaced entirely by Blender's native BMesh undo via temp VGs (see 0016). The layer-switch desync
> risk is now managed by `__ssp_meta` and `_sync_after_undo()` in `undo_manager.py`.

# 0001 — Layer-undo silently desyncs after layer switches

**Date:** 2026-06-17
**Area:** `core/layer_undo.py`, `core/ui_controller.py`

> **Note on file paths:** at the time of this bug, `LayerUndoManager` lived in
> `core/layer_undo.py` and `UIController` was a single `core/ui_controller.py` file
> with methods directly on `self`. Both were later refactored into the
> `core/ui_controller/` package (see AGENTS.md's Key Modules §1) — `undo_manager.py`,
> `layer_crud.py`, `pipeline.py`, and `operations.py` are now separate files, each
> taking a `ctrl` parameter instead of using `self`, and the import alias changed
> from `layer_undo` to `undo_manager`. The mechanism and fix described below are
> unchanged; only the module paths and code style differ from current source. For
> example, current `switch_to_layer` lives in `core/ui_controller/layer_crud.py` as:
> ```python
> def switch_to_layer(ctrl, index: int, *, push_undo: bool = True):
>     if index == ctrl.active_layer_index:
>         return
>     if push_undo:
>         undo_manager.push(ctrl.obj, gate="always")
>     # ...unchanged below this line
> ```

## Symptom
Ctrl+Z visibly reverted real Vertex Group weights in the viewport, but the
underlying layer storage (`ss_layer_N`) didn't revert with it. After
several undos, applying any new weight operation would "snap back" to a
state that looked like nothing had been undone at all — because the
operation read from the still-fully-applied `ss_layer_N` and reflattened
on top of it, overwriting whatever Blender's own undo had just reverted
in the viewport.

## Root cause (the underlying mechanism, twice over)
Blender's Edit-Mode undo is a lightweight, BMesh-only system that
snapshots vertex positions, selection, and the deform/vertex-group
CustomData layer — but never ID Properties on the Mesh datablock, which is
exactly how `LayerStorageService` stores every `ss_*` key. A first fix
(`core/layer_undo.py`: a parallel per-mesh undo/redo stack hooked on
`bpy.app.handlers.undo_post` / `redo_post`) addressed this for the six
weight operations and five layer-CRUD operations, gated by a checksum of
the mesh's real deform weights so an unrelated undo elsewhere in the scene
couldn't desync this mesh.

That first fix passed a clean single-action test (one Add, one Ctrl+Z,
verified via debug prints) — but a longer session that interleaved weight
edits with clicking between layers in the Layers tab still desynced. The
actual remaining gap: `UIController.switch_to_layer()` changes
`ss_active_layer` (an untracked ID property, the exact same root cause as
above) and reflattens to a different real-weight result — but it never
called `layer_undo.push()`. The UI operator behind a plain layer-switch
click (`SUPERSKIN_OT_layer_select_by_item`) has `'UNDO'` in its
`bl_options`, so Blender recorded an undo step for every layer switch
regardless of whether our parallel system was tracking it. Every layer
switch put our stack one entry behind Blender's real one, and every
Ctrl+Z after that point popped the wrong snapshot.

## Why the first fix didn't catch this
The checksum-gated design was built around "did this *weight operation*
change the data," which made it easy to overlook that *switching the
active layer* changes the real on-mesh weights through the exact same
mechanism (reflatten → different composited result) without going through
any of the six weight-op methods. A single isolated test (one action, one
undo) can't surface a missing push on a *different* method — it only
shows up several actions later, once the two systems' step counts have
already diverged, by which point the symptom ("undo doesn't work") looks
completely disconnected from the actual cause (a layer switch three
actions ago).

## Fix
Added a `push_undo: bool = True` parameter to `switch_to_layer()`,
pushing a `gate="always"` snapshot whenever it's reached as a standalone
action:

```python
def switch_to_layer(self, index: int, *, push_undo: bool = True):
    if index == self.active_layer_index:
        return
    if push_undo:
        layer_undo.push(self.obj, gate="always")
    # ...unchanged below this line
```

`create_layer()`, `duplicate_layer()`, and the fallback branch of
`remove_layer()` — all of which call `switch_to_layer()` internally
*after* already pushing once for their own mutation — pass
`push_undo=False`, so one logical user action never produces two stack
entries against Blender's one recorded undo step. (Pushing twice for a
single Blender-recorded step is just as harmful as not pushing at all —
the two stacks' lengths have to stay in lockstep, or every undo after the
mismatch pops the wrong entry.)

## How it was diagnosed
Added a `_DEBUG` flag and `_dbg()` print helper to `core/layer_undo.py` at
every push / sync_checksum / undo_post / redo_post / restore decision
point. A single Add + Ctrl+Z test showed the core mechanism working
correctly (push → checksum mismatch detected → restore → resync, no
errors) — which was useful on its own, since it ruled out "the handler
isn't firing at all" as a hypothesis and narrowed the search to
*something else* mutating the mesh without going through `push()`.
Re-auditing every `UIController` method that calls `_flatten_to_mesh()` /
`_flatten_to_mesh_edit()` — not just the ones that look like weight
operations — found `switch_to_layer()` as the gap.

The `_DEBUG` flag was left in the file (set to `False`, not deleted)
specifically so the same instrumentation is available instantly if
something in this area regresses again. If picking this up after some
other change to undo-adjacent code, flip `_DEBUG = True` and re-run a
single-action-then-undo test before guessing at the cause.

## General lesson
`layer_undo.push()` is needed by *any* `UIController` method that changes
the real on-mesh weights or `ss_active_layer` / `ss_layers_meta` — not
only ones that look like "weight operations." If a future method
reflattens for any reason and is reachable from an undo-enabled operator,
it needs the same treatment, following the `push_undo: bool = True` /
internal-caller-opts-out pattern shown above.