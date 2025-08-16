#!/usr/bin/env python3
import sys, os, json, time, re, argparse, hashlib, statistics, urllib.request

CITE_BRACKET = re.compile(r"\[(.*?)\]")          # [AAPL 2023 10-K — Item 1A]
ITEM_RE = re.compile(r"item\s+([0-9a-zA-Z]+)", re.I)

def post_chat(api_url: str, query: str, timeout=40):
    url = api_url.rstrip("/") + "/chat"
    data = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    dt_ms = int((time.time() - t0) * 1000)
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        payload = {"answer": body.decode("utf-8", "ignore")}
    return payload.get("answer", ""), dt_ms

def extract_item_labels(answer: str):
    labels = []
    for m in CITE_BRACKET.finditer(answer):
        content = m.group(1)
        m2 = ITEM_RE.search(content)
        if m2:
            labels.append("Item " + m2.group(1).upper())
    return labels

def count_quotes(answer: str):
    # count bullet lines that look like "* ..." or "• ..."
    return len(re.findall(r"(^|\n)\s*(?:\*|•)\s+", answer))

def keyword_coverage(answer: str, keywords):
    a = answer.lower()
    if not keywords:
        return 1.0
    hits = sum(1 for k in keywords if k.lower() in a)
    return hits / max(1, len(keywords))

def jaccard(a: str, b: str):
    A = set(w for w in re.findall(r"\w+", a.lower()) if len(w) > 2)
    B = set(w for w in re.findall(r"\w+", b.lower()) if len(w) > 2)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)

def deterministic_sample(ids, frac):
    if frac <= 0: return set()
    target_pct = int(round(frac * 100))
    picks = set()
    for i in ids:
        h = int(hashlib.md5(i.encode("utf-8")).hexdigest()[:4], 16) % 100
        if h < target_pct:
            picks.add(i)
    return picks

def parse_args():
    p = argparse.ArgumentParser(description="Lightweight eval for SEC RAG /chat endpoint")
    p.add_argument("api_url", help="API base URL (e.g., https://<api-id>.execute-api.<region>.amazonaws.com[/<stage>])")
    p.add_argument("questions", help="Path to questions .jsonl")
    p.add_argument("--repeat", action="store_true", help="Also re-ask a subset to measure stability (uses cache)")
    p.add_argument("--repeat-frac", type=float, default=0.0, help="Fraction (0..1) of questions to repeat (default 0)")
    p.add_argument("--max", type=int, default=0, help="Cap number of questions processed (0 = all)")
    p.add_argument("--timeout", type=int, default=40, help="HTTP timeout seconds")
    p.add_argument("--out", default="eval/out/results_multi.json", help="Output JSON path")
    return p.parse_args()

def main():
    args = parse_args()

    # Read questions
    rows = []
    with open(args.questions, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            if line.startswith("#"): continue
            rows.append(json.loads(line))

    if args.max and args.max > 0:
        rows = rows[:args.max]

    ids = [r["id"] for r in rows]
    repeat_ids = deterministic_sample(ids, args.repeat_frac)
    do_repeat = args.repeat or (args.repeat_frac > 0)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    results, latencies, stabilities = [], [], []
    per_ticker_map = {}

    print(f"Running eval on {len(rows)} questions; repeat_frac={args.repeat_frac} → {len(repeat_ids)} repeats")

    for row in rows:
        qid = row["id"]
        query = row["query"]
        exp_items = [e.strip().lower() for e in row.get("expected_items", [])]
        keywords = row.get("keywords", [])
        ticker = row.get("ticker")
        ftype  = row.get("filing_type")
        fyear  = row.get("filing_year")

        ans, ms = post_chat(args.api_url, query, timeout=args.timeout)
        latencies.append(ms)

        items = [x.lower() for x in extract_item_labels(ans)]
        cim = 1 if any(e in items for e in exp_items) else 0
        mqs = 1 if count_quotes(ans) >= 2 else 0
        kc  = round(keyword_coverage(ans, keywords), 3)

        stability = None
        if do_repeat and qid in repeat_ids:
            ans2, _ = post_chat(args.api_url, query, timeout=args.timeout)
            stability = round(jaccard(ans, ans2), 3)
            stabilities.append(stability)

        preview = (ans[:260] + "…") if len(ans) > 260 else ans
        rec = {
            "id": qid,
            "ticker": ticker,
            "filing_type": ftype,
            "filing_year": fyear,
            "latency_ms": ms,
            "citation_items_found": items,
            "CIM": cim,
            "MQS": mqs,
            "KC": kc,
            "stability": stability,
            "answer_preview": preview
        }
        results.append(rec)

        # per-ticker aggregation key
        key = None
        if ticker and ftype and fyear:
            key = f"{ticker} {fyear} {ftype}"
        elif ticker:
            key = ticker
        if key:
            per_t = per_ticker_map.setdefault(key, {"rows": []})
            per_t["rows"].append(rec)

    # Summaries
    n = len(results)
    cim_avg = sum(r["CIM"] for r in results) / n if n else 0.0
    mqs_avg = sum(r["MQS"] for r in results) / n if n else 0.0
    kc_avg  = sum(r["KC"]  for r in results) / n if n else 0.0
    p50 = int(statistics.median(latencies)) if latencies else None
    p95 = int(sorted(latencies)[max(0, int(len(latencies)*0.95)-1)]) if latencies else None
    stab_avg = round(sum(stabilities)/len(stabilities), 3) if stabilities else None

    summary = {
        "N": n,
        "repeats_N": len(stabilities),
        "CIM@Item (accuracy)": round(cim_avg, 3),
        "MQS@2+quotes": round(mqs_avg, 3),
        "KC@keywords(avg)": round(kc_avg, 3),
        "latency_p50_ms": p50,
        "latency_p95_ms": p95,
        "stability_avg": stab_avg
    }

    # Per-ticker summary
    per_ticker = {}
    for key, obj in per_ticker_map.items():
        rows_k = obj["rows"]
        per_ticker[key] = {
            "N": len(rows_k),
            "CIM": round(sum(r["CIM"] for r in rows_k)/len(rows_k), 3),
            "MQS": round(sum(r["MQS"] for r in rows_k)/len(rows_k), 3),
            "KC":  round(sum(r["KC"]  for r in rows_k)/len(rows_k), 3),
            "latency_p50_ms": int(statistics.median([r["latency_ms"] for r in rows_k])),
        }

    # Write JSON
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "per_ticker": per_ticker, "results": results}, f, indent=2)

    # Also write a short Markdown summary for your repo
    md_path = os.path.join(os.path.dirname(args.out) or ".", "summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("## Eval Summary\n\n")
        for k, v in summary.items():
            f.write(f"- **{k}**: {v}\n")
        if per_ticker:
            f.write("\n### By filing/ticker\n\n")
            f.write("| Filing | N | CIM | MQS | KC | p50 (ms) |\n|---|---:|---:|---:|---:|---:|\n")
            for k, v in per_ticker.items():
                f.write(f"| {k} | {v['N']} | {v['CIM']} | {v['MQS']} | {v['KC']} | {v['latency_p50_ms']} |\n")

    # Print to stdout for tee
    print("\n=== EVAL SUMMARY ===")
    for k, v in summary.items():
        print(f"{k}: {v}")
    if per_ticker:
        print("\n=== BY FILING/TICKER ===")
        for k, v in per_ticker.items():
            print(f"{k}: N={v['N']} CIM={v['CIM']} MQS={v['MQS']} KC={v['KC']} p50={v['latency_p50_ms']}ms")
    print(f"\nSaved: {args.out}")
    print(f"Wrote: {md_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
