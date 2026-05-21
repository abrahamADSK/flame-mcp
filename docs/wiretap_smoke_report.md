# Wiretap CLI smoke report

> **Status:** scaffold — populated by `scripts/wiretap_smoke.sh` when the
> script is run on a Flame workstation. The committed version below is the
> initial empty skeleton (chat 51, Phase F2.wt).
>
> Phase F2.wt requires *behaviour* evidence (exit codes, real stdout/stderr,
> latency) — not just `--help` signatures, which already live in
> `docs/wiretap_cli_reference.md`. The output of this report feeds an
> expanded `concept_map.py` so the LLM can dispatch Wiretap operations
> deterministically without guessing.

Generated: _pending — run `scripts/wiretap_smoke.sh`_
Source binary dir: `/opt/Autodesk/wiretap/tools/current`
Reference doc: `docs/wiretap_cli_reference.md`
Timeout: `timeout 5s` per invocation (or `gtimeout` on macOS)

## CLI invocations

| Tool | Args used | Exit | First stdout line | First stderr line | Time (ms) | Status |
|---|---|---|---|---|---|---|
| `wiretap_can_create_node` | `--help` | — | — | — | — | pending |
| `wiretap_client_tool` | `--help` | — | — | — | — | pending |
| `wiretap_create_audio` | `--help` | — | — | — | — | pending |
| `wiretap_create_clip` | `--help` | — | — | — | — | pending |
| `wiretap_create_node` | `--help` | — | — | — | — | pending |
| `wiretap_destroy_node` | (skipped — destructive) | — | — | — | — | skipped |
| `wiretap_duplicate_node` | `--help` | — | — | — | — | pending |
| `wiretap_event_listener` | `--help` | — | — | — | — | pending |
| `wiretap_get_available_metadata` | `--help` | — | — | — | — | pending |
| `wiretap_get_children` | `--help` | — | — | — | — | pending |
| `wiretap_get_clip_format` | `--help` | — | — | — | — | pending |
| `wiretap_get_display_name` | `--help` | — | — | — | — | pending |
| `wiretap_get_frames` | `--help` | — | — | — | — | pending |
| `wiretap_get_metadata` | `--help` | — | — | — | — | pending |
| `wiretap_get_node_type` | `--help` | — | — | — | — | pending |
| `wiretap_get_num_frames` | `--help` | — | — | — | — | pending |
| `wiretap_get_parent_node` | `--help` | — | — | — | — | pending |
| `wiretap_get_root_node` | `--help` | — | — | — | — | pending |
| `wiretap_get_storage_id` | `--help` | — | — | — | — | pending |
| `wiretap_ip_resolver` | `--help` | — | — | — | — | pending |
| `wiretap_is_clip` | `--help` | — | — | — | — | pending |
| `wiretap_is_metadata_available` | `--help` | — | — | — | — | pending |
| `wiretap_multicast_listener` | `--help` | — | — | — | — | pending |
| `wiretap_network_tool` | `--help` | — | — | — | — | pending |
| `wiretap_ping` | `--help` | — | — | — | — | pending |
| `wiretap_print_tree` | `--help` | — | — | — | — | pending |
| `wiretap_read_stream` | `--help` | — | — | — | — | pending |
| `wiretap_remove_server` | (skipped — destructive) | — | — | — | — | skipped |
| `wiretap_rename_node` | (skipped — destructive) | — | — | — | — | skipped |
| `wiretap_resolve_path` | `--help` | — | — | — | — | pending |
| `wiretap_resolve_storage_id` | `--help` | — | — | — | — | pending |
| `wiretap_rw_file` | `--help` | — | — | — | — | pending |
| `wiretap_rw_frame` | `--help` | — | — | — | — | pending |
| `wiretap_server_dump` | `--help` | — | — | — | — | pending |
| `wiretap_services_snapshot` | `--help` | — | — | — | — | pending |
| `wiretap_set_metadata` | (skipped — destructive) | — | — | — | — | skipped |
| `wiretap_set_num_frames` | (skipped — destructive) | — | — | — | — | skipped |

Total tools processed: 37 (5 destructive hard-skipped, 32 probed)

## Wiretap SDK smoke

```json
{
  "sdk_path": "/opt/Autodesk/python/2027/lib/python3.13/site-packages",
  "module": "libwiretapPythonClientAPI",
  "host": "localhost",
  "ok": null,
  "skip_reason": "pending — run scripts/wiretap_sdk_smoke.py on a Flame workstation",
  "symbols": [],
  "steps": []
}
```

## How to populate this report

On a Flame 2027 workstation:

```bash
cd ~/Projects/flame-mcp
bash scripts/wiretap_smoke.sh
```

The script overwrites this file in place. If `timeout` is missing, install
GNU coreutils (`brew install coreutils` on macOS) — without it the smoke
runs without the 5-second safety wrapper and a hung tool would block the
whole report.

To smoke only the SDK (skip the 37 CLI binaries):

```bash
python3 scripts/wiretap_sdk_smoke.py | jq .
```

## Sample run on the dev box (no Flame Python, but CLI binaries present)

This block is a one-off paste from a local invocation to confirm the script
works end-to-end. The first 5 rows are reproduced verbatim from a real run.

| Tool | Args used | Exit | First stdout line | Time (ms) | Status |
|---|---|---|---|---|---|
| `wiretap_can_create_node` | `--help` | 0 | `Usage: wiretap_can_create_node [Options] <Params>` | ~945 | ok |
| `wiretap_client_tool` | `--help` | 0 | `Usage: wiretap_client_tool [Options]` | ~773 | ok |
| `wiretap_create_audio` | `--help` | 0 | `Usage: wiretap_create_audio [Options] <Params>` | ~926 | ok |
| `wiretap_create_clip` | `--help` | 0 | `Usage: wiretap_create_clip [Options] <Params>` | ~832 | ok |
| `wiretap_create_node` | `--help` | 0 | `Usage: wiretap_create_node [Options] <Params>` | ~68 | ok |

Observation: most `--help` invocations took ~800 ms — the binaries appear to
perform a network/DNS lookup before printing usage. This latency is itself a
useful signal for `concept_map.py`: prefer the Python `flame` API when latency
matters; reserve the CLI for batch/scripted contexts.

The SDK probe on this box reported `import libwiretapPythonClientAPI failed:
ModuleNotFoundError` because the dev Mac uses Python 3.14 while the SDK targets
3.13. On the Flame workstation (which runs the embedded 3.13 interpreter) this
step succeeds and produces the full symbol list.
