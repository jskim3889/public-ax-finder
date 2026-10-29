"""공공 AX 사례 찾기 웹앱. 로컬에서는 python app.py, Vercel에서는 같은 app 객체를 쓴다.

브라우저에는 키를 두지 않는다. 브라우저는 질의 문장만 보내고, 임베딩 호출은 이 서버가 한다 (7강 #14).
"""

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


@app.get("/api/search")
def api_search():
    query = request.args.get("q", "")
    try:
        hits = search_core.search(query, top_k=10)
    except TimeoutError:
        return jsonify(error="검색 서버가 응답하지 않습니다. 잠시 뒤 다시 시도해 주세요."), 504
    meta, _, _ = search_core.load_index()
    return jsonify(query=query[: search_core.MAX_QUERY_CHARS], total=meta["count"], hits=hits)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
