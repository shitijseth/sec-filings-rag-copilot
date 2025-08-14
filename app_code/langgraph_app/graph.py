import os, json, boto3
from .retriever import search
from .prompts import SYSTEM_PROMPT

region = os.environ["AWS_REGION"]
bedrock = boto3.client("bedrock-runtime", region_name=region)
EMBED_MODEL = os.environ["BEDROCK_EMBED_MODEL_ID"]
TEXT_MODEL  = os.environ["BEDROCK_TEXT_MODEL_ID"]

def embed(text: str):
    resp = bedrock.invoke_model(modelId=EMBED_MODEL,
                                body=json.dumps({"inputText": text}))
    return json.loads(resp["body"].read())["embedding"]

def generate(system_prompt: str, user_prompt: str):
    resp = bedrock.invoke_model(modelId=TEXT_MODEL,
        body=json.dumps({
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                {"role": "user",   "content": [{"type": "text", "text": user_prompt}]}
            ],
            "max_tokens": 512
        }))
    data = json.loads(resp["body"].read())
    return data["output"]["message"]["content"][0]["text"]

def run(question: str):
    vec   = embed(question)
    hits  = search(vec, k=8)
    ctx   = "\n\n".join(
        f'{h["ticker"]} {h["filing_year"]} {h["filing_type"]} p.{h.get("page",1)}: {h["text"][:400]}'
        for h in hits)
    answer = generate(SYSTEM_PROMPT, f"User question: {question}\n\nContext:\n{ctx}")
    return {"answer": answer}
