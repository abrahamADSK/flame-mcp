"""
_plan_schema.py
===============
F5b — Ruta A: structured plan output schema (AJUSTE 1 of chat 51 v2 plan).

The deepest reliability win of the chat 51 roadmap: the LLM no longer
writes raw Python that we forward to Flame. Instead it returns a
**structured plan** — a closed JSON document of named ops with typed
arguments — that the server validates against a registry and dispatches
to existing handlers.

Why this matters
----------------
As long as the LLM emits Python, it can hallucinate symbols
(`flame.selection`, typo'd methods, wrong arg shapes). F3a refuses to
*route* such symbols and F4b refuses to *execute* them, but the LLM
still has to construct valid Python from a grammar it does not fully
control. With Ruta A the LLM never produces Python — it picks an op
from a closed enum and fills typed slots. The class of "wrong
Python" disappears at the protocol level.

Co-existence with execute_python
--------------------------------
`execute_python` is NOT deprecated by this PR. It remains the escape
hatch for operations that are not yet covered by the plan registry.
The intended migration path is:

    1. Land Ruta A with a small set of ops (this PR).
    2. Observe via F0 telemetry which `execute_python` calls land
       repeatedly — those are candidates for new plan ops.
    3. Migrate each one, deprecating it from `execute_python` only
       once the corresponding plan op is stable.
    4. `execute_python` may eventually become read-only or be removed
       — that decision is downstream of this PR.

Schema shape (v1)
-----------------
Top-level::

    {
        "ops": [
            {"op": "<op_name>", "args": {<typed args>}},
            ...
        ]
    }

Validation rules:
- `ops` must be a non-empty list. The plan is dispatched op-by-op
  in order; a failure short-circuits the remainder (no partial-state
  ambiguity).
- Each entry has exactly the keys ``op`` (str) and ``args`` (dict);
  any extra keys → schema rejection.
- `op` must be a known op name (see :data:`OP_REGISTRY`).
- `args` must match the op's pydantic model; missing required args,
  unknown args, or wrong types → schema rejection.

Op registry
-----------
Each entry in :data:`OP_REGISTRY` carries:

- ``args_model``: pydantic ``BaseModel`` subclass with
  ``extra="forbid"`` and ``str_strip_whitespace=True``.
- ``handler``: callable ``(args: BaseModel) -> str`` that performs
  the op and returns its result text. Handlers reuse existing
  dedicated-tool implementations where possible — Ruta A is a
  protocol change, not a behaviour change.
- ``description``: short human-readable summary surfaced in error
  messages and the tool's docstring.

To register a new op, add an entry to :data:`OP_REGISTRY` and a
matching pydantic args class. The ``every_op_is_in_graph`` invariant
verifies each op resolves to an `api_graph.json` entry OR an existing
dedicated MCP tool name.
"""

from __future__ import annotations

from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Common strict config — forbid extras, strip whitespace, mirror the
# rest of the codebase (cf. server.py and concept_map.py patterns).
_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# Per-op argument models
# ---------------------------------------------------------------------------


class ListLibrariesArgs(BaseModel):
    """No arguments — list every visible library in the active project."""

    model_config = _STRICT


class ListReelsArgs(BaseModel):
    """Filter the reels listing to a single library (optional)."""

    model_config = _STRICT
    library_name: str = Field(
        default="",
        description="Library to list reels for. Empty = all visible libraries.",
    )


class ListClipsArgs(BaseModel):
    """List clips in a specific library + reel combination."""

    model_config = _STRICT
    library_name: str = Field(..., description="Library name (required).")
    reel_name: str = Field(..., description="Reel name (required).")


class GetProjectInfoArgs(BaseModel):
    """No arguments — return the active project's metadata."""

    model_config = _STRICT


class GetClipMetadataArgs(BaseModel):
    """Metadata for a single clip identified by its library/reel/name."""

    model_config = _STRICT
    library_name: str = Field(..., description="Library name (required).")
    reel_name: str = Field(..., description="Reel name (required).")
    clip_name: str = Field(..., description="Clip name (required).")


