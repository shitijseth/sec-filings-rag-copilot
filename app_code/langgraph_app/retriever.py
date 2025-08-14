import os, re, json, hashlib, boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

region   = os.environ["AWS_REGION"]
endpoint = os.environ["OPENSEARCH_ENDPOINT"]
index    = os.environ.get("OPENSEARCH_INDEX","kb_chunks")

sess  = boto3.session.Session()
creds = sess.get_credentials().get_frozen_credentials()
auth  = AWS4Auth(creds.access_key,creds.secret_key,region,"es",session_token=creds.token)

client = OpenSearch(
    hosts=[{"host": endpoint.replace("https://",""), "port": 443}],
    http_auth=auth, use_ssl=True, verify_certs=True,
    connection_class=RequestsHttpConnection,
)

def _guess_ticker(q: str):
    if re.search(r"\bAAPL\b|\bApple\b", q, re.I): return "AAPL"
    return None

def _section_hint(q: str):
    ql = q.lower()
    if "risk" in ql or "supply-chain" in ql or "supply chain" in ql:
        return "Item 1A"     # Risk Factors
    if "cash" in ql or "liquidity" in ql or "balance sheet" in ql or "cash flow" in ql:
        return "Item 7"      # MD&A (often liquidity) or Item 8
    return None

_KWS = ["supply chain","supplier","component","shortage","manufactur","risk",
        "cash","liquidity","balance sheet","competition","regulatory"]

def _score(q: str, s: dict):
    txt = s.get("text","").lower()
    score = 0.0
    # keyword boosts
    for kw in _KWS:
        if kw in q.lower() or kw in txt:
            score += 1.5
    # exact phrase boosts from query tokens
    for tok in re.findall(r"[a-z0-9\-]+", q.lower()):
        if tok and tok in txt:
            score += 0.2
    # section bias
    sec = _section_hint(q)
    if sec and s.get("item_label","").lower().startswith(sec.lower()):
        score += 5.0
    # prefer same filing type and recent year (light)
    if s.get("filing_type") in ("10-K","10-Q"): score += 0.2
    score += 0.01*int(s.get("filing_year") or 0)
    return score

def _fingerprint(s: str):
    t = " ".join(s.split()).lower()
    return hashlib.md5(t[:160].encode()).hexdigest()

def search(vec, qtext: str, k=8):
    # 1) get wider pool via kNN + ticker filter
    filt = []
    tk = _guess_ticker(qtext or "")
    if tk:
        filt.append({"term": {"ticker": tk}})
    body = {
      "size": max(k*4, 30),
      "query": { "bool": { "must": [ {"knn": {"embedding": {"vector": vec, "k": max(k*4, 30)}}} ],
                           "filter": filt } },
      "_source": ["doc_id","ticker","filing_type","filing_year","item_label","page","text"]
    }
    res = client.search(index=index, body=body)

    # 2) score, 3) de-dupe by text fingerprint
    seen = set()
    cand = []
    for h in res["hits"]["hits"]:
        s = h["_source"]
        fp = _fingerprint(s.get("text",""))
        if fp in seen: continue
        seen.add(fp)
        cand.append( ( _score(qtext, s), s ) )

    cand.sort(key=lambda x: x[0], reverse=True)
    return [s for _,s in cand[:k]]
