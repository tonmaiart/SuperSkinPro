> [ARCHIVED 2026-06-26] The checksum gate and `LayerUndoManager._swap()` described here have been
> fully removed. Undo is now handled natively by Blender via temp VGs (see 0016).
> This file is kept for historical reference only.

# 0011 — Deferred checksum baseline computed AFTER native undo, so the checksum gate always skipped restore

**Date:** 2026-06-19
**Area:** `core/ui_controller/undo_manager.py`

## Symptom

Ctrl+Z after a weight op (Add / Scale / Smooth / Sharpen / Mirror / Auto) or
a layer switch appeared to do nothing — pressing undo "wouldn't undo." (Note:
this is distinct from `0010` — that bug was about the *visualizer* not
redrawing after a fresh op; this one is about undo itself not restoring
SuperSkinPro's layer storage.)

## Root cause

`LayerUndoManager`'s undo/redo gate (`_swap()`, the body of `_on_undo_post` /
`_on_redo_post`) compares two checksums of the mesh's real deform weights:

```python
snap, gate = stack[-1]
current = _deform_checksum(obj)       # computed NOW
last = _ensure_checksum_fresh(obj)    # computed lazily, ALSO now
if gate == "checksum" and last == current:
    return  # "mesh wasn't touched" — skip restore
```

`bpy.app.handlers.undo_post` / `redo_post` fire **after** Blender's native
Edit-Mode (BMesh-level) undo has already reverted the real vertex-group
weights. `_ensure_checksum_fresh()` only recomputes `last` lazily, when
`_checksum_dirty[mesh_name]` is `True` — and the only place that ever
consumes (clears) that dirty flag was `_swap()` itself, called from
*inside* the `undo_post` handler. So whenever the operation now being
undone was the most recent thing to call `sync_checksum()` (i.e. on every
single ordinary undo, the exact case this gate exists to handle), `last`
got computed from the **same already-reverted mesh** that `current` was
just computed from one line above it — with no mutation in between. The two
checksums were therefore guaranteed to be equal, every time, and the gate
always concluded "this mesh wasn't touched by SuperSkinPro" and skipped the
restore.

Blender's own BMesh-level undo still correctly reverted the *real* Vertex
Group weights, so the mesh itself looked right for a moment — but
`ss_layer_N` / `ss_active_layer` storage (read by the GPU visualizer and
re-applied on the next reflatten) stayed pinned to the post-operation data,
silently re-stamping the "undone" weights back onto the mesh the next time
anything reflattened. This is the exact failure mode
`docs/bug-history/0001` and the module's own top-of-file docstring describe
— reintroduced here through a different mechanism (a deferred-computation
timing bug) rather than a missing push/sync call.

## Why it wasn't obvious

`_ensure_checksum_fresh()`'s own docstring stated the intended design
correctly in spirit — "only the LAST sync before an actual undo/redo event
ever triggers a real computation" — and that statement is true. The bug is
*when* "the actual undo/redo event" was interpreted to be: the code treated
`undo_post` (after the mutation) as that moment, when it needed to be
`undo_pre` (before it). Both `current` and the lazily-computed `last` read
from the identical, already-mutated mesh, so there was no exception, no
mismatch in an obviously-wrong direction, and no log output indicating
anything had gone wrong — `last == current` is exactly the value you'd
expect to see logged on a genuinely-untouched mesh too, so even with
`_DEBUG = True` the printed values looked plausible at a glance.

## Fix

Added `_on_undo_pre` / `_on_redo_pre` handlers (both
`@bpy.app.handlers.persistent`, registered/unregistered alongside the
existing `_post` handlers) that call `_ensure_checksum_fresh()` on the
active object *before* Blender mutates anything. This freshens
`_last_checksum` (and clears `_checksum_dirty`) at the correct moment, so by
the time `_swap()` runs in `_on_undo_post` / `_on_redo_post`, `last` already
holds the genuine pre-undo baseline and its own (still-present, now
defensive/no-op in the common case) call to `_ensure_checksum_fresh()` just
reads the cached value. `current`, computed fresh inside `_swap()` itself,
correctly reflects the post-undo state — so the two values now actually
diverge when a restore is needed.

This preserves the perf intent behind the dirty-flag deferral
(`sync_checksum()` itself stays O(1) — no recompute on every weight op or
layer switch in a row): the expensive `O(vertices × groups)` checksum scan
now runs at most once per *actual* Ctrl+Z / Ctrl+Shift+Z keypress, which is
the genuinely low-frequency event the deferral was always meant to gate on
— not on the high-frequency weight-op/layer-switch calls `0007`/`0008` were
optimizing away.

## How it was diagnosed

Re-read `_swap()` against the project's own Undo Safety Rule and
`docs/bug-history/0001`'s description of the failure mode it fixes, then
walked the literal order of operations for `current`/`last` inside `_swap()`
and asked "what mesh state does each of these two calls actually read, and
when." Both turned out to read the same call-time mesh state because
`_ensure_checksum_fresh()`'s only call site is inside the very handler that
fires after Blender's mutation — confirmed by checking
`bpy.app.handlers.undo_post`'s documented firing order (after) versus the
need for a "before" hook, which led directly to `undo_pre`/`redo_pre` as the
fix.

## General lesson

A "compute lazily, right before it's needed" optimization is only correct
if "right before it's needed" is verified against the *actual* event
ordering of whatever external system you're racing — not just the call
graph within your own module. Here, "needed" meant "before Blender's own
undo runs," but the only call site available inside this module's own
functions was structurally *after* that point. When deferring a
read-for-comparison computation across an event boundary owned by another
system (Blender's undo stack, here), check both `_pre` and `_post` hooks
exist and pick deliberately — don't assume the post-hook is early enough
just because it's the first place your code reads the value.
