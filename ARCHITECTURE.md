# Architecture

The same system at increasing zoom (the **C4 model**): start at the map, descend
into detail only when needed. Each box shows its name on the first line and its
contents below. Colour carries meaning (see legend). The deepest level (code) is
generated automatically by Graphify (god nodes, call-flow) — not redrawn here.

> **Colour legend** — blue = my code (servers / tools / logic) · amber = safety & validation ·
> purple = knowledge / RAG · green = connectivity / bridge · teal = state / journal ·
> yellow = governance / concept registry · tan = external systems & apps · grey = actors.

## Level 1 — System Context (the map)

```mermaid
flowchart TB
  classDef actor fill:#eceff1,stroke:#78909c,color:#37474f;
  classDef system fill:#e3f2fd,stroke:#1976d2,color:#0d47a1;
  classDef govern fill:#fff8e1,stroke:#f9a825,color:#f57f17;
  classDef entry fill:#e3f2fd,stroke:#1976d2,color:#0d47a1;
  classDef safety fill:#fff3e0,stroke:#ef6c00,color:#e65100;
  classDef knowledge fill:#f3e5f5,stroke:#8e24aa,color:#6a1b9a;
  classDef state fill:#e0f2f1,stroke:#00897b,color:#00695c;
  classDef conn fill:#e8f5e9,stroke:#43a047,color:#2e7d32;
  classDef external fill:#efebe9,stroke:#a1887f,color:#4e342e;

  user(["Human operator<br/>manual control / decisions"])
  claude(["Claude<br/>drives the servers via MCP"])
  system["MCP VFX Automation<br/>fpt-mcp<br/>maya-mcp<br/>flame-mcp"]
  fpt_sys[("Flow Production Tracking<br/>cloud · production tracking")]
  maya["Autodesk Maya 2027<br/>local DCC app"]
  flame["Autodesk Flame 2027<br/>local DCC app"]
  gpu["LAN GPU host<br/>Linux · Ollama / vision3d"]

  user --> claude
  claude --> system
  system -->|Flow Production Tracking API| fpt_sys
  system -->|Command Port TCP| maya
  system -->|bridge socket| flame
  system -.->|optional local LLM| gpu

  class user,claude actor;
  class system system;
  class fpt_sys,maya,flame,gpu external;
```

## Level 2 — Containers (the three servers)

```mermaid
flowchart TB
  classDef actor fill:#eceff1,stroke:#78909c,color:#37474f;
  classDef system fill:#e3f2fd,stroke:#1976d2,color:#0d47a1;
  classDef govern fill:#fff8e1,stroke:#f9a825,color:#f57f17;
  classDef entry fill:#e3f2fd,stroke:#1976d2,color:#0d47a1;
  classDef safety fill:#fff3e0,stroke:#ef6c00,color:#e65100;
  classDef knowledge fill:#f3e5f5,stroke:#8e24aa,color:#6a1b9a;
  classDef state fill:#e0f2f1,stroke:#00897b,color:#00695c;
  classDef conn fill:#e8f5e9,stroke:#43a047,color:#2e7d32;
  classDef external fill:#efebe9,stroke:#a1887f,color:#4e342e;

  claude(["Claude<br/>MCP client"])

  subgraph eco["MCP VFX Automation"]
    direction TB
    fpt["fpt-mcp<br/>Flow Production Tracking + Toolkit client"]
    maya["maya-mcp<br/>Maya automation"]
    flame["flame-mcp<br/>Flame automation"]
    registry["Concept registry<br/>.concepts.yml<br/>verify_concepts<br/>byte-identical across repos"]
  end

  fpt_sys[("Flow Production Tracking")]
  mayaApp["Maya 2027"]
  flameApp["Flame 2027"]
  gpu["LAN GPU host"]

  claude -->|MCP| fpt
  claude -->|MCP| maya
  claude -->|MCP| flame
  fpt -->|shotgun_api3| fpt_sys
  maya -->|Command Port localhost:8100| mayaApp
  flame -->|Unix socket bridge| flameApp
  fpt -.->|local LLM| gpu
  flame -.->|local LLM| gpu
  registry -.->|guards drift in| fpt
  registry -.-> maya
  registry -.-> flame

  class claude actor;
  class fpt,maya,flame system;
  class registry govern;
  class fpt_sys,mayaApp,flameApp,gpu external;
```

## Level 3 — Components (flame-mcp)

```mermaid
flowchart TB
  classDef actor fill:#eceff1,stroke:#78909c,color:#37474f;
  classDef system fill:#e3f2fd,stroke:#1976d2,color:#0d47a1;
  classDef govern fill:#fff8e1,stroke:#f9a825,color:#f57f17;
  classDef entry fill:#e3f2fd,stroke:#1976d2,color:#0d47a1;
  classDef safety fill:#fff3e0,stroke:#ef6c00,color:#e65100;
  classDef knowledge fill:#f3e5f5,stroke:#8e24aa,color:#6a1b9a;
  classDef state fill:#e0f2f1,stroke:#00897b,color:#00695c;
  classDef conn fill:#e8f5e9,stroke:#43a047,color:#2e7d32;
  classDef external fill:#efebe9,stroke:#a1887f,color:#4e342e;

  claude(["Claude"])

  subgraph s["flame-mcp"]
    direction TB
    tools["Tool layer — 38 tools<br/>list / create<br/>render / export<br/>timeline"]
    plan["execute_plan / execute_python<br/>closed-schema plan<br/>raw escape hatch"]
    safety["Safety and validation<br/>F4b AST validator<br/>dry-run<br/>delete gating"]
    rag["RAG engine<br/>FLAME_API.md corpus + index"]
    journal["Operation journal + undo<br/>idle-event-safe<br/>structural deletes"]
    bridgec["Bridge client<br/>Unix socket<br/>off the event loop"]
  end

  hook["Bridge hook<br/>runs inside Flame"]
  flameApp["Flame 2027<br/>Python API"]

  claude -->|MCP| tools
  tools --> plan
  plan --> safety
  safety --> bridgec
  tools -.->|how do I…| rag
  tools -.->|record op| journal
  bridgec --> hook
  hook --> flameApp

  class claude actor;
  class tools,plan entry;
  class safety safety;
  class rag knowledge;
  class journal state;
  class bridgec,hook conn;
  class flameApp external;
```

For component-internal detail see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md);
for function-level code use the Graphify graph of `src/`.

## Level 4 — Code (deepest zoom)

Below components is the actual code (functions, classes, call paths). It is
generated on demand by **Graphify** (god nodes, call-flow, interactive graph) —
run it over `src/` rather than maintaining it by hand.

*C4 levels: 1 Context → 2 Containers → 3 Components → 4 Code. Top-down for
understanding; Graphify owns the bottom.*
