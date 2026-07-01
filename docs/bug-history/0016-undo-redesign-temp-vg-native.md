# 0016 — Undo system redesigned: Temp Vertex Groups replace parallel stack

**Date:** 2026-06-25
**Area:** `core/ui_controller/undo_manager.py`, `core/layer_storage/temp_vg_bridge.py`,
          `core/ui_controller/pipeline.py`, `core/ui_controller/layer_crud.py`,
          `operators/ops_scene_modes.py`

## Root cause fixed

Blender's Edit-Mode undo (BMesh) tracks Vertex Group weights natively but
never tracks ID Properties (ss_layer_N). undo_manager.py maintained a parallel
snapshot stack to compensate, causing bugs 0001, 0011, 0012, 0013.

## Solution

On Enter Edit Mode, the active layer is loaded into real Vertex Groups with
the `__ssp_*` prefix. Blender's BMesh undo tracks these automatically. On
Exit Edit Mode (or layer switch), they are baked back to ss_layer_N.
`__ssp_meta` stores the active layer index as a custom property so
undo_post can restore the correct layer after a Ctrl+Z of a layer switch.

## What was deleted

~350 lines + Rust checksum replaced by ~60 lines + temp_vg_bridge.py (~150 lines).
Bugs 0001, 0011, 0012, 0013 are eliminated structurally.

## Retained

`_undo_restore_in_progress` flag retained — ShaderManager still needs it to
ignore the transient EDIT→OBJECT→EDIT bounce that memfile restore causes.
push() and sync_checksum() retained as no-op stubs for call-site compatibility.