class PingArgs(BaseModel):
    """No arguments — heartbeat to the Flame bridge."""

    model_config = _STRICT


class ExportClipArgs(BaseModel):
    """Export a single clip to disk via a Flame export preset (PyExporter).

    DESTRUCTIVE op: schedules an export inside Flame. Mirrors the export_clip
    dedicated tool 1:1.
    """

    model_config = _STRICT
    library_name: str = Field(..., description="Library holding the clip.")
    reel_name: str = Field(..., description="Reel within the library.")
    clip_name: str = Field(..., description="Clip to export.")
    preset_path: str = Field(
        ..., description="Absolute path to a Flame export preset (.xml)."
    )
    output_directory: str = Field(
        ..., description="Destination folder (created if missing)."
    )


class RenderBatchArgs(BaseModel):
    """Render the current Batch Group's active Render/Write File nodes.

    DESTRUCTIVE op: schedules a render inside Flame (default Background
    Reactor). Mirrors the render_batch dedicated tool 1:1.
    """

    model_config = _STRICT
    render_option: Literal["Background Reactor", "Foreground", "Burn"] = Field(
        default="Background Reactor",
        description=(
            "Rendering method. 'Background Reactor' (off-thread, recommended), "
            "'Foreground' (blocks Flame's UI), or 'Burn'."
        ),
    )
    generate_proxies: bool = Field(
        default=False, description="Render at proxy resolution."
    )
    include_history: bool = Field(
        default=False, description="Create History with the rendering."
    )


class CreateLibraryArgs(BaseModel):
    """Create a new library in the active workspace."""

    model_config = _STRICT
    library_name: str = Field(..., description="Name for the new library.")


class CreateReelArgs(BaseModel):
    """Create a new reel inside a library."""

    model_config = _STRICT
    library_name: str = Field(..., description="Target library.")
    reel_name: str = Field(..., description="Name for the new reel.")


class CreateFolderArgs(BaseModel):
    """Create a new folder inside a library."""

    model_config = _STRICT
    library_name: str = Field(..., description="Target library.")
    folder_name: str = Field(..., description="Name for the new folder.")


class CreateReelGroupArgs(BaseModel):
    """Create a new reel group inside a library."""

    model_config = _STRICT
    library_name: str = Field(..., description="Target library.")
    reel_group_name: str = Field(..., description="Name for the new reel group.")


class CreateBatchGroupArgs(BaseModel):
    """Create a new empty Batch Group on the desktop."""

    model_config = _STRICT
    name: str = Field(..., description="Name for the new batch group.")


class ImportClipsArgs(BaseModel):
    """Import media from disk into a library (optionally a reel)."""

    model_config = _STRICT
    path: str = Field(..., description="Absolute filesystem path to the media.")
    library_name: str = Field(..., description="Destination library.")
    reel_name: str = Field(
        default="", description="Optional destination reel within the library."
    )


class SetupCompBatchArgs(BaseModel):
    """Create a shot's comp batch group wired source → Write File.

    Chat 98: one deterministic op per shot — batch group ``<shot>_comp``
    with a ``sources`` reel, the shot's open clip imported as the source
    Clip node, and a Write File node connected to it whose open-clip
    target is the SOURCE's ``.clip`` (the operator's decision: comp
    versions land in the conformed clip, so the timeline flips natively).
    Write File attributes are set defensively and reported — the node's
    attribute surface is dynamic, so unknown names degrade to a report
    line, never an error.
    """

    model_config = _STRICT
    shot: str = Field(..., description="Shot code, e.g. 'SEQ001_SH001'.")
    clip_path: str = Field(
        ..., description="Absolute path to the shot's source open clip "
        "(.clip). Also used as the Write File's open-clip target."
    )
    comp_dir: str = Field(
        default="",
        description="Directory for the Write File's rendered media. Empty = "
        "derived from clip_path: the 'comp' sibling of its 'clip' folder "
        "(…/finishing/comp).",
    )


