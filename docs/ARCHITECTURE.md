# flame-mcp — Architecture & Query Flow

## System blocks

```
┌─────────────────────┐   MCP (stdio)   ┌──────────────────────┐   TCP 4444   ┌──────────────────┐
│  Claude Code        │ ◄────────────── │  flame_mcp_server    │ ◄─────────── │  Autodesk Flame  │
│  Claude Desktop     │ ───────────────►│  (Python · macOS)    │ ────────────►│  Python bridge   │
│  Cowork · Chat      │                 │  + ChromaDB RAG      │              │  flame module    │
└─────────────────────┘                 └──────────────────────┘              └──────────────────┘
```

| Block | File | Role |
|---|---|---|
| **Claude** | — | Understands the request, calls MCP tools, generates Python code |
| **MCP Server** | `flame_mcp_server.py` | Exposes tools (`execute_python`, `search_flame_docs`, `learn_pattern`), routes RAG queries |
| **TCP Bridge** | `hooks/flame_mcp_bridge.py` | Flame Python hook · TCP server on port 4444 · executes code inside Flame's interpreter |
| **RAG Engine** | `rag/` | ChromaDB + BGE embeddings · 375 chunks across 7 source docs |

---

## Query flow & decision tree

```mermaid
flowchart TD
    A(["User request\nClaude Code · Desktop · Cowork · Chat"])
    B["search_flame_docs(query)\nRAG · ChromaDB · 375 chunks"]
    C{"score ≥ 60%?"}
    D["Pattern found\nuse chunk as reference"]
    E["Pattern missing ⚠\nbest effort + warn"]
    F["execute_python(code)\nTCP 4444 → Flame bridge"]
    G{"Execution\nsucceeded?"}
    H["learn_pattern()\nappend to FLAME_API.md\nrebuild index 🧠"]
    I["Retry max 3×\nread traceback\nmodify code"]
    J(["Answer + stats footer\nto user"])

    A --> B
    B --> C
    C -->|YES| D
    C -->|NO| E
    D --> F
    E --> F
    F --> G
    G -->|YES · score was low| H
    G -->|YES · already known| J
    G -->|NO| I
    H --> J
    I --> F

    style A fill:#1e3a5f,color:#93c5fd,stroke:#3b82f6
    style B fill:#451a03,color:#fcd34d,stroke:#f59e0b
    style C fill:#451a03,color:#fcd34d,stroke:#f59e0b
    style D fill:#052e16,color:#6ee7b7,stroke:#10b981
    style E fill:#450a0a,color:#fca5a5,stroke:#ef4444
    style F fill:#1e1b4b,color:#c4b5fd,stroke:#7c3aed
    style G fill:#451a03,color:#fcd34d,stroke:#f59e0b
    style H fill:#052e16,color:#6ee7b7,stroke:#10b981
    style I fill:#450a0a,color:#fca5a5,stroke:#ef4444
    style J fill:#1e3a5f,color:#93c5fd,stroke:#3b82f6
```

---

## Self-improving loop

Every successful `execute_python` call where RAG scored < 60% triggers `learn_pattern()`:

1. Working code appended as a structured block in `FLAME_API.md`
2. ChromaDB index rebuilt in background (~8 s)
3. Next session — same query returns > 70% relevance, no retries

---

## Knowledge base — 375 chunks across 7 source docs

| File | Chunks | Content |
|---|---|---|
| `FLAME_API.md` | 116 | Core API + self-learned patterns (auto-extended by `learn_pattern`) |
| `docs/flame_advanced_api.md` | 74 | Action, Color Management, Exporter, Conform/AAF, Timeline FX/BFX |
| `docs/flame_api_full.md` | 71 | PySequence, PyTrack, PyVersion, PyMarker, PyProject, PyWorkspace |
| `docs/flame_segment_timeline_api.md` | 61 | PySegment, PyClip.render(), PyBatch.create_batch_group() |
| `docs/flame_community_workflows.md` | 23 | Logik Forum operator jargon → API mapping |
| `docs/flame_cookbook_official.md` | 22 | Official Autodesk Python code samples |
| `docs/flame_vocabulary.md` | 8 | Operator terminology glossary |

> **Token economics:** RAG injects ~600 tokens per query vs ~38,000 for the full doc. Typical session saving: **80–85%**.
