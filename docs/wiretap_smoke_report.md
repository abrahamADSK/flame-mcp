# Wiretap CLI smoke report

Generated: 2026-06-10T14:31:38Z
Source binary dir: `/opt/Autodesk/wiretap/tools/current`
Reference doc: `/Users/abraham/Projects/flame-mcp/docs/wiretap_cli_reference.md`
Timeout: **none** (`timeout` / `gtimeout` not installed — install GNU coreutils for safety)

## CLI invocations

| Tool | Args used | Exit | First stdout line | First stderr line | Time (ms) | Status |
|---|---|---|---|---|---|---|
| `wiretap_can_create_node` | `--help` | 0 | `Usage: wiretap_can_create_node [Options] <Params>` | ` ` | 79 | ok |
| `wiretap_client_tool` | `--help` | 0 | `Usage: wiretap_client_tool [Options]` | ` ` | 64 | ok |
| `wiretap_create_audio` | `--help` | 0 | `Usage: wiretap_create_audio [Options] <Params>` | ` ` | 62 | ok |
| `wiretap_create_clip` | `--help` | 0 | `Usage: wiretap_create_clip [Options] <Params>` | ` ` | 63 | ok |
| `wiretap_create_node` | `--help` | 0 | `Usage: wiretap_create_node [Options] <Params>` | ` ` | 54 | ok |
| `wiretap_destroy_node` | (skipped — destructive) | — | — | — | — | skipped |
| `wiretap_duplicate_node` | `--help` | 0 | `Usage: wiretap_duplicate_node [Options] <Params>` | ` ` | 60 | ok |
| `wiretap_event_listener` | `--help` | 0 | `Usage: wiretap_event_listener [Options] <Params>` | ` ` | 70 | ok |
| `wiretap_get_available_metadata` | `--help` | 0 | `Usage: wiretap_get_available_metadata [Options] <Params>` | ` ` | 64 | ok |
| `wiretap_get_children` | `--help` | 0 | `Usage: wiretap_get_children [Options] <Params>` | ` ` | 65 | ok |
| `wiretap_get_clip_format` | `--help` | 0 | `Usage: wiretap_get_clip_format [Options] <Params>` | ` ` | 61 | ok |
| `wiretap_get_display_name` | `--help` | 0 | `Usage: wiretap_get_display_name [Options] <Params>` | ` ` | 71 | ok |
| `wiretap_get_frames` | `--help` | 0 | `Usage: wiretap_get_frames [Options] <Params>` | ` ` | 65 | ok |
| `wiretap_get_metadata` | `--help` | 0 | `Usage: wiretap_get_metadata [Options] <Params>` | ` ` | 69 | ok |
| `wiretap_get_node_type` | `--help` | 0 | `Usage: wiretap_get_node_type [Options] <Params>` | ` ` | 61 | ok |
| `wiretap_get_num_frames` | `--help` | 0 | `Usage: wiretap_get_num_frames [Options] <Params>` | ` ` | 66 | ok |
| `wiretap_get_parent_node` | `--help` | 0 | `Usage: wiretap_get_parent_node [Options] <Params>` | ` ` | 71 | ok |
| `wiretap_get_root_node` | `--help` | 0 | `Usage: wiretap_get_root_node [Options]` | ` ` | 69 | ok |
| `wiretap_get_storage_id` | `--help` | 0 | `Usage: wiretap_get_storage_id [Options] ` | ` ` | 63 | ok |
| `wiretap_ip_resolver` | `--help` | 0 | `Usage: wiretap_ip_resolver [Options]` | ` ` | 64 | ok |
| `wiretap_is_clip` | `--help` | 0 | `Usage: wiretap_is_clip [Options] <Params>` | ` ` | 61 | ok |
| `wiretap_is_metadata_available` | `--help` | 0 | `Usage: wiretap_is_metadata_available [Options] <Params>` | ` ` | 56 | ok |
| `wiretap_multicast_listener` | `--help` | 0 | `Usage: wiretap_multicast_listener [Options]` | ` ` | 63 | ok |
| `wiretap_network_tool` | `--help` | 0 | `Usage: wiretap_network_tool [Options]` | ` ` | 62 | ok |
| `wiretap_ping` | `--help` | 0 | `Usage: wiretap_ping [Options]` | ` ` | 60 | ok |
| `wiretap_print_tree` | `--help` | 0 | `Usage: wiretap_print_tree [Options]` | ` ` | 58 | ok |
| `wiretap_read_stream` | `--help` | 0 | `Usage: wiretap_read_stream [Options] <Params>` | ` ` | 63 | ok |
| `wiretap_remove_server` | (skipped — destructive) | — | — | — | — | skipped |
| `wiretap_rename_node` | (skipped — destructive) | — | — | — | — | skipped |
| `wiretap_resolve_path` | `--help` | 0 | `Usage: wiretap_resolve_path [Options] <Params>` | ` ` | 65 | ok |
| `wiretap_resolve_storage_id` | `--help` | 0 | `Usage: wiretap_resolve_storage_id [Options] <Params>` | ` ` | 63 | ok |
| `wiretap_rw_file` | `--help` | 0 | `Usage: wiretap_rw_file [Options] <Params>` | ` ` | 67 | ok |
| `wiretap_rw_frame` | `--help` | 0 | `Usage: wiretap_rw_frame [Options] <Params>` | ` ` | 63 | ok |
| `wiretap_server_dump` | `--help` | 0 | `Usage: wiretap_server_dump [Options]` | ` ` | 68 | ok |
| `wiretap_services_snapshot` | `--help` | 0 | `Usage: /opt/Autodesk/wiretap/tools/current/wiretap_services_snapshot [-p <port>\|...] [-f <output> ] [<hostname>\|...] [-h]` | ` ` | 75 | ok |
| `wiretap_set_metadata` | (skipped — destructive) | — | — | — | — | skipped |
| `wiretap_set_num_frames` | (skipped — destructive) | — | — | — | — | skipped |

