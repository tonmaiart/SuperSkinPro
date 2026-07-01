# 0006 — Clipboard operators referenced in UI before registration,
          causing "unknown operator" draw errors

**Date:** 2026-06-19
**Area:** `clipboard/ops.py` (formerly `operators/ops_weight_apply.py`), `ui/widget_deform_bones.py`,
          `ui/widget_tools.py`

## Symptom

On panel draw in Edit Mode, the Blender console printed:

    UILayout.operator(): unknown operator 'object.ssp_paste_weight_subtract'
    UILayout.operator(): unknown operator 'object.ssp_paste_weight_replace'

The SuperSkinPro sidebar panel drew with missing/grey buttons for the
new clipboard Paste Subtract and Paste Replace operations. The Copy,
Cut, and Paste Add buttons may or may not have shown the same error
depending on deployment order.

## Root cause

Blender resolves `layout.operator(bl_idname)` calls at **draw time**,
not at Python parse/import time. If the operator class has not been
registered with `bpy.utils.register_class()` before the panel draws,
Blender logs the "unknown operator" warning and skips the button — it
does not raise a Python exception, so the panel continues drawing
partially.

The UI files (`widget_deform_bones.py`, `widget_tools.py`) were updated
to include all five clipboard operator `bl_idname` strings in their
`button_defs` lists. However, the corresponding operator classes
(`OBJECT_OT_ssp_paste_weight_subtract`, etc.) were either not yet added
to `operators/ops_weight_apply.py` or were added but omitted from the
`_classes` tuple, so `register()` never called
`bpy.utils.register_class()` on them.

## Why it wasn't obvious

The error does not crash the panel — it only logs a console warning and
skips the button. A developer who deployed the UI changes first (to
verify layout) and planned to add the operator logic second would see a
working (but partially empty) panel, not a traceback. The warning
message names the `bl_idname` string, not the class or file, which
requires knowing the `bl_idname` → class → file mapping to find the
fix.

This class of error is also invisible during the static analysis
phase: Python can parse both files successfully, import them
successfully, and call `register()` successfully — the failure only
manifests when Blender tries to resolve the string against the live
RNA registry during the first draw call.

## Fix

Added all five clipboard operator class definitions
(`OBJECT_OT_ssp_copy_weight`, `OBJECT_OT_ssp_cut_weight`,
`OBJECT_OT_ssp_paste_weight_add`, `OBJECT_OT_ssp_paste_weight_subtract`,
`OBJECT_OT_ssp_paste_weight_replace`) to `clipboard/ops.py`
(they were originally placed in the now-deleted `operators/ops_weight_apply.py`)
and included them in the `_classes` tuple so `register()` /
`unregister()` process them automatically.

## General lesson

**Always add the operator class to `_classes` before deploying the UI
button that references it.** The safe deployment order is:

  1. Add operator class + add to `_classes` (register step)
  2. Add UI button referencing the `bl_idname`
  3. Test that the panel draws without console warnings

The reverse order (UI first, operator second) works at Python level but
fails silently in Blender's draw system. In this codebase, Steps 1 and
2 should be in the same commit / agent run — see the "Append, don't
reorder" note in AGENTS.md's Cache Stability section.
