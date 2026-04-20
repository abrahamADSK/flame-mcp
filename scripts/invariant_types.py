"""Invariant types for cross-cutting concept verification (.concepts.yml).

Each invariant function takes a dict of parameters (from YAML) and returns:
    (passed: bool, message: str)

The runner (verify_concepts.py) dispatches on the `type` field declared in YAML.

Types provided here:
    - tool_count       : count of a code pattern matches a literal in a doc block
    - subset           : one set is a subset of another (or bidirectional)
    - file_exists      : a referenced file exists on disk
    - version_match    : two version strings agree
    - claim_verifies   : a documentation claim is backed by code (grep-based)
    - review_expiry    : a manual-review timestamp has not gone stale
    - glob_count       : number of files matching N glob patterns equals expected
    - commits_since_tag: commits past latest tag within cadence thresholds

Item sources (used inside `subset`):
    ast_list, ast_decorator_functions (with optional name_kwarg),
    ast_tuple_list_column, yaml_values, json_array_field, anchor_list,
    ast_decorator_args, ast_decorator_kwarg (back-compat alias of
    ast_decorator_functions+name_kwarg), ast_enum_values, ast_dict_keys,
    literal_set, file_regex_matches, command_lines.

No --fix mode. Verification only. Humans resolve drift.
"""

from __future__ import annotations

import ast
import re
import subprocess
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _read(path: str | Path) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p.read_text(encoding="utf-8")


