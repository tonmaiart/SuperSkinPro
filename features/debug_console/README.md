# Debug Console Domain Specification

Presents SuperSkinPro's runtime debug log (`core_subsystems/debug_logging/DebugLogService`)
as a live, scrollable panel in the "Preference" sidebar tab, replacing the
plain checkbox list that used to live inline in `interface/widget_preferences.py`.

## ⚙️ Domain Identity

- `domain_id = "debug_console"`
- `actions = []` — no entries in the `SUPERSKIN_OT_execute_action` dispatch table. See "Why no dispatch actions" below.
- `draw_tab = "PREFERENCE"`, `collapsible = True`

## 🏛️ Architecture & Dataflow

```
draw_section() ──reads──> CoreFacade.get_debug_logs() / get_debug_categories()
                ──mirrors filtered results into──> SSPrefDebugConsole.log_items (CollectionProperty)
                ──draws──> template_list() (native scrollbar) + popover(category visibility)
ops.py operators ──calls──> get_visible_entries() (this domain) / CoreFacade.clear_debug_logs()
category checkboxes ──read/write──> context.window_manager.superskin_prefs.debug.<category>
```

**Capture vs. display are fully decoupled.** `DebugLogService.is_enabled()`
always returns `True` — every category is always printed to the system
console and buffered, unconditionally. The per-category checkboxes
(`SSPrefDebug`, still core-owned, persisted to `user.json`) no longer gate
capture; this domain is the *only* consumer that reads them, purely as a
**display filter** for which categories the log view currently shows. This
guarantees the buffer's history is always complete regardless of which
categories are checked at any given moment — turning a category off just
hides it from view, it does not stop it from being logged.

This domain owns four PropertyGroups, all **transient UI-only state** (none
of it is "the log data" — that's `DebugLogService`'s buffer; `defaults_path`
is intentionally unset since there's nothing here worth surviving a restart):
- `SSPrefDebugConsole` — the search string, the `log_items` `CollectionProperty`
  that `template_list()` reads from (rebuilt from `CoreFacade.get_debug_logs()`
  on every `draw_section()` call), and `domain_visibility` (see below).
- `SSPrefDebugLogEntry` — one row's worth of log data (`timestamp`,
  `category`, `message`), the item type for `log_items`.
- `SSPrefDebugDomainVisibility` — one registered `domain_id`'s show/hide
  state (`.name` holds the `domain_id`, `.visible` the toggle). Unlike
  `log_items`, entries here are **not** cleared/rebuilt every draw
  (`_sync_domain_visibility_collection()` only *adds* missing domain_ids) —
  it holds real user toggle state that must persist across redraws.

## 🖱️ UI Widgets

- **`SUPERSKIN_PT_debug_console_categories`** — a popover `Panel` (invoked via
  `layout.popover(..., text="", icon=...)`, icon-only, not a `Menu`) holding
  one eye-icon (`HIDE_OFF`/`HIDE_ON`) toggle per category. A popover was used
  instead of drawing the checkboxes inline specifically so toggling several
  categories doesn't cost six lines of vertical space in the always-visible
  section, and instead of a `Menu` because Blender closes a `Menu` after
  every single property click, making multi-category toggling annoying — a
  popover panel stays open across clicks. The invoking button's icon reflects
  whether all six categories are currently visible (`HIDE_OFF`) or at least
  one is hidden (`HIDE_ON`).
- **`SUPERSKIN_PT_debug_console_feature_domains`** — a second, *nested*
  popover (opened via a small arrow button next to the "Feature Domains" row
  inside the first popover) listing every currently-registered `domain_id`
  (from `UnifiedRegistry.get_all()`) with its own eye-icon toggle. Lets one
  domain's dispatch-log lines (e.g. just `mirror`) be hidden without muting
  the whole `feature_domains` category. Membership is a **best-effort text
  match** (`_guess_domain_for_message()`): a message is attributed to a
  domain if it starts with `f"{domain_id}."` or `f"{domain_id}:"`, per the
  prefix convention already used by `weight_apply`/`weight_transfer`'s
  `debug_log("feature_domains", ...)` calls. A message matching no known
  `domain_id` is never hidden by this sub-filter (fail-open), only by the
  category-level toggle — this avoids silently dropping log lines just
  because a caller didn't follow the naming convention.
