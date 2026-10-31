"""공공 AX 사례 찾기 웹앱. 로컬에서는 python app.py, Vercel에서는 같은 app 객체를 쓴다.

브라우저에는 키를 두지 않는다. 브라우저는 질의 문장만 보내고, 임베딩 호출은 이 서버가 한다 (7강 #14).
"""

import hmac
import urllib.error
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import leads
import report
import search_core

PUBLIC_DIR = Path(__file__).resolve().parent / "public"

# Vercel은 public/ 파일을 CDN에서 직접 내보내고 Flask static_folder는 쓰지 말라고 한다.
# 아래 "/" 경로는 로컬 실행용이다
app = Flask(__name__, static_folder=None)


@app.get("/")
def index():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.get("/privacy.html")
def privacy_page():
    return send_from_directory(PUBLIC_DIR, "privacy.html")


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


@app.get("/api/config")
def api_config():
    # 리포트 메일 기능은 운영사 배포본에서만 켠다 (LEAD_FORM_ENABLED=1)
    return jsonify(lead_form=report.enabled(), operator=report.operator(), max_projects=report.MAX_PROJECTS,
                   privacy=report.privacy())


@app.get("/api/purge")
def api_purge():
    # Vercel Cron이 하루 한 번 부른다(vercel.json). Vercel은 CRON_SECRET을 Authorization: Bearer로 실어 보낸다.
    # 비밀값이 설정되지 않았으면 아무도 부를 수 없게 막는다
    secret = search_core.env("CRON_SECRET")
    given = request.headers.get("Authorization", "")
    if not secret or not hmac.compare_digest(given, f"Bearer {secret}"):
        return jsonify(error="unauthorized"), 401
    try:
        return jsonify(deleted=leads.purge())
    except (OSError, ValueError):
        return jsonify(error="purge failed"), 502


@app.post("/api/report")
def api_report():
    if not report.enabled():
        return jsonify(error="이 배포본에서는 리포트 메일 기능을 제공하지 않습니다."), 404
    body = request.get_json(silent=True) or {}
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    try:
        return jsonify(report.handle(body, ip))
    except report.ReportError as e:
        return jsonify(error=str(e)), 400
    except (TimeoutError, urllib.error.URLError):
        return jsonify(error="AI 요약을 만드는 중 응답이 늦어 리포트를 보내지 못했습니다. 잠시 뒤 다시 시도해 주세요."), 504
    except (RuntimeError, OSError):
        # 메일 계정 설정 누락, SMTP 접속·인증 실패 등. 이용자 입력은 다시 보내면 된다
        return jsonify(error="리포트 메일을 보내지 못했습니다. 잠시 뒤 다시 시도해 주세요."), 502


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
