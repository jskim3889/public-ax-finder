"""리드(신청자) 저장소. 신청자와 신청 기록을 남겨 운영사가 문의를 관리하게 한다.

자료 발송은 이 기록과 무관하다. 지도 요약과 비교 리포트는 이전 신청 여부를 따지지 않고 요청한 대로 보낸다.
신규·재방문 표시는 운영사 메일에만 쓴다.

    SUPABASE_URL, SUPABASE_KEY   Supabase 프로젝트 주소와 서버 전용 Secret key(sb_secret_…)
    LEADS_STORE=file             Supabase 없이 cache/leads.json에 저장한다 (로컬 시험 전용)

Secret key는 RLS를 건너뛰므로 서버 환경변수에만 둔다. 새 형식 키는 JWT가 아니라서
Authorization: Bearer가 아니라 apikey 헤더에만 싣는다(Supabase 새 API 키 안내).
테이블과 함수는 supabase/schema.sql. 마지막 이용일로부터 1년이 지난 리드는 등록 함수가 지운다.
"""

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from search_core import env

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / "cache" / "leads.json"
TIMEOUT_SEC = 10
RETENTION_SEC = 365 * 24 * 3600


def backend():
    if env("SUPABASE_URL") and env("SUPABASE_KEY"):
        return "supabase"
    if os.environ.get("LEADS_STORE") == "file":
        return "file"
    return ""


def _rpc(name, args):
    url = env("SUPABASE_URL").rstrip("/") + "/rest/v1/rpc/" + urllib.parse.quote(name)
    request = urllib.request.Request(
        url, data=json.dumps(args).encode("utf-8"), method="POST",
        headers={"apikey": env("SUPABASE_KEY"), "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
        return json.load(response)


def _file_register(email, name, org, kind, ids, query, needs):
    data = json.loads(LOCAL.read_text(encoding="utf-8")) if LOCAL.exists() else {"leads": {}, "requests": []}
    now = time.time()
    expired = [k for k, v in data["leads"].items() if now - v["last_seen"] > RETENTION_SEC]
    for k in expired:
        del data["leads"][k]
    data["requests"] = [r for r in data["requests"] if r["email"] not in expired]
    lead = data["leads"].get(email)
    is_new = lead is None
    if is_new:
        lead = data["leads"][email] = {"name": name, "org": org, "first_seen": now, "visits": 0}
    lead.update(name=name, org=org, last_seen=now, visits=lead["visits"] + 1)
    data["requests"].append({"email": email, "kind": kind, "ids": ids, "query": query, "needs": needs,
                             "created_at": now})
    LOCAL.parent.mkdir(parents=True, exist_ok=True)
    LOCAL.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"is_new": is_new, "visits": lead["visits"]}


def register(email, name, org, kind, ids, query, needs):
    """신청을 기록하고 {"is_new", "visits"}를 돌려준다. 저장소가 없으면 None.

    kind: "map"(전국 공공 AX 지도 요약) 또는 "report"(고른 사업 비교 리포트). 신청자가 고른 그대로 기록한다
    """
    email = email.strip().lower()
    store = backend()
    if store == "file":
        return _file_register(email, name, org, kind, ids, query, needs)
    if store != "supabase":
        return None
    # 한 번의 호출로 조회·등록·방문 수 갱신을 묶는다. 동시에 두 번 눌러도 신규는 한 번만 잡힌다
    row = _rpc("register_lead", {"p_email": email, "p_name": name, "p_org": org})
    row = row[0] if isinstance(row, list) else row
    _rpc("log_lead_request", {"p_lead": row["lead_id"], "p_kind": kind, "p_ids": ids,
                              "p_query": query, "p_needs": needs})
    return {"is_new": bool(row["is_new"]), "visits": int(row["visits"])}
