# SEC Filings RAG Copilot

Turn dense SEC filings into **instant, cited answers**. A low-cost, serverless Retrieval-Augmented Generation (RAG) system that ingests 10-K/10-Q PDFs, indexes them, and serves a **public `/chat` API** with grounded citations. Built to showcase **end-to-end product thinking**, **cost discipline**, and a **modern AWS stack**.

---

## Highlights

- **Production-style RAG:** S3 → Step Functions → Lambda → Bedrock Titan Embeddings → OpenSearch (k-NN) → API Gateway → Router Lambda → Bedrock Text (primary + fallback).
- **Grounded answers:** quotes-only format with **explicit citations** like `[AAPL 2023 10-K — Item 1A]`.
- **Cost control:** **DynamoDB TTL cache** for answers (query-hash keyed) to minimize LLM calls; small `k`, modest `max_tokens`, light models.
- **Clean outputs:** router enforces `<final>…</final>` and strips prompt echos/system tokens.

---

## Architecture

> PNG (no Mermaid needed). Put/keep the image at `docs/arch.png`.

<p align="center">
  <img src="docs/arch.png" alt="Architecture diagram: Ingest and Serve paths" width="840">
</p>

**Ingest (batch/offline)**  
S3 (filings) → Step Functions → `extract_clean` Lambda (parse/clean) → `chunk_embed` Lambda (chunk + **Titan Embeddings**) → **OpenSearch** (k-NN index)

**Serve (online)**  
API Gateway (`POST /chat`) → `router` Lambda → **OpenSearch** (retrieve) → **Bedrock Text** (primary + fallback) → **DynamoDB** cache (TTL)

---

## Stack

- **AWS:** S3, Step Functions, Lambda (Python 3.11), API Gateway (HTTP API v2), DynamoDB (TTL), Bedrock (Titan Embeddings + Text provider), OpenSearch (k-NN)
- **Python:** minimal deps; retrieval helpers in `app_code/langgraph_app/`
- **Data:** SEC 10-K/10-Q
- **Eval:** `eval/run_eval.py` (CIM, MQS, KC, latency, stability)

---

## Quickstart (local operator notes)

1) **Configure environment** (never commit real values):
```bash
cp .env.example .env
# edit .env with your endpoints/IDs/region, then:
export $(grep -v '^#' .env | xargs)
```

2) Create OpenSearch index:
```bash
python3 scripts/create_index.py
```

3) Download + ingest a few filings:

```bash
bash scripts/download_sec.sh    # writes to your S3 bucket
# Deploy/attach Step Functions to run extract_clean → chunk_embed for embeddings
```

4) Serve the API (Router Lambda + API Gateway):
- lambdas/router/app.py (uses env vars below)
- API Gateway route POST /chat → Router Lambda
- DynamoDB table (e.g., sec_copilot_cache) with TTL on ttl

5) Smoke test:
```bash
# API_URL should look like: https://<api-id>.execute-api.<region>.amazonaws.com
curl -s -X POST "${API_URL%/}/chat" \
  -H 'Content-Type: application/json' \
  -d '{"query":"Where does Apple discuss supply-chain risk?"}' | jq .
```

---

## Configuration (Lambda env vars)

| Variable | Example | Purpose |
|---|---|---|
| OPENSEARCH_ENDPOINT | search-xxxxx.us-east-2.es.amazonaws.com | OpenSearch domain host (no scheme). |
| OPENSEARCH_INDEX | kb_chunks | Name of the k-NN index. |
| BEDROCK_EMBED_MODEL_ID | amazon.titan-embed-text-v2:0 | Embedding model for chunk vectors. |
| BEDROCK_TEXT_MODEL_ID | anthropic.claude-3-haiku-20240307-v1:0 | Primary text model for answers. |
| BEDROCK_TEXT_MODEL_FALLBACK_ID | meta.llama3-3-70b-instruct-v1:0 | Fallback text model. |
| CACHE_TABLE | sec_copilot_cache | DynamoDB cache table (TTL enabled on "ttl"). |
| AWS_REGION | us-east-2 | Region for Bedrock/OpenSearch/DynamoDB. |

---

## API

**Endpoint:** `POST /chat`  
**Returns:** One-sentence answer + 2-3 quoted bullets with SEC citations.

