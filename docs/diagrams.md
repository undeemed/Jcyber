# Diagrams (Mermaid)

Single source of truth for the diagrams in this repo. `PLAN.md` §3 and
`README.md` link here — when the architecture changes, edit the diagram
here only.

## Stack architecture

```mermaid
flowchart LR
  OP[Operator / driving agent]
  TG[In-scope target]

  subgraph JCYBER[Jcyber stack]
    DEC[Jev system_one<br/>atomic question fan-out]
    GATE[Router<br/>deterministic scope + confidence gates]
    NORM[Normalizer<br/>raw to vault, E-###, embed]
    LEARN[Distiller<br/>to outbox queue]

    HX[("HexStrike MCP<br/>150+ tools<br/>REST 127.0.0.1:8888")]
    CD[("Caido 0.57.1<br/>proxy 127.0.0.1:8889 (pinned)<br/>HTTPQL, replay, Autorize/Scanner passive")]
    MG[("Memgraph<br/>engagement graph + vector index")]
    TD[("TencentDB Memory<br/>L0-L3, Skills, Wiki")]
  end

  OP -->|target + scope.toon| GATE
  DEC --> GATE
  GATE -->|"gated action: tool, closed-set params, proxy"| HX
  HX -->|all target-touching traffic| CD
  CD <-->|MITM: log, record, passive plugins| TG
  HX -.->|"passive tools: subfinder, crt.sh, unproxied"| TG
  HX -->|raw tool output| NORM
  CD -->|plugin findings + replay/export evidence| NORM
  NORM --> MG
  MG -->|Cypher to text state snapshot| DEC
  MG -->|outbox| LEARN
  DEC <-->|skill pick| TD
  TD -->|priors + L1 atoms| DEC
  LEARN -->|committed atoms + skills| TD
  MG -->|reports, PoCs| OP

  classDef infra fill:#f4f4f4,stroke:#999,stroke-dasharray:4 3,color:#111
  class HX,CD,TG infra
```

Data flows one way except the operator interface. The cylinder nodes
(HexStrike, Caido, Memgraph, TencentDB) are the substrate the loop runs on:
data still flows one way across every edge into `DEC`, and Caido has no edge
toward the gate — one way in with findings, never with opinions.

## Decision gate (one loop iteration)

```mermaid
flowchart TD
  N[Jev: next_action + atomic question fan-out<br/>choice/score/noul with confidences] --> G0D{"Deterministic scope gate<br/>target string-matches scope.toon<br/>in-scope AND not out-of-scope (string only, no model)"}
  G0D -->|"any out-of-scope match wins: block, record, no target contact"| X[:Decision node: rejection<br/>loop continues from recorded state]
  G0D -->|in-scope| G0M{Jev scope_safe noul >= 0.90<br/>catalog G0, scope_model_floor}
  G0M -->|"below floor: queue with reasoning"| Q[Operator queue<br/>:Decision node recorded]
  G0M -->|pass| G1{Class gate: answer confidence vs<br/>catalog G1 auto threshold for the chosen class}
  G1 -->|"auto (threshold met)"| ACT[Execute: HexStrike MCP tool<br/>closed-set params + caido.proxy from config]
  G1 -->|"else: confirm (probing/fuzzing/report/exploit)"| C[Operator confirm<br/>action parked with full audit record]
  G1 -->|"else: queue (recon below floor)"| Q
  ACT --> ENG{route_via_engine? engine.enabled AND yes}
  ENG -->|yes: one BYOK call, evidence-only| EV1[Engine output = :Evidence<br/>tool: engine/&lt;model&gt;; gates unchanged]
  ENG -->|no / disabled: default| NORM[NORMALIZE: raw to vault, sha256, E-###, embed, dedup]
  EV1 --> NORM
  NORM --> V[Apply verdicts: hypothesis support thresholds<br/>report_ready gates render + tdb.commit]
```

Notes:
- The deterministic gate runs on **every** action, before the model layer,
  and cannot be bypassed by any model answer (AGENTS.md invariant #3).
- `route_via_engine` is a Jev question, not a branch the engine controls:
  the engine augments an *already-gated* action and its output feeds the
  same dedup/hypothesis gates as any tool output (`orchestrator/loop.md`
  §3, `config/decision-catalog.md` G1).
- Thresholds shown are from the canonical set in
  `config/decision-catalog.md` (the one place per doc set they may live).

## Service usage (per iteration)

How each system is used in one loop iteration: Memgraph holds the state and the
audit, Jev is the only decision-maker, HexStrike and Caido are the hands and the
wire, TencentDB (memory-core) is the cross-engagement brain, and Prometheus is
doctrine compiled into the schema (not a runtime).

```mermaid
flowchart TB
  OP([Operator / driving agent]) -->|target + scope.toon| INTAKE[Intake: synthesize scope]
  INTAKE --> REC

  subgraph ITER[One loop iteration]
    direction TB
    REC[TencentDB memory-core<br/>RECALL priors + skills] --> OBS[Memgraph<br/>OBSERVE: project state]
    OBS --> DEC[Jev / TypeSafe<br/>DECIDE: one atomic-question call]
    DEC --> GATE{Router<br/>GATE: deterministic scope AND confidence}
    GATE -->|out-of-scope or below floor| AUD[Memgraph :Decision<br/>blocked / parked, no contact]
    GATE -->|auto| ACT[HexStrike<br/>ACT: run the closed-set tool]
    ACT -->|target traffic| CD[Caido<br/>PROXY: log + passive plugins]
    ACT --> NORM[Normalizer<br/>STORE: raw to E-### + sha256]
    CD -->|plugin findings| NORM
    NORM --> MG[Memgraph<br/>evidence, verdicts, :Decision audit]
    MG -->|on close| LRN[TencentDB memory-core<br/>LEARN: commit atoms/skills]
  end

  LRN -.->|next engagement| REC
  MG --> OUT[jcyber report / trace<br/>Markdown + decision audit]
  OUT --> OP

  classDef svc fill:#f4f4f4,stroke:#999,color:#111
  class REC,OBS,DEC,ACT,CD,NORM,MG,AUD,LRN,OUT svc
```