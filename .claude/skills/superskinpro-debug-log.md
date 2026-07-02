---
name: superskinpro-debug-log
description: Use this skill whenever debugging or investigating a suspected bug in SuperSkinPro's core/, core_subsystems/, or features/ layers, BEFORE proposing a root cause or writing a fix. Also use it whenever adding new diagnostic output to the codebase. Trigger on "debug", "bug", "ยังไม่หาย" / "still broken" / "ไม่ทำงาน", requests to trace why something silently fails or produces wrong output, requests to read or interpret console log lines starting with "[SSP:", or any mention of "debug log", "log print", "print debug", "DebugLogService". This skill governs two things: (1) requesting and reading structured debug-log output from the user via SuperSkinPro's built-in category-gated logging system (core_subsystems/debug_logging/) instead of guessing at root causes from source reading alone, and (2) how to add new DebugLogService.log() calls when instrumenting a subsystem that isn't covered yet. See docs/bug-history/0020 and 0021 for the case study that motivated this system: two real bugs that were misdiagnosed from source reading alone and only found once real runtime log output was captured.
---

# SuperSkinPro — Debug Log Skill

SuperSkinPro has a permanent, toggleable, category-gated debug-logging system
(`core_subsystems/debug_logging/`, `DebugLogService`) — built specifically so
debugging no longer requires hand-inserting `print("[SSP-DBG]...")` statements
and hand-removing them once a bug is fixed. Log calls now **stay in the code
permanently**, gated by per-category checkboxes in Edit > Preferences > Add-ons
> Super Skin Pro > Developer / Debug Tools. This skill governs how to use it
when debugging, and how to extend it.

---

## The Core Rule: Ask for Real Logs Before Diagnosing

**Do not propose a root cause for a non-trivial core/core_subsystems bug from
source reading alone.** Read the relevant code to form a hypothesis, then ask
the user to enable the matching categories, reproduce the bug, and paste the
console output — *before* writing a fix.

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
2. Ask the user to enable exactly those categories in Preferences (not "enable
   everything" — extra categories add noise that obscures the real trail).
3. Ask them to reproduce the exact failing action once, then copy the full
   console output containing lines starting with `[SSP:<CATEGORY>]`.
4. Read the log top-to-bottom in call order. Compare values across paired
   entry/exit log lines from the same call (e.g. "verts=N before" vs "verts=N
   after") rather than assuming a function did what its name implies.

## Category → Subsystem Map

| Category (checkbox / log tag) | Covers | Real files |
|---|---|---|
| `TEMP_VG` | Edit/Object Mode transitions, `__ssp_*` temp Vertex Group bake/restore/write | `core/layer_storage/temp_vg_bridge.py`, `core/ui_controller/pipeline.py` |
| `CORE_PIPELINE` | Layer/mask read-write, composite flattening, `ss_layer_N` / `ss_mask_N` I/O | `core/facade/write.py`, `core/facade/read.py`, `core_subsystems/layer_compositor/` |
| `RUST_FFI` | Data crossing the Python↔Rust FFI boundary | `core_subsystems/rust_weight_engine/`, any `*_gateway.py` |
| `VIEWPORT_VIZ` | Heatmap/HUD drawing, shader cache invalidation, deform-generation bumps | `core/facade/visualizer.py`, `core/shaders/shader_manager.py` |
| `BONE_ID` | Bone lock/mapping resolution, orphan bone scanning and remapping | bone identity / unified mapping code (see `docs/bug-history/0021`) |
| `FEATURE_DOMAINS` | Extra Domain `execute()` dispatch (weight_apply, mirror, clipboard, etc.) | `features/*/*_feature.py` |

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

**Style:** log at entry (with the key input values) and at exit or right
before a write call (with the key output/result values) — a single log line
with no counterpart is much less useful than a before/after pair, since most
bugs in this codebase manifest as "a value silently didn't change" rather
than a crash. Prefer logging counts/lengths/small samples of dicts over full
dict dumps for anything vertex-indexed (meshes can have thousands of verts).

---

## Reference

Full design rationale: `docs/bug-history/0020-write-active-layer-mask-wipe.md`
and `docs/bug-history/0021-locks-by-id-sparse-dict-blocks-smooth.md`. The
`core_subsystems/debug_logging/` package itself has no README — this skill
file is its documentation.
