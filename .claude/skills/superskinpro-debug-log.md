---
name: superskinpro-debug-log
description: Use this skill whenever debugging or investigating a suspected bug in SuperSkinPro's core/, core_subsystems/, or features/ layers, BEFORE proposing a root cause or writing a fix. Also use it whenever adding new diagnostic output to the codebase. Trigger on "debug", "bug", "ยังไม่หาย" / "still broken" / "ไม่ทำงาน", requests to trace why something silently fails or produces wrong output, requests to read or interpret console log lines starting with "[SSP:", or any mention of "debug log", "log print", "print debug", "DebugLogService", "debug console". This skill governs three things: (1) requesting and reading structured debug-log output from the user via SuperSkinPro's built-in debug-logging system (core_subsystems/debug_logging/, surfaced in the viewport sidebar by features/debug_console/) instead of guessing at root causes from source reading alone, (2) how to add new DebugLogService.log() calls when instrumenting a subsystem that isn't covered yet, and (3) the UI location/behavior of the Debug Console panel itself. See docs/bug-history/0020 and 0021 for the case study that motivated this system: two real bugs that were misdiagnosed from source reading alone and only found once real runtime log output was captured.
---

# SuperSkinPro — Debug Log Skill

SuperSkinPro has a permanent, always-on, category-tagged debug-logging system
(`core_subsystems/debug_logging/`, `DebugLogService`) — built specifically so
debugging no longer requires hand-inserting `print("[SSP-DBG]...")` statements
and hand-removing them once a bug is fixed. Log calls **stay in the code
permanently** and are **always captured** — `DebugLogService.is_enabled()`
always returns `True`, so every category is always printed to the system
console and buffered, unconditionally, whether or not anyone has ever opened
the Debug Console. This skill governs how to use it when debugging, and how
to extend it. For the console's own internal architecture (PropertyGroups,
popover widgets, priority pinning, etc.), see `features/debug_console/README.md`
— this skill file only covers the parts relevant to *using* it while debugging.

## Where the Debug Console lives

3D Viewport sidebar → "Super Skin Pro" tab → **Preference** panel → the very
first collapsible section (pinned above "Single Mode Color Ramp" — a
one-off hardcoded exception in `interface/widget_preferences.py`, not a
generic priority mechanism other domains can use). One compact row holds,
left to right: an icon-only popover button (eye icon) for category
visibility, a search box, and icon-only Copy/Clear buttons — followed by a
scrollable log list (4 rows tall by default, native scrollbar).

**The category checkboxes are a display filter only, not a capture switch.**
Unchecking a category in the popover just hides it from the on-screen list;
it does not stop that category from being logged to the system console or
buffered. There is no "please enable category X first" step before
reproducing a bug — everything is always being captured already.

---

## The Core Rule: Ask for Real Logs Before Diagnosing

**Do not propose a root cause for a non-trivial core/core_subsystems bug from
source reading alone.** Read the relevant code to form a hypothesis, then ask
the user to reproduce the bug and paste the console output — *before* writing
a fix.

This is not optional caution — it is a documented lesson from this project's
own history. `docs/bug-history/0020` and `0021` were both first investigated
by reading source code and proposing a fix from static analysis (including a
fix independently proposed by a different AI that converged on the same
plausible-but-wrong-or-incomplete diagnosis). Both fixes were confirmed wrong
or incomplete only once real debug-log output was captured — one turned out
to be a genuine second bug hiding behind the first, invisible from source
reading because two unrelated code paths produced the identical symptom.
Treat "the code looks like it should be right" as insufficient evidence when
a fix doesn't resolve the user's reported symptom on retest.

**When to skip asking for logs:** trivial, obviously-localized bugs (typo,
off-by-one, wrong operator string, syntax error) where the fix is unambiguous
from reading the one relevant line. For anything where the failure crosses
more than one function or the mechanism isn't immediately obvious, ask first.

---

## Requesting Logs

1. Identify which categories are relevant to the symptom (table below).
2. Ask the user to reproduce the exact failing action once, then either:
   - Copy the raw system console output containing lines starting with
     `[SSP:<CATEGORY>]`, **or**
   - Use the Debug Console's icon-only Copy button, after first opening the
     "Visible Categories" popover and checking only the relevant category
     boxes (unrelated categories add noise). If the symptom is specifically
     in `feature_domains`, the popover has a nested sub-popover (small arrow
     next to that row) to narrow it to one specific domain (e.g. just
     `mirror`) instead of every domain's dispatch log mixed together — see
     "Per-domain sub-filter caveat" below before relying on this for a
     domain you're not certain follows the naming convention.
