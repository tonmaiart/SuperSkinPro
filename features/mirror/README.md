```markdown
# Mirror Domain Specification

Provides mirror capabilities for skin weights and mask data across a symmetrical axis using ngSkinTools-style search and replace name-matching pairs.

## ⚙️ Domain Actions Matrix

| Action | Operator ID | Purpose |
|---|---|---|
| `mirror` | `object.mirror_weights` | Mirrors weight and mask topologies across the chosen axis. |

*Note: Pair management operators (`superskin.add_mirror_sr` and `superskin.remove_mirror_sr`) manipulate the `SUPERSKIN_UL_mirror_sr` UIList descriptor.*

## 🧬 Core Logic Flow & FFI Bridges
1. **Planning Step (String-Based):** `generate_pairs` resolves symmetrical name pairs based on 3D bone centers and search/replace rules. This step operates strictly on bone name strings.
2. **Apply Step (Integer-ID CSR Bridge):** Converts matched strings to Integer IDs before invoking the Rust core. Mask mirroring utilizes `mask_to_flat()` to build dense contiguous flat buffers for zero-copy FFI execution via `rust_mirror_apply_mask_flat`.

## 🚨 CRITICAL: Weight and Mask Channels Use INDEPENDENT Side-Classification — Never Reunify

`execute_mirror_pipeline()` runs two channels (bone-weight via `apply()`/`rust_mirror_apply`, and mask via `apply_mask_flat()`/`rust_mirror_apply_mask_flat`). **These two channels deliberately use two different, unrelated methods for deciding which vertex is "source side" vs "target side," and must stay that way:**

- **Weight channel** (`apply()`) uses `classify_sides_by_topology()` — a geodesic/Dijkstra, multi-seed, whole-mesh-span-margin classification (see that function's own extensive docstring for the three prior approaches that were tried and regressed before landing on this one). This exists to survive self-intersecting geometry (e.g. an oversized pant leg poking into the other leg) where a raw coordinate-sign test misclassifies vertices.
- **Mask channel** (`apply_mask_flat()`) intentionally stays on the **original raw coordinate-sign test**, computed independently inside Rust (`flat_bridge::flat_mirror_apply_mask`'s own local `is_source_side`/`is_target_side` closures) — **not** `classify_sides_by_topology()`'s output.

**Why this split exists (confirmed by direct testing, not a hypothetical):** `classify_sides_by_topology()` was once wired into the mask channel too (both channels sharing one `target_side_mask`). That regressed mask coverage across most of a complex character mesh — only a small, simple region (e.g. the feet) classified correctly; gap-fill was silently papering over the rest. The weight channel's own use of the same function was independently confirmed to work well. **Any future change to `classify_sides_by_topology()` (margin tuning, a new classification strategy, etc.) affects the WEIGHT channel only if the mask channel is never wired back into it.** Before changing this function, re-verify both channels separately on a real, complex character mesh (not just a synthetic two-limb test) — a synthetic test that only covers a simple case will not catch this class of regression.

**Guardrail for future edits:** if you need to change how "which side" is decided, do it inside ONE channel's own function only (`apply()`'s call site or `apply_mask_flat()`'s call site), never by editing a shared helper both channels call — that coupling is exactly what caused the regression above.

**Gap-fill exists on BOTH channels, always runs (no toggle) whenever gaps are detected, but each builds its own surface — never share this either:**
- Weight: `_fill_weight_gaps()` + `build_source_side_surface(core_facade, target_side_mask)` (topology-based).
- Mask: `_fill_mask_gaps()` + `build_source_side_surface_raw(core_facade, axis_idx, direction)` (raw coordinate-sign, self-contained). This exists because the mask channel needed the same "auto-fill asymmetric-topology gaps instead of leaving a hole" behavior as weight, without reintroducing the shared-classification regression above — same BVH + barycentric-blend technique, independent side test. Its missing-vertex fallback uses the active Layer's own `mask_default` (see `docs/bug-history/0024`), never a hardcoded constant.

## 🎯 Center-Seam Vertex Symmetrization (Weight Channel Only)

`_symmetrize_center_vertices()` runs after `apply()`/`_fill_weight_gaps()`, forcing a true 50/50 split on each mirrored bone-pair's weight for any vertex sitting exactly on the mirror plane (see `docs/bug-history/0025`). A seam vertex is a single, shared point — neither source nor target — so it must never end up holding 100% of one paired bone and 0% of the other.

**This uses a small, FIXED absolute epsilon (`_CENTER_EPSILON`), deliberately unrelated to `classify_sides_by_topology()`'s wide classification margin.** A prior attempt at this same feature coupled seam detection into that wide margin and regressed self-intersecting-mesh handling — it must stay a narrow, independent check that only ever matches vertices genuinely on the mirror plane. Locked bones are skipped per-pair, matching the rest of the pipeline's lock contract. Mask channel is unaffected — this is weight-channel-only.

## 🛠️ Configuration Spec (`default_config.json`)
```json
{
  "mirror_axis": "X",
  "direction": "POS_NEG",
  "mirror_data": "BOTH",
  "search_replace_pairs": [
    ["*.l", "*.r"],
    ["*.L", "*.R"],
    ["*_L", "*_R"],
    ["*_l", "*_r"]
  ]
}