class _TimelineEditArgs(BaseModel):
    """Shared args for timeline_insert / timeline_overwrite."""

    model_config = _STRICT
    sequence_library: str = Field(..., description="Library holding the target sequence.")
    sequence_reel: str = Field(..., description="Reel holding the target sequence.")
    sequence_name: str = Field(..., description="Target sequence name.")
    source_library: str = Field(..., description="Library holding the source clip.")
    source_reel: str = Field(..., description="Reel holding the source clip.")
    source_clip: str = Field(..., description="Source clip name.")
    record_frame: int | None = Field(
        None,
        description="Optional explicit sequence frame for the edit point "
        "(flame.PyTime). Omit for Flame's default position.",
    )


class TimelineInsertArgs(_TimelineEditArgs):
    """Insert a source clip into a sequence's timeline (ripple)."""


class TimelineOverwriteArgs(_TimelineEditArgs):
    """Overwrite part of a sequence's timeline with a source clip."""


# ---------------------------------------------------------------------------
# Op registry — single source of truth for "what does the LLM see?"
# ---------------------------------------------------------------------------
#
# The handler signatures are deferred via Callable[[BaseModel], str] so the
# server can wire them at import time without circular-importing server.py
# back into this module.  See `register_op()` below.

_OP_REGISTRY: dict[str, dict[str, Any]] = {
    "list_libraries": {
        "args_model": ListLibrariesArgs,
        "handler": None,  # wired by server.py at import
        "description": "List visible libraries (excludes Timeline FX, Grabbed References).",
        "tool": "list_libraries",
    },
    "list_reels": {
        "args_model": ListReelsArgs,
        "handler": None,
        "description": "List reels in a library (or across all libraries).",
        "tool": "list_reels",
    },
    "list_clips": {
        "args_model": ListClipsArgs,
        "handler": None,
        "description": "List clips inside a specific library + reel.",
        "tool": "list_clips",
    },
    "get_project_info": {
        "args_model": GetProjectInfoArgs,
        "handler": None,
        "description": "Active project metadata (name, fps, resolution, bit depth).",
        "tool": "get_project_info",
    },
    "get_clip_metadata": {
        "args_model": GetClipMetadataArgs,
        "handler": None,
        "description": "Technical metadata of a single clip.",
        "tool": "get_clip_metadata",
    },
    "ping": {
        "args_model": PingArgs,
        "handler": None,
        "description": "Bridge heartbeat — confirms Flame is reachable.",
        "tool": "ping",
    },
    "render_batch": {
        "args_model": RenderBatchArgs,
        "handler": None,
        "description": (
            "DESTRUCTIVE — schedule a render of the current Batch Group "
            "(Background Reactor by default; scheduled via idle event)."
        ),
        "tool": "render_batch",
    },
    "export_clip": {
        "args_model": ExportClipArgs,
        "handler": None,
        "description": (
            "DESTRUCTIVE — export a clip to disk via a Flame preset "
            "(PyExporter; scheduled via idle event)."
        ),
        "tool": "export_clip",
    },
    "create_library": {
        "args_model": CreateLibraryArgs,
        "handler": None,
        "description": "Create a new library in the active workspace.",
        "tool": "create_library",
    },
    "create_reel": {
        "args_model": CreateReelArgs,
        "handler": None,
        "description": "Create a new reel inside a library.",
        "tool": "create_reel",
    },
    "create_folder": {
        "args_model": CreateFolderArgs,
        "handler": None,
        "description": "Create a new folder inside a library.",
        "tool": "create_folder",
    },
    "create_reel_group": {
        "args_model": CreateReelGroupArgs,
        "handler": None,
        "description": "Create a new reel group inside a library.",
        "tool": "create_reel_group",
    },
    "create_batch_group": {
        "args_model": CreateBatchGroupArgs,
        "handler": None,
        "description": "Create a new empty Batch Group on the desktop.",
        "tool": "create_batch_group",
    },
    "import_clips": {
        "args_model": ImportClipsArgs,
        "handler": None,
        "description": "Import media from disk into a library/reel.",
        "tool": "import_clips",
    },
    "setup_comp_batch": {
        "args_model": SetupCompBatchArgs,
        "handler": None,
        "description": "DESTRUCTIVE — create a shot's comp batch group wired "
        "source Clip → Write File (open-clip target = the source .clip).",
        "tool": "execute_plan",
    },
    "timeline_insert": {
        "args_model": TimelineInsertArgs,
        "handler": None,
        "description": "DESTRUCTIVE — ripple-insert a clip into a sequence's timeline.",
        "tool": "timeline_insert",
    },
    "timeline_overwrite": {
        "args_model": TimelineOverwriteArgs,
        "handler": None,
        "description": "DESTRUCTIVE — overwrite part of a sequence's timeline with a clip.",
        "tool": "timeline_overwrite",
    },
}


