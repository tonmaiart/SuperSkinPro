# multi_color_preview — Multi-Color Per-Bone Weight Visualizer

## Domain Identity

- **Domain ID:** `multi_color_preview`
- **Actions:** `start_multi_color`, `stop_multi_color`, `toggle_multi_color`
- **Tab:** `PREFERENCE`
- **Keymap:** Alt+3 → `superskin.toggle_multi_color`

## Architecture & Dataflow

```
Alt+3 keymap
  → superskin.toggle_multi_color (ops.py)
  → run_domain_via_unified(context, "multi_color_preview", "toggle_multi_color") (interface/utils/op_exec.py)
  → UnifiedRegistry.execute(...) → MultiColorPreviewFeature.execute(...)
  → draw.toggle() / draw.start() / draw.stop()
  → SpaceView3D draw_handler_add / remove
```

Data reads in the draw callback use Blender properties directly (`obj["__ssp_meta_map"]`, `obj.data["ss_layer_N"]`, bmesh deform layers) — no core imports.

## File Manifest

| File | Responsibility |
|---|---|
| `__init__.py` | Bottom-up micro-reload, register/unregister lifecycle |
| `multi_color_preview_feature.py` | `MultiColorPreviewFeature(UnifiedFeatureExtension)` — action dispatch (start/stop/toggle → `draw.py`), no-op UI layout, `SSPrefMultiColorPreview` PropertyGroup (placeholder, no configurable properties yet) |
| `draw.py` | GPU draw callback, 3-tier cache (topo/sel/col), color computation, handle lifecycle |
| `ops.py` | `superskin.toggle_multi_color` operator shell |
| `keymap.py` | Alt+3 keymap binding |
| `default_config.json` | Default `active_bone_boost` value |

## Guardrails & Invariants

- **No core imports.** `draw.py` reads only Blender data-bus properties.
- **`__ssp_meta_map`** on the object stores `{str(bone_id): bone_name}`, written by `core/layer_storage/temp_vg_bridge.py` when loading temp VGs. The draw callback parses this to map temp VG indices to bone names in Edit Mode.
- **`__ssp_deform_gen`** on the object is incremented by `pipeline.finish()` on every weight write. The color cache key includes this value to detect weight changes at the same Blender frame.
- **Native overlay toggle:** `start()` disables `overlay.show_vertex_group_weights` (to prevent color blending with native layer). `stop()` and `cleanup()` restore it.
- **`draw.cleanup()`** is called from `unregister()` — always removes any live draw handles.
- **PREFERENCE tab:** registered with `draw_tab = "PREFERENCE"`; there is no `'SYSTEM'` tab in the current registry (see `interface/registry/register_api.py` — valid values are `'LAYER'`, `'SKINNING'`, `'PREFERENCE'`).
- The domain self-registers via `UnifiedRegistry.register(MultiColorPreviewFeature())`, called from `register()` in `__init__.py` — not automatically at import time.
