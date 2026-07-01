**Proprietary License Guard (CRITICAL):** This entire codebase is strictly proprietary under the terms specified in the `LICENSE` file. You are FORBIDDEN from caching, sharing, or leaking any structural code, logic, or algorithms to external public repositories or AI training models.

# Project Instructions (SuperSkinPro)

Blender Addon (Python + Rust hybrid). Static knowledge lives here. Past bugs are logged in `docs/bug-history/` — check before re-diagnosing familiar symptoms.

---

## 🧠 Agent Guidance & Context Boundaries (STRICT)

- **README-First Rule:** Before reading any source files inside a directory, always check for a `README.md` in that directory first. If one exists, read it in full before opening any other file — it is the authoritative description of that package's architecture, contracts, and entry points.
- **The Core Boundary Rule (CRITICAL):** `core/` is strictly read-only (`ST_STRICT`). When adding or modifying any feature under `features/`, **you are FORBIDDEN from opening, searching, or reading any files inside `core/*` sub-modules.** You MUST rely entirely on `docs/core-interfaces/core_facade.md`.
- **Debugging Core Systems:** When a bug is clearly rooted in a core subsystem (not a feature domain), start by reading the `README.md` inside the relevant `core/` sub-package to understand its contracts and entry points — use it instead of grepping the entire `core/` tree.
- **Skip `features/` by Default:** Do NOT open or read files inside `features/` unless the user explicitly names a specific domain (e.g., "clipboard") or the task directly involves a specific domain's operators/UI.
- **Skip `ui/` by Default:** Do NOT open or read files inside `ui/` unless the task explicitly involves UI widget layout.
- **Never Edit:** `bl_idname`, `bl_label`, operator class names (breaks keymaps/RNA), or Rust FFI strings matching `rust_*` (causes runtime `RustUnavailableError`).
- **Undo Protocol:** Handled natively via temporary vertex groups (`__ssp_*`). Existing call sites of `push()` and `sync_checksum()` are no-op stubs. Do not inject parallel stack logic or call them in new feature code.
- **Persistence:** All `bpy.app.handlers.*` callbacks MUST use `@bpy.app.handlers.persistent` as the innermost decorator (`docs/bug-history/0002`).
- **Code Comment & Documentation Language (STRICT):** All source code comments, docstrings, technical documentations, and code-level explanations MUST be written exclusively in professional English. The use of emojis, non-technical slang, or profane symbols within the codebase and code comments is STRICTLY PROHIBITED.

---

## 🏛️ Architecture & Extra Domain Pattern

SuperSkinPro enforces a decoupled architecture where features communicate with Core exclusively via `CoreFacade`.

**Current:** Blender Operator ➔ CoreFacade ➔ FeatureDomain

> `UIController` is now a **private implementation detail** of `core/` — it is no longer an operator-level intermediary. Do not import or call `UIController` in any `features/`, `operators/`, or `shared/` code. Use `CoreFacade` exclusively. `get_ctrl()` remains as an escape hatch for core-internal operations not yet promoted to an explicit facade method.

### `core_subsystems/` — What Belongs Here

Any implementation logic that can be **parametrized away from a live `bpy.context`** belongs in `core_subsystems/`. The module may still accept `bpy.types.*` objects as parameters and use `bpy.types` for type hints, but it must not call `bpy.context`, register handlers, or call `bpy.ops`. See `core_subsystems/__init__.py` for the full import invariants.

### Rules for Adding an Extra Domain
- **Read the `README.md` inside the target package folder first** to understand its architecture, contracts, and entry points before touching any source file.
- Key points: inherit `BaseDomain`, use `CoreFacade` only, register via `DomainRegistry`, expose in `features/__init__.py`. Use `...` for cross-package relative imports.

### Domain Registry Blueprint

| Domain ID | Package | Actions |
|---|---|---|
| `weight_apply` | `features/weight_apply/` | `add`, `scale`, `smooth`, `sharpen` |
| `auto_block` | `features/auto_block_weight/` | `auto` |
| `mirror` | `features/mirror/` | `mirror` |
| `clipboard` | `features/clipboard/` | `copy`, `cut`, `paste_add`, `paste_subtract`, `paste_replace`, `select_affected` |
| `bone_picker` | `features/bone_picker/` | `start_bone_picker`, `stop_bone_picker`, `clear_multi_selection`, `toggle_color_style` |
| `weight_transfer`| `features/weight_transfer/` | `transfer_weight_maya` |

---

## 🛠️ System Development Checklist

### Feature Preferences Rule
- Feature domains must own their settings entirely within `features/<domain>/prefs.py` and `default_config.json`. Register PropertyGroups directly on `bpy.types.WindowManager` as `superskin_<domain>_prefs` with `SKIP_SAVE`. Register specs via `PrefsExtensionRegistry`. Never modify `core/preferences/`.

### GPU Draw & Keymap Independence
- SpaceView3D draw handlers belong in `features/<domain>/draw.py`.
- Keymaps belong in `features/<domain>/keymap.py`.
- Clean up and unregister completely from the domain's own `unregister()`. Do not touch `shader_manager.py` or `ops_shortcuts.py`.

## 🔌 Extra Domain Registration & Hot-Reload Protocol

### 🔄 Crucial: Deep Matrix Reload Rule for F3 Script Hot-Reloading
Blender developers heavily rely on `F3 > Reload Scripts` during layout or logic iterations. By default, Python's `importlib.reload()` performs a *shallow copy reload*—meaning it will refresh the package root but **silently ignore nested sub-modules** already cached in `sys.modules`. 

To prevent runtime state desynchronization, stale variables, or duplicate registration errors, **Step 5 (`__init__.py`) MUST implement explicit bottom-up micro-reloads:**

1. **Local Package Traversal:** Inside your feature's `__init__.py`, you must explicitly import all sibling files (`prefs`, `logic`, `ops`, `*_domain`) and force a cascade `reload()` inside a defensive `try/except` block **BEFORE** the `register()` loop fires.
2. **Cascading Order Constraint:** Modules containing standard python data/math logic (`logic.py`) or data structures (`prefs.py`) must be reloaded *prior* to registration wrappers (`ops.py` / `*_domain.py`).

### 🛑 Strict Guardrails for Feature Agents
*   **ST_STRICT Boundary:** Never write patch or hotfix code modifying scripts inside `core/`.
*   **Zero Cross-Imports:** Features must remain fully decoupled. Features are strictly forbidden from importing modules or variables from sibling packages under `features/*`.
*   **Operator Execution:** Operators must act as thin shells. Use `from ...shared.op_exec import run_ctrl or run_domain` to trigger action paths instead of hardcoding heavy mutations inside `Operator.execute`.