"""나라장터 입찰공고(용역) 중 AI 관련 공고를 받아 발주계획과 연결한다.

1단계 수집: 조달청 나라장터 입찰공고정보서비스(data.go.kr 15129394)의 "검색조건에 의한 용역조회"를
월 단위 x 키워드로 호출한다(한 번에 1개월까지만 조회된다). 받은 공고는 cache/notices.jsonl에 모은다.
2단계 연결: 발주계획(../data/order_plans_dedup.csv)의 입찰공고번호와 맞춰 data/notices.json을 만든다.

담당자 이름·전화번호·이메일은 저장하지 않는다. 아래 KEEP 목록에 있는 항목만 남긴다.
키는 환경변수 DATA_GO_KR_SERVICE_KEY, 없으면 ~/.ghost-alice/secrets.env 에서 읽는다.

사용 예:
    python fetch_notices.py collect --from 2023-10 --to 2026-10
    python fetch_notices.py link
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache" / "notices.jsonl"
DONE = ROOT / "cache" / "done.json"
OUT = ROOT / "data" / "notices.json"
PLANS = ROOT.parent / "data" / "order_plans_dedup.csv"

API_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch"
PAGE_SIZE = 999
REQUEST_INTERVAL_SEC = 0.3

# 과제 1 수집 키워드와 같다 (../scripts/collect_order_plans.py)
KEYWORDS = ["인공지능", "AI", "AX", "생성형", "LLM", "GPT", "거대언어", "초거대", "챗봇", "머신러닝", "딥러닝"]

# 화면에 쓰는 공개 항목만 남긴다. 담당자(Ofcl) 항목은 넣지 않는다
KEEP = [
    "bidNtceNo", "bidNtceOrd", "ntceKindNm", "bidNtceNm", "ntceInsttNm", "dminsttNm",
    "bidNtceDt", "bidClseDt", "opengDt", "presmptPrce", "asignBdgtAmt",
    "cntrctCnclsMthdNm", "bidNtceDtlUrl",
] + [f"ntceSpecFileNm{i}" for i in range(1, 11)] + [f"ntceSpecDocUrl{i}" for i in range(1, 11)]


def service_key():
    key = os.environ.get("DATA_GO_KR_SERVICE_KEY")
    if key:
        return key.strip()
    secrets = Path.home() / ".ghost-alice" / "secrets.env"
    for line in secrets.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("DATA_GO_KR_SERVICE_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("DATA_GO_KR_SERVICE_KEY 가 없습니다")


def months(start, end):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch(key, year, month, keyword, page):
    last_day = [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    query = {
        "serviceKey": key, "type": "json", "inqryDiv": "1",
        "inqryBgnDt": f"{year}{month:02d}010000", "inqryEndDt": f"{year}{month:02d}{last_day}2359",
        "bidNtceNm": keyword, "numOfRows": str(PAGE_SIZE), "pageNo": str(page),
    }
    request = urllib.request.Request(API_URL + "?" + urllib.parse.urlencode(query), headers={"User-Agent": "itm690-ax-finder/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.load(response)["response"]
    if data["header"]["resultCode"] != "00":
        raise RuntimeError(f"{data['header']['resultCode']} {data['header']['resultMsg']}")
    return data["body"].get("items") or [], int(data["body"].get("totalCount") or 0)


def collect(args):
    key = service_key()
    CACHE.parent.mkdir(exist_ok=True)
    done = set(json.loads(DONE.read_text(encoding="utf-8"))) if DONE.exists() else set()
    calls = 0
    with CACHE.open("a", encoding="utf-8") as out:
        for year, month in months(args.order_from, args.order_to):
            for keyword in KEYWORDS:
                task = f"{year}-{month:02d}|{keyword}"
                if task in done:
                    continue
                page, got = 1, 0
                while True:
                    items, total = fetch(key, year, month, keyword, page)
                    calls += 1
                    for item in items:
                        out.write(json.dumps({k: item.get(k, "") for k in KEEP}, ensure_ascii=False) + "\n")
                    got += len(items)
                    if got >= total or not items:
                        break
                    page += 1
                    time.sleep(REQUEST_INTERVAL_SEC)
                done.add(task)
                DONE.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")
                print(f"  {task}: {got}건 (누적 호출 {calls})", flush=True)
                time.sleep(REQUEST_INTERVAL_SEC)
    print(f"수집 끝. 이번 실행 호출 {calls}회")


def split_notice_no(no):
    """발주계획에 적힌 번호를 (공고번호, 차수)로 나눈다. 새 형식 R25BK00605188001, 옛 형식 20241237000000"""
    if re.fullmatch(r"R\d{2}[A-Z]{2}\d{8}\d{3}", no):
        return no[:13], no[13:]
    if re.fullmatch(r"\d{14}", no):
        return no[:11], no[11:]
    return no, ""


def link(args):
    latest = {}
    for line in CACHE.open(encoding="utf-8"):
        notice = json.loads(line)
        no, order = notice["bidNtceNo"], notice["bidNtceOrd"]
        # 정정 공고는 차수가 올라간다. 가장 최신 차수만 남긴다
        if no not in latest or order > latest[no]["bidNtceOrd"]:
            latest[no] = notice
    linked, plans_with_no, plans_linked = {}, 0, 0
    with PLANS.open(encoding="utf-8-sig") as f:
        for plan in csv.DictReader(f):
            numbers = [n for n in re.split(r"[,|\s]+", plan["bidNtceNoList"].strip()) if n]
            if not numbers:
                continue
            plans_with_no += 1
            found = []
            for n in dict.fromkeys(split_notice_no(n)[0] for n in numbers):
                if n in latest:
                    found.append(compact(latest[n]))
            if found:
                plans_linked += 1
                linked[plan["orderPlanUntyNo"]] = found
    OUT.write_text(json.dumps(linked, ensure_ascii=False), encoding="utf-8")
    print(f"공고 {len(latest)}건(최신 차수), 공고번호가 있는 발주계획 {plans_with_no}건 중 {plans_linked}건 연결")


# 첨부 중 공고 내용을 담은 핵심 서류만 남긴다. 수의계약 공고에는 업체가 낸 확인서·각서가 붙어
# 업체명이 드러나므로(10-30 확인) 업체 서류로 보이는 파일은 뺀다
CORE_FILE = re.compile(r"공고문|제안요청|과업|규격|RFP|사업안내|사업계획", re.IGNORECASE)
VENDOR_FILE = re.compile(r"주식회사|\(주\)|㈜|확인서|각서|서약|현황")


# 나라장터가 붙이는 파일명 앞머리("20240321888-00_1710390798612_")를 화면에서 뗀다
FILE_PREFIX = re.compile(r"^(\d{8,}-\d{2}_\d{10,}_)+")


def compact(n):
    files = [
        {"name": FILE_PREFIX.sub("", n[f"ntceSpecFileNm{i}"]), "url": n[f"ntceSpecDocUrl{i}"]}
        for i in range(1, 11)
        if n.get(f"ntceSpecFileNm{i}") and n.get(f"ntceSpecDocUrl{i}")
        and CORE_FILE.search(n[f"ntceSpecFileNm{i}"]) and not VENDOR_FILE.search(n[f"ntceSpecFileNm{i}"])
    ]
    price = n.get("presmptPrce") or n.get("asignBdgtAmt") or ""
    return {
        # 최신 차수가 취소공고면 화면에 "취소된 공고"로 표시한다 (등록공고·변경공고·취소공고)
        "no": n["bidNtceNo"], "ord": n["bidNtceOrd"], "kind": n.get("ntceKindNm", ""), "name": n["bidNtceNm"],
        "agency": n["ntceInsttNm"], "posted": n["bidNtceDt"][:10], "close": n["bidClseDt"][:16],
        "open": n["opengDt"][:16], "price": int(float(price)) if price else 0,
        "method": n["cntrctCnclsMthdNm"], "url": n["bidNtceDtlUrl"], "files": files,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="step", required=True)
    p = sub.add_parser("collect")
    p.add_argument("--from", dest="order_from", required=True, help="YYYY-MM")
    p.add_argument("--to", dest="order_to", required=True, help="YYYY-MM")
    sub.add_parser("link")
    args = parser.parse_args()
    collect(args) if args.step == "collect" else link(args)


if __name__ == "__main__":
    main()
