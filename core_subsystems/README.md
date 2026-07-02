# core_subsystems — Backend Pillar Layer

## Role in the 3-Layer Architecture

```
[ Layer 3: features/ ]       — Pluggable extras; use CoreFacade exclusively
         |
         v (CoreFacade boundary)
[ Layer 1: core/ ]  <->  [ Layer 2: core_subsystems/ ]  — Always-present backend
```

`core_subsystems/` provides stateless backend services. Code here may accept
`bpy.types.*` objects as parameters but must never call `bpy.context`, register
handlers, or invoke `bpy.ops`.

---

## Encapsulation Model

Every subsystem is an **encapsulated package**: a directory whose `__init__.py`
exports exactly **one public class**. Internal modules are private implementation
details — never import them from outside the package.

```python
# Correct
from core_subsystems.rust_weight_engine import RustWeightEngine

# Forbidden — reaches into a private submodule
from core_subsystems.rust_weight_engine.data_bridge import map_layer_to_int
```

The public class owns all functionality for that subsystem via static or class
methods. Adding a new capability means adding a method to the class — never
exposing a new submodule.

---

## Registered Subsystems

| Package | Public Class | Responsibility |
|---------|-------------|----------------|
| `rust_weight_engine/` | `RustWeightEngine` | Rust binary loader, FFI dispatch, data-bridge conversions, flat CSR array bridge |
| `layer_compositor/` | `LayerCompositor` | Layer metadata CRUD, compositing, topology healing, merge, flatten pipeline helpers |
| `topology_cache_manager/` | `TopologyCacheManager` | VG-index mapping cache, mesh-neighbor topology, bone proximity ordering |
| `context_selection_service/` | `ContextSelectionService` | Viewport selection, mask-context detection, undo-restore flag, weight normalisation |
| `license_gateway/` | `LicenseGateway` | Gumroad license verification, Pro-tier feature gating |
| `preferences/` | `PreferencesService` | *(legacy package, retained pending a separate migration pass)* Preference I/O and core `bpy.types.PropertyGroup` definitions |

---

## Package Layout Convention

```
<subsystem>/
├── __init__.py      — exports ONE public class; handles cascading reloads
├── <subsystem>.py   — public class (the portal)
└── <private>.py     — internal helpers; never imported externally
```

`__init__.py` must reload its private modules in bottom-up dependency order
to support Blender's *Reload Scripts* without stale references.

---

## Import Invariants

| # | Rule |
|---|------|
| 1 | `core/` may import from `core_subsystems/` directly. |
| 2 | Intra-subsystem imports must follow strict one-way chains — no circular imports. |
| 3 | `features/` must NOT import from `core_subsystems/` directly; use `CoreFacade`. |
| 4 | External callers import the package's public class only — never a private submodule. |
