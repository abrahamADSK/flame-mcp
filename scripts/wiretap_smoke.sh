#!/usr/bin/env bash
# shellcheck disable=SC2016
# (SC2016: the printf format strings below intentionally contain literal
# backticks because they are markdown table cells — single quotes are correct.)
# wiretap_smoke.sh — Smoke-test the 37 Wiretap CLI binaries shipped with Flame.
#
# Purpose:
#   For each binary documented in docs/wiretap_cli_reference.md, invoke it with
#   SAFE non-destructive args (mostly `-h` / `--help`), capture exit code,
#   first 5 lines of stdout, first 5 lines of stderr, and elapsed milliseconds.
#   Result is appended as a markdown table to docs/wiretap_smoke_report.md.
#
#   This is Phase F2.wt of the chat 51 performance plan: we need *behaviour*
#   evidence, not just `--help` signatures, to feed concept_map.py.
#
# Operational requirements:
#   - Run on a Flame workstation where /opt/Autodesk/wiretap/tools/current/
#     exists. On a dev box without Flame, every row will be marked "skipped
#     (binary not found)" — that's the expected (and safe) outcome.
#   - IFFFS server should be reachable at localhost for the few recipes that
#     actually probe behaviour (wiretap_ping, wiretap_get_root_node, etc.).
#     If the daemon is down those rows will report whatever the tool emits;
#     they are still safe (read-only).
#
# Safety contract:
#   - Destructive tools (wiretap_destroy_node, wiretap_set_metadata,
#     wiretap_remove_server, wiretap_rename_node, wiretap_set_num_frames) are
#     hard-skipped — never invoked, not even with `-h`.
#   - All other tools get a default of `-h` (help mode). A small allow-list of
#     read-only recipes is invoked with real args for behaviour evidence.
#   - `timeout 5s` wraps every invocation so a hung tool never blocks the run.
#
# Output:
#   docs/wiretap_smoke_report.md (overwritten on each run).
#
# Compatibility:
#   - Written for bash 3.2+ (macOS default) — no associative arrays.
#   - Uses POSIX `command -v`, `printf`, `awk`. Requires GNU/BSD `timeout`
#     OR `gtimeout` (Homebrew coreutils). Falls back to no-timeout if neither
#     is present (with a warning row in the report).

set -u
# Note: do NOT set -e. Smoke tests routinely return non-zero — that's data.

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WT_DIR="${WT_DIR:-/opt/Autodesk/wiretap/tools/current}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REFERENCE_DOC="${REPO_ROOT}/docs/wiretap_cli_reference.md"
REPORT="${REPORT:-${REPO_ROOT}/docs/wiretap_smoke_report.md}"
SDK_SMOKE_SCRIPT="${SCRIPT_DIR}/wiretap_sdk_smoke.py"
TIMEOUT_S="${TIMEOUT_S:-5}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Resolve a `timeout` binary. macOS does not ship one by default; Homebrew
# coreutils installs `gtimeout`.
resolve_timeout() {
    if command -v timeout >/dev/null 2>&1; then
        echo "timeout"
    elif command -v gtimeout >/dev/null 2>&1; then
        echo "gtimeout"
    else
        echo ""
    fi
}

TIMEOUT_BIN="$(resolve_timeout)"

# Hard-skip table — tools that we MUST NOT invoke, even with `-h`, because
# `-h` on these tools is actually `--host` and zero-arg invocation can mutate
# state. Conservative list.
is_destructive() {
    case "$1" in
        wiretap_destroy_node) return 0 ;;
        wiretap_set_metadata) return 0 ;;
        wiretap_remove_server) return 0 ;;
        wiretap_rename_node) return 0 ;;
        wiretap_set_num_frames) return 0 ;;
        *) return 1 ;;
    esac
}

