# 0015 — Customized Preferences silently blank out after opening a different .blend file

**Date:** 2026-06-21
**Area:** `core/preferences/property_groups.py`, `core/preferences/__init__.py`

## Symptom

User report: "opening certain files makes the Preferences panel stop showing
my customized values, even though preferences aren't supposed to be
per-file." The Customize tab (ramp stops, palette, bone-picker colors) would
sometimes come up looking like nothing had ever been customized — not
reverted to factory defaults, but with **zero ramp stops at all** — only
after switching back to the original file (or restarting Blender) did the
real values reappear.

## Root cause

`bpy.types.WindowManager.superskin_prefs = bpy.props.PointerProperty(type=SSPrefRoot)`
was registered with no `options={'SKIP_SAVE'}`. `WindowManager` is itself an
ID data-block that Blender saves inside every `.blend` file (to restore
window/screen layout). Any custom property registered on it — including this
one — gets serialized into the file at save time and **restored from the
file** at load time, exactly like any other addon data living on `Scene` or
`Object`.

`PreferencesService.load()` (which reads `default.json` + `user.json` and
populates the live PropertyGroup) was only ever called once, from
`core/preferences/__init__.py`'s `register()` — i.e. once per addon-enable,
not on every file load. So opening a *different* `.blend` file mid-session
swaps in that file's own `WindowManager` ID-block, whose `superskin_prefs`
either:
- never existed when that file was saved (property added later) → Blender
  default-initializes it fresh, which for a `CollectionProperty`-backed ramp
  means **zero stops**, not even factory defaults, or
- holds whatever was live in *that* file at its own save time (stale,
  possibly mid-customization).

Either way, the live values stop reflecting `user.json` — the actual
per-machine source of truth — and nothing re-syncs them.

## Why it wasn't obvious

The docstring on `property_groups.py` already says "Registered on
`WindowManager.superskin_prefs` — not Scene, because these values are
per-machine, not saved with the .blend file" — but registering on
`WindowManager` instead of `Scene` only avoids the most *obvious* per-file
trap (visibly different per-scene panel state); it does nothing to stop
Blender from serializing the property into the file anyway, since
`WindowManager` is saved too. The bug only shows up when a *second* file is
opened in the same session — a single-file test (enable addon, open
Preferences, customize, done) never exercises the file-swap path at all,
the same shape of gap as 0002 and 0011.

## Fix

1. Added `options={'SKIP_SAVE'}` to the `superskin_prefs` `PointerProperty`
   registration, so Blender never writes it into `.blend` files (and never
   restores stale/blank data from one).
2. Added a `@bpy.app.handlers.persistent` `load_post` handler
   (`_superskin_prefs_load_handler`) in `core/preferences/__init__.py` that
   calls `PreferencesService.load()` after every file load. This is
   necessary *in addition to* `SKIP_SAVE` — `SKIP_SAVE` only stops the bad
   data path, it doesn't make the live values survive a file swap, since
   opening any file still hands the addon a brand-new `WindowManager`
   ID-block whose `PointerProperty` starts at type-defaults (empty
   collections). The handler re-populates it from `user.json` every time,
   matching the existing `_superskin_layers_load_handler` pattern in
   `ui/utils.py`.

## How it was diagnosed

A headless `blender --background --python` script reproduced the file-swap
directly: enable the addon, set a distinctive customized ramp color, call
`save_to_user_file()`, then `bpy.ops.wm.read_homefile(use_empty=True)` to
simulate opening another file in the same session, then re-read the live
PropertyGroup. Before the fix this came back with `len(stops) == 0`; after
adding `SKIP_SAVE` + the `load_post` handler it correctly returned all 7
stops with the customized color intact.

## General lesson

"Not saved with the .blend file" is not automatically true just because a
property lives on `WindowManager`/`WindowManager`-adjacent storage instead
of `Scene`/`Object` — `WindowManager` *is* part of the file. Any addon state
meant to be truly per-machine needs **both** `options={'SKIP_SAVE'}` (stop
the bad write/read) **and** an explicit `load_post` re-populate from the
real per-machine source (JSON, in this case) — `SKIP_SAVE` alone leaves the
live value blank after every file swap, not merely "not corrupted."
