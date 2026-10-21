# Opsboard RAG Retrieval Quality Evaluation Report

**Generated:** 2026-10-21T03:02:42.855395+00:00  
**Evaluation Harness:** Golden Operational Benchmark  
**Dataset Size:** 4 queries across 6 challenge categories  

## Summary Metrics

| Metric | Target | Result | Status |
|---|---|---|---|
| **Recall@5** | ≥ 0.80 | **100.00%** | PASSED |
| **Recall@1** | ≥ 0.50 | **100.00%** | PASSED |
| **Mean Reciprocal Rank (MRR)** | ≥ 0.60 | **1.0000** | PASSED |
| **Average Retrieval Latency** | < 100 ms | **94.33 ms** | PASSED |

## Detailed Query Benchmark

| Question | Expected | Top 3 Retrieved | Hits@5 | Latency |
|---|---|---|---|---|
| What customer was double charged on checkout during the card processing spike? | `PAY-101` | PAY-101 | Pass | 115.32 ms |
| What enterprise customer requested a $15,000 refund due to downtime SLA credit? | `PAY-102` | PAY-102 | Pass | 84.78 ms |
| Why did Redis connection pool exhaustion occur during nightly batch export? | `ENG-201` | ENG-201 | Pass | 82.0 ms |
| Which customer reported webhook signature validation mismatch on callback payload? | `PAY-103` | PAY-103, PAY-101 | Pass | 95.21 ms |

## Evaluation Notes
- Vector embeddings computed offline via `FakeEmbeddingProvider` (deterministic 384-dimensional term hashing) with zero external network reliance.
- Pre-filtering strictly enforced at query-time via `team_id` constraint before ranking.
- Target Recall@5 threshold satisfied (≥ 0.80).