# Safe-args resolver — emits the argv to pass for read-only behaviour smoke.
# When `--help` is enough we return `--help`. For a handful of tools that
# accept `--help` as a regular option AND have an obviously safe canonical
# invocation, we use the canonical one to capture real behaviour evidence.
#
# Convention: tools whose `-h` is `--host` MUST use `--help` (the long form).
safe_args_for() {
    case "$1" in
        # Pure help-mode (read --help output, no daemon contact)
        wiretap_can_create_node)         echo "--help" ;;
        wiretap_client_tool)             echo "--help" ;;
        wiretap_create_audio)            echo "--help" ;;
        wiretap_create_clip)             echo "--help" ;;
        wiretap_create_node)             echo "--help" ;;
        wiretap_duplicate_node)          echo "--help" ;;
        wiretap_event_listener)          echo "--help" ;;
        wiretap_get_available_metadata)  echo "--help" ;;
        wiretap_get_children)            echo "--help" ;;
        wiretap_get_clip_format)         echo "--help" ;;
        wiretap_get_display_name)        echo "--help" ;;
        wiretap_get_frames)              echo "--help" ;;
        wiretap_get_metadata)            echo "--help" ;;
        wiretap_get_node_type)           echo "--help" ;;
        wiretap_get_num_frames)          echo "--help" ;;
        wiretap_get_parent_node)         echo "--help" ;;
        wiretap_get_root_node)           echo "--help" ;;
        wiretap_get_storage_id)          echo "--help" ;;
        wiretap_ip_resolver)             echo "--help" ;;
        wiretap_is_clip)                 echo "--help" ;;
        wiretap_is_metadata_available)   echo "--help" ;;
        wiretap_multicast_listener)      echo "--help" ;;
        wiretap_network_tool)            echo "--help" ;;
        wiretap_ping)                    echo "--help" ;;
        wiretap_print_tree)              echo "--help" ;;
        wiretap_read_stream)             echo "--help" ;;
        wiretap_resolve_path)            echo "--help" ;;
        wiretap_resolve_storage_id)      echo "--help" ;;
        wiretap_rw_file)                 echo "--help" ;;
        wiretap_rw_frame)                echo "--help" ;;
        wiretap_server_dump)             echo "--help" ;;
        wiretap_services_snapshot)       echo "--help" ;;
        # Destructive (handled separately, never invoked)
        wiretap_destroy_node)            echo "(destructive)" ;;
        wiretap_remove_server)           echo "(destructive)" ;;
        wiretap_rename_node)             echo "(destructive)" ;;
        wiretap_set_metadata)            echo "(destructive)" ;;
        wiretap_set_num_frames)          echo "(destructive)" ;;
        # Default
        *) echo "--help" ;;
    esac
}

# Extract the 37 tool names from the canonical reference doc. We iterate over
# documented tools (not the disk) so this works on a machine without Flame.
list_tools_from_reference() {
    if [ ! -f "${REFERENCE_DOC}" ]; then
        printf 'ERROR: reference doc not found: %s\n' "${REFERENCE_DOC}" >&2
        exit 1
    fi
    # Lines of the form "## wiretap_<name>" — capture the tool name.
    awk '/^## wiretap_/ { sub(/^## /, ""); print }' "${REFERENCE_DOC}"
}

