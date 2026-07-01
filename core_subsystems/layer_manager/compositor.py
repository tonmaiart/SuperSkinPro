"""Layer data encoding / decoding helpers + layer compositing engine.

Serialisation pipeline: pickle → zlib → base64 → "SSLY" header.
No bpy imports.  Operates on plain dict / str / float data only.

Compositing: decodes/coerces layer & mask blobs into FFI-ready dicts in
Python, then dispatches the actual top-down alpha-blend to the native
Rust core (no Python fallback — see core/rust_loader.py).
"""

import pickle
import zlib
import base64

from ..rust_weight_engine import RustWeightEngine as RustGateway

# ═══════════════════════════════════════════════════════════════════════════
#  Encoding / Decoding (formerly codec.py)
# ═══════════════════════════════════════════════════════════════════════════

MAGIC_STR = "SSLY"


def decode_layer_dict(raw):
    """Decode a pickled layer blob → ``{v_idx: {vg_idx: weight}}``.

    Returns ``{}`` on failure or when *raw* is falsy / not a string.
    """
    if not raw or not isinstance(raw, str) or not raw.startswith(MAGIC_STR):
        return {}
    try:
        compressed = base64.b64decode(raw[4:])
        return pickle.loads(zlib.decompress(compressed))
    except Exception:
        return {}


def encode_layer_dict(layer_dict):
    """Encode a ``{v_idx: {vg_idx: weight}}`` dict → pickled blob string."""
    raw = pickle.dumps(layer_dict, protocol=pickle.HIGHEST_PROTOCOL)
    compressed = zlib.compress(raw, level=1)
    return MAGIC_STR + base64.b64encode(compressed).decode("ascii")


def mask_value(raw):
    """Safely extract a ``float`` mask value from either storage format.

    **New format:** *raw* is a plain ``float`` (0.0–1.0).
    **Legacy format:** *raw* is ``{vg_idx: weight}`` → first value extracted.

    Returns ``1.0`` for falsy inputs (missing mask → fully visible).
    """
    if isinstance(raw, dict):
        return next(iter(raw.values()), 1.0) if raw else 1.0
    if isinstance(raw, (int, float)):
        return float(raw)
    return 1.0


# ═══════════════════════════════════════════════════════════════════════════
#  Layer Compositing
# ═══════════════════════════════════════════════════════════════════════════

def composite_layers(meta_list, layer_data_map, mask_data_map, idx_to_name, num_verts):
    meta_clean = []
    layer_decoded_map = {}
    mask_decoded_map = {}
    # meta_list is topmost-first (display order); process bottom-to-top
    ordered_meta = reversed(meta_list)
    foundation_seen = False

    for layer in ordered_meta:
        if not layer.get("visible", True): continue
        l_idx = int(layer["index"])
        raw_layer = layer_data_map.get(l_idx)
        if not raw_layer:
            continue
        decoded = decode_layer_dict(raw_layer)
        if not decoded:
            continue
        # v_idx coerced to int defensively (mirrors map_layer_to_int's
        # int(v_idx)) — rust_composite_layers expects
        # HashMap<usize, HashMap<usize, HashMap<String, f32>>>, and a
        # stray str vertex-index key crashes the FFI call.
        layer_decoded_map[l_idx] = {int(v): w for v, w in decoded.items()}

        meta_clean.append({
            "index": float(l_idx),
            "mask_default": float(layer.get("mask_default", 1.0)),
            "is_base": 1.0 if not foundation_seen else 0.0,
        })
        foundation_seen = True

        raw_mask = mask_data_map.get(l_idx)
        if raw_mask:
            mask_dict = decode_layer_dict(raw_mask)
            mask_decoded_map[l_idx] = {
                int(v): (next(iter(w.values()), 0.0) if isinstance(w, dict) else float(w))
                for v, w in mask_dict.items()
            }
        else:
            mask_decoded_map[l_idx] = {}

    rust = RustGateway("layer_compositor")
    return rust.call("rust_composite_layers", meta_clean, layer_decoded_map, mask_decoded_map, num_verts)


