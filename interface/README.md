# Interface — Closed Subsystem for SuperSkinPro

This is a strictly closed interface subsystem. External feature packages under
`features/*` are strictly prohibited from importing internal layout widgets,
panels, or operators directly. External features MUST communicate with the
interface exclusively via the public Registry API
(`interface.registry.register_api`) and inherit from template components
(`interface.template_ui`).

## Package Structure

```
interface/
├── __init__.py                # Master lifecycle controller (bottom-up micro-reloads)
├── panel_main.py              # Main Sidebar panel frame (VIEW3D_PT_superskin_main); poll() requires activation; owns the superskin_active_interface WindowManager property
├── panel_gate.py               # Status + Preference panel (VIEW3D_PT_superskin_gate) — always visible, bl_order=2000000 (sorts after panel_main); hosts license entry + update checker plus the migrated System/Customize settings (ramps, palette, PREFERENCE-tab extensions — including the `debug_console` feature domain's log toggles/view, about) drawn directly below, with no nested collapsible wrapper
├── widget_preferences.py      # Layout draw engine (reads from UnifiedRegistry)
├── addon_preferences.py       # Minimal AddonPreferences stub, kept only for the vendored updater's property lookup — no longer draws user-facing settings
├── ops_preferences.py         # Preference action operators (ramp, license, reset)
├── ops_preferences_lists.py   # Scrollable UIList classes for preference collections
│
├── registry/                  # Registration API
│   ├── __init__.py
│   ├── register_api.py        # Canonical UnifiedFeatureExtension + UnifiedRegistry — draw_tab accepts a single string or an iterable of strings (get_draw_tabs() normalizes to a set) so an extension can render in more than one tab
│   └── prefs_extension_registry.py # Legacy preference registry (still defined but no longer consumed at runtime)
│
├── template_ui/               # UI Components & Mixins
│   ├── __init__.py
│   ├── base_list.py           # SuperSkinListMixin
│   ├── layout.py              # draw_list_with_sidebar
│   └── select_ops.py          # ListSelectionAdapter + resolve_row_click_selection
│
└── utils/                     # Helpers & Shaders
    ├── __init__.py
    ├── utils.py               # Context switches, caches, handlers, identity sync
    ├── gpu_utils.py           # GL primitives, bone colors
    └── op_exec.py             # Shared Operator.execute() dispatch bodies
```

## Registration Order

The `interface/__init__.py` performs bottom-up micro-reloads and registration
in this strict order:

1. **Foundations**: `register_api`, `utils` (no bpy classes)
2. **Operators**: `ops_preferences`, `ops_preferences_lists`
3. **Layout Frames**: `widget_preferences`, `addon_preferences`, `panel_main`, `panel_gate`

## Interface State (`superskin_active_interface`)

`panel_main.py` registers `WindowManager.superskin_active_interface` (EnumProperty,
values `'LAYER'` / `'SKINNING'`, default `'LAYER'`, `SKIP_SAVE`). This is the
single source of truth `widget_preferences.draw_mode_split_ui()` reads to
decide which tab's sections to draw in the main sidebar panel.

**It is deliberately decoupled from `bpy.context.mode`.** Pressing Blender's
native Tab key does not, by itself, change this state — only the explicit
"Edit Layer Weight" / "Save Weights" operators and the auto-save guard's
unguarded-exit detection flip it (`features/controller/ops_scene_modes.py`:
`_enter_edit_mode()` sets `'SKINNING'`; `_exit_edit_mode()` and
`_superskin_auto_save_guard()` set `'LAYER'`). A bare Tab press into Edit
Mode with no prior "Edit Layer Weight" trigger leaves the sidebar showing
`'LAYER'` content, since none of SuperSkinPro's own layer-editing setup
(temp `__ssp_*` vertex groups, overlays) ran.

`SUPERSKIN_OT_enter_layer_edit`'s (`"Edit Layer Weight"`) `poll()` gates on
this same state (`superskin_active_interface == 'LAYER'`), not on
`context.mode == 'OBJECT'` — `_enter_edit_mode()` already handles being
invoked from either Object Mode or a bare-Tab Edit Mode, so gating the
button on `context.mode` would leave it wrongly disabled whenever the user
tabbed into Edit Mode natively before ever clicking the button.
`SUPERSKIN_OT_save_weights` still gates on `context.mode == 'EDIT_MESH'`,
since baking the temp VGs genuinely requires being in Edit Mode.

## Invariants

- External code must NOT import from `interface.panel_main`, `interface.panel_gate`, `interface.widget_preferences`, or `interface.addon_preferences` directly.
- Feature domains interact with the registry exclusively through `interface.registry.register_api`.
- Template components (`interface.template_ui`) are the only public UI building blocks for feature domains.
- All `bl_idname`, `bl_label`, and operator class names remain unchanged, with one deliberate, narrow exception: `VIEW3D_PT_superskin_gate`'s `bl_label` was changed from `"Status"` to `"Preference"` (a Panel header string, not looked up by keymaps/RNA/F3-search the way an operator's `bl_idname`/`bl_label` is) to reflect its expanded role after the Add-on Preferences consolidation. `bl_idname` was not touched.
- Activation is enforced at the single `CoreFacade.__init__` chokepoint (`core/facade/__init__.py`), not per-panel or per-feature. `panel_main.poll()` only controls *visibility*, driven by `CoreFacade.is_system_activated()` — it is not itself a security boundary. `panel_gate.py` has no `poll()` override — it is always visible.
