# Claude Code skills owned by flame-mcp

Procedural knowledge for *driving Flame through this server* — the order of
operations and what fails silently. Distinct from the three other layers:

| Layer | Holds | Where |
|---|---|---|
| **Tool** | Side effects, enforcement, I/O | `src/flame_mcp/server.py` |
| **Skill** | The recipe: which tools, in what order, the traps | here |
| **RAG** | Reference manual: classes, methods, signatures | `src/flame_mcp/docs/*.md` |
| **Memory** | Cross-session state and behavioural feedback | `~/.claude/.../memory/` |

A skill costs its `description` in **every** session and loads its body only when
the description matches the user's intent. Keep descriptions tight and triggery.

## Why they live here and not in `.claude/skills/`

`.gitignore` excludes `.claude/` wholesale in this repo, so a skill placed there
would be silently untracked. Keeping them under `docs/` makes them version
controlled and subject to the atomic-docs rule: **a skill ships in the same commit
as the code it describes.**

They are *activated* by symlinking into the user-level skills directory, which is
what makes them fire from any working directory — not only when the cwd is this
repo. Skill discovery follows symlinked directories (verified).

## Activating them on a fresh clone

```bash
for s in flame-batch-authoring flame-delivery; do
  ln -s "$PWD/docs/skills/$s" ~/.claude/skills/"$s"
done
```

Remove with `rm ~/.claude/skills/<name>` — that deletes the symlink, never the
tracked content.

## Current skills

| Skill | Fires on |
|---|---|
| `flame-batch-authoring` | Any `flame.batch` call, **reads included**: the main-thread idle-event contract, the active group that cannot be switched from Python, node-name scoping |
| `flame-delivery` | Render → export → review Version → open clip, and the traps in each: export deadlocks, a start frame that moves with the current version, presets that apply no colour |

## Relationship to `concept_map.py`

`resolve_concept` carries a `recipe` field — a home-grown version of the same idea,
routed by hand-tuned keyword matching whose failure is documented in its own source
(`concept_map.py:663-666`, "three failed queries per session"). A skill
`description` does that routing by semantic match instead.

The generic batch contract now lives in `flame-batch-authoring` and is **duplicated**
in the `build comp` recipe. That duplication is deliberate for now: removing it from
the recipe bets on the skill always firing, and if it does not, the agent loses the
threading contract entirely — which ends in a Flame crash. Deduplicate once the
skills have proven they fire in real use, not before.

## Editing

Edit the file in this repo — the symlink means the change is live immediately, with
no reinstall and no MCP restart. That is the main reason procedure belongs in a
skill rather than in a tool docstring or the server `instructions` block, both of
which need a release and a full Claude Code restart to take effect.
