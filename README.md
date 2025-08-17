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
Create OpenSearch index:

bash
Copy
Edit
python3 scripts/create_index.py
Download + ingest a few filings:

bash
Copy
Edit
bash scripts/download_sec.sh    # writes to your S3 bucket
# Deploy/attach Step Functions to run extract_clean → chunk_embed for embeddings
Serve the API (Router Lambda + API Gateway):

lambdas/router/app.py (uses env vars below)

API Gateway route POST /chat → Router Lambda

DynamoDB table (e.g., sec_copilot_cache) with TTL on ttl

Smoke test:

bash
Copy
Edit
# API_URL should look like: https://<api-id>.execute-api.<region>.amazonaws.com
curl -s -X POST "${API_URL%/}/chat" \
  -H 'Content-Type: application/json' \
  -d '{"query":"Where does Apple discuss supply-chain risk?"}' | jq .
Configuration (Lambda env vars)
VariablePurpose
OPENSEARCH_ENDPOINTOpenSearch domain (no https://)
OPENSEARCH_INDEXe.g., kb_chunks
BEDROCK_EMBED_MODEL_IDe.g., amazon.titan-embed-text-v2:0
BEDROCK_TEXT_MODEL_IDprimary (e.g., anthropic.claude-3-haiku-20240307-v1:0 or meta.llama3-3-70b-instruct-v1:0)
BEDROCK_TEXT_MODEL_FALLBACK_IDfallback model id
CACHE_TABLEDynamoDB cache table (TTL enabled on ttl)
AWS_REGIONe.g., us-east-2

API
Endpoint: POST /chat
Request:

json
Copy
Edit
{ "query": "Where does Apple discuss supply-chain risk?" }
Response (example):

json
Copy
Edit
{
  "answer": "Apple discusses supply-chain risk in Item 1A (“Risk Factors”) and references in Item 8 notes.\n* ... [AAPL 2023 10-K — Item 1A]\n* ... [AAPL 2023 10-K — Item 8]"
}
Behavior: one-sentence answer + 2–3 quoted bullets with citations. If unsupported, the API suggests likely sections (Item 1A, 7, or 8).

Evaluation (latest)
Low-cost eval across AAPL/MSFT/AMZN 2023 10-Ks (12 Qs total, ~50% repeats leveraging cache).

Overall

CIM@Item (accuracy): 0.833

MQS@2+quotes: 0.917

KC@keywords(avg): 0.931

Latency p50 / p95: 2271 ms / 3106 ms

Stability (avg): 0.732

Repeats: 4 (cache reduces LLM spend)

Per filing

AAPL 2023 10-K — N=4 • CIM=1.00 • MQS=0.75 • KC=1.00 • p50=1891 ms

MSFT 2023 10-K — N=4 • CIM=0.75 • MQS=1.00 • KC=0.917 • p50=2244 ms

AMZN 2023 10-K — N=4 • CIM=0.75 • MQS=1.00 • KC=0.875 • p50=2693 ms

Reproduce:

bash
Copy
Edit
# single-ticker sample
python3 eval/run_eval.py "$API_URL" eval/questions.jsonl --repeat
# multi-ticker (12 Qs + ~50% repeats)
python3 eval/run_eval.py "$API_URL" eval/questions_multi.jsonl --repeat --repeat-frac 0.5
Cost story (practical)
Serverless & pay-per-request; no idle compute.

Largest driver is text generation → pick small models + modest max_tokens.

DynamoDB TTL cache avoids repeated LLM calls (esp. evals & common queries).

Titan Embeddings v2 are inexpensive; chunk ~500–800 tokens with overlap.

Start with a small OpenSearch dev domain; scale shards/replicas later.

Security & privacy
No secrets in Git: use .env locally, Lambda env vars in AWS.

IDs/ARNs sanitized for public repo; optional scanning with trufflehog.

Data stays in your AWS account (Bedrock/OpenSearch/DynamoDB).

Repo layout
bash
Copy
Edit
app_code/langgraph_app/      # retrieval helpers (search, prompts)
lambdas/
  extract_clean/app.py       # parse & clean filings
  chunk_embed/app.py         # chunk + Titan embeddings → OpenSearch
  router/app.py              # /chat: retrieval + generation + cache
scripts/
  create_index.py            # OpenSearch index (vector mappings)
  download_sec.sh            # sample fetch of 10-Ks from SEC
eval/
  run_eval.py                # CIM/MQS/KC/latency/stability metrics
docs/
  arch.png                   # architecture PNG
.env.example
README.md
Roadmap
Multi-doc ranking + deduped quotes

Smarter query parsing (ticker/year inference & keyword boosts)

Streaming responses (SSE) via API Gateway

Optional auth (API key or Cognito) for demos

Simple dashboard (latency, cache hit-rate, spend)

License
MIT
