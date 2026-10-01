---
name: flame-batch-authoring
description: Build or modify a Flame Batch/BFX node graph from Python — create and wire nodes, read node lists or sockets, set Write File, render. Fire BEFORE any flame.batch call, read included — main-thread idle-event contract, an active group that cannot be switched from Python, node-name scoping. E.g. "monta el batch", "conecta estos nodos", "expande el multicanal", "renderiza el batch", "add a node to the comp".
---

# Flame Batch authoring from Python

Applies to **any** Batch or BFX graph, not one project's comp. Everything here was
falsified in-vivo against Flame 2027; none of it is inferable from the API docs.

For *which* class or method to call, use `search_flame_docs` — that is the
reference layer and it covers the whole product. This skill is the **order of
operations and what fails silently**.

## The three non-negotiables

### 1. Batch state is UI-backed: everything runs on the main thread

Every batch call — `create_node`, `connect_nodes`, `import_clip`, **and even
reading node lists or sockets** — must execute inside a function handed to
`flame.schedule_idle_event`, writing its result to a file the caller polls.

A worker-thread node drill killed Flame in-vivo. **Reads are not exempt**: this is
the mistake that looks safest and is not.

```python
# shape, not a literal snippet — budget ~15 s for the poll
import flame, json, pathlib

OUT = pathlib.Path("/tmp/flame_batch_probe.json")

def _work():
    bg = flame.batch
    if bg.name.get_value() != EXPECTED_GROUP:      # see §2 — guard EVERY event
        OUT.write_text(json.dumps({"error": "wrong active group"}))
        return
    OUT.write_text(json.dumps({"nodes": [n.name.get_value() for n in bg.nodes]}))

flame.schedule_idle_event(_work)
# caller polls OUT until it exists or the budget expires
```

Never touch `flame.batch` from the exec thread directly. `execute_python` blocks
some unwrapped patterns, but it cannot catch all of them — the discipline is yours.

### 2. The active batch group cannot be switched from Python

On Flame 2027 `bg.open()` is a **silent no-op** when another group is current;
`open()` + `go_to()` fails the same way, also without error.

Consequences:

- All wiring operates on `flame.batch`, i.e. whatever group the operator has open.
- **Verify its name first.** If it is not the target, ask the operator to
  double-click the target group in the UI, then wait.
- **Never write retry loops around `open()`.** They cannot succeed and they burn
  the idle budget.
- **Guard every mutating idle event on the batch-group name** so a wrong active
  group is never modified. A guard that only runs once, up front, is not enough —
  the operator can change the active group between events.

### 3. Node-name uniqueness validates against the ACTIVE group

Flame checks a new node's name against the group that is currently active, not
against the group you believe you are building. Three discriminating tests
confirmed this. A name that is free in the target group can still be rejected,
and a name you think is unique can collide.

This is why `wire_comp_tree` was abandoned rather than fixed: the operation cannot
be made safe while the active group is both unswitchable and the validation scope.

## Rendering

- Render through the **`render_batch` tool**, never `flame.batch.render()`.
- `render_batch` has reported success in Foreground while the work had only
  *started*. Do not hand control back on "started".
- **Wait for the full frame count.** A verdict that inspects only the first frame
  will sign off a 2-frame render of a 100-frame range as `-> OK`.
- Any range correction must be checked at **both** ends. A fix conditioned on the
  start failing is skipped entirely by a Write File already parked at the start.

## Reading before writing

`list_batch_groups` and the dedicated read tools answer structural questions
without Python. Reach for them first; drop to `execute_python` only for graph
shapes the tools do not expose — and then still inside an idle event.

**Names read back quoted.** `str(node.name)` (and any clip, reel or group name)
returns the value *with* its quotes — `"'CMP'"`. An equality test against
`'CMP'` is silently `False`, so a lookup reports "not found" with no error.
Compare `node.name.get_value()`, or `str(node.name).strip("'")`; the guard in
the probe above does exactly that.

## What this skill is not

- **Not the delivery cycle.** For the full relit-shot comp build and the
  render → publish → conform → review Version chain, fetch the recipe:
  `resolve_concept('expand multilayer')`.
- **Not an API reference.** Class and method lookup is `search_flame_docs`.
- **Not timeline editing.** `timeline_insert` / `timeline_overwrite` carry their
  own contracts in their docstrings.