Total tools processed: 37

## Wiretap SDK smoke

```json
{
  "sdk_path": "/opt/Autodesk/python/2027/lib/python3.13/site-packages/adsk",
  "module": "libwiretapPythonClientAPI",
  "host": "localhost",
  "platform": "darwin",
  "python": "3.13.3",
  "ok": true,
  "skip_reason": null,
  "symbols": [
    "Blob",
    "WireTapAudioFormat",
    "WireTapClient",
    "WireTapClientInit",
    "WireTapClientUninit",
    "WireTapClipFormat",
    "WireTapFindChild",
    "WireTapFrameId",
    "WireTapInt",
    "WireTapMetaData",
    "WireTapNodeHandle",
    "WireTapNodeId",
    "WireTapOS",
    "WireTapResolveDisplayPath",
    "WireTapServerHandle",
    "WireTapServerId",
    "WireTapServerInfo",
    "WireTapServerList",
    "WireTapServerList_Base",
    "WireTapSetDefaultCallTimeoutMS",
    "WireTapStr",
    "WireTapStrList"
  ],
  "steps": [
    {
      "step": "WireTapClientInit",
      "ok": true,
      "value": "True",
      "ms": 1
    },
    {
      "step": "WireTapServerHandle",
      "ok": true,
      "value": "<libwiretapPythonClientAPI.WireTapServerHandle object at 0x104b36f70>",
      "ms": 0
    },
    {
      "step": "WireTapNodeHandle('/')",
      "ok": true,
      "value": "<libwiretapPythonClientAPI.WireTapNodeHandle object at 0x104c8d580>",
      "ms": 0
    },
    {
      "step": "getNumChildren",
      "ok": true,
      "value": "{'ok': False, 'n': 0}",
      "ms": 1043
    },
    {
      "step": "WireTapClientUninit",
      "ok": true,
      "value": "None",
      "ms": 2014
    }
  ],
  "symbol_count": 22
}
```
