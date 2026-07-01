"""Layer data encoding/decoding and top-down compositing engine.

Serialisation pipeline: pickle -> zlib -> base64 -> "SSLY" header.
No bpy imports; operates on plain dict/str/float data.

Compositing: decodes/coerces layer and mask blobs into FFI-ready dicts,
then dispatches the actual top-down alpha-blend to the native Rust core
via RustWeightEngine (no Python fallback).
"""

import pickle
import zlib
import base64

from ..rust_weight_engine import RustWeightEngine

# =========================================================================
#  Serialisation (formerly codec.py inside layer_manager/)
# =========================================================================

MAGIC_STR = "SSLY"


def decode_layer_dict(raw):
    """Decode a pickled layer blob -> ``{v_idx: {vg_idx: weight}}``.

    Returns ``{}`` on failure or when *raw* is falsy/not a string.
    """
    if not raw or not isinstance(raw, str) or not raw.startswith(MAGIC_STR):
        return {}
    try:
        compressed = base64.b64decode(raw[4:])
        return pickle.loads(zlib.decompress(compressed))
    except Exception:
        return {}


def encode_layer_dict(layer_dict):
    """Encode a ``{v_idx: {vg_idx: weight}}`` dict -> pickled blob string."""
    raw = pickle.dumps(layer_dict, protocol=pickle.HIGHEST_PROTOCOL)
    compressed = zlib.compress(raw, level=1)
    return MAGIC_STR + base64.b64encode(compressed).decode("ascii")


def mask_value(raw):
    """Safely extract a ``float`` mask value from either storage format.

    New format: *raw* is a plain ``float`` (0.0-1.0).
    Legacy format: *raw* is ``{vg_idx: weight}`` -> first value extracted.

    Returns ``1.0`` for falsy inputs (missing mask -> fully visible).
    """
    if isinstance(raw, dict):
        return next(iter(raw.values()), 1.0) if raw else 1.0
    if isinstance(raw, (int, float)):
        return float(raw)
    return 1.0


# =========================================================================
#  Layer Compositing (formerly composite_layers in compositor.py)
# =========================================================================

def _composite_layers(meta_list, layer_data_map, mask_data_map, idx_to_name, num_verts):
    """Top-down alpha-blend all visible layers via the native Rust core.

    This is the private implementation function; external callers must use
    LayerCompositor.composite_layers() which delegates here.
    """
    meta_clean = []
    layer_decoded_map = {}
    mask_decoded_map = {}
    ordered_meta = reversed(meta_list)
    foundation_seen = False

    for layer in ordered_meta:
        if not layer.get("visible", True):
            continue
        l_idx = int(layer["index"])
        raw_layer = layer_data_map.get(l_idx)
        if not raw_layer:
            continue
        decoded = decode_layer_dict(raw_layer)
        if not decoded:
            continue
        # Coerce v_idx to int defensively: rust_composite_layers expects
        # HashMap<usize, ...> and a stray str key crashes the FFI call.
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

    rust = RustWeightEngine("layer_compositor")
    return rust.call("rust_composite_layers", meta_clean, layer_decoded_map, mask_decoded_map, num_verts)
