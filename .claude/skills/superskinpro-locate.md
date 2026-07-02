---
name: superskinpro-locate
description: Use this skill FIRST whenever a task requires finding a file, folder, class, or function in SuperSkinPro, or answering "where is X" / "which file handles Y" / "find the code that does Z". Also use it as the shared reading-discipline reference invoked by superskinpro-domain, superskinpro-core-debug, and superskinpro-core-subsystem before they open any source file. Trigger on "find", "locate", "where is", "which file", "which folder", "search for", or any request naming a symbol, feature, or behavior without an explicit file path already given. Enforces three rules: identify the correct folder from the routing table below, read that folder's README.md first, then read only files inside that folder — never scan sibling top-level folders speculatively.
---

# SuperSkinPro — Locate Skill

Canonical reading-discipline reference for this project. Every other
SuperSkinPro skill (`superskinpro-domain`, `superskinpro-core-debug`,
`superskinpro-core-subsystem`) points here instead of duplicating this
protocol — if you are inside one of those skills and need to find a file,
apply the rules below rather than reading ad hoc.

---

## Reading Discipline (Strict)

1. **README-first.** Before opening any source file inside a folder, check
   the Routing Table below for that folder's `README.md`. If it has one,
   read it in full first — it is the authoritative map of that package's
   files, contracts, and entry points. Do not open source files "just to
   look around" before doing this.
2. **Scope-limit.** Once a target folder is identified, read only files
   inside that folder (and its own subfolders, if the README points there).
   Do not open files in sibling top-level folders (`core/` vs `features/`
   vs `interface/` vs `core_subsystems/`, etc.) on the assumption they might
   be related — confirm via the README or an explicit cross-reference first.
3. **Minimal-read.** Prefer `grep -n` for a specific symbol over reading a
   whole large file. When you do read a file, use `Read` with `offset`/
   `limit` if you only need one section. Read a file in full only when the
   README says it's the primary entry point, or it's already small.

---

## Folder Routing Table

### Feature domains — `features/<domain>/`

Every domain has its own `README.md`; read it before opening `ops.py`,
`logic.py`, or `<domain>_feature.py`. `features/README.md` is the
cross-domain developer guide and holds the full domain table — read it when
the task isn't scoped to one specific domain yet, or to confirm the current
list of all domains.

| Keyword triggers | Folder | README |
|---|---|---|
| layer list, layer viewer, layer panel | `features/layer_viewer/` | ✅ |
| deform bone list, bone list, influence list | `features/deform_bone_viewer/` | ✅ |
| add/scale/smooth/sharpen weight, weight apply | `features/weight_apply/` | ✅ |
| auto block, auto-assign, auto weight | `features/auto_block_weight/` | ✅ |
| mirror, mirror pair, search/replace bone name | `features/mirror/` | ✅ |
| clipboard, copy/cut/paste weight | `features/clipboard/` | ✅ |
| circle brush radius, circle tool | `features/circle_tool_adjust/` | ✅ |
| pie menu, scene mode, enter/exit edit mode, safe shrink | `features/controller/` | ✅ |
| bone picker, alt+2, diamond wedge overlay | `features/bone_picker/` | ✅ |
| multi color preview, alt+3, per-bone color overlay | `features/multi_color_preview/` | ✅ |
| weight transfer, maya-style transfer | `features/weight_transfer/` | ✅ |
| export/import json, data io, weight json | `features/data_io/` | ✅ |
| "which domains exist", domain registry, new feature | `features/` (root) | ✅ |

### Other documented layers

| Keyword triggers | Folder | README |
|---|---|---|
| registry, UnifiedFeatureExtension, UnifiedRegistry, template UI, N-panel widgets | `interface/` | ✅ `interface/README.md` |
| core_subsystems, backend pillar, rust gateway, subsystem | `core_subsystems/` | ✅ `core_subsystems/README.md` |
| CoreFacade, facade method, what can features call | `core/facade/` | ✅ `core/facade/README.md` — **the sanctioned entry point for all `core/` contracts; see Core Boundary Rule in CLAUDE.md** |
| past bug, known issue, "has this happened before" | `docs/bug-history/` | ✅ `docs/bug-history/README.md` |

### Undocumented core internals — ST_STRICT, no README at this level

These are read-only for feature work per the Core Boundary Rule in
`CLAUDE.md`. If the task is feature-domain work, do not open these at all —
rely on `core/facade/README.md`. If the task is genuinely a core bug, use
`superskinpro-core-debug`'s embedded architecture map and symptom table
instead of exploring freely here.

| Keyword triggers | Folder |
|---|---|
| undo, redo, temp VG bridge, flatten, layer switch, bone lock write | `core/ui_controller/` |
| ss_layer_N, ss_mask_N, ss_layers_meta storage | `core/layer_storage/` |
| orphan bone, bone UUID, armature identity | `core/bone_identity/` |
| GPU visualizer, shader, draw handle, deform generation | `core/shaders/` |
| preferences I/O stub (real service is in `core_subsystems/preferences/`) | `core/preferences/` |

### No-README, no-skill folders

| Keyword triggers | Folder | Note |
|---|---|---|
| default prefs json, factory preferences | `prefs/` | Single file, `default_prefs.json` — read directly. |
| rust ffi, .rs file, weight compositing math in rust | `rust_logic/src/` | No README. Match by filename instead: `auto_logic.rs`, `bone_analyzer.rs`, `checksum.rs`, `flat_bridge.rs`, `layer_compositor.rs`, `lib.rs`, `license_logic.rs`, `mirror_logic.rs`, `norm.rs`, `simple_ops_logic.rs`, `smooth_logic.rs`, `visualizer.rs`. |
| updater, addon update check | `bin/`, `superskinpro_updater/`, `bl_ext.user_default.superskinpro_updater/` | Peripheral/build artifacts — out of scope unless explicitly named. |

---

## Fallback Protocol (folder has no `README.md`)

1. Do **not** silently substitute a sibling folder's README as a stand-in.
2. If the folder is one of the "Undocumented core internals" above and the
   task is a bug/behavior question, switch to `superskinpro-core-debug` and
   use its symptom table instead of opening files ad hoc.
3. Otherwise, narrow by filename: `find <folder> -iname "*<keyword>*"`, then
   read only the matched file(s) — not the whole folder.
4. If nothing matches and the folder genuinely has no obvious entry point,
   read that folder's `__init__.py` only (it's almost always the smallest
   file that explains what the package does), then stop and report back
   rather than expanding into more folders.

## Scoped Search Command Patterns

Always scope `find`/`grep` to the identified folder — never start with an
unscoped repo-root search.

```bash
# Good — scoped to the folder identified from the routing table
find features/mirror -iname "*pair*"
grep -rn "search_replace" features/mirror

# Bad — repo-wide scan as a first move
find . -iname "*pair*"
grep -rn "search_replace" .
```

Only widen the search past the initially identified folder if:
- the folder's `README.md` explicitly points elsewhere (e.g. "see
  `core/facade/README.md`"), or
- the scoped search inside the folder is exhausted with no match, and the
  task genuinely requires looking further.

## Stop Conditions / Anti-Patterns

- Do not open a sibling top-level folder "just in case" — `core/`,
  `core_subsystems/`, `features/`, `interface/` are siblings, not a search
  path to walk.
- Do not read every file in a folder to "get context" — read the README,
  then read only the specific file(s) the task needs.
- Do not re-derive the domain list or subsystem list by listing directories
  when `features/README.md` / `core_subsystems/README.md` already state it.
- If genuinely unsure which folder applies, say so and ask, rather than
  scanning broadly to guess.
