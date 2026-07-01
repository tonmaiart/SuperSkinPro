# 0008 — Layer/Bone list row dead-zone: native click bypassing custom operator

**Date:** 2026-06-19
**Area:** `ui/list_widget/base_list.py`

## Symptom

Rapid or imprecise clicking on a layer/bone list row sometimes leaves the
previously selected row stuck in a "selected but not active" alert/highlight
state — the same visible symptom as 0005 and 0010. The native "active" index
updates correctly to the newly clicked row, but the custom selection-pool
storage (`layer_selected_indices` for Layers, `selected_names` for Bones) is
never touched, so the previously-clicked row keeps rendering with
`selected=True, active=False`.

The trigger is clicking slightly to the right of the bone/layer name text
(within the row but not on the text itself), which happens more often with
fast or imprecise mouse movements.

## Root cause

**Not** reentrancy (0010's mechanism) and **not** CRUD operators forgetting to
sync (0005's mechanism). The root cause is a literal unclickable dead zone in
the row layout geometry.

In `SuperSkinListMixin.draw_item()` (`ui/list_widget/base_list.py`):

```python
text_row = item_split.row(align=True)
text_row.alignment = 'LEFT'          # ← THIS LINE
op_text = text_row.operator(
    self.get_row_operator_id(),
    text=self.get_search_text(item), icon=main_icon, emboss=False,
)
```

Setting `text_row.alignment = 'LEFT'` causes the operator button drawn inside
`text_row` to **shrink to fit its icon+text content** instead of stretching to
fill the full width of `text_row`. This leaves a strip of empty space to the
right of the layer/bone name (within the 85% column, before the 15%
`right_zone` column) that is still part of the `template_list` row but is
**not covered by the custom operator button**.

When a click lands in that empty strip, Blender falls back to **native
`template_list` row-select behavior**, which writes directly to the property
bound via `active_data` / `active_propname` (`obj.superskin_layers_idx` for
Layers, `obj.vertex_groups.active_index` / `superskin_storage.last_clicked_index`
path for Bones) **without invoking the custom operator**. This means:

- The native "active" index updates correctly to the newly clicked row.
- The custom selection-pool storage (`layer_selected_indices`,
  `selected_names`) is never touched, because `switch_to_layer()` /
  `write_selection()` never ran.
- The previously-clicked row (which *did* go through the custom operator and
  is still recorded as "selected" in the custom storage) keeps rendering with
  `selected=True, active=False` — the "stuck ghost selection."

This is the same **symptom class** as 0005 (two independently maintained
selection-state fields drifting apart) but with a different **trigger**: here
it's a literal unclickable dead zone in the row layout, not a CRUD operator
forgetting to sync.

## Why the previous fix attempt (0010) didn't catch it

0010 correctly diagnosed and fixed a reentrancy mechanism: unnecessary
`bpy.ops.object.mode_set()` round-trips pumping Blender's event queue and
allowing reentrant operator dispatch before the first invocation finished
writing its state. That was a real bug with a real fix, and it did eliminate
one class of stale-selection occurrences.

However, the dead-zone click-bypass mechanism is completely unrelated to
event-pump reentrancy. A click in the dead zone triggers Blender's native
row-select behavior in a single, synchronous event — no reentrancy, no mode
switching, no event-pump involvement at all. The custom operator simply never
runs. This mechanism was only found by directly re-examining the row
layout/hit-box geometry after 0010's fix failed to fully resolve the symptom.

## Fix

Removed `text_row.alignment = 'LEFT'` from `draw_item()` in
`ui/list_widget/base_list.py` (line 275).

Without the alignment override, the operator button naturally stretches to
fill the full width of `text_row` (the 85% column). Blender's default button
rendering keeps the icon and label **left-justified inside the button**
regardless of how wide the button itself is, so the visual appearance of the
layer/bone name text is unchanged — it stays left-aligned, same as before.

The only visible change is that the row's hover/click highlight background
now spans the entire 85% column width (not just the text's natural width),
and the dead zone is eliminated.

### Right-zone audit

The `right_zone` (15% column, containing the eye-toggle icon for Layers or
lock-toggle icon for Bones) has the same structural risk:
`right_zone.alignment = 'RIGHT'` causes the icon button inside to shrink to
its content (just the icon glyph), leaving a narrow strip of empty space
within the 15% column that is also a potential dead zone.

However, removing `right_zone.alignment = 'RIGHT'` would cause the icon-only
button (drawn with `text=""`) to stretch to fill the full 15% column. Blender
centers icons within icon-only buttons by default, which would move the
eye/lock icon from its current flush-right position to a centered position
within the 15% column — violating the visual constraint that the icon should
remain flush-right.

The dead zone in `right_zone` is also much narrower (~20-25px in a 15%
column at typical sidebar widths) and is at the far right edge of the row,
making it a less likely accidental click target than the main text dead zone
was. For these reasons, `right_zone` is left as-is. If future testing shows
this gap is a real problem in practice, a more sophisticated fix (e.g.,
restructuring the right column to use a full-width button with a right-aligned
sub-layout) can be applied.

## How it was diagnosed

The diagnosis came from directly examining the row layout geometry in
`draw_item()` after 0010's reentrancy fix failed to eliminate the symptom:

1. The symptom persisted despite zero event-pump opportunities in the
   layer-select operator's fast path (no `mode_set` calls, no reentrancy
   window).
2. The symptom only occurred when clicking "slightly to the right" of the
   bone/layer name — never when clicking directly on the name text itself.
3. This suggested a hit-box problem: the custom operator button's clickable
   area didn't cover the full row.
4. The `text_row.alignment = 'LEFT'` line was the only layout property that
   could constrain the button's width below the row's full width.
5. Removing it and testing confirmed: the dead zone disappeared, the text
   stayed left-aligned (Blender's default button rendering), and the
   stale-selection symptom was fully resolved for this trigger mechanism.

## General lesson

When a custom `bpy.types.UIList.draw_item()` overrides the default row-click
behavior with its own operator button, the button's **hit-box must cover the
entire row area** that `template_list` considers part of that row. Any
unintentional `alignment` constraint that shrinks the button below the row's
full width re-exposes Blender's native (and in this codebase, unwanted)
row-select fallback for whatever area is left uncovered.

This is a layout/geometry invariant, not a logic invariant — it's easy to
overlook during code review because the layout code looks innocuous and the
button appears to work correctly when clicked precisely on its visible
content.
