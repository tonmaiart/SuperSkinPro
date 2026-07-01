# 0002 — Undo/redo handlers silently dropped after file load

**Date:** 2026-06-17
**Area:** `core/ui_controller/undo_manager.py`, `core/shaders/shader_manager.py`

## Symptom

After performing a weight operation (Add/Scale) then pressing Ctrl+Z, the
underlying layer storage (`ss_layer_N` custom properties) never reverted,
and the GPU weight-color visualizer never refreshed on undo either. The
next weight operation (e.g. Smooth) then read the stale post-operation
data and re-applied it, visually looking like the undo "bounced back."

This only reproduced in a normal dev workflow — start Blender, enable the
addon, open/reload a `.blend` file, then test. A test session where the
file was never re-opened after addon enable would pass because the
handlers were still in the list.

## Root cause

`core/ui_controller/undo_manager.py`'s `_on_undo_post` / `_on_redo_post`
and `core/shaders/shader_manager.py`'s `ShaderManager._on_undo` /
`ShaderManager._on_depsgraph_update` were registered via
`bpy.app.handlers.undo_post` / `redo_post` / `depsgraph_update_post`
**without** the `@bpy.app.handlers.persistent` decorator.

Blender clears all **non-persistent** handlers from these lists every time
a `.blend` file is loaded (including reopening the same file). The
addon's `register()` only runs once at Blender startup / addon-enable — it
does **not** re-run on file load. So in any session where the addon was
enabled and then a file was opened/reloaded afterward, these handlers
silently stopped existing in the handler list with zero error output.

## Why it wasn't obvious

- The handlers are appended in `register()` which runs successfully. There
  is no error message, no traceback, and no visible symptom until the
  user presses Ctrl+Z — at which point nothing happens, but "nothing
  happens" is hard to distinguish from "the undo stack was empty" or "the
  checksum gate skipped the restore."
- `_DEBUG` prints in `undo_manager.py` (`=== undo_post fired ===`, etc.)
  never appeared — but a handler that was never called is
  indistinguishable from a handler whose debug prints were suppressed, or
  one that encountered an early `return` via the guard clause in
  `_swap()`. Only after adding an unconditional print at the very first
  line of `_on_undo_post` (before any logic) did it become clear the
  function itself was never invoked at all.
- The "Read blend" log line in Blender's console (printed on every file
  open) was the key clue: every test session that reproduced the bug had
  this line immediately before the test, meaning a file load had occurred
  after `register()` ran.
- `ui/utils.py`'s `_superskin_layers_depsgraph_handler` and
  `_superskin_layers_load_handler` already correctly used
  `@bpy.app.handlers.persistent` and showed no equivalent symptoms —
  making the inconsistency easy to overlook since "some handlers work,
  others don't" isn't the first thing you check.

## Fix

Added `@bpy.app.handlers.persistent` to all four handler functions:

**`core/ui_controller/undo_manager.py`:**
```python
@bpy.app.handlers.persistent
def _on_undo_post(*_args):
    _dbg("=== undo_post fired ===")
    _swap(_undo_stacks, _redo_stacks, "UNDO")

@bpy.app.handlers.persistent
def _on_redo_post(*_args):
    _dbg("=== redo_post fired ===")
    _swap(_redo_stacks, _undo_stacks, "REDO")
```

**`core/shaders/shader_manager.py`:**
```python
@classmethod
@bpy.app.handlers.persistent
def _on_depsgraph_update(cls, scene, depsgraph):
    ...

@classmethod
@bpy.app.handlers.persistent
def _on_undo(cls, *args):
    ShaderManager().invalidate_and_redraw()
```

For the `ShaderManager` classmethods, `@bpy.app.handlers.persistent` is
the **innermost** decorator (closest to `def`), with `@classmethod`
outermost. This ensures `_bpy_persistent = True` is set on the underlying
function before the `classmethod` descriptor wraps it. When Blender
checks persistence via `getattr(handler, '_bpy_persistent', False)`,
Python bound-method attribute lookup delegates to `__func__` and finds
the flag.

## How it was diagnosed

1. Added unconditional debug print (`_dbg("=== undo_post fired ===")`)
   as the **very first line** of `_on_undo_post` — before any guard
   clauses, early returns, or logic. This ruled out "the handler fires
   but bails early" as a hypothesis when the print never appeared across
   multiple confirmed Ctrl+Z presses.

2. Noticed the "Read blend" log line in Blender's console immediately
   preceding every test session that reproduced the bug, indicating a
   file load had occurred.

3. Checked `bpy.app.handlers.undo_post` from Blender's Python console
   after file load — confirmed the handler was absent from the list.

4. Compared against `ui/utils.py`'s handlers which **did** survive file
   loads, noticed they used `@bpy.app.handlers.persistent` while the
   undo/redo handlers did not.

5. Applied the decorator, re-ran the exact repro (file load → Add →
   Ctrl+Z), and confirmed `=== undo_post fired ===` appeared in console
   and weight data correctly reverted.

## General lesson

**Every handler registered in `bpy.app.handlers.*` that must survive
across file loads needs `@bpy.app.handlers.persistent`.** Blender
provides no warning when non-persistent handlers are silently dropped —
the only symptom is "the handler stops firing," which can manifest as
any number of downstream bugs. When adding a new handler, either use the
decorator or consciously decide the handler should only live for the
current file session.

For classmethods, the decorator ordering is `@classmethod` outermost,
`@bpy.app.handlers.persistent` innermost. Verify with:
```python
getattr(ShaderManager._on_undo, '_bpy_persistent', False)  # must be True
```
If this returns `False` in a given Blender version, refactor to
module-level plain functions instead.