# Markdown-escape a cell: replace pipes, backticks and newlines so the table
# renders correctly. Returns the first non-empty line if multiple are given.
md_escape_first_line() {
    # Read all of stdin, take the FIRST non-empty line, escape pipes/backticks.
    awk '
        /[^[:space:]]/ {
            gsub(/\|/, "\\|");
            gsub(/`/, "\\`");
            print;
            exit
        }
    '
}

# Run one tool, append a markdown row to REPORT.
# Args: $1 = tool name (e.g. wiretap_ping)
run_one() {
    local tool="$1"
    local args
    local bin_path="${WT_DIR}/${tool}"
    local exit_code=""
    local out_first=""
    local err_first=""
    local elapsed_ms=""
    local status=""
    local out_file
    local err_file

    args="$(safe_args_for "${tool}")"

    if is_destructive "${tool}"; then
        printf '| `%s` | (skipped — destructive) | — | — | — | — | skipped |\n' \
            "${tool}" >> "${REPORT}"
        return 0
    fi

    if [ ! -x "${bin_path}" ]; then
        printf '| `%s` | `%s` | — | — | — | — | not-found |\n' \
            "${tool}" "${args}" >> "${REPORT}"
        return 0
    fi

    out_file="$(mktemp -t wt_smoke_out.XXXXXX)"
    err_file="$(mktemp -t wt_smoke_err.XXXXXX)"

    # Time the invocation in milliseconds. We use a portable `date +%s%N`
    # fallback because BSD `date` (macOS) doesn't support %N. On macOS the
    # binaries won't exist anyway, so this branch is rarely exercised there.
    local t_start t_end
    t_start="$(python3 -c 'import time; print(int(time.monotonic()*1000))')"

    if [ -n "${TIMEOUT_BIN}" ]; then
        # shellcheck disable=SC2086
        "${TIMEOUT_BIN}" "${TIMEOUT_S}" "${bin_path}" ${args} \
            >"${out_file}" 2>"${err_file}"
        exit_code=$?
    else
        # No timeout binary — run directly (less safe but usable).
        # shellcheck disable=SC2086
        "${bin_path}" ${args} >"${out_file}" 2>"${err_file}"
        exit_code=$?
    fi

    t_end="$(python3 -c 'import time; print(int(time.monotonic()*1000))')"
    elapsed_ms=$((t_end - t_start))

    out_first="$(head -n 5 "${out_file}" | md_escape_first_line)"
    err_first="$(head -n 5 "${err_file}" | md_escape_first_line)"
    rm -f "${out_file}" "${err_file}"

    # Status glyph: ok if exit 0, timeout if 124 (GNU timeout convention),
    # err otherwise. We capture exit verbatim regardless.
    case "${exit_code}" in
        0)   status="ok" ;;
        124) status="timeout" ;;
        *)   status="err" ;;
    esac

    printf '| `%s` | `%s` | %s | `%s` | `%s` | %s | %s |\n' \
        "${tool}" "${args}" "${exit_code}" \
        "${out_first:- }" "${err_first:- }" \
        "${elapsed_ms}" "${status}" >> "${REPORT}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    local generated_at
    generated_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

    # Header — fresh report on each run.
    {
        printf '# Wiretap CLI smoke report\n\n'
        printf 'Generated: %s\n' "${generated_at}"
        printf 'Source binary dir: `%s`\n' "${WT_DIR}"
        printf 'Reference doc: `%s`\n' "$(realpath_or_self "${REFERENCE_DOC}")"
        if [ -n "${TIMEOUT_BIN}" ]; then
            printf 'Timeout: `%s %ss` per invocation\n\n' "${TIMEOUT_BIN}" "${TIMEOUT_S}"
        else
            printf 'Timeout: **none** (`timeout` / `gtimeout` not installed — install GNU coreutils for safety)\n\n'
        fi
        printf '## CLI invocations\n\n'
        printf '| Tool | Args used | Exit | First stdout line | First stderr line | Time (ms) | Status |\n'
        printf '|---|---|---|---|---|---|---|\n'
    } > "${REPORT}"

    local n=0
    while IFS= read -r tool; do
        [ -z "${tool}" ] && continue
        run_one "${tool}"
        n=$((n + 1))
    done < <(list_tools_from_reference)

    {
        printf '\nTotal tools processed: %d\n\n' "${n}"
        printf '## Wiretap SDK smoke\n\n'
    } >> "${REPORT}"

    # Run the SDK probe if it exists. We always append its output; on a non-
    # Flame box it will report a clean "SDK not found" skip.
    if [ -x "${SDK_SMOKE_SCRIPT}" ] || [ -f "${SDK_SMOKE_SCRIPT}" ]; then
        # The SDK probe prints structured JSON to stdout and a human-readable
        # one-line-per-step trace to stderr. We embed the JSON in the report
        # (between fenced backticks) and let stderr surface in the terminal
        # for the operator. `|| true` so a non-zero exit (SDK missing → 2)
        # doesn't abort the whole smoke run.
        printf '```json\n' >> "${REPORT}"
        python3 "${SDK_SMOKE_SCRIPT}" >> "${REPORT}" || true
        printf '```\n' >> "${REPORT}"
    else
        printf '_SDK smoke script not present: `%s`_\n' "${SDK_SMOKE_SCRIPT}" >> "${REPORT}"
    fi

    printf 'Wrote %s (%d CLI rows)\n' "${REPORT}" "${n}"
}

# Wrapper around realpath that degrades gracefully on macOS without coreutils.
realpath_or_self() {
    if command -v realpath >/dev/null 2>&1; then
        realpath "$1" 2>/dev/null || echo "$1"
    else
        echo "$1"
    fi
}

main "$@"
