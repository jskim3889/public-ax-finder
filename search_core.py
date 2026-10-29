"""질의 문장을 임베딩해 가까운 사업을 찾는다. 로컬 서버와 Vercel 함수가 함께 쓴다.

키는 환경변수 OPENROUTER_API_KEY에서 읽는다. 로컬에서 환경변수가 없으면
~/.ghost-alice/secrets.env에서 같은 이름을 찾는다. 키는 코드와 저장소에 두지 않는다.

사용 예 (화면 없이 검증):
    python search_core.py "민원 상담 챗봇을 도입한 기관"
"""

import json
import os
import sys
import urllib.request
from functools import lru_cache
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent / "data"
API_URL = "https://openrouter.ai/api/v1/embeddings"
MAX_QUERY_CHARS = 200
TIMEOUT_SEC = 15
ATTEMPTS = 2


def api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    secrets = Path.home() / ".ghost-alice" / "secrets.env"
    if secrets.exists():
        for line in secrets.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("OPENROUTER_API_KEY 환경변수가 없습니다")


@lru_cache(maxsize=1)
def load_index():
    meta = json.loads((DATA_DIR / "index.meta.json").read_text(encoding="utf-8"))
    vectors = np.fromfile(DATA_DIR / "vectors.f16", dtype=np.float16)
    vectors = vectors.reshape(meta["count"], meta["dimension"]).astype(np.float32)
    docs = json.loads((DATA_DIR / "docs.json").read_text(encoding="utf-8"))
    return meta, vectors, docs


@lru_cache(maxsize=256)
def fetch_embedding(text, model):
    # 임베딩 API가 가끔 30초 넘게 응답하지 않는다(10-29 시험에서 4번 중 2번). 짧게 끊고 다시 묻는다
    body = json.dumps({"model": model, "input": [text]}).encode("utf-8")
    for attempt in range(ATTEMPTS):
        request = urllib.request.Request(
            API_URL, data=body,
            headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
                return tuple(json.load(response)["data"][0]["embedding"])
        except TimeoutError:
            if attempt == ATTEMPTS - 1:
                raise


def embed_query(text, meta):
    vector = np.array(fetch_embedding(text, meta["model"]), dtype=np.float32)
    # 색인과 같은 방식: 앞쪽 차원만 남기고 길이 1로 맞춘다
    vector = vector[: meta["dimension"]]
    return vector / np.linalg.norm(vector)


def search(query, top_k=10):
    query = query.strip()[:MAX_QUERY_CHARS]
    if not query:
        return []
    meta, vectors, docs = load_index()
    scores = vectors @ embed_query(query, meta)
    order = np.argsort(-scores)[:top_k]
    return [{**docs[i], "score": round(float(scores[i]), 4)} for i in order]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for hit in search(" ".join(sys.argv[1:]), top_k=5):
        print(f"{hit['score']:.3f}  {hit['name']}  | {hit['agency']} | {hit['year_month']}")
