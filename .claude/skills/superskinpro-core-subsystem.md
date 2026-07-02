---
name: superskinpro-core-subsystem
description: Use this skill for ANY task involving SuperSkinPro core_subsystems/ layer. Covers four modes: (1) CREATING — scaffolding a new subsystem package under core_subsystems/; (2) REFINING — improving or extending an existing subsystem's logic, gateway, or service class; (3) VERIFYING — pre-handoff correctness gate checking all 5 invariants; (4) EDITING — targeted changes to a specific file inside core_subsystems/. Trigger on any prompt mentioning "core subsystem", "new subsystem", "add subsystem", "create subsystem", "refine subsystem", "edit subsystem", "verify subsystem", "audit subsystem", "preferences subsystem", "license subsystem", "rust gateway", "FFI layer", or any request to read, write, or inspect files under core_subsystems/. Always trigger when the task names a specific file such as preferences_service.py, license_gateway.py, property_groups.py, rust_weight_engine.py, flat_array_bridge.py, or topology_cache_manager.py inside core_subsystems/.
---

# SuperSkinPro — Core Subsystem Skill

This skill governs all work inside the `core_subsystems/` Backend Pillar Layer.
Jump to the relevant mode below.

- **[Mode A: Create](#mode-a-create)** — Scaffold a new subsystem package
- **[Mode B: Refine](#mode-b-refine)** — Extend or improve an existing subsystem
- **[Mode C: Verify](#mode-c-verify)** — Pre-handoff correctness gate
- **[Mode D: Edit](#mode-d-edit)** — Targeted single-file change
---

Before opening any file, invoke `superskinpro-locate` for the reading
discipline and to confirm which subsystem folder applies — it also lists
`core_subsystems/README.md` as the always-read entry point for this layer.

## Layer Contract (Read Before Any Mode)

`core_subsystems/` is the **Backend Pillar Layer** — stateless infrastructure
that upper core modules call directly. It sits *below* `core/` and *above* Rust FFI.

```
features/          ← NEVER imports from core_subsystems/ directly
core/              ← Only layer allowed to import core_subsystems/
core_subsystems/   ← THIS LAYER (stateless, leaf-node modules)
Rust binary        ← Called only via gateway files using flat arrays
```

### The 5 Invariants — Violations are BLOCKERS

**INV-1 — ST_PURE_BACKEND (Upper-Only Access)**
Only `core/` may import from `core_subsystems/`. `features/` importing here
directly is a hard violation. All feature access must go through `CoreFacade`.

**INV-2 — One-Way Dependency Chains Only**
Intra-subsystem imports between encapsulated packages are permitted only in
strict one-way dependency chains — circular imports are forbidden. Prefer
threading data through method arguments from the caller in `core/` over
adding a new cross-subsystem import; only add a direct one-way import when
that's clearly cleaner, and never introduce a cycle.

**INV-3 — No `bpy.ops`, No `bpy.context` Mutation**
Read-only access to `bpy.types` or primitive data is allowed. Calling
`bpy.ops.*` or mutating `bpy.context` state is strictly forbidden. Mode and
state transitions are controlled by the layer above.

**INV-4 — Pure Data-Driven FFI Interface**
Rust gateway functions must send and receive only `array.array` (contiguous
flat arrays) or plain Python types (`dict`, `list`, `str`, `int`, `float`).
Never pass Python objects or complex structures across the FFI boundary.
This enforces Zero-Copy Execution and prevents memory leaks.

**INV-5 — Strict English, No Emojis**
All source code, docstrings, comments, and error messages must be written in
professional English. No emojis, slang, or informal symbols anywhere in code.

### Approved Exceptions to INV-2

Two subsystems have pre-approved cross-layer access — do not flag these as violations:

| File | Approved Exception |
|---|---|
| `preferences/property_groups.py` | May lazy-import `ShaderManager` from core inside `update` callbacks to trigger viewport color refresh |
| `license_gateway/license_gateway.py` (`LicenseGateway`) | May access `PreferencesService` for License Key / Activation Token I/O (Preferences acts as generic file I/O, not a domain concern) |

---

## Standard Subsystem Structure

```
core_subsystems/my_subsystem/
├── __init__.py                  # Package lifecycle + re-export shims + hot-reload
├── my_subsystem_gateway.py      # Low-level FFI / RustGateway bridge (if Rust is involved)
└── my_subsystem_service.py      # OOP service class — business logic and data processing
```

`gateway.py` is optional — only needed when the subsystem calls Rust FFI.
`service.py` is always required — it is the public surface consumed by `core/`.

### Standard `__init__.py` (Hot-Reload Safe)

```python
from importlib import reload
from . import my_subsystem_gateway
from . import my_subsystem_service

# Bottom-up reload: gateway (foundations) before service (consumer)
for mod in (my_subsystem_gateway, my_subsystem_service):
    try:
        reload(mod)
    except Exception:
        pass

from .my_subsystem_service import MySubsystemService
__all__ = ["MySubsystemService"]
```

If no gateway file exists, remove it from the reload loop and imports.

---

## Mode A: Create

Scaffold a brand-new subsystem under `core_subsystems/`.

### A1 — Determine Files Needed

| Condition | Files |
|---|---|
| Pure Python logic, no Rust | `__init__.py` + `my_subsystem_service.py` |
| Calls Rust FFI | `__init__.py` + `my_subsystem_gateway.py` + `my_subsystem_service.py` |

### A2 — Write `my_subsystem_service.py` First

```python
"""
<subsystem_name> service — <one-line description>.

Consumed exclusively by core/ modules. Must not be imported from features/.
"""
from __future__ import annotations


class MySubsystemService:
    """<Class docstring — what this service does and its stateless contract.>"""

    @staticmethod
    def some_operation(data: list[float]) -> dict:
        """<Method docstring.>

        Args:
            data: <description>

        Returns:
            <description>
        """
        ...
```

Rules for service classes:
- All methods are `@staticmethod` or `@classmethod` — no instance state.
- Arguments and return types are plain Python types or `array.array`.
- No `bpy.ops` calls, no `bpy.context` mutations.
- No imports from sibling subsystem packages.

**Real example to check the pattern against:** `context_selection_service/`
— `__init__.py` reloads its one private module then exports exactly one
public class, `ContextSelectionService`, via `__all__`. Use it as the
reference shape when scaffolding a new subsystem.

### A3 — Write `my_subsystem_gateway.py` (Only if Rust FFI Needed)

```python
"""
<subsystem_name> gateway — low-level Rust FFI bridge.

Translates Python data structures into contiguous flat arrays for
zero-copy handoff to the Rust binary. Never called directly from features/.
"""
from __future__ import annotations
import array
from ...core_subsystems.rust_loader import get_rust_module


def call_rust_operation(flat_data: array.array) -> array.array:
    """<Docstring.>

    Args:
        flat_data: array.array of type 'f' (float32), length = n_verts * n_bones.

    Returns:
        array.array of type 'f' with result data.
    """
    rust = get_rust_module()
    if rust is None:
        raise RuntimeError("Rust module unavailable.")
    return rust.my_operation(flat_data)
```

FFI rules:
- Input and output: `array.array` with explicit typecode (`'f'` for float32, `'i'` for int32).
- Never wrap Rust results in Python objects before returning — keep flat.
- Always guard with `get_rust_module()` null check and raise `RuntimeError` on unavailable.

### A4 — Wire `__init__.py`

Use the standard hot-reload template from the Layer Contract section above.
Export only the service class via `__all__`.

### A5 — Register in `core_subsystems/__init__.py`

```python
# core_subsystems/__init__.py — append to existing imports
from . import my_subsystem

# If the subsystem has no bpy classes, no register()/unregister() needed.
# Only add register/unregister if the subsystem introduces PropertyGroups.
```

### A6 — Mode A Checklist

- [ ] `my_subsystem_service.py` uses only `@staticmethod` / `@classmethod` — no instance state
- [ ] No `bpy.ops` or `bpy.context` mutation anywhere in the new files
- [ ] No imports from sibling `core_subsystems/*` packages (INV-2)
- [ ] FFI functions use `array.array` only — no Python objects across boundary (INV-4)
- [ ] `get_rust_module()` null-guarded in every gateway call
- [ ] `__init__.py` has bottom-up reload loop and exports only the service class
- [ ] Subsystem imported in `core_subsystems/__init__.py`
- [ ] All docstrings and comments in professional English, no emojis (INV-5)

---

## Mode B: Refine

Extend or improve an existing subsystem. Read the target files first, then apply changes.

### B1 — Before Touching Any File

1. Read the target subsystem files to understand current structure.
2. Identify which of the 5 invariants the planned change could affect.
3. If adding a new method that might need data from another subsystem,
   prefer threading the data through the caller in `core/` (INV-2). A direct
   one-way import from another subsystem is only acceptable if it doesn't
   create a cycle — never add a new cross-import without checking this.

### B2 — Adding a New Method to a Service

- Add as `@staticmethod` or `@classmethod`.
- Type-annotate all arguments and return value.
- Write a complete docstring (Args + Returns sections).
- If the method calls Rust, add the FFI call to `gateway.py` first,
  then call the gateway from the service. Never call Rust directly from service.

### B3 — Adding a New Rust FFI Call

1. Add the gateway function in `*_gateway.py` with `array.array` I/O.
2. Add the corresponding service method in `*_service.py` that calls the gateway.
3. Never expose the gateway function publicly — `__all__` exports only the service.

### B4 — Refine Checklist

- [ ] No new cross-imports between sibling subsystems introduced
- [ ] New methods are stateless (`@staticmethod` / `@classmethod`)
- [ ] FFI boundary still uses `array.array` only
- [ ] `__init__.py` reload loop updated if new files were added
- [ ] Docstrings updated to reflect new behaviour
- [ ] Approved exceptions (preferences lazy-import, license_gateway PreferencesService access) preserved if present

---

## Mode C: Verify

Pre-handoff correctness gate. Run all checks below and produce a report.
A "VERIFIED" sign-off requires zero BLOCKERs.

### C1 — Invariant Scan (grep / read each file)

For each file in the subsystem, check:

```
[INV-1] BLOCKER  — any import of core_subsystems/* from inside features/
[INV-2] BLOCKER  — any circular cross-import between sibling subsystem packages
                   (exception: preferences→ShaderManager, license_gateway→PreferencesService;
                   one-way, non-circular cross-imports are otherwise permitted)
[INV-3] BLOCKER  — any call to bpy.ops.* or mutation of bpy.context
[INV-4] BLOCKER  — any Python object (non-primitive) passed across FFI boundary
[INV-5] WARNING  — emoji, non-English comment, or informal language in code
```

### C2 — Structure Check

| Item | Expected |
|---|---|
| `__init__.py` exists | ✅ |
| `__init__.py` has bottom-up reload loop | ✅ |
| `__init__.py` exports only service class via `__all__` | ✅ |
| `*_service.py` exists | ✅ |
| All service methods are `@staticmethod` or `@classmethod` | ✅ |
| `*_gateway.py` present if Rust FFI used | ✅ |
| Gateway functions return `array.array` only | ✅ |
| `get_rust_module()` null-guarded in every gateway call | ✅ |
| Subsystem listed in `core_subsystems/__init__.py` | ✅ |

### C3 — Docstring Completeness

Every public method in the service class must have:
- One-line summary
- `Args:` section (if arguments exist)
- `Returns:` section (if non-None return)
- Written in professional English

### C4 — Report Format

```
SUBSYSTEM: <name>
MODE: VERIFY

[BLOCKER] <file>:<line> — <invariant violated> — <description>
[WARNING] <file>:<line> — <issue description>
[INFO]    <file> — <observation>

RESULT: VERIFIED — ready for handoff
      | VERIFY FAILED — X blocker(s) must be resolved
```

---

## Mode D: Edit

Targeted change to a single file. Use this mode for small fixes, docstring
updates, or adding one method without restructuring the subsystem.

### D1 — Scope Gate

Before editing, confirm the change stays within one file. If the edit
requires touching both `*_gateway.py` and `*_service.py`, switch to Mode B.

### D2 — Edit Rules

- Read the full target file before making any change.
- Preserve all existing `@staticmethod` / `@classmethod` decorators.
- Do not introduce imports from sibling subsystems.
- Do not add `bpy.ops` calls.
- If modifying a gateway function signature, update the calling service
  method in the same edit to keep them in sync.

### D3 — Post-Edit Micro-Checklist

- [ ] No new cross-sibling imports
- [ ] FFI boundary unchanged or still `array.array` compliant
- [ ] Docstring updated if method behaviour changed
- [ ] `__init__.py` reload loop still covers all files in the subsystem