- **`SUPERSKIN_UL_debug_console_log`** — a minimal read-only `UIList` (no
  selection/search semantics, unlike `interface.template_ui.SuperSkinListMixin`
  which is built for selectable bone/layer rows and doesn't fit a log viewer).
  Feeds `layout.template_list()` for a real native scrollbar. Sets
  `use_filter_show = False` and overrides `draw_filter()` as a no-op — same
  technique `SuperSkinListMixin` uses (see `features/deform_bone_viewer/ui.py`)
  — to suppress Blender's own built-in filter row, since this domain already
  draws its own search box instead; Blender always draws the little
  filter-toggle icon itself for `template_list(type='DEFAULT')` (no public
  flag removes it), but with `draw_filter()` a no-op, clicking it just reveals
  an empty row instead of Blender's text/case/whole-word/invert/sort controls.
- The category popover, search box (`dc.search_query`), and the Copy/Clear
  operators are all packed into one `row(align=True)` above the list —
  Copy/Clear are icon-only (`text=""`) so the row stays compact with the
  search field getting most of the width.

There is deliberately no single-select "category filter" `EnumProperty` (an
earlier iteration of this domain had one) — the per-category visibility
checkboxes are multi-select and serve as the only filter needed, so a second,
separate single-choice filter was redundant.

## 📌 Section Placement (Priority)

`UnifiedFeatureExtension.priority` exists but only sorts extensions *within*
`UnifiedRegistry.get_by_tab('PREFERENCE')`'s own loop — it has no effect on
the hardcoded "Single Mode Color Ramp" / "Multi Mode Color Palette" / "Mask /
Layer Color Ramp" sections in `interface/widget_preferences.py::_draw_preferences()`,
since those are drawn directly, before that loop even runs, not through
`UnifiedRegistry` at all. There is no generic "draw before the hardcoded
content" hook. To put this domain's section above all three ramp/palette
sections, `_draw_preferences()` special-cases it explicitly: it looks up
`UnifiedRegistry.get_by_id("debug_console")` and draws it first, then skips
it (by id) in the later extensions loop to avoid a duplicate draw. This is a
one-off, hardcoded exception in `widget_preferences.py` — not a mechanism
another domain can opt into without a similar explicit edit there.

### Why no dispatch actions

`SUPERSKIN_OT_execute_action.execute()` always constructs `CoreFacade(context)`,
which raises `ValueError` if SuperSkinPro is not Pro-activated or there is no
active mesh object (see `core/facade/__init__.py:CoreFacade.__init__`). A
debug tool that stops working exactly when something is already broken (no
license, no object selected) defeats its own purpose. So this domain's two
real operators (`superskin.copy_debug_log`, `superskin.clear_debug_log`,
defined in `ops.py`) are standalone `bpy.types.Operator` subclasses that call
only the `@classmethod` surface of `CoreFacade`
(`get_debug_logs`/`clear_debug_logs`/`get_debug_categories`), none of which
require an instance, plus this domain's own `get_visible_entries()` helper.
This mirrors the existing precedent of `superskin.reset_prefs` /
`superskin.reset_license_activation` in `interface/ops_preferences.py`.

## 📄 File Manifest

| File | Responsibility |
|---|---|
| `debug_console_feature.py` | `SSPrefDebugLogEntry` + `SSPrefDebugDomainVisibility` + `SSPrefDebugConsole` PropertyGroups; `SUPERSKIN_UL_debug_console_log` (UIList); `SUPERSKIN_PT_debug_console_categories` (popover Panel) + `SUPERSKIN_PT_debug_console_feature_domains` (nested popover Panel); `get_visible_entries(context)` (shared visibility+search filter, used by both `draw_section()` and `ops.py`); `DebugConsoleFeature(UnifiedFeatureExtension)` — `draw_section()` draws the icon-only popover button, Copy/Clear buttons, the scrollable log list, then the search box; a `bpy.app.timers` periodic redraw (~0.5s) that only fires `tag_redraw()` on `VIEW_3D` areas while this domain's collapsible section is expanded. |
| `ops.py` | `SUPERSKIN_OT_copy_debug_log` (formats `get_visible_entries()`'s result as plain text and writes it to `context.window_manager.clipboard`), `SUPERSKIN_OT_clear_debug_log` (calls `CoreFacade.clear_debug_logs()`). |
| `__init__.py` | Reload loop (⚠️ `debug_console_feature` must reload before `ops` — `ops.py` imports `get_visible_entries` from it) + `register()`/`unregister()`; also starts/stops the redraw timer. |

No `logic.py` (no non-trivial computation), no `default_config.json` /
`defaults_path` (nothing persisted by this domain), no `draw.py`/`keymap.py`
(no viewport GPU overlay or shortcuts).

## 🛡️ Guardrails & Invariants

- Never call `CoreFacade(context)` (instance constructor) from this domain — every facade call here must be one of the `@classmethod`s listed in `core/facade/README.md`'s "Debug Logging" section, precisely so this panel keeps working when the rest of the addon can't.
- The per-category checkboxes read/write `context.window_manager.superskin_prefs.debug.<category>` directly (same object `interface/widget_preferences.py` used to draw before this domain existed) — this is core-owned persisted state, not a `core/*` file import, so it does not violate the Core Boundary Rule. Category names are sourced from `CoreFacade.get_debug_categories()`, never hardcoded, so this file never drifts from `DebugLogService.CATEGORIES`.
- **Do not reintroduce a capture-gating role for the checkboxes.** If a future change needs "only capture category X", that is a `core_subsystems/debug_logging` change, not a `features/debug_console` one — this domain must only ever read these booleans for display filtering.
- `dc.log_items` is rebuilt (cleared + re-added) from `get_visible_entries()` on every `draw_section()` call — simple and correct for a buffer capped at 200 entries, but do not use this pattern for a collection with unbounded size.
- The redraw timer checks `WindowManager.superskin_debug_console_expanded` (auto-registered by `UnifiedRegistry.register()`) every tick and no-ops when collapsed, to avoid redrawing the viewport when nobody is looking at the panel.
- `populate()`/`serialize_into()` are both no-ops (defaults from `UnifiedFeatureExtension` are already no-ops) since there is nothing to persist.
