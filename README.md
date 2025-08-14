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

