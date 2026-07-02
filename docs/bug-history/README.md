# Bug History

Write-ups of bugs in SuperSkinPro that took real diagnostic effort to find
— not typos or one-line fixes, but anything where the root cause wasn't
obvious from the symptom, or where a first attempted fix looked correct
but didn't actually work. The goal is to make the second occurrence of a
similar bug (or a similar-smelling one) cheaper to diagnose than the
first, for both human and AI contributors.

## When to add an entry

Add one when:
- The fix required understanding something non-obvious about Blender's
  API, the Rust FFI boundary, or this addon's own architecture.
- A first fix attempt looked correct on inspection but didn't actually
  work, and the real cause only showed up after adding debug
  instrumentation or testing a longer/different sequence of actions.
- Future-you (or a future AI agent) would benefit from knowing "we tried
  X, it didn't work because Y, the actual fix was Z" instead of
  re-deriving that from scratch.

Don't add one for routine fixes, typos, or anything where the cause was
obvious straight from the error message.

## Format

One file per bug: `NNNN-short-kebab-case-title.md`, numbered sequentially.
Check the highest existing number in this folder before picking the next
one — don't derive it from a date or guess. Inside, cover:

- **Symptom** — what was actually observed, in the reporter's own words
  where possible. Don't paraphrase this into something that sounds more
  precise than what was actually seen; the gap between "what it looked
  like" and "what was actually wrong" is often the most useful part.
- **Root cause** — the real mechanism, not just "X was missing."
- **Why it wasn't obvious / why a first attempt didn't catch it** — if
  relevant. This is often the highest-value section for preventing a
  repeat.
- **Fix** — the actual code change, or a pointer to the relevant
  commit/file/method.
