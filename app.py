"""공공 AX 사례 찾기 웹앱. 로컬에서는 python app.py, Vercel에서는 같은 app 객체를 쓴다.

브라우저에는 키를 두지 않는다. 브라우저는 질의 문장만 보내고, 임베딩 호출은 이 서버가 한다 (7강 #14).
"""

import urllib.error
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import search_core

PUBLIC_DIR = Path(__file__).resolve().parent / "public"

# Vercel은 public/ 파일을 CDN에서 직접 내보내고 Flask static_folder는 쓰지 말라고 한다.
# 아래 "/" 경로는 로컬 실행용이다
app = Flask(__name__, static_folder=None)


@app.get("/")
def index():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.post("/api/search")
def api_search():
    # 질의 문장이 접속 기록의 주소에 남지 않도록 GET 주소 대신 POST 본문으로 받는다
    body = request.get_json(silent=True) or {}
    query = str(body.get("q", ""))
    try:
        offset = int(body.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    # 실패는 모두 JSON으로 돌려준다. 화면이 "찾는 중…"에 멈추지 않고 원인별 안내를 띄울 수 있게 한다
    try:
        page = search_core.search_page(query, offset=offset)
    except TimeoutError:
        return jsonify(kind="timeout", error="AI 검색 서비스가 제때 응답하지 않았습니다. 잠시 뒤 다시 시도해 주세요."), 504
    except urllib.error.HTTPError as e:
        if e.code in (402, 429):
            return jsonify(kind="quota", error="AI 검색 서비스 사용량이 한도에 도달했습니다. 잠시 뒤 다시 시도해 주세요."), 503
        return jsonify(kind="upstream", error=f"AI 검색 서비스 오류({e.code})로 검색하지 못했습니다."), 502
    except urllib.error.URLError:
        return jsonify(kind="upstream", error="AI 검색 서비스에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요."), 502
    except RuntimeError:
        return jsonify(kind="config", error="검색 서버 설정 문제로 검색하지 못했습니다."), 500
    meta, _, _ = search_core.load_index()
    # 1위 유사도는 첫 페이지에서만 알 수 있으므로 안내 여부도 첫 페이지에서만 판단한다
    low_match = page["offset"] == 0 and bool(page["hits"]) and page["hits"][0]["score"] < search_core.LOW_MATCH_SCORE
    return jsonify(
        query=query[: search_core.MAX_QUERY_CHARS],
        total=meta["count"],
        related=page["related"],
        related_score=search_core.LOW_MATCH_SCORE,
        offset=page["offset"],
        has_more=page["has_more"],
        hits=page["hits"],
        low_match=low_match,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
