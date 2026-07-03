# Edit-Mode Weight Read/Write Pattern

Canonical reference for how a feature domain reads and writes active-layer
weight data. Referenced by `docs/bug-history/0019`'s fix note. Read this
before adding any new code path that touches active-layer weights.

## The rule

Never call `CoreFacade.get_active_layer_dict()` / `write_layer_dict()`
directly from code reachable in Edit Mode. Use one of:

- `facade.read_active_layer()` / `facade.write_active_layer(layer_str, color_only=...)`
- `facade.mutate_active_layer(color_only=...)` (context manager wrapping the pair above)
- `facade.write_active_layer_from_calc(layer_int, id_to_bone)` for Rust-backed
  domains that already have int-keyed output (caller must call `finish()` after)

## Why

After the `0016` undo redesign, the active layer's source of truth in Edit
Mode is the `__ssp_*` BMesh temp VGs, not `ss_layer_N`. `ss_layer_N` is only
written on a deliberate Save Weight action or on exiting Edit Mode.

`get_active_layer_dict()` / `write_layer_dict()` read and write `ss_layer_N`
unconditionally — they have no mode check. In Object Mode this is correct
and is exactly what they're for. In Edit Mode with temp VGs present:

- `get_active_layer_dict()` returns the Edit-Mode-entry snapshot, not the
  live BMesh state — appears to work, silently stale.
- `write_layer_dict()` writes somewhere nothing reads until Exit Edit Mode,
  at which point the bake-back from `__ssp_*` overwrites it — the write is
  silently lost.

Both call sites log a `core_pipeline` debug warning automatically if hit
while in Edit Mode with temp VGs present (see `core/facade/read.py` and
`core/facade/write.py`), but that is a diagnostic backstop, not a substitute
for using the correct method.

`docs/bug-history/0018` and `0019` are two independent domains
(`weight_apply`, `auto_block_weight`) that shipped with this exact mistake.

## The correct read/write cycle

```python
with facade.mutate_active_layer(color_only=True) as layer_data:
    # layer_data: {v_idx (int): {bone_name (str): weight (float)}}
    # already the correct source for the current mode (temp VG in Edit Mode,
    # ss_layer_N outside it) -- mutate in place.
    for v_idx in facade.get_selected_verts():
        ...
```

On a clean exit, this:
1. Converts the string-keyed dict back to int-keyed via the bone mapping
   cached by `read_active_layer()`.
2. Re-merges orphan bone entries (bones with no current vertex group) that
   were present on entry, so they are not silently dropped.
3. Routes the write to `__ssp_*` temp VGs (Edit Mode) or `ss_layer_N`
   (Object Mode).
4. Calls `finish()` — reflattens to the real deform VGs, bumps the deform
   generation counter, and schedules a redraw.

If an exception is raised inside the `with` block, nothing is written.

Do not reach for `mutate_active_layer()` and then also manually call
`read_active_layer()` / `write_active_layer()` inside the block — the
context manager already owns that pair.

**`mutate_active_layer()` requires in-place mutation of the yielded dict.**
The context manager captures the dict object at `yield` time; if the code
inside the `with` block rebinds the local name to a *new* dict (e.g.
`layer_data = core_facade.normalize_weights(layer_data, ...)`, which returns
a new dict rather than mutating its argument), the write on exit still uses
the original, pre-mutation object — the rebind is invisible outside the
block. `features/auto_block_weight/auto_block_feature.py` does exactly this
(reassigns `layer_dict` from `normalize_weights()` in a loop) and correctly
uses plain `read_active_layer()` / `write_active_layer()` instead of
`mutate_active_layer()` for that reason. Prefer `mutate_active_layer()` only
when every write to the dict is a subscript assignment.

## Rust-backed domains

Domains that call into `rust_logic` with int-keyed data (smooth, sharpen,
auto-block) should prefer `write_active_layer_from_calc()` over converting
Rust's int-keyed output to strings just to hand it to `write_active_layer()`
— it skips the redundant string round-trip. It does **not** call `finish()`
itself; the caller must call `facade.finish()` / `facade.finish_color_only()`
after all writes for that operator execution are complete.

## Sparse-dict-to-Rust hazard (related, not the same bug)

Separately from the read/write store mismatch above: any dict handed to a
Rust FFI call that filters its iteration domain from the dict's own keys
(rather than an explicit passed-in universe) must be dense over the full
bone set, not sparse. `get_locks_by_id()` / `facade.get_bone_locks()` already
do this correctly (default every bone to `False`/unlocked). See
`docs/bug-history/0021` for the case where a sparse `bone_locks` dict made
Smooth/Sharpen silently no-op on any layer with no explicitly-locked bones.
