# flame-mcp — Architecture & Query Flow

## System architecture

```mermaid
flowchart LR
    subgraph CLI["Clients  ·  MCP stdio"]
        A1["Claude Code"]
        A2["Claude Desktop"]
        A3["Cowork / Chat"]
    end

    subgraph SRV["flame_mcp_server.py"]
        T1["search_flame_docs()"]
        T2["execute_python()"]
        T3["learn_pattern()"]
    end

    subgraph RAG["RAG Engine  ·  rag/"]
        R1["BGE encoder"]
        R2[("ChromaDB<br/>375 chunks")]
    end

    subgraph KB["Knowledge Base  ·  7 docs"]
        K1(["FLAME_API.md · 116 ch"])
        K2["advanced_api · 74 ch"]
        K3["api_full · 71 ch"]
        K4["segment_api · 61 ch"]
        K5["community · 23 ch"]
        K6["cookbook · 22 ch"]
        K7["vocabulary · 8 ch"]
    end

    subgraph FLM["Autodesk Flame  ·  macOS"]
        B1["TCP Bridge :4444"]
        B2["flame module"]
    end

    CLI  -->|"stdio"| SRV
    T1   --> R1
    R1  <--> R2
    R2   --> K1 & K2 & K3 & K4 & K5 & K6 & K7
    T2   -->|"TCP 4444"| B1
    B1   --> B2
    T3  -.->|"append"| K1
    T3  -.->|"rebuild"| R2

    style K1 fill:#052e16,color:#6ee7b7,stroke:#10b981
    style T3 fill:#052e16,color:#6ee7b7,stroke:#10b981
    style R2 fill:#1e1b4b,color:#c4b5fd,stroke:#7c3aed
    style R1 fill:#1e1b4b,color:#c4b5fd,stroke:#7c3aed
    style T2 fill:#1e1b4b,color:#c4b5fd,stroke:#7c3aed
    style T1 fill:#451a03,color:#fcd34d,stroke:#f59e0b
    style B1 fill:#450a0a,color:#fca5a5,stroke:#ef4444
    style B2 fill:#450a0a,color:#fca5a5,stroke:#ef4444
```

| Block | File | Role |
|---|---|---|
| **Claude** | — | Understands the request, calls MCP tools, generates Python code |
| **MCP Server** | `flame_mcp_server.py` | Exposes tools (`execute_python`, `search_flame_docs`, `learn_pattern`), routes RAG queries |
| **BGE encoder** | `rag/` | BAAI/bge-small-en-v1.5 · converts query to vector for similarity search |
| **ChromaDB** | `rag/chroma_db/` | Vector store · 375 chunks indexed across 7 source docs |
| **FLAME_API.md** | `FLAME_API.md` | Cheatsheet · self-extended by `learn_pattern()` after every successful undocumented call |
| **TCP Bridge** | `hooks/flame_mcp_bridge.py` | Flame Python hook · TCP server on port 4444 · executes code inside Flame's interpreter |

---

## Query flow & decision tree

```mermaid
flowchart TD
    A(["User request"])
    B["search_flame_docs()"]
    C{"score ≥ 60%?"}
    D["Pattern found"]
    E["Pattern missing ⚠"]
    F["execute_python(code)"]
    G{"Execution OK?"}
    H["learn_pattern()<br/>rebuild index 🧠"]
    I["Retry · max 3x"]
    J(["Answer + stats to user"])

    A --> B
    B --> C
    C -->|YES| D
    C -->|NO| E
    D --> F
    E --> F
    F --> G
    G -->|YES, low score| H
    G -->|YES, known| J
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
