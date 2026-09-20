# Diagrams (Mermaid)

Single source of truth for the diagrams in this repo. `PLAN.md` and
`README.md` link here.

## Stack architecture

```mermaid
flowchart LR
  OP[Agent Harness]
  TG[In-scope target]

  subgraph JCYBER[Jcyber MCP Server]
    SCOPE[Scope Gate<br/>deterministic pre-hook]
    NORM[Normalizer<br/>raw to vault, E-###]
    LEARN[Distiller<br/>to long-term memory]
  end

  HX[("HexStrike<br/>150+ tools<br/>REST 127.0.0.1:8888")]
  CD[("Caido<br/>proxy 127.0.0.1:8889<br/>HTTPQL, Autorize, Scanner")]
  MG[("Memgraph<br/>engagement graph")]
  TD[("TencentDB Memory<br/>cross-engagement recall")]

  OP -->|MCP tool call| SCOPE
  SCOPE -->|gated call, closed-set params| HX
  HX -->|target-touching traffic| CD
  CD <-->|MITM: log, passive plugins| TG
  HX -.->|passive tools: subfinder, unproxied| TG
  HX -->|raw tool output| NORM
  CD -->|plugin findings| NORM
  NORM --> MG
  MG -->|state, evidence, findings| OP
  TD -->|priors| OP
  LEARN -->|committed atoms| TD
  MG -->|reports| OP

  classDef infra fill:#f4f4f4,stroke:#999,stroke-dasharray:4 3,color:#111
  class HX,CD,TG infra
```

## Tool call flow (one MCP tool invocation)

```mermaid
flowchart TD
  A[Agent calls MCP tool] --> B{Scope gate}
  B -->|in scope| C{Exploit tool?}
  B -->|out of scope| REJECT[Return error: BLOCKED]
  C -->|yes| CONFIRM[Return: CONFIRMATION_REQUIRED]
  C -->|no| D{Fuzzing + protected path?}
  D -->|yes| REJECT2[Return error: no_fuzzing_on]
  D -->|no| E[Call HexStrike REST]
  E --> F[Normalize output]
  F --> G[sha256 dedup check]
  G -->|new| H[Insert E-### into Memgraph]
  G -->|duplicate| I[Skip insert]
  H --> J[Return evidence summary to agent]
  I --> J

  classDef gate fill:#fee,stroke:#c00,color:#111
  class B,C,D gate
```

## Service usage (per tool call)

How each system is used when the agent calls an MCP tool:

```mermaid
sequenceDiagram
    participant A as Agent
    participant M as MCP Server
    participant S as Scope Gate
    participant H as HexStrike
    participant C as Caido
    participant G as Memgraph

    A->>M: call tool (target, params)
    M->>S: check scope(target)
    alt out of scope
        S-->>M: BLOCKED
        M-->>A: error
    else in scope
        S-->>M: pass
        M->>H: POST /api/tools/{slug}
        H->>C: proxied request
        C->>C: log + passive check
        H-->>M: raw output
        M->>M: normalize (sha256, summary)
        M->>G: INSERT Evidence
        M-->>A: evidence summary
    end
```