**Request**
```json
{ "query": "Where does Apple discuss supply-chain risk?" }
```

**Response (example)**
```json
{
  "answer": "Apple discusses supply-chain risk in Item 1A (Risk Factors) and references in Item 8 notes.\n* ... [AAPL 2023 10-K - Item 1A]\n* ... [AAPL 2023 10-K - Item 8]"
}
```

**cURL smoke test**
```bash
# API_URL should look like: https://<api-id>.execute-api.<region>.amazonaws.com
curl -s -X POST "${API_URL%/}/chat"   -H 'Content-Type: application/json'   -d '{"query":"Where does Apple discuss supply-chain risk?"}' | jq .
```

---

## Architecture

![Architecture](docs/arch.png)

Ingest (batch/offline): S3 -> Step Functions -> Lambda (extract + chunk + embed) -> Bedrock Titan Embeddings -> OpenSearch (kNN).  
Serve (real-time): API Gateway -> Lambda router -> OpenSearch retrieve -> Bedrock (primary/fallback) -> DynamoDB cache (TTL).

---

## Evaluation (latest)

Low-cost eval across AAPL/MSFT/AMZN 2023 10-Ks (12 questions total; ~50% repeats leverage cache).

### Overall
| Metric | Value |
|---|---|
| N (questions) | 12 |
| Repeats | 4 |
| CIM@Item (accuracy) | 0.833 |
| MQS@2+ quotes | 0.917 |
| KC@keywords (avg) | 0.931 |
| Latency p50 / p95 (ms) | 2271 / 3106 |
| Stability (avg) | 0.732 |

### Per filing
| Filing | N | CIM | MQS | KC | p50 (ms) |
|---|---|---|---|---|---|
| AAPL 2023 10-K | 4 | 1.00 | 0.75 | 1.000 | 1891 |
| MSFT 2023 10-K | 4 | 0.75 | 1.00 | 0.917 | 2244 |
| AMZN 2023 10-K | 4 | 0.75 | 1.00 | 0.875 | 2693 |

**Reproduce locally**
```bash
# Single-ticker sample (6 questions)
python3 eval/run_eval.py "$API_URL" eval/questions.jsonl --repeat

# Multi-ticker (12 questions, ~50% repeats for cache savings)
python3 eval/run_eval.py "$API_URL" eval/questions_multi.jsonl --repeat --repeat-frac 0.5
```

**Metric definitions**
- CIM (Citation-Item Match): any cited bracket includes the expected Item label (for example, "Item 1A").
- MQS (Minimum Quote Support): answer includes at least 2 quoted bullets.
- KC (Keyword Coverage): fraction of expected keywords present in the answer.
- Stability: token-set similarity between first and repeated answers.

---

## Cost story

- Serverless, pay-per-request architecture.
- DynamoDB cache with TTL cuts repeat LLM calls to near-zero.
- Efficient primary model with fallback only on failure or low confidence.
- OpenSearch dev-sized domain; scale shards/replicas only when required.
- Titan Embeddings v2; chunk size ~500-800 tokens with small overlap.

---

## Security and privacy

- No secrets in repo; use `.env` locally and Lambda environment variables in AWS.
- Repo sanitized (IDs/ARNs redacted). Optional scans with `trufflehog`.
- Data stays within your AWS account (Bedrock, OpenSearch, DynamoDB).

---

## Repository layout

```
app_code/langgraph_app/      # retrieval helpers (search, prompts)
lambdas/
  extract_clean/app.py       # parse & clean filings
  chunk_embed/app.py         # chunk + embeddings -> OpenSearch
  router/app.py              # /chat: retrieval + generation + cache
scripts/
  create_index.py            # OpenSearch index mappings
  download_sec.sh            # sample SEC download
eval/
  run_eval.py                # metrics + summary
docs/
  arch.png                   # architecture diagram
.env.example
README.md
```

---

## Roadmap

- Multi-document ranking and duplicate-quote suppression
- Query parsing improvements (ticker/year inference)
- Streaming responses (SSE) via API Gateway
- Optional auth (API key or Cognito) for demos
- Simple dashboard (latency, cache hit rate, spend)

---

## License

MIT
