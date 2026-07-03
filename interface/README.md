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
├── panel_main.py              # Main Sidebar panel frame (VIEW3D_PT_superskin_main); poll() requires activation
├── panel_gate.py               # Activation gate panel (VIEW3D_PT_superskin_gate) — shown instead of panel_main when not activated; hosts license entry + update checker
├── widget_preferences.py      # Layout draw engine (reads from UnifiedRegistry)
├── addon_preferences.py       # Blender native Addon Preferences block
├── ops_preferences.py         # Preference action operators (ramp, license, reset)
├── ops_preferences_lists.py   # Scrollable UIList classes for preference collections
│
├── registry/                  # Registration API
│   ├── __init__.py
│   ├── register_api.py        # Canonical UnifiedFeatureExtension + UnifiedRegistry
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

## Invariants

- External code must NOT import from `interface.panel_main`, `interface.panel_gate`, `interface.widget_preferences`, or `interface.addon_preferences` directly.
- Feature domains interact with the registry exclusively through `interface.registry.register_api`.
- Template components (`interface.template_ui`) are the only public UI building blocks for feature domains.
- All `bl_idname`, `bl_label`, and operator class names remain unchanged.
- Activation is enforced at the single `CoreFacade.__init__` chokepoint (`core/facade/__init__.py`), not per-panel or per-feature. `panel_main.poll()` and `panel_gate.poll()` only control *visibility*, driven by `CoreFacade.is_system_activated()` — they are not themselves a security boundary.
