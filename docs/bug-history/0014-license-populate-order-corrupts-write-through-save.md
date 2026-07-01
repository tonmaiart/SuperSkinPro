# 0014 — Field order inside `_populate_from_dict` corrupted the license section via its own write-through save

**Date:** 2026-06-20
**Area:** `core/preferences/preferences_service.py`, `core/preferences/property_groups.py`

## Symptom

A test that called `PreferencesService.set_license_activation(key, token, msg)`
(persisting a valid activation), then `reset_to_default()`, then `load()` —
exactly the populate path every register() goes through — came back with
`license_key == ""` but `activation_token` sometimes still holding the old,
now-orphaned value. The two fields, written together by the same call, came
back out of sync with each other.

## Root cause

`license_key` carries `update=_on_license_field_changed`, which calls
`PreferencesService.save_to_user_file()` immediately — the same write-through
pattern every Customize field already uses, since `invoke_popup` has no
reliable close event to defer a save to (see `_on_visual_pref_changed`'s
docstring).

`_populate_from_dict()` set the three license fields in declaration order:
`license_key`, then `activation_token`, then `status_message`. Setting
`license_key` first fires the update callback **immediately**, which
serializes the *entire* live PropertyGroup to disk right then — at a point
where `license_key` already holds its new (post-populate) value but
`activation_token` / `status_message` still hold whatever they were *before*
this populate call started. The save captures a half-old, half-new state.
Nothing re-saves the fully-updated state afterward, because the two
fields set after `license_key` have no callback of their own.

## Why it wasn't obvious

`set_license_activation()` itself looked safe in isolation — it ends with an
explicit `cls.save_to_user_file()` call, which overwrites whatever the
mid-function callback wrote with the fully correct final state, so calling it
directly and reading the result back from disk works fine. The corruption
only showed up when *another* populate-style call (`reset_to_default()`,
or `load()`'s own internal `_populate_from_dict()`) ran afterward and hit the
same field-ordering hazard a second time, this time with no trailing explicit
save to paper over it. A single-call test of `set_license_activation()` would
have passed; only a populate-after-populate sequence exposed it — the same
shape of bug as `0011` (a timing/ordering hazard invisible to the simplest
test).

## Fix

In both `_populate_from_dict()` and `set_license_activation()`, set
`activation_token` and `status_message` **before** `license_key`. Since
`license_key` is the only field of the three with an update callback,
ordering it last guarantees that whenever its callback fires, the other two
fields already hold their final values for that call — so the resulting
save (premature or not) is always internally consistent. `set_license_activation()`
keeps its own trailing explicit `save_to_user_file()` as defense in depth.

This does not eliminate the *earlier-than-documented* save during
`reset_to_default()` (its docstring says "does not write to disk," but the
write-through callback fires regardless) — that mismatch already existed for
every other Customize field before this change and is out of scope here;
the fix only guarantees the save that does happen is never a torn/inconsistent
write.

## How it was diagnosed

A headless `blender --background --python` script exercised the full
activate → reset → reload round trip end-to-end (register the addon, call
the real operators/services, read back via `bpy.context...`) rather than
unit-testing each function in isolation. Printing the live PropertyGroup
state at each step showed `activation_token` surviving while `license_key`
reverted, which only makes sense if a save fired *between* the two
assignments — pointing straight at the update-callback ordering inside
`_populate_from_dict`.

## General lesson

A property with a write-through `update=` callback is not just "set this
field" — it's "set this field AND immediately serialize whatever else is
currently sitting in the rest of the group." Any function that sets multiple
sibling fields in the same group must order the callback-bearing field
**last**, or every other field it sets alongside it is at risk of being
read mid-flight. This generalizes to the three pre-existing Customize
groups too (ramp stops, palette, bone picker all use the same callback) —
they happen not to trigger visible corruption today only because nothing
currently reads them back mid-populate the way this test did.
