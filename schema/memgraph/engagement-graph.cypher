// Jcyber engagement graph — Memgraph (Cypher)
// Doctrine sources: Prometheus ID model (H/E/F/VF/AC) + evidence discipline.
// Tenancy: single open-core instance; every node carries `engagement_id` (D3).
// Apply per fresh engagement: set $eid, then run nodes + indexes + seed.

// ── Parameters ────────────────────────────────────────────────────────────
// SET $eid = 'acme-lab';   -- engagement slug
// Use a parameter or replace with a literal for each engagement.

// ── Node labels ───────────────────────────────────────────────────────────
// Engagement   {id, target, program, status, created_at, closed_at}
// Scope        {engagement_id, id, kind, value, in_scope, source, note}
//              kind: host|prefix|path|ip_range|other
// Asset        {engagement_id, id, host, ip, port?, service?, version?, state}
// Endpoint     {engagement_id, id, url, method?, params, tech, last_status, state}
// Technology   {engagement_id, id, name, category, version?}
// Hypothesis   {engagement_id, id,      // 'H-###', sequential per engagement
//               text, status,           // open|promoted|retired|validated
//               support,                 // last Jev noul (0-1)
//               created_by,              // decision id that raised it
//               created_at}
// Evidence     {engagement_id, id,      // 'E-###'
//               tool, target, ts,
//               summary,                // <= 1 sentence, text-only (Jev state)
//               sha256, raw_path,       // vault, immutable
//               vector: FLOAT[] }       // embedding of summary+target
// Finding      {engagement_id, id,      // 'F-###' provisional, 'VF-###' validated
//               title, vuln_class,
//               severity,               // last Jev score (0-4)
//               bounty,                 // last Jev score (0-3)
//               status,                 // provisional|validated|reported|rejected
//               justification}
// AttackChain  {engagement_id, id,      // 'AC-###'
//               title, entry?, impact,
//               status,                 // theoretical|demonstrated
//               evidence_ids}
// ToolRun      {engagement_id, id, tool, params_json, exit,
//               started_at, duration_ms, rate_profile}
// Decision     {engagement_id, id,      // audit log, immutable
//               ts, phase, state_hash,
//               questions_json,         // catalog question ids asked
//               answers_json,           // typed answers + confidences
//               gate,                   // scope_det: pass|fail, scope_model: 0-1,
//                                       // confidence: class+value, outcome
//               outcome,                // auto|confirm_parked|blocked|halted
//               action?, tool?}

// ── Relationships ─────────────────────────────────────────────────────────
// (Engagement)-[:HAS_SCOPE]->(Scope)
// (Asset)-[:HAS_ENDPOINT]->(Endpoint)
// (Asset)-[:RUNS]->(Technology)
// (Endpoint)-[:REVEALED_BY]->(Evidence)
// (Hypothesis)-[:SUPPORTED_BY]->(Evidence)
// (Hypothesis)-[:DERIVES]->(Finding)          // H-### -> F-###
// (Finding)-[:SUPPORTED_BY]->(Evidence)
// (Finding)-[:AFFECTS]->(Endpoint|Asset)
// (AttackChain)-[:STEP 1..n]->(Finding|Hypothesis)   // ordered: :STEP {n}
// (ToolRun)-[:PRODUCES]->(Evidence)
// (Decision)-[:EXECUTED]->(ToolRun)
// (Decision)-[:VALIDATED]->(Hypothesis)        // the verdict it applied
// (Evidence)-[:DUP_OF]->(Evidence)

// ── Invariants (checked by a post-write assertion query, not trust) ───────
// 1. :Finding{status:validated} MUST have >=1 :SUPPORTED_BY to :Evidence.
// 2. :Finding{id starting 'VF'} MUST have a PoC raw_path recorded (in
//    justification or Finding.poc_path) — enforced by report_ready gate.
// 3. :Hypothesis ids are monotonically increasing per engagement; same for
//    E/F/VF/AC. (Enforced by the orchestrator; queryable for audit.)
// 4. Every :ToolRun has a parent :Decision. (No unexplained actions.)
// 5. :Scope{in_scope:false} nodes are never targets of any action; the
//    deterministic gate reads them directly.

// ── Invariant checks (run via `ycb doctor <eid>`) ─────────────────────────
// MATCH (f:Finding{engagement_id:$eid, status:'validated'})
// WHERE NOT (f)-[:SUPPORTED_BY]->(:Evidence)
// RETURN f.id;                                     // expect: empty

// MATCH (t:ToolRun{engagement_id:$eid})
// WHERE NOT (t)<-[:EXECUTED]-(:Decision)
// RETURN t.id;                                     // expect: empty

// ── Indexes ───────────────────────────────────────────────────────────────
// Point indexes — engagement-scoped lookups.
// Syntax per memgraph.com/docs/fundamentals/indexes: `CREATE INDEX ON
// :Label(props)` — Memgraph indexes are unnamed (`SHOW INDEX INFO` to
// inspect, `DROP INDEX ON :Label(props)` to remove). Composite indexes are
// supported; leftmost-prefix rule applies, so (engagement_id, id) serves
// both by-id and by-engagement lookups. Bootstrap runs once per fresh
// graph container; for re-runs on a warm container use `schema.assert()`.
CREATE INDEX ON :Scope(engagement_id, id);
CREATE INDEX ON :Asset(engagement_id, host);
CREATE INDEX ON :Endpoint(engagement_id, url);
CREATE INDEX ON :Hypothesis(engagement_id, id);
CREATE INDEX ON :Evidence(engagement_id, id);
CREATE INDEX ON :Finding(engagement_id, id);
CREATE INDEX ON :AttackChain(engagement_id, id);
CREATE INDEX ON :Decision(engagement_id, id);
// Dedup: vector similarity over evidence summaries.
// Syntax verified against memgraph.com/docs/querying/vector-search:
// `dimension` + `capacity` are mandatory; metric default is l2sq.
// dimension 768 tracks the embedder choice (D5) — adjust together.
CREATE VECTOR INDEX evid_vec ON :Evidence(vector)
WITH CONFIG {"dimension": 768, "capacity": 1024, "metric": "cos"};
// (No `IF NOT EXISTS` for vector indexes in current docs; bootstrap runs this
// once per fresh graph container. `SHOW VECTOR INDEX INFO` to inspect.)

// Text search over evidence for operator greps
// (Tantivy-backed; query via text_search.search — property names get a data. prefix)
CREATE TEXT INDEX evid_ft ON :Evidence(summary, target, tool);
// CALL text_search.search("evid_ft", "data.tool:sqlmap data.summary:union") YIELD node, score RETURN node.id;

// ── The state projector (Cypher) ──────────────────────────────────────────
// This exact query feeds the Jev `state` object. Keep it cheap: bounded,
// no raw payloads, ids + summaries only.
//
// MATCH (eng:Engagement {id: $eid})
// WHERE eng.status = 'active'
// OPTIONAL MATCH (eng)-[:HAS_SCOPE]->(sc:Scope)
// OPTIONAL MATCH (a:Asset {engagement_id:$eid})<-[:AFFECTS|HAS_ENDPOINT]-(x)
// OPTIONAL MATCH (h:Hypothesis {engagement_id:$eid, status:'open'})
// OPTIONAL MATCH (f:Finding {engagement_id:$eid, status:'provisional'})
// OPTIONAL MATCH (e:Evidence {engagement_id:$eid})
// WHERE e.ts > (currentTimestamp()*1000 - $window_ms)
// RETURN ...

// (Implemented in the orchestrator with bounded limits, e.g. top 10 by ts.)