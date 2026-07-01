> [ARCHIVED 2026-06-26] The Rust checksum system described here has been fully removed.
> `rust_deform_checksum()` is no longer called anywhere in the codebase. See 0016 for the redesign.
> This file is kept for historical reference only.

# 0012 — `rust_deform_checksum` collides for "round" weight values, silently skipping undo restore

**Date:** 2026-06-20
**Area:** `rust_logic/src/checksum.rs`

## Symptom

Ctrl+Z after a weight op (Add was the reported case) appeared to do
nothing — both the real on-mesh weights and the visualizer color stayed at
the post-op state. Console showed the `0011` fix's diagnostic pre/post gate
working exactly as designed, but always landing on the wrong verdict:

```
🔍 [LayerUndo] UNDO: mesh='Cube.001' obj_mode=EDIT stack_len=2 gate=checksum last_checksum=3116509661 current_checksum=3116509661
🔍 [LayerUndo] UNDO: checksum MATCH → treating as 'this mesh wasn't touched', SKIPPING restore
```

This looks identical to `0011` at first glance (same log line, same
"checksum MATCH" verdict) but `0011` was already fixed — the pre/post
timing split documented there is intact and was confirmed correct by
reading the code. The bug is one layer deeper: the checksum *values being
compared* are wrong, not the *timing* of when they're computed.

## Root cause

`deform_checksum_engine()` in `rust_logic/src/checksum.rs` mixes
`v_idx`, `g_idx`, and the weight's `f64::to_bits()` into a running hash
`h: u64`, then truncated it to `u32` **on every iteration**:

```rust
h = h.wrapping_mul(1000003).wrapping_add(mixed) & 0xFFFFFFFF;
```

`mixed` includes `rounded.to_bits()` — the full 64-bit IEEE-754
representation of the weight. For any "clean" weight value whose mantissa
needs fewer than 20 fractional bits (0.5, 1.0, 0.25, 0.75, 2.0 — extremely
common in practice: default Add intensity saturating at 1.0, manual
weights, normalized results), **the low 32 bits of that float's bit
pattern are all zero**. Masking `& 0xFFFFFFFF` immediately after mixing
throws away exactly the high bits (sign/exponent/top mantissa) that would
have distinguished e.g. 0.5 from 1.0 — so two different weight values on
the same `(v_idx, g_idx)` produce the identical checksum. Confirmed
directly against the shipped `bin/linux/rust_logic.so`:

```python
>>> rust_logic.rust_deform_checksum({0: {0: 0.5}})
0
>>> rust_logic.rust_deform_checksum({0: {0: 1.0}})
0
>>> rust_logic.rust_deform_checksum({})        # even an empty dict!
0
```

The degenerate case is worst when `v_idx == 0` and `g_idx == 0` (the very
first mixed term, with `h` still `0`), where the entire hash for that
iteration collapses to `rounded.to_bits() & 0xFFFFFFFF` — but the same
masking discards real entropy on *every* iteration, not just the first.

Since `LayerUndoManager`'s gate (`core/ui_controller/undo_manager.py`,
`_swap()`) treats `last_checksum == current_checksum` as proof "this mesh
wasn't touched by this undo step," a value-only weight change that
collides this way is invisible to the gate — it silently skips the
storage restore exactly as if nothing had happened, even though Blender's
native Edit-Mode undo (or lack thereof) is irrelevant at that point: the
checksums were never going to differ.

## Why it wasn't obvious / why `0011`'s fix didn't catch it

`0011` fixed a real, distinct bug (the checksum baseline being computed
*after* the native undo mutation instead of before). Its fix is correct
and still in place. But both bugs produce the **exact same console
signature** — "checksum MATCH → SKIPPING restore" — so seeing that line
again reads as a regression of `0011` rather than a new, independent bug
in the checksum *function* itself. Confirming `0011`'s timing fix was
intact (it was) ruled out the first hypothesis; the actual cause only
surfaced by calling `rust_deform_checksum` directly, outside Blender, with
hand-picked before/after weight dicts and noticing the returned values
were identically `0` regardless of the weight.

