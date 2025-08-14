import os, boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

region   = os.environ.get("REGION") or os.environ.get("AWS_REGION") or "us-east-2"
endpoint = os.environ["OPENSEARCH_ENDPOINT"]
index    = os.environ.get("OPENSEARCH_INDEX", "kb_chunks")

session = boto3.session.Session()
creds   = session.get_credentials().get_frozen_credentials()
awsauth = AWS4Auth(creds.access_key, creds.secret_key, region, "es", session_token=creds.token)

client = OpenSearch(
    hosts=[{"host": endpoint.replace("https://",""), "port": 443}],
    http_auth=awsauth, use_ssl=True, verify_certs=True,
    connection_class=RequestsHttpConnection,
)

body = {
  "settings": {
    "index": {
      "knn": True,
      "knn.algo_param.ef_search": 64,
      "knn.algo_param.ef_construction": 128,
      "knn.space_type": "cosinesimil"
    }
  },
  "mappings": {
    "properties": {
      "chunk_id":    { "type": "keyword" },
      "doc_id":      { "type": "keyword" },
      "ticker":      { "type": "keyword" },
      "filing_type": { "type": "keyword" },
      "filing_year": { "type": "integer" },
      "item_label":  { "type": "keyword" },
      "page":        { "type": "integer" },
      "text":        { "type": "text" },
      "embedding":   { "type": "knn_vector", "dimension": 1024 },
      "metadata":    { "type": "object", "enabled": True }
    }
  }
}

if client.indices.exists(index=index):
    print(f"Index '{index}' already exists. ✅")
else:
    resp = client.indices.create(index=index, body=body)
    print("Created index:", resp["index"])

print("Indices:", client.cat.indices(format="json"))
