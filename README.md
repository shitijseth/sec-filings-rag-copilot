# SEC Filings RAG Copilot (serverless, low-cost)

A production-style Retrieval-Augmented Generation (RAG) system that ingests 10-K/10-Q filings and answers questions with citations.

**Stack**: AWS S3, Step Functions, Lambda, Bedrock Titan Embeddings, OpenSearch, DynamoDB TTL Cache, API Gateway

**Architecture:**
```mermaid
flowchart LR

%% ---------------- Ingest (batch & offline) ----------------
subgraph IN["Ingest (batch & offline)"]
  S3["S3: 10-K / 10-Q PDFs"]
  SF["Step Functions"]
  EC["Lambda: extract & clean"]
  CE["Lambda: chunk & embed"]
  EMB["Bedrock Titan Embeddings"]
  OS["OpenSearch kNN index"]

  S3 -->|1 new filing| SF
  SF -->|2 extract| EC
  EC -->|3 chunks| CE
  CE -->|4 embed| EMB
  EMB -->|5 vectors| OS
end

%% ---------------- Serve (real-time /chat) ----------------
subgraph SV["Serve (real-time chat)"]
  API["API Gateway: POST /chat"]
  RT["Lambda: chat-router"]
  DDB["DynamoDB cache (TTL)"]
  BRP["Bedrock Text (primary)"]
  BRF["Bedrock Text (fallback)"]

  API -->|request| RT
  RT -->|A kNN retrieve| OS
  RT -->|B cache get/set| DDB
  RT -->|C generate| BRP
  RT -.->|C' fallback| BRF
  RT -->|response| API
end

%% ---------------- Styling ----------------
classDef store  fill:#F0F7FF,stroke:#4A90E2,stroke-width:1px;
classDef compute fill:#FFF7E6,stroke:#F5A623,stroke-width:1px;
classDef model  fill:#F0FFF4,stroke:#27AE60,stroke-width:1px;
classDef edge   fill:#F8F9FA,stroke:#6C757D,stroke-dasharray:3 3,stroke-width:1px;

class S3,OS,DDB store
class SF,EC,CE,RT compute
class EMB,BRP,BRF model
class API edge
```

Features:

Low-cost, serverless RAG on AWS

DynamoDB cache to reduce LLM calls

Public API Gateway endpoint

Easily extensible to other document sets

Deployment
See DEPLOY.md for AWS setup instructions.

