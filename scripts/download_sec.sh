#!/usr/bin/env bash
set -euo pipefail

# Requirements:
#  - env: UA set to your SEC-friendly user agent
#  - company_tickers.json present in cwd
#  - jq installed
#  - will write to data/raw/<TICKER>/<YYYY>/<FORM>/

TICKERS=("$@")
if [ ${#TICKERS[@]} -eq 0 ]; then
  echo "Usage: $0 TICKER [TICKER ...]" >&2
  exit 1
fi

mkdir -p data/raw
CUTOFF_DATE=$(date -d '5 years ago' +%Y-%m-%d)
echo "Cutoff (last 5 years): $CUTOFF_DATE"

for T in "${TICKERS[@]}"; do
  # Resolve CIK via mapping file
  CIK=$(jq -r --arg t "$T" '.[] | select(.ticker==$t) | .cik_str' company_tickers.json)
  if [ -z "$CIK" ] || [ "$CIK" = "null" ]; then
    echo "Could not find CIK for $T in company_tickers.json; skipping." >&2
    continue
  fi

  CIK_PADDED=$(printf "%010d" "$CIK")
  SUB_URL="https://data.sec.gov/submissions/CIK${CIK_PADDED}.json"
  echo "== $T (CIK $CIK) =="
  echo "Fetching $SUB_URL"

  TMP_JSON=$(mktemp)
  curl -s -L -H "User-Agent: $UA" -o "$TMP_JSON" "$SUB_URL" || { echo "Failed $T"; rm -f "$TMP_JSON"; continue; }

  # Build records, filter to 10-K/10-Q since cutoff, then output as TSV
  jq -r --arg cutoff "$CUTOFF_DATE" '
    .filings.recent as $r
    | [ range(0; ($r.form | length)) ]
    | map({
        form: $r.form[.],
        date: $r.filingDate[.],
        acc:  $r.accessionNumber[.],
        doc:  $r.primaryDocument[.]
      })
    | map(select((.form=="10-K" or .form=="10-Q") and (.date >= $cutoff)))
    | .[]
    | [.form, .date, .acc, .doc]                          # <— array for @tsv
    | @tsv
  ' "$TMP_JSON" | while IFS=$'\t' read -r FORM FDATE ACC DOC; do

      YEAR=${FDATE%%-*}
      ACC_NODASH=$(echo "$ACC" | tr -d '-')
      URL="https://www.sec.gov/Archives/edgar/data/${CIK}/${ACC_NODASH}/${DOC}"

      OUTDIR="data/raw/${T}/${YEAR}/${FORM}"
      mkdir -p "$OUTDIR"
      OUTFILE="${OUTDIR}/${DOC}"

      if [ -s "$OUTFILE" ]; then
        echo "  already exists: $OUTFILE"
      else
        echo "  downloading: $FORM $FDATE -> $OUTFILE"
        curl -s -L -H "User-Agent: $UA" -o "$OUTFILE" "$URL" || true
        if [ ! -s "$OUTFILE" ] || [ "$(wc -c < "$OUTFILE")" -lt 1000 ]; then
          echo "    (removed; empty or too small) $OUTFILE"
          rm -f "$OUTFILE"
        fi
        sleep 0.3
      fi
  done

  rm -f "$TMP_JSON"
done