A `--background` Blender repro was tried first and seemed to show the
*same* symptom for an unrelated reason (Blender disables Edit-Mode BMesh
undo by default in `--background` mode — confirmed with a control test
translating a vertex, which also failed to undo). That was a real but
separate dead end: it proved background-mode scripting can't validate
this class of bug at all, which is why the checksum function itself had
to be isolated and tested directly via `bin/linux/rust_logic.so`, with no
Blender involved.

## Fix

Removed the per-iteration `& 0xFFFFFFFF` mask so `h` carries the full
64-bit accumulated state across the whole loop, and fold the two halves
together once at the very end instead of truncating blindly (a bare `h as
u32` at the end would reintroduce the same collision for the *last*
mixed entry specifically):

```rust
h = h.wrapping_mul(1000003).wrapping_add(mixed);   // no per-iteration mask
// ...after the loop:
(h ^ (h >> 32)) as u32
```

Verified with a standalone `rustc`-compiled comparison of the old vs. new
function across six cases (value-only change, empty-vs-nonempty,
different `v_idx`, different `g_idx`, an 8-vertex mesh matching the live
repro) — the old version collided on every value-only case including the
exact 8-vertex/0.5→1.0 case from the live repro (checksum `2337850812`
both ways); the new version distinguishes all six.

**The compiled `bin/linux/rust_logic.so` must be rebuilt from this source
change before the fix takes effect** — `rust_logic/Cargo.toml`,
`Cargo.lock`, `pyproject.toml`, and `build_all.py` are intentionally
outside an AI agent's reach for this project (see root `CLAUDE.md`'s
Ignored Directories), so the rebuild has to go through the project's
normal human-run build process.

**Rebuilding the `.so` is not enough on its own — Blender must be fully
restarted, not just "Reload Scripts".** `core/rust_loader.py` caches the
loaded extension module in two process-lifetime globals
(`_cached_rust_module`, `_has_attempted_load`), and `_internal_load_binary()`
tries a bare `import rust_logic` *first* — which is satisfied straight out
of Python's own `sys.modules` cache if `rust_logic` was ever imported
earlier in the same process (true for any session that already triggered
a Rust call before the rebuild). The explicit `del sys.modules["rust_logic"]`
+ fresh `importlib.import_module()` path only runs when that bare import
*fails*, so it's never reached in a long-running session — "Reload
Scripts" re-executes the `.py` files but leaves the stale pre-fix `.so`
loaded in memory, and testing against it reproduces the exact same bug
signature as before the fix, making it look like the fix didn't work.
This cost a full extra round of live debugging (re-confirming the gate
timing, dumping live-bmesh weight sums, etc.) before a full Blender
restart was tried and the fix was confirmed working immediately.

## How it was diagnosed

1. User reported "undo doesn't work, shader doesn't update" after a
   weight op, with the exact `0011`-style "checksum MATCH" log line.
2. Re-read `undo_manager.py` and `pipeline.py` to confirm the `0011` fix
   (pre/post split, `bump_deform_generation()` placement) was still
   correctly in place — it was, which ruled out a regression of `0011`
   itself and pointed at the checksum *values* instead of the *timing*.
3. Built a throwaway cube+armature rig and drove it via
   `blender --background --python`, which reproduced "checksum MATCH" —
   but a control test (plain vertex translate + undo) showed *geometry*
   undo also silently failing in background mode, proving background-mode
   scripting can't be trusted for this class of bug at all (Blender
   disables Edit-Mode BMesh undo there by default).
4. Re-ran interactively against the real X11 session (`DISPLAY=:0`) with
   `bpy.ops.screen.screenshot()` to visually confirm the *forward* op
   (color genuinely changed after Add) — isolating that the visualizer
   and the forward weight-write path were both fine, narrowing the
   problem specifically to the undo-restore decision.
5. Loaded `bin/linux/rust_logic.so` directly in plain Python (outside
   Blender entirely, via `sys.path` + `import rust_logic`) and called
   `rust_deform_checksum()` with hand-picked before/after dicts — this is
   what actually exposed the collision, in under a second per case, with
   no Blender startup cost.
6. Confirmed the exact fix by porting both the old and new hashing logic
   into a standalone `rustc`-compiled comparison program before touching
   the real source file.