def register_op(name: str, handler: Callable[[Any], str]) -> None:
    """Wire a handler for an op declared in :data:`_OP_REGISTRY`.

    The handler's parameter is typed as ``Any`` rather than
    ``BaseModel`` so each handler can declare a concrete pydantic
    args type without fighting mypy's contravariant Callable rules.
    The dispatch path guarantees the handler always receives an
    instance of its declared ``args_model``.

    Called from server.py at import time once the dedicated-tool
    functions exist. Raises if ``name`` is not a registered op so
    typos surface loudly.
    """
    if name not in _OP_REGISTRY:
        raise ValueError(
            f"register_op: unknown op name {name!r}. "
            f"Known ops: {sorted(_OP_REGISTRY)}"
        )
    _OP_REGISTRY[name]["handler"] = handler


def op_names() -> list[str]:
    """Return the sorted list of registered op names. Used by tests + docs."""
    return sorted(_OP_REGISTRY.keys())


def op_tool(name: str) -> Optional[str]:
    """Return the dedicated MCP tool an op maps to, or None if not yet wired."""
    entry = _OP_REGISTRY.get(name)
    return entry["tool"] if entry else None


# ---------------------------------------------------------------------------
# Plan-level validation + dispatch
# ---------------------------------------------------------------------------


class PlanValidationError(Exception):
    """Raised when a plan document does not conform to the v1 schema.

    The message is the LLM-facing rejection text; callers can surface
    it verbatim or wrap with additional context.
    """


def _validate_one_op(op_entry: Any, index: int) -> tuple[str, BaseModel]:
    """Validate a single ops[i] entry. Returns (op_name, args_instance).

    Raises :class:`PlanValidationError` with a structured message.
    """
    if not isinstance(op_entry, dict):
        raise PlanValidationError(
            f"ops[{index}]: expected an object, got {type(op_entry).__name__}."
        )
    extra_keys = set(op_entry.keys()) - {"op", "args"}
    if extra_keys:
        raise PlanValidationError(
            f"ops[{index}]: unexpected keys {sorted(extra_keys)}. "
            f"Each op must have exactly 'op' and 'args'."
        )
    if "op" not in op_entry:
        raise PlanValidationError(f"ops[{index}]: missing required key 'op'.")
    if "args" not in op_entry:
        raise PlanValidationError(f"ops[{index}]: missing required key 'args'.")

    op_name = op_entry["op"]
    if not isinstance(op_name, str):
        raise PlanValidationError(
            f"ops[{index}].op: expected str, got {type(op_name).__name__}."
        )
    if op_name not in _OP_REGISTRY:
        raise PlanValidationError(
            f"ops[{index}].op = {op_name!r} is not a registered op. "
            f"Known ops: {op_names()}."
        )

    args_raw = op_entry["args"]
    if not isinstance(args_raw, dict):
        raise PlanValidationError(
            f"ops[{index}].args: expected an object, "
            f"got {type(args_raw).__name__}."
        )

    args_model_cls = _OP_REGISTRY[op_name]["args_model"]
    try:
        args_instance = args_model_cls(**args_raw)
    except ValidationError as exc:
        raise PlanValidationError(
            f"ops[{index}].args ({op_name!r}): {exc.errors(include_url=False)}"
        ) from exc

    return op_name, args_instance


