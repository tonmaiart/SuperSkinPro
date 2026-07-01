# SuperSkinPro

Professional weight painting layers system for Blender (Python + Rust hybrid).

## Architecture

Features communicate with Core exclusively via `CoreFacade`. `UIController` is a private implementation detail of `core/` — feature code must never import or depend on it directly.

### Unified Component Architecture

Every feature domain under `features/<name>/` is a self-contained package with a single entry-point class inheriting from `UnifiedFeatureExtension` (defined in `registry/unified_feature_api.py`).

```
[UI Layout Click] → SUPERSKIN_OT_execute_action (domain_id, action_id)
                  → UnifiedRegistry.get_by_id(domain_id).execute(action_id, ctx, facade)
```

Each extension owns:
- **Action dispatch** — `execute(action, context, core_facade)` routes to domain logic.
- **UI layout** — `draw_section(layout, context)` renders the N-panel section body.
- **JSON persistence** — `populate(data)` / `serialize_into(full_dict)` handle load/save.
- **PropertyGroups** — Blender RNA properties registered on `WindowManager`.
- **Collapsible control** — `is_collapsible()` controls whether the section is wrapped in a collapsible header.

### Tab Assignment

| Tab | Domains |
|---|---|
| `LAYER` | `layer_viewer` (non-collapsible), `data_io`, `weight_transfer` |
| `SKINNING` | `deform_bone_viewer` (non-collapsible), `weight_apply`, `mirror`, `clipboard`, `auto_block_weight`, `circle_tool_adjust`, `controller` |
| `CUSTOMIZE` | `bone_picker`, `multi_color_preview` (hosted in Add-on Preferences) |

### Registration Flow

1. `features/<name>/<name>_feature.py` — defines a `UnifiedFeatureExtension` subclass and a module-level `register()` that calls `UnifiedRegistry.register(MyFeature())`.
2. `features/<name>/__init__.py` — imports `<name>_feature` and calls `<name>_feature.register()`.
3. `features/__init__.py` — imports each domain package; order controls tab rendering priority.
4. `__init__.py` (top-level) — calls `registry.register_operator()` to register `SUPERSKIN_OT_execute_action`.

### Example: Mirror Feature

The mirror domain (`features/mirror/`) is fully self-contained:

- **`mirror_feature.py`** — `MirrorFeature(UnifiedFeatureExtension)` with action dispatch, UI layout, `SSPrefMirror` PropertyGroup, `MirrorPreferencesService`, and JSON persistence hooks.
- **`ops.py`** — Operator dispatch only. Performs early pair-existence check, sets the transaction flag, then delegates to `execute_mirror_pipeline`.
- **`logic.py`** — Full pipeline (`execute_mirror_pipeline`), pair generation, Rust-accelerated apply for layer and mask channels.

Rust math is invoked via `CoreFacade.get_rust_gateway()`.

## Adding a New Feature Domain

See `registry/README.md` for the full quick-start guide with annotated template code.

Quick checklist:
1. Create `features/<name>/<name>_feature.py` extending `UnifiedFeatureExtension`.
2. Implement `get_id()`, `get_actions()`, `get_section_title()`, `get_draw_tab()`, `execute()`, `draw_section()`.
3. Add `register()` / `unregister()` calling `UnifiedRegistry.register()`.
4. Wire up `features/<name>/__init__.py` to call `<name>_feature.register()`.
5. Add `from . import <name>` to `features/__init__.py` and append to `_modules`.

## Invariants

- **ST_STRICT**: `core/` is read-only for feature code. All access routes through `CoreFacade`.
- **Naming stability**: Existing `bl_idname` values, RNA property names, and operator class names must not be renamed unless the refactoring pipeline explicitly requires it.
- **Code language**: All comments, docstrings, and documentation must be written in professional English only.