def _extract_concept_block(text: str, concept_id: str) -> str | None:
    """Find content between concept start/end markers.

    Supports two comment styles (flexibility across file types):
        Markdown / HTML : <!-- concept:<id> start --> ... <!-- concept:<id> end -->
        Shell / Python  : # concept:<id> start             ... # concept:<id> end

    The first matching style wins.
    """
    patterns = [
        rf"<!--\s*concept:{re.escape(concept_id)}\s+start\s*-->"
        r"(.*?)"
        rf"<!--\s*concept:{re.escape(concept_id)}\s+end\s*-->",
        rf"#\s*concept:{re.escape(concept_id)}\s+start\s*\n"
        r"(.*?)"
        rf"#\s*concept:{re.escape(concept_id)}\s+end",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
    return None


def _decorator_name(node) -> str:
    """Turn an AST decorator node into 'x.y' dotted form."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _decorator_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _flatten_ast_strings(node) -> set[str]:
    """Collect every string literal inside an AST subtree."""
    items: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            items.add(sub.value)
    return items


# --------------------------------------------------------------------------- #
# Invariant types
# --------------------------------------------------------------------------- #

def tool_count(params: dict) -> tuple[bool, str]:
    """Assert the number of `@decorator` matches in a .py file equals the
    number written inside a markdown anchor block.

    params:
        code_file   : path to .py
        decorator   : decorator fully-qualified name, e.g. 'mcp.tool'
        doc_file    : path to .md
        concept_id  : anchor id used in <!-- concept:<id> start/end -->
    """
    code_file = params["code_file"]
    doc_file = params["doc_file"]
    concept_id = params["concept_id"]
    decorator = params.get("decorator", "mcp.tool")

    tree = ast.parse(_read(code_file))
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                if _decorator_name(deco) == decorator:
                    count += 1
                    break

    block = _extract_concept_block(_read(doc_file), concept_id)
    if block is None:
        return False, f"no anchor block 'concept:{concept_id}' in {doc_file}"

    match = re.search(r"\b(\d+)\b", block)
    if not match:
        return False, f"no number found inside concept:{concept_id} block"

    doc_count = int(match.group(1))
    if doc_count == count:
        return True, f"tool_count={count} (agrees with {doc_file})"
    return False, f"tool_count mismatch: code={count}, {doc_file}={doc_count}"


def subset(params: dict) -> tuple[bool, str]:
    """Assert items from source A ⊆ items from source B (or bidirectional).

    params:
        a_source   : {type: 'ast_list'|'anchor_list', file, symbol|concept_id}
        b_source   : same shape as a_source
        direction  : 'a_subset_b' | 'b_subset_a' | 'bidirectional'
                     default: 'a_subset_b'
    """
    a = _extract_items(params["a_source"])
    b = _extract_items(params["b_source"])
    direction = params.get("direction", "a_subset_b")

    messages = []
    passed = True

    if direction in ("a_subset_b", "bidirectional"):
        missing = a - b
        if missing:
            passed = False
            messages.append(f"in A but not B: {sorted(missing)}")
    if direction in ("b_subset_a", "bidirectional"):
        missing = b - a
        if missing:
            passed = False
            messages.append(f"in B but not A: {sorted(missing)}")

    if passed:
        return True, f"subset OK (|A|={len(a)}, |B|={len(b)}, direction={direction})"
    return False, "; ".join(messages)


def _extract_items(source: dict) -> set[str]:
    """Extract a set of string items from a declared source.

    Supported `type` values:
        ast_list                  : every string literal inside an AST
                                    list/tuple assigned to `symbol`.
        ast_decorator_functions   : names of functions decorated with the
                                    given `decorator` (e.g. 'mcp.tool').
                                    If `name_kwarg` is set (e.g. "name"),
                                    the decorator call's kwarg value is
                                    used as the canonical name whenever
                                    present; otherwise the Python function
                                    name is used as fallback. This covers
                                    both the fpt-mcp pattern
                                    (@mcp.tool(name="sg_find") on
                                    async def sg_find_tool) and plain
                                    @mcp.tool decorators in the same
                                    source file.
        ast_decorator_kwarg       : DEPRECATED alias of
                                    ast_decorator_functions + name_kwarg.
                                    Kept for backwards compatibility with
                                    existing .concepts.yml files that use
                                    the explicit `kwarg:` key. New
                                    registries should prefer
                                    ast_decorator_functions.
        ast_decorator_args        : positional arg at `arg_index` (default 0)
                                    of every call-form decorator whose name
                                    is in `decorators` (or equals
                                    `decorator`). Useful for FastAPI/Flask
                                    route inventories.
        ast_tuple_list_column     : for a top-level `SYMBOL = [(...), ...]`
                                    return the string literal at `column`
                                    of each inner element, optionally
                                    filtered by `filter_column`/
                                    `filter_value`.
        ast_enum_values           : for `class SYMBOL(..., Enum)` return the
                                    set of RHS string literal values of
                                    every member assignment.
        ast_dict_keys             : for a top-level `SYMBOL = {...}` return
                                    the set of string keys.
        yaml_values               : values at dotted `key` inside a YAML
                                    file (repo-relative, ecosystem-relative,
                                    or absolute). Dict → values, list →
                                    elements, scalar → singleton.
        json_array_field          : for a JSON file whose root is an array
                                    of objects, collect `field` (dot-path)
                                    from every element.
        anchor_list               : items inside a markdown
                                    <!-- concept:<id> start/end --> block.
                                    By default extracts bullet-list items;
                                    pass `item_pattern` (regex with one
                                    group) to extract matches instead
                                    (e.g. every backtick-wrapped
                                    identifier in a table).
        literal_set               : hardcoded expected set from YAML.
        file_regex_matches        : re.findall across the whole file (with
                                    MULTILINE). Returns first-group
                                    captures.
        command_lines             : run a shell command, return each
                                    non-empty output line as an element.
    """
    kind = source["type"]
    if kind == "ast_list":
        tree = ast.parse(_read(source["file"]))
        target = source["symbol"]
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == target:
                        return _flatten_ast_strings(node.value)
        raise ValueError(f"symbol {target} not found in {source['file']}")
    if kind == "ast_decorator_functions":
        # Return the canonical identifier for each function decorated with
        # the given decorator. By default this is the Python function name;
        # if `name_kwarg` is set (e.g. "name"), the decorator call's kwarg
        # value is used instead when present. fpt-mcp uses
        # @mcp.tool(name="sg_find") on async def sg_find_tool(...) — the
        # public name is "sg_find". Missing kwarg falls back to the
        # function's Python name.
        tree = ast.parse(_read(source["file"]))
        decorator = source["decorator"]
        name_kwarg = source.get("name_kwarg")
        items: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for deco in node.decorator_list:
                    deco_name = _decorator_name(deco)
                    if deco_name != decorator:
                        continue
                    canonical = node.name
                    if name_kwarg and isinstance(deco, ast.Call):
                        for kw in deco.keywords:
                            if kw.arg == name_kwarg and isinstance(kw.value, ast.Constant) \
                                    and isinstance(kw.value.value, str):
                                canonical = kw.value.value
                                break
                    items.add(canonical)
                    break
        return items
    if kind == "ast_decorator_kwarg":
        # DEPRECATED: kept for backwards compatibility with existing
        # .concepts.yml files (notably maya-mcp's) that pass
        #     type: ast_decorator_kwarg
        #     decorator: mcp.tool
        #     kwarg: name
        # Semantically equivalent to `ast_decorator_functions` with
        # `name_kwarg=<kwarg>`. Accepts either `decorator` (single) or
        # `decorators` (list of aliases). The first matching decorator on
        # each function contributes; if the kwarg is missing, the function
        # name is used as fallback. New registries should use
        # `ast_decorator_functions` with `name_kwarg`.
        tree = ast.parse(_read(source["file"]))
        decorators = source.get("decorators") or [source["decorator"]]
        kwarg = source["kwarg"]
        items: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for deco in node.decorator_list:
                    found_name: str | None = None
                    if isinstance(deco, ast.Call):
                        deco_name = _decorator_name(deco.func)
                        if deco_name in decorators:
                            for kw in deco.keywords:
                                if kw.arg == kwarg and isinstance(kw.value, ast.Constant) \
                                        and isinstance(kw.value.value, str):
                                    found_name = kw.value.value
                                    break
                            if found_name is None:
                                # Decorator matched but no kwarg — fall back
                                # to the function's own Python name.
                                found_name = node.name
                    elif _decorator_name(deco) in decorators:
                        # Bare decorator (no arguments): use the function name.
                        found_name = node.name
                    if found_name is not None:
                        items.add(found_name)
                        break
        return items
    if kind == "ast_tuple_list_column":
        # For a top-level assignment `SYMBOL = [(...), (...), ...]`, return
        # the string literals at `column` of each tuple/list element.
        # Optional: `filter_column` + `filter_value` restrict to rows whose
        # `filter_column`-th cell equals `filter_value` (e.g. backend="anthropic").
        tree = ast.parse(_read(source["file"]))
        target = source["symbol"]
        column = int(source.get("column", 1))
        filter_column = source.get("filter_column")
        filter_value = source.get("filter_value")
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == target:
                        value = node.value
                        if not isinstance(value, (ast.List, ast.Tuple)):
                            return set()
                        items: set[str] = set()
                        for element in value.elts:
                            if not isinstance(element, (ast.Tuple, ast.List)) or len(element.elts) <= column:
                                continue
                            if filter_column is not None and filter_value is not None:
                                if len(element.elts) <= int(filter_column):
                                    continue
                                fcell = element.elts[int(filter_column)]
                                if not (isinstance(fcell, ast.Constant) and fcell.value == filter_value):
                                    continue
                            cell = element.elts[column]
                            if isinstance(cell, ast.Constant) and isinstance(cell.value, str):
                                items.add(cell.value)
                        return items
        raise ValueError(f"symbol {target} not found in {source['file']}")
    if kind == "yaml_values":
        # Read a YAML file (possibly outside the repo) and return the set of
        # values found at `key` (dot-separated). If the key resolves to a
        # mapping, values are taken; if to a list, elements are taken;
        # otherwise the scalar is returned as a single-element set.
        import yaml
        raw_path = source["file"]
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            candidate = REPO_ROOT / raw_path
            path = candidate if candidate.exists() else REPO_ROOT.parent / raw_path
        if not path.exists():
            raise ValueError(f"yaml_values: file not found: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cursor = data
        for k in source["key"].split("."):
            if not isinstance(cursor, dict):
                raise ValueError(f"yaml_values: key path {source['key']} broke at {k} in {path}")
            cursor = cursor.get(k, {})
        if isinstance(cursor, dict):
            return {str(v) for v in cursor.values()}
        if isinstance(cursor, list):
            return {str(v) for v in cursor}
        return {str(cursor)} if cursor else set()
    if kind == "json_array_field":
        # Read a JSON file whose root is an array of objects; for each element,
        # collect the value at `field` (dot-separated). Returns the union set.
        # Typical use: extract `metadata.source` from rag/corpus.json to get
        # the distinct set of indexed documents.
        import json
        path = Path(source["file"])
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.exists():
            raise ValueError(f"json_array_field: file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        field_parts = source["field"].split(".")
        items: set[str] = set()
        for element in (data if isinstance(data, list) else []):
            cursor = element
            for p in field_parts:
                if isinstance(cursor, dict):
                    cursor = cursor.get(p)
                else:
                    cursor = None
                    break
            if cursor is not None:
                items.add(str(cursor))
        return items
    if kind == "anchor_list":
        block = _extract_concept_block(_read(source["file"]), source["concept_id"])
        if block is None:
            return set()
        pattern = source.get("item_pattern")
        if pattern:
            return set(re.findall(pattern, block))
        items = set()
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith(("- ", "* ")):
                items.add(stripped[2:].strip("` \"'"))
        return items
    if kind == "ast_decorator_args":
        # For decorators like @app.get("/path") or @app.post("/path"), extract
        # the positional arg at `arg_index` (default 0). Accepts a list of
        # decorator names in `decorators` or a single `decorator`. Useful for
        # FastAPI / Flask route inventories.
        tree = ast.parse(_read(source["file"]))
        decorators = source.get("decorators") or [source["decorator"]]
        arg_index = int(source.get("arg_index", 0))
        items: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for deco in node.decorator_list:
                    if isinstance(deco, ast.Call):
                        name = _decorator_name(deco.func)
                        if name in decorators and len(deco.args) > arg_index:
                            arg = deco.args[arg_index]
                            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                items.add(arg.value)
                                break
        return items
    if kind == "ast_enum_values":
        # For a class body like `class SessionAction(str, Enum): PING = "ping"`,
        # return the set of RHS string literal values. Works for Python's
        # built-in enum (the str-subclassed pattern commonly used for API
        # dispatch tables) — we do not actually check the base class because
        # any class whose members are string constants works the same way.
        tree = ast.parse(_read(source["file"]))
        target = source["symbol"]
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == target:
                values: set[str] = set()
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant) \
                            and isinstance(stmt.value.value, str):
                        values.add(stmt.value.value)
                return values
        raise ValueError(f"class {target} not found in {source['file']}")
    if kind == "ast_dict_keys":
        # For a top-level assignment `SYMBOL = {...}`, return the set of
        # string keys.
        tree = ast.parse(_read(source["file"]))
        target = source["symbol"]
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == target:
                        if isinstance(node.value, ast.Dict):
                            keys: set[str] = set()
                            for key in node.value.keys:
                                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                                    keys.add(key.value)
                            return keys
                        return set()
        raise ValueError(f"symbol {target} not found in {source['file']}")
    if kind == "literal_set":
        # Hardcoded expected set declared inline in the YAML. Useful as the
        # truth side of a bidirectional subset when no code or file naturally
        # holds the authoritative list (e.g. stable preset names).
        return {str(v) for v in source["values"]}
    if kind == "file_regex_matches":
        # Run re.findall across the whole file (MULTILINE on) and return the
        # set of first-group captures. Useful for scanning CHANGELOG for
        # `## [X.Y.Z]` version headings without wrapping in an anchor block.
        text = _read(source["file"])
        pattern = source["pattern"]
        return set(re.findall(pattern, text, re.MULTILINE))
    if kind == "command_lines":
        # Run a shell command and return each non-empty output line as an
        # element. Useful for pulling `git tag --list 'v*'` into a set.
        cmd = source["cmd"]
        try:
            out = subprocess.check_output(
                cmd, shell=True, cwd=REPO_ROOT, text=True,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            return set()
        return {line.strip() for line in out.splitlines() if line.strip()}
    raise ValueError(f"unknown item-source type: {kind}")


def file_exists(params: dict) -> tuple[bool, str]:
    """Assert a referenced file exists.

    params:
        path     : absolute or repo-relative path
        context  : optional description of who references it (for the message)
    """
    path = Path(params["path"])
    if not path.is_absolute():
        path = REPO_ROOT / path
    if path.exists():
        return True, f"exists: {path}"
    ctx = params.get("context", "")
    suffix = f" (referenced in {ctx})" if ctx else ""
    return False, f"MISSING: {path}{suffix}"


def version_match(params: dict) -> tuple[bool, str]:
    """Assert two version strings are equal.

    params:
        a : source spec (see _read_version)
        b : source spec
    """
    a = _read_version(params["a"])
    b = _read_version(params["b"])
    if a == b:
        return True, f"version agrees: {a}"
    return False, f"version mismatch: a={a}, b={b}"


def _read_version(spec: dict) -> str:
    src = spec["source"]
    if src == "literal":
        return str(spec["value"])
    if src == "file_regex":
        text = _read(spec["file"])
        # re.MULTILINE so callers can anchor patterns with ^ at line starts
        # without having to know about the flag (common for `version = "X"`
        # style config fields that live on a line by themselves).
        m = re.search(spec["pattern"], text, re.MULTILINE)
        return m.group(1) if m else "<not_found>"
    if src == "command":
        try:
            out = subprocess.check_output(
                spec["cmd"], shell=True, cwd=REPO_ROOT, text=True
            ).strip()
            return out
        except subprocess.CalledProcessError:
            return "<command_failed>"
    raise ValueError(f"unknown version source: {src}")


def claim_verifies(params: dict) -> tuple[bool, str]:
    """Assert that a documentation claim is backed by code (or absent).

    params:
        claim         : human description of the claim (used in report)
        code_grep     : {regex, file_pattern}
                        regex        : egrep pattern
                        file_pattern : glob relative to REPO_ROOT (default: '.')
        expected      : 'found' | 'not_found'  (default: 'found')
    """
    spec = params["code_grep"]
    expected = params.get("expected", "found")
    file_pattern = spec.get("file_pattern", ".")

    # Use rg if available, else grep -rE.
    tool = "rg" if _which("rg") else "grep"
    if tool == "rg":
        cmd = ["rg", "-n", "--", spec["regex"], file_pattern]
    else:
        cmd = ["grep", "-rnE", spec["regex"], file_pattern]

    try:
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        found = result.returncode == 0 and bool(result.stdout.strip())
    except Exception as e:
        return False, f"grep failed: {e}"

    if expected == "found":
        if found:
            return True, f"claim backed by code: '{params['claim']}'"
        return False, f"claim NOT backed by code: '{params['claim']}' (pattern: {spec['regex']})"
    if expected == "not_found":
        if not found:
            return True, f"claim correctly absent: '{params['claim']}'"
        return False, f"claim present in code but expected absent: '{params['claim']}'"
    return False, f"unknown expected value: {expected}"


def _which(cmd: str) -> bool:
    from shutil import which
    return which(cmd) is not None


def review_expiry(params: dict) -> tuple[bool, str]:
    """Assert a manual-review timestamp has not gone stale.

    params:
        file          : path to YAML containing the timestamp
                        (may be outside the repo, e.g. ~/Projects/.external_versions.yml)
        key           : dotted path to the block with {reviewed_at, expiry_days}
        expiry_days   : optional override if not declared inside the block
    """
    import yaml  # deferred import

    raw_path = params["file"]
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        # Try repo-relative first, then one level up (ecosystem location)
        candidate = REPO_ROOT / raw_path
        path = candidate if candidate.exists() else REPO_ROOT.parent / raw_path

    if not path.exists():
        return False, f"review file missing: {path}"

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cursor = data
    for k in params["key"].split("."):
        if not isinstance(cursor, dict):
            return False, f"key path {params['key']} broke at {k} in {path}"
        cursor = cursor.get(k, {})

    if not isinstance(cursor, dict):
        return False, f"key {params['key']} did not resolve to a dict in {path}"

    reviewed_at = cursor.get("reviewed_at")
    expiry_days = params.get("expiry_days") or cursor.get("expiry_days")

    if reviewed_at is None or expiry_days is None:
        return False, f"reviewed_at/expiry_days missing under {params['key']} in {path}"

    if isinstance(reviewed_at, str):
        reviewed_at = date.fromisoformat(reviewed_at)
    elif isinstance(reviewed_at, datetime):
        reviewed_at = reviewed_at.date()

    age_days = (date.today() - reviewed_at).days
    if age_days <= int(expiry_days):
        return True, f"review fresh: {params['key']} age={age_days}d/{expiry_days}d"
    return False, (
        f"REVIEW EXPIRED: {params['key']} age={age_days}d > {expiry_days}d "
        f"(last reviewed {reviewed_at})"
    )


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

def commits_since_tag(params: dict) -> tuple[bool, str]:
    """Assert commits accumulated past the latest annotated tag are within
    cadence thresholds. Prevents silently accumulating 50+ commits without
    cutting a release.

    params:
        max_commits   : int   — hard ceiling; exceeded → fail
        warn_commits  : int   — soft threshold; warns but still passes
                                (default: half of max_commits)
        max_age_days  : int|None — if the tag is older than N days AND
                                any commits are past it, fail
    """
    import time

    max_commits = int(params.get("max_commits", 30))
    warn_commits = int(params.get("warn_commits", max_commits // 2))
    max_age_days = params.get("max_age_days")

    try:
        latest_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        return True, "no tags yet — release-cadence check skipped"

    try:
        count = int(subprocess.check_output(
            ["git", "rev-list", "--count", f"{latest_tag}..HEAD"],
            cwd=REPO_ROOT, text=True,
        ).strip())
    except subprocess.CalledProcessError as e:
        return False, f"git rev-list failed: {e}"

    if count == 0:
        return True, f"at tag {latest_tag} (0 commits since)"

    if max_age_days is not None:
        try:
            tag_ts = int(subprocess.check_output(
                ["git", "log", "-1", "--format=%at", latest_tag],
                cwd=REPO_ROOT, text=True,
            ).strip())
            age_days = (time.time() - tag_ts) / 86400
        except subprocess.CalledProcessError:
            age_days = 0
        if age_days > int(max_age_days):
            return False, (
                f"tag {latest_tag} is {age_days:.0f}d old with {count} "
                f"commit(s) pending — consider cutting a release"
            )

    if count > max_commits:
        return False, (
            f"{count} commits since tag {latest_tag} > max_commits={max_commits} "
            f"— cut a release before the backlog grows further"
        )
    if count > warn_commits:
        return True, (
            f"{count} commits since tag {latest_tag} (warn_commits={warn_commits}) "
            f"— consider tagging a release soon"
        )
    return True, f"{count} commits since tag {latest_tag} (under thresholds)"


def glob_count(params: dict) -> tuple[bool, str]:
    """Assert the number of repo-root files matching any of N glob patterns
    equals the expected value. Useful for ecosystem rules such as
    "exactly one install script per repo root".

    params:
        patterns : list of glob patterns (relative to REPO_ROOT)
        expected : int
    """
    patterns = params["patterns"]
    expected = int(params["expected"])
    matches: set[str] = set()
    for pat in patterns:
        for m in REPO_ROOT.glob(pat):
            if m.is_file():
                # Store as path relative to REPO_ROOT for readable diagnostics.
                matches.add(str(m.relative_to(REPO_ROOT)))
    actual = len(matches)
    if actual == expected:
        return True, f"glob_count: {patterns} → {actual} file(s) ({sorted(matches)})"
    return False, (
        f"glob_count mismatch: patterns {patterns} matched {actual} file(s) "
        f"({sorted(matches)}), expected {expected}"
    )


INVARIANT_TYPES = {
    "tool_count":         tool_count,
    "subset":             subset,
    "file_exists":        file_exists,
    "version_match":      version_match,
    "claim_verifies":     claim_verifies,
    "review_expiry":      review_expiry,
    "glob_count":         glob_count,
    "commits_since_tag":  commits_since_tag,
}