3. Read the log top-to-bottom in call order. Compare values across paired
   entry/exit log lines from the same call (e.g. "verts=N before" vs "verts=N
   after") rather than assuming a function did what its name implies.

### Per-domain sub-filter caveat

The nested "Feature Domains" sub-filter attributes a log line to a domain by
a **text-prefix guess** (`message.startswith(f"{domain_id}.")` or
`f"{domain_id}:"`), not a real structured tag — `DebugLogService.log()` only
ever stores `(category, message)`, nothing that identifies which domain
called it. A message that doesn't follow this prefix convention is never
hidden by the sub-filter (fail-open) but also won't be pulled in when a user
filters down to one specific domain. If a "Copy Log" capture filtered to one
domain looks unexpectedly empty or thin, check whether the domain's
`debug_log("feature_domains", ...)` calls actually follow the convention (see
"Adding New Log Calls" below) before concluding the domain isn't logging
anything at all.

## Category → Subsystem Map

| Category (checkbox / log tag) | Covers | Real files |
|---|---|---|
| `TEMP_VG` | Edit/Object Mode transitions, `__ssp_*` temp Vertex Group bake/restore/write | `core/layer_storage/temp_vg_bridge.py`, `core/ui_controller/pipeline.py` |
| `CORE_PIPELINE` | Layer/mask read-write, composite flattening, `ss_layer_N` / `ss_mask_N` I/O | `core/facade/write.py`, `core/facade/read.py`, `core_subsystems/layer_compositor/` |
| `RUST_FFI` | Data crossing the Python↔Rust FFI boundary | `core_subsystems/rust_weight_engine/`, any `*_gateway.py` |
| `VIEWPORT_VIZ` | Heatmap/HUD drawing, shader cache invalidation, deform-generation bumps | `core/facade/visualizer.py`, `core/shaders/shader_manager.py` |
| `BONE_ID` | Bone lock/mapping resolution, orphan bone scanning and remapping | bone identity / unified mapping code (see `docs/bug-history/0021`) |
| `FEATURE_DOMAINS` | Extra Domain `execute()` dispatch (weight_apply, mirror, clipboard, etc.) — sub-filterable per domain in the Debug Console, see above | `features/*/*_feature.py` |

If a symptom spans two categories (e.g. a weight-apply action that also
touches temp VGs), ask for both together — the interleaved log order across
categories is itself diagnostic evidence (which subsystem ran first, whether
one call's output feeds the next call's input).

---

## Adding New Log Calls

Use this when instrumenting a subsystem that has no `DebugLogService.log(...)`
calls yet. Log calls are permanent additions, not scaffolding to delete later
— pick the correct existing category rather than inventing a new one unless
the code genuinely doesn't fit any of the six above (adding a 7th category
requires updating `CATEGORIES` in `core_subsystems/debug_logging/debug_log_service.py`
**and** the matching field in `SSPrefDebug`
(`core_subsystems/debug_logging/property_groups.py`) — the assert at the
bottom of that file will fail loudly at import time if they drift apart).

**From `core/` or `core_subsystems/` files** — import and call directly:
```python
from ...core_subsystems.debug_logging import DebugLogService
DebugLogService.log("temp_vg", f"write_layer_to_temp_vgs_bm() ENTRY: verts={len(layer_str)}")
```
(adjust the relative-import dot count to the file's actual depth)

**From `features/*_feature.py` files** — never import `core_subsystems/`
directly (`ST_PURE_BACKEND` boundary, see `superskinpro-domain` skill). Go
through the facade instead — `execute()` always receives `core_facade`:
```python
core_facade.debug_log("feature_domains", f"weight_apply.execute() action={action!r}")
```

**Required convention for `"feature_domains"` category specifically:** start
the message with the domain's exact `domain_id` followed by `.` or `:`
(`f"{domain_id}.execute() ..."` or `f"{domain_id}: ..."`), matching the
existing `weight_apply`/`weight_transfer` calls. This is what lets the Debug
Console's per-domain sub-filter attribute the line correctly — without it,
the line still always prints/buffers (capture is unconditional either way),
it just can't be isolated to one domain in the console, only shown/hidden as
part of the whole `feature_domains` category. Other categories have no such
convention since they aren't sub-filterable per-domain.

**Style:** log at entry (with the key input values) and at exit or right
before a write call (with the key output/result values) — a single log line
with no counterpart is much less useful than a before/after pair, since most
bugs in this codebase manifest as "a value silently didn't change" rather
than a crash. Prefer logging counts/lengths/small samples of dicts over full
dict dumps for anything vertex-indexed (meshes can have thousands of verts).

---

## Reference

Full design rationale for the logging system itself: `docs/bug-history/0020-write-active-layer-mask-wipe.md`
and `docs/bug-history/0021-locks-by-id-sparse-dict-blocks-smooth.md`. The
`core_subsystems/debug_logging/` package itself has no README — this skill
file is its documentation. For the Debug Console panel's own architecture
(PropertyGroups, popover widgets, the scrollable UIList, the priority-pinning
special case, the per-domain sub-filter's implementation), see
`features/debug_console/README.md`.
