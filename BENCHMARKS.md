# Benchmarks

Retrieval quality and reranker latency numbers, produced by the [eval harness](README.md#reranker-configuration) (`clawdiney-eval`). Reproduce with:

```bash
./venv/bin/clawdiney-eval --all-modes
```

## Retrieval quality by mode

Fixture vault (`tests/eval/fixture_vault/`, 8 synthetic notes — exact-term, semantic-paraphrase, and negative-control queries), 8 golden queries, k=5. Current numbers, also stored in `tests/eval/baseline.json` and checked by `./scripts/run_tests.sh`:

| Mode | recall@5 | MRR | hit_rate |
|---|---|---|---|
| Hybrid (BM25 + vector) + rerank | 1.000 | 1.000 | 1.000 |
| Hybrid (BM25 + vector), no rerank | 1.000 | 1.000 | 1.000 |
| BM25-only | 1.000 | 1.000 | 1.000 |
| Vector-only | 1.000 | 1.000 | 1.000 |

**Honest caveat**: every mode scores perfectly on this fixture. With only 8 notes covering clearly distinct topics, k=5 retrieval is easy for any single retriever — this fixture proves the harness itself works correctly (component isolation, regression gate, baseline comparison) and that nothing is *broken*, but it does not yet demonstrate hybrid's or rerank's marginal contribution over a single retriever. That requires a larger, harder golden set (near-duplicate topics, distractors sharing vocabulary with the correct answer) — tracked as an open item, not fabricated here.

## Reranker model comparison

Same fixture and golden set, `--mode hybrid --rerank`, CPU fallback (no GPU headroom in the measurement environment — expect a larger absolute gap, not necessarily the same ratio, on GPU):

| Model | Params | Wall time (8 queries, warm) | recall@5 / MRR / hit_rate |
|---|---|---|---|
| `BAAI/bge-reranker-v2-m3` (default) | ~568M | ~80s (~10s/query) | 1.00 / 1.00 / 1.00 |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | ~22M | ~30s (~4s/query) | 1.00 / 1.00 / 1.00 |
| rerank disabled (`ENABLE_RERANK=false`) | — | fastest (RRF order only) | 1.00 / 1.00 / 1.00 |

Swap the model via `RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2` (see `.env.example`). As with the retrieval-mode table above, identical scores here reflect the fixture's difficulty ceiling, not proof that the smaller model preserves precision on a larger vault — re-run the harness against your own vault (or an expanded golden set) before adopting a non-default `RERANK_MODEL` as your default.

## Why embedded SQLite instead of a service stack

Peers in the AI-memory space (mem0, Zep/Graphiti, Letta/MemGPT) typically run a vector DB + graph DB + cache as separate services. Clawdiney holds vectors (`sqlite-vec`), full-text (FTS5), and the knowledge graph (relational tables) in one `brain.db` file:

| | Clawdiney | Typical peer stack |
|---|---|---|
| Infrastructure | 1 file (`brain.db`) | Vector DB + graph DB (e.g. Neo4j) + cache (e.g. Redis) |
| Setup | `pip install`, point `BRAIN_DB_PATH` | Provision + configure 2-3 services |
| Deploy | Copy a file | Orchestrate a stack (Docker Compose / k8s) |
| Backup | Copy a file | Backup each service independently |
| Query latency floor | No network hop between vector/graph/cache | Cross-service round trips |

This is a deliberate trade-off, not a free lunch: embedded SQLite means single-writer-at-a-time semantics and no built-in horizontal scaling — fine for a single-user or small-team coding-agent memory layer (this project's actual use case), not a substitute for a multi-tenant SaaS backend.
