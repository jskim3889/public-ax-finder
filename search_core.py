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
# 1위 유사도가 이보다 낮으면 화면에 "딱 맞는 사업이 없을 수 있다"를 띄운다.
# 10-29 측정: 정상 질의 1위 최저 0.729, 무관 질의("asdfqwer") 1위 0.691
LOW_MATCH_SCORE = 0.70
# 같은 기관의 두 사업이 이 이상 비슷하면 한 카드로 묶는다.
# 10-29 측정: 김포시 챗봇 "서비스/시스템 구축" 0.974, 같은 사업의 긴급 재공고 0.930, 해마다 갱신하는 같은 용역 0.90~0.92
SAME_PROJECT_SIM = 0.93
# 카드 1장을 만들 때 살펴보는 후보 수. 묶이는 사업까지 찾으려고 카드 수보다 넉넉히 본다
CANDIDATES_PER_CARD = 6
PAGE_SIZE = 10
# "더 보기"로 볼 수 있는 최대 카드 수. 이보다 아래 순위는 관련성이 낮다
MAX_CARDS = 100


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


def search_page(query, offset=0, limit=PAGE_SIZE):
    """유사도 순 카드 offset+1번째부터 limit장과, 유사도 LOW_MATCH_SCORE 이상인 사업 수를 돌려준다."""
    query = query.strip()[:MAX_QUERY_CHARS]
    offset = max(0, min(int(offset), MAX_CARDS))
    if not query:
        return {"hits": [], "related": 0, "has_more": False, "offset": offset}
    meta, vectors, docs = load_index()
    scores = vectors @ embed_query(query, meta)
    wanted = min(offset + limit, MAX_CARDS)
    groups = []
    # 카드 묶기는 위 순위부터 차례로 해야 페이지마다 결과가 같으므로, 앞 페이지까지 다시 계산한다
    for i in np.argsort(-scores)[: wanted * CANDIDATES_PER_CARD]:
        lead = next(
            (g for g in groups
             if docs[g["row"]]["agency"] == docs[i]["agency"]
             and float(vectors[g["row"]] @ vectors[i]) >= SAME_PROJECT_SIM),
            None,
        )
        if lead:
            lead["similar"].append(docs[i])
        elif len(groups) < wanted:
            groups.append({"row": i, "similar": []})
    hits = [
        {**docs[g["row"]], "score": round(float(scores[g["row"]]), 4), "similar": g["similar"]}
        for g in groups[offset:wanted]
    ]
    return {
        "hits": hits,
        "related": int((scores >= LOW_MATCH_SCORE).sum()),
        "has_more": wanted < MAX_CARDS and len(groups) == wanted,
        "offset": offset,
    }


def search(query, top_k=PAGE_SIZE):
    return search_page(query, 0, top_k)["hits"]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for hit in search(" ".join(sys.argv[1:]), top_k=5):
        print(f"{hit['score']:.3f}  {hit['name']}  | {hit['agency']} | {hit['year_month']}")