def merge_layers(meta_list, layer_data_map, mask_data_map, selected_indices, num_verts):
    """Composite ONLY the layers in *selected_indices*, ignoring every
    other layer in *meta_list* entirely — same top-down alpha-blend
    algorithm as ``composite_layers``, just restricted to a subset.

    Used by the "Merge Selected Layers" feature: the caller writes the
    returned weight dict into the target layer's storage slot, the
    returned mask dict into the target layer's mask slot, and deletes
    the other selected layers.

    Args:
        meta_list: full layer metadata stack, in display order (as
            returned by ``LayerStorageService.read_meta_list()``).
        layer_data_map: ``{layer_index: raw_encoded_str}`` for every layer.
        mask_data_map: ``{layer_index: raw_encoded_str}`` for every layer
            that has a mask.
        selected_indices: set/list of layer slot indices to merge. Order
            within this collection does NOT matter — compositing order is
            derived from each entry's position in *meta_list*.
        num_verts: vertex count of the target mesh.

    Returns:
        ``(weight_dict, mask_dict)`` tuple:
        - ``weight_dict``: ``{v_idx: {bone_name: weight}}`` — same format
          ``flatten_visible_layers_to_mesh`` consumes via
          ``LayerStorageService.write_layer_dict``.
        - ``mask_dict``: ``{v_idx: float}`` — coverage mask for the merged
          layer, consumed via ``LayerStorageService.write_mask_dict``. Only
          contains entries where coverage > 0.001 (vertices outside this
          dict should be treated as fully uncovered, i.e. the merged layer
          contributes nothing there and whatever is below shows through
          unchanged once the merged layer rejoins the full stack).

    IMPORTANT — why a separate mask pass is needed: ``composite_layers``'s
    weight result is always normalized to sum to 1.0 at every vertex that
    accumulated ANY weight, which destroys the information needed to know
    how much mask coverage produced it. Without writing a real mask back,
    the merged layer would default to ``mask_default`` (typically 1.0 =
    fully opaque) once it rejoins the live stack, silently overriding
    every layer below it across the WHOLE mesh — not just the originally
    masked region. This is why merge must compute coverage independently,
    not derive it from the weight result.

    Every entry in the subset is treated as ``visible=True`` regardless of
    its actual ``visible`` flag in *meta_list* — a layer the user
    explicitly multi-selected for merging should always contribute, even
    if its eye-toggle is currently off. This applies to BOTH the weight
    composite and the mask coverage composite below, for consistency.

    Vertices the compositor left completely void are backfilled from the
    subset's foundation layer's raw weight data: whichever selected layer
    ends up lowest in the subset (``composite_layers``'s own ``is_base``)
    has nothing beneath it *within this subset*. When that layer's own
    per-vertex mask is at/near 0 at a vertex — the common case, since
    every newly-created layer defaults to ``mask_default: 0.0`` (see
    ``LayerManager.create_layer``) and most layers are never explicitly
    mask-painted — ``composite_layers`` scales its weight there down to
    ~0 and the final-normalisation step drops the vertex entirely, even
    though real weight data is sitting right there with nothing else in
    the subset to fall back on. This backfill only touches vertices
    ``composite_layers`` produced NO entry for at all; any vertex that
    received a real contribution (from the foundation layer at a
    meaningful mask value, or blended with an overlay) is left exactly as
    ``composite_layers`` computed it — masked overlap regions still blend
    by their real mask ratios. The mask coverage pass below is unaffected
    either way — it always reads the real mask data, so the resulting
    merged layer's own mask (used once it rejoins the full stack) stays
    accurate.
    """
    selected_set = set(selected_indices)
    subset_meta = [
        {**layer, "visible": True}
        for layer in meta_list
        if layer.get("index") in selected_set
    ]
    weight_dict = composite_layers(subset_meta, layer_data_map, mask_data_map, {}, num_verts)

    # Mirror composite_layers()'s own bottom-to-top scan to find which
    # selected layer was treated as this subset's foundation.
    base_idx = None
    for layer in reversed(subset_meta):
        l_idx = int(layer["index"])
        raw = layer_data_map.get(l_idx)
        if raw and decode_layer_dict(raw):
            base_idx = l_idx
            break

    if base_idx is not None:
        base_weights = {int(v): w for v, w in decode_layer_dict(layer_data_map.get(base_idx)).items()}
        for v_idx, bone_weights in base_weights.items():
            if v_idx in weight_dict or not bone_weights:
                continue
            total = sum(bone_weights.values())
            if total > 0.001:
                weight_dict[v_idx] = {
                    name: w / total for name, w in bone_weights.items() if w > 0.001
                }

    mask_dict = _composite_subset_coverage(meta_list, mask_data_map, selected_set, num_verts)
    return weight_dict, mask_dict


def _composite_subset_coverage(meta_list, mask_data_map, selected_indices, num_verts):
    """Alpha-over composite of just the MASK channel across *selected_indices*,
    in *meta_list* stack order (bottom-to-top, mirroring ``composite_layers``'
    own processing order). Returns ``{v_idx: float}``, omitting entries with
    coverage <= 0.001.

    Standard "over" alpha compositing: at each vertex, starting from 0
    coverage at the bottom of the subset and working upward, each layer's
    mask value *m* combines with the coverage accumulated so far as
    ``new_coverage = m + coverage * (1 - m)`` — equivalent to "this layer
    shows through fully where its own mask is 1, and lets whatever's
    already accumulated show through proportionally where its mask is
    less than 1." A vertex covered at mask=1.0 by ANY layer in the subset
    ends up at coverage=1.0 regardless of the others; a vertex covered by
    none of them stays at 0.0 and is omitted from the result entirely.

    Pure Python, O(num_verts * len(selected_indices)) — acceptable here
    because this runs once per user-initiated merge click, not per frame
    or per paint-stroke, unlike the GPU-visualizer / weight-op hot paths
    elsewhere in this codebase that need the Rust-accelerated path.
    """
    ordered = [layer for layer in reversed(meta_list)
               if layer.get("index") in selected_indices]
    coverage = [0.0] * num_verts
    for layer in ordered:
        l_idx = layer["index"]
        mask_default = float(layer.get("mask_default", 1.0))
        raw_mask = mask_data_map.get(l_idx)
        mask_dict = ({int(v): w for v, w in decode_layer_dict(raw_mask).items()}
                     if raw_mask else {})
        for v in range(num_verts):
            m = mask_value(mask_dict.get(v, mask_default))
            m = max(0.0, min(1.0, m))
            coverage[v] = coverage[v] * (1.0 - m) + m
    return {v: c for v, c in enumerate(coverage) if c > 0.001}
