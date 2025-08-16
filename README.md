# SEC Filings RAG Copilot (serverless, low-cost)

A production-style Retrieval-Augmented Generation (RAG) system that ingests 10-K/10-Q filings and answers questions with citations.

**Stack**: AWS S3, Step Functions, Lambda, Bedrock Titan Embeddings, OpenSearch, DynamoDB TTL Cache, API Gateway

**Architecture:**
```mermaid
flowchart LR
  subgraph Ingest
    S3[S3 bucket: filings] --> SF[Step Functions]
    SF --> L1[Lambda: chunk+embed]
    L1 --> BR[Bedrock Titan Embeddings]
    L1 --> OS[(OpenSearch kNN index)]
  end

  subgraph Serve
    API[API Gateway /chat] --> L3[Lambda: chat-router]
    L3 --> BR2[Bedrock Text (primary/fallback)]
    L3 --> OS
    L3 --> DDBC[(DynamoDB cache, TTL)]
  end

Features:

Low-cost, serverless RAG on AWS

DynamoDB cache to reduce LLM calls

Public API Gateway endpoint

Easily extensible to other document sets

Deployment
See DEPLOY.md for AWS setup instructions.




## Evaluation Results (2025-08-16)

| Metric | Value |
|---|---|
| Questions (N) | 12 |
| CIM@Item (accuracy) | 0.833 |
| MQS@2+quotes | 0.917 |
| KC@keywords(avg) | 0.931 |
| Latency p50 (ms) | 2271 |
| Latency p95 (ms) | 3106 |
| Stability avg | 0.732 |

#### By Filing/Ticker

| Filing | N | CIM | MQS | KC | p50 (ms) |
|---|---:|---:|---:|---:|---:|
| AAPL 2023 10-K | 4 | 1.0 | 0.75 | 1.0 | 1891 |
| MSFT 2023 10-K | 4 | 0.75 | 1.0 | 0.917 | 2244 |
| AMZN 2023 10-K | 4 | 0.75 | 1.0 | 0.875 | 2693 |