- **How it was diagnosed** — keep this even after the fix is old news;
  the diagnostic technique (e.g. "added debug prints at every decision
  point in the handler chain") is usually more reusable than the specific
  fix is.

## Index

| # | Title | Area |
|---|---|---|
| [0001](0001-layer-undo-edit-mode-desync.md) | Layer-undo silently desyncs after layer switches | `core/layer_undo.py`, `core/ui_controller.py` |
| [0002](0002-undo-handlers-not-persistent.md) | Undo/redo handlers silently dropped after file load | `core/ui_controller/undo_manager.py`, `core/shaders/shader_manager.py` |
| [0003](0003-native-vg-sync-removal-uncovered-masked-selection-bugs.md) | Native vertex-group sync removal uncovered masked selection-tracking bugs | `ui/__init__.py`, `operators/ops_interface.py`, `core/shaders/bone_mode.py`, `core/shaders/deform_bone_overlay.py` |
| [0004](0004-panel-auto-collapse-on-layer-ops.md) | Panel auto-collapses on layer select / add / remove / move / duplicate | `core/shaders/shader_manager.py`, `ui/utils.py`, `operators/ops_interface.py`, `ui/widget_tools.py` |
| [0005](0005-layer-multiselect-pool-stale-after-crud.md) | Stale layer multi-selection after Add / Remove / Move / Duplicate | `ui/utils.py`, `operators/ops_interface.py` |
| [0006](0006-clipboard-operator-registered-after-ui.md) | Clipboard operators referenced in UI before registration | `clipboard/ops.py`, `ui/widget_deform_bones.py`, `ui/widget_tools.py` |
| [0007](0007-full-invalidate-and-python-checksum-causing-lag.md) | Full GPU cache invalidation + Python-only undo checksum causing severe lag on bone hover, bone select, and layer switch | `core/shaders/shader_manager.py`, `core/ui_controller/layer_crud.py`, `core/ui_controller/ui_controller.py`, `core/ui_controller/undo_manager.py`, `rust_logic/src/checksum.rs` |
| [0008](0008-list-row-dead-zone-native-click-bypass.md) | Row layout dead-zone: native template_list click bypassing custom operator | `ui/list_widget/base_list.py` |
| [0009](0009-merge-layers-voids-deform-weight-outside-mask.md) | Merge Selected Layers voids deform-bone weight data outside mask | `core/layer_manager/compositor.py` |
| [0010](0010-color-only-invalidate-stale-deformed-coords.md) | `color_only` invalidate left the visualizer drawing weight-driven deformation at stale coordinates | `core/shaders/visualizer_base.py`, `core/shaders/bone_mode.py`, `core/shaders/mask_mode.py`, `core/shaders/shader_manager.py`, `core/ui_controller/pipeline.py`, `core/ui_controller/layer_crud.py` |
| [0011](0011-checksum-gate-always-skips-restore.md) | Deferred checksum baseline computed AFTER native undo, so the checksum gate always skipped restore | `core/ui_controller/undo_manager.py` |
| [0012](0012-checksum-collision-on-round-floats.md) | `rust_deform_checksum` collides for "round" weight values, silently skipping undo restore | `rust_logic/src/checksum.rs` |
| [0013](0013-undo-of-weight-op-bounces-through-object-mode.md) | Undo of a weight op transiently exits Edit Mode, tearing down the visualizer/panel | `core/shaders/shader_manager.py`, `core/ui_controller/undo_manager.py` |
| [0014](0014-license-populate-order-corrupts-write-through-save.md) | Field order inside `_populate_from_dict` corrupted the license section via its own write-through save | `core/preferences/preferences_service.py`, `core/preferences/property_groups.py` |
| [0015](0015-windowmanager-prefs-leak-per-file.md) | Customized Preferences silently blank out after opening a different .blend file (WindowManager is saved in the file) | `core/preferences/property_groups.py`, `core/preferences/__init__.py` |
| [0016](0016-undo-redesign-temp-vg-native.md) | Undo system redesigned: Temp Vertex Groups replace parallel stack | `core/ui_controller/undo_manager.py`, `core/layer_storage/temp_vg_bridge.py`, `core/ui_controller/pipeline.py`, `core/ui_controller/layer_crud.py`, `operators/ops_scene_modes.py` |
| [0017](0017-orphan-bone-weight-ops.md) | Orphan bones now fully supported in weight ops | `core/orphan_resolver/`, `core/ui_controller/ui_controller.py`, `core/ui_controller/operations.py`, `core/layer_storage/geometry.py`, `core/layer_storage/temp_vg_bridge.py` |
| [0018](0018-weight-op-stale-temp-vg-read-after-undo-redesign.md) | Weight ops read stale temp VG data after 0016 undo redesign | `core/ui_controller/pipeline.py`, `core/layer_storage/temp_vg_bridge.py`, `core/ui_controller/ui_controller.py`, `features/weight_apply/weight_apply_domain.py` |
| [0019](0019-auto-block-weight-stale-write-path-edit-mode.md) | Auto Block Weight stale write path bypasses temp VG bridge in Edit Mode | `features/auto_block_weight/auto_block_domain.py` |
| [0020](0020-write-active-layer-mask-wipe.md) | Layer mask silently wiped on every weight op in Edit Mode | `core/facade/write.py`, `core/layer_storage/temp_vg_bridge.py` |
| [0021](0021-locks-by-id-sparse-dict-blocks-smooth.md) | Smooth/Sharpen silently no-op on any layer with no explicitly-locked bones | `core/facade/read.py`, `rust_logic/src/smooth_logic.rs`, `features/weight_apply/weight_apply_feature.py` |
| [0022](0022-deform-bones-list-selfheal-checks-mask-row-only.md) | Deform Bones list stuck showing only "Mask" — self-heal resync only detected a missing Mask row, not missing real bone rows | `features/deform_bone_viewer/ui.py`, `interface/utils/utils.py` |
| [0023](0023-weight-transfer-mask-default-fallback.md) | Weight Transfer wrote zero vertices because a missing mask entry was treated as `0.0` instead of the layer's `mask_default` | `features/weight_transfer/ops.py`, `core/layer_storage/topology_heal.py` |