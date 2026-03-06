# flame-mcp — Architecture & Query Flow

## System blocks

```
┌──────────────────┐    MCP (stdio)    ┌──────────────────────┐    TCP 4444    ┌─────────────────┐
│  Claude Code /   │ ◄──────────────── │   flame_mcp_server   │ ◄──────────── │  Autodesk Flame │
│  Claude Desktop  │ ─────────────────►│   (Python, macOS)    │ ─────────────►│  Python bridge  │
│  Cowork / Chat   │                   │  + ChromaDB RAG       │                │  flame module   │
└──────────────────┘                   └──────────────────────┘                └─────────────────┘
```

| Block | File | Role |
|---|---|---|
| **Claude** | — | Understands the request, calls MCP tools, generates Python code |
| **MCP Server** | `flame_mcp_server.py` | Exposes tools (`execute_python`, `search_flame_docs`, `learn_pattern`), routes RAG queries |
| **TCP Bridge** | `hooks/flame_mcp_bridge.py` | Flame Python hook, TCP server on port 4444, executes code inside Flame's interpreter |
| **RAG Engine** | `rag/` | ChromaDB + BGE embeddings, 375 chunks across 7 source docs |

---

## Query flow & decision tree

```mermaid
flowchart TD
    USER(["👤 User\nClaude Code · Desktop · Cowork · Embedded Chat"])

    USER -->|natural language request| CLAUDE["🤖 Claude\nreceives request"]

    CLAUDE -->|"search_flame_docs(query)"| RAG

    subgraph RAG ["🔍 RAG — Semantic Search"]
        direction TB
        EMBED["Embed query\nBAAI/bge-small-en-v1.5"]
        CHROMA[("ChromaDB\n375 chunks\n7 source docs")]
        TOP5["Top 5 chunks\n+ max_relevance_score"]
        EMBED --> CHROMA --> TOP5
    end

    TOP5 --> SCORE{{"max_relevance\n≥ 60% ?"}}

    SCORE -->|"✅ YES\nhigh confidence"| HIGHCONF["Pattern found\nUse chunk as API reference\n~120–600 tokens injected"]
    SCORE -->|"⚠️ NO\nnot documented"| LOWCONF["Pattern missing\nClaude attempts from\ngeneral knowledge\n+ emits LOW RELEVANCE warning"]

    HIGHCONF --> BUILD["Build Python code\nfrom pattern + context"]
    LOWCONF --> BUILD

    BUILD -->|"execute_python(code)"| MCP["MCP Tool Call\nflame_mcp_server.py"]

    MCP -->|"TCP · port 4444"| BRIDGE["flame_mcp_bridge.py\n(Flame Python hook)"]

    BRIDGE --> EXEC["Flame Python\ninterpreter\nexecutes code"]

    EXEC --> RESULT{{"Execution\nresult ?"}}

    RESULT -->|"✅ SUCCESS"| WASLOW{{"Was relevance\n< 60% ?"}}
    RESULT -->|"❌ ERROR\nexception / wrong output"| RETRY["Claude reads traceback\nmodifies code\nretries execute_python"]
    RETRY -->|"max 3 attempts"| EXEC

    WASLOW -->|"YES — new pattern"| LEARN["learn_pattern(\n  description, code\n)"]
    WASLOW -->|"NO — already known"| STATS

    LEARN --> APPEND["Append to\nFLAME_API.md"]
    APPEND --> REBUILD["Rebuild RAG index\n(background subprocess)"]
    REBUILD -->|"🧠 self-improved!"| STATS

    STATS["📊 Stats footer\nRAG tokens used · tokens saved\nsession totals"]

    STATS --> ANSWER(["💬 Answer returned\nto user"])

    subgraph DOCS ["📚 Knowledge Base (docs/)"]
        direction LR
        D1["FLAME_API.md\n116 chunks\nCore API + learned patterns"]
        D2["flame_advanced_api.md\n74 chunks\nAction · Color Mgmt · Conform"]
        D3["flame_api_full.md\n71 chunks\nSequences · Projects · Archive"]
        D4["flame_segment_timeline_api.md\n61 chunks\nPySegment · PyBatch · Timeline"]
        D5["flame_community_workflows.md\n23 chunks\nLogik Forum jargon → API"]
        D6["flame_cookbook_official.md\n22 chunks\nOfficial Autodesk code samples"]
        D7["flame_vocabulary.md\n8 chunks\nOperator terminology glossary"]
    end

    DOCS -.->|"indexed at build time"| CHROMA
    APPEND -.->|"extends"| D1

    style USER fill:#2d3748,color:#e2e8f0,stroke:#4a5568
    style ANSWER fill:#2d3748,color:#e2e8f0,stroke:#4a5568
    style SCORE fill:#744210,color:#fefcbf,stroke:#d69e2e
    style RESULT fill:#744210,color:#fefcbf,stroke:#d69e2e
    style WASLOW fill:#744210,color:#fefcbf,stroke:#d69e2e
    style HIGHCONF fill:#1a365d,color:#bee3f8,stroke:#2b6cb0
    style LOWCONF fill:#742a2a,color:#fed7d7,stroke:#c53030
    style LEARN fill:#1c4532,color:#c6f6d5,stroke:#276749
    style REBUILD fill:#1c4532,color:#c6f6d5,stroke:#276749
    style APPEND fill:#1c4532,color:#c6f6d5,stroke:#276749
    style RETRY fill:#742a2a,color:#fed7d7,stroke:#c53030
    style EXEC fill:#44337a,color:#e9d8fd,stroke:#6b46c1
    style BRIDGE fill:#44337a,color:#e9d8fd,stroke:#6b46c1
    style CHROMA fill:#3d2a00,color:#fbd38d,stroke:#c05621
    style D1 fill:#1a365d,color:#bee3f8,stroke:#2b6cb0
```

---

## Self-improving loop

Every successful `execute_python` call where RAG scored < 60% triggers `learn_pattern()`:

1. Working code is appended as a structured block in `FLAME_API.md`
2. The ChromaDB index is rebuilt in a background subprocess (~8 s)
3. Next session the same query returns > 70% relevance — no retries, no guessing

---

## Knowledge base — 375 chunks across 7 source docs

| File | Chunks | Content |
|---|---|---|
| `FLAME_API.md` | 116 | Core API + self-learned patterns (auto-extended by `learn_pattern`) |
| `docs/flame_advanced_api.md` | 74 | Action, Color Management, Exporter, Conform/AAF, Timeline FX/BFX |
| `docs/flame_api_full.md` | 71 | PySequence, PyTrack, PyVersion, PyMarker, PyProject, PyWorkspace |
| `docs/flame_segment_timeline_api.md` | 61 | PySegment, PyClip.render(), PyBatch.create_batch_group() |
| `docs/flame_community_workflows.md` | 23 | Logik Forum jargon → API mapping |
| `docs/flame_cookbook_official.md` | 22 | Official Autodesk Python code samples |
| `docs/flame_vocabulary.md` | 8 | Operator terminology glossary |

> Token economics: RAG injects ~600 tokens per query vs ~38,000 for the full doc. Typical session saving: **80–85%**.