def validate_plan(plan: Any) -> list[tuple[str, BaseModel]]:
    """Validate a top-level plan document and return parsed (op, args) pairs.

    Args:
        plan: The parsed JSON document the LLM submitted.

    Returns:
        List of ``(op_name, args_instance)`` pairs in the order
        declared by the LLM. Callers iterate and dispatch.

    Raises:
        PlanValidationError: on any schema deviation.
    """
    if not isinstance(plan, dict):
        raise PlanValidationError(
            f"plan: expected an object, got {type(plan).__name__}."
        )
    extra_keys = set(plan.keys()) - {"ops"}
    if extra_keys:
        raise PlanValidationError(
            f"plan: unexpected top-level keys {sorted(extra_keys)}. "
            f"Schema v1 only allows 'ops'."
        )
    if "ops" not in plan:
        raise PlanValidationError("plan: missing required key 'ops'.")
    ops = plan["ops"]
    if not isinstance(ops, list):
        raise PlanValidationError(
            f"plan.ops: expected list, got {type(ops).__name__}."
        )
    if not ops:
        raise PlanValidationError(
            "plan.ops: list is empty. A valid plan has at least one op."
        )

    return [_validate_one_op(entry, i) for i, entry in enumerate(ops)]


def dispatch_plan(plan: Any) -> str:
    """Validate, then dispatch every op in order. Returns a joined text.

    Per-op output is fenced with a header so the LLM (or a human
    reading the response) can match an op to its result. If any op
    handler raises, the dispatch short-circuits — preceding ops have
    ALREADY executed (their side effects persist), so the error
    message states the exact index where the run stopped.

    Args:
        plan: Already-parsed JSON document.

    Returns:
        Multi-line string with per-op headers + outputs + a final
        summary line.

    Raises:
        PlanValidationError: when the plan or any op fails schema
            validation. Execution does NOT start in that case.
        RuntimeError: when an op's handler is not wired (server.py
            should call :func:`register_op` for every entry at import).
    """
    parsed = validate_plan(plan)

    parts: list[str] = []
    completed = 0
    for index, (op_name, args_instance) in enumerate(parsed):
        entry = _OP_REGISTRY[op_name]
        handler = entry["handler"]
        if handler is None:
            raise RuntimeError(
                f"plan op {op_name!r} has no handler wired. "
                f"server.py must call register_op('{op_name}', ...)."
            )
        header = f"── op {index} · {op_name} ──"
        try:
            result = handler(args_instance)
        except Exception as exc:  # noqa: BLE001 — handler may raise anything
            parts.append(header)
            parts.append(f"❌ FAILED: {exc!r}")
            parts.append(
                f"\nPlan short-circuited at op {index} of {len(parsed)}. "
                f"{completed} op(s) completed before this failure; their "
                f"side effects (if any) persist."
            )
            return "\n".join(parts)
        parts.append(header)
        parts.append(str(result))
        completed += 1

    parts.append(
        f"\n✅ Plan executed: {completed}/{len(parsed)} ops succeeded."
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Tooling helpers (used by tests + by the CLAUDE.md generator)
# ---------------------------------------------------------------------------


def describe_registry() -> dict[str, dict[str, Any]]:
    """Return a serialisable description of the registry for docs / tests.

    Does NOT expose the handler callable — only metadata. Useful for
    generating the structured-plan section of CLAUDE.md from a single
    source of truth, and for the concept-registry invariant that pins
    each op to a known dedicated tool.
    """
    return {
        name: {
            "description": entry["description"],
            "tool": entry["tool"],
            "args_schema": entry["args_model"].model_json_schema(),
        }
        for name, entry in _OP_REGISTRY.items()
    }
