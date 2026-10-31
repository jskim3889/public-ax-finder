"""전국 공공 AX 지도(과제 1 사이트 B)의 집계를 메일용 요약 파일로 옮긴다.

원본 ../site-b/map-data.js, ../site-b/v3-data.js는 읽기만 한다. 결과는 data/insights.json.
    python build_insights.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE_B = ROOT.parent / "site-b"
OUT = ROOT / "data" / "insights.json"

# 소속 문자열에서 시·도를 찾을 때 쓰는 이름. 지도의 17개 시·도 키와 같다
REGION_NAMES = {
    "서울": ["서울"], "부산": ["부산"], "대구": ["대구"], "인천": ["인천"], "광주": ["광주광역시"],  # 경기 광주시와 헷갈리지 않게 광역시만
    "대전": ["대전"], "울산": ["울산"], "세종": ["세종"], "경기": ["경기"], "강원": ["강원"],
    "충북": ["충북", "충청북도"], "충남": ["충남", "충청남도"], "전북": ["전북", "전라북도"], "전남": ["전남", "전라남도"],
    "경북": ["경북", "경상북도"], "경남": ["경남", "경상남도"], "제주": ["제주"],
}


def load_js(path):
    text = path.read_text(encoding="utf-8")
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


def main():
    m = load_js(SITE_B / "map-data.js")
    v = load_js(SITE_B / "v3-data.js")
    labels = {g["key"]: g["label"] for g in m["groups"]}
    out = {
        "total": v["total"],
        "groups": [{"key": g["key"], "label": g["label"], "count": g["count"], "amount": g["amount"],
                    "years": dict(g["years"])} for g in m["groups"]],
        "clusters": sorted(({"name": c["name"], "group": labels[c["group"]], "count": c["count"],
                             "amount": c["amount"], "years": dict(c["years"]),
                             "kinds": c["kinds"][:3]} for c in m["clusters"]),
                           key=lambda c: -c["count"]),
        "rising": [{"word": w["word"], "count": w["count"], "insts": w["insts"], "example": w["examples"][0]}
                   for w in v["words"]["rising"][:6]],
        "rising_phrases": [{"phrase": p["phrase"], "count": p["count"], "example": p["examples"][0]}
                           for p in v["phrases"]["rising"][:5]],
        "region_coverage": v["region_coverage"],
        "group_order": [g["label"] for g in m["groups"]],
        "regions": {name: {"n": r["n"], "amount": r["amount"], "groups": r["groups"]}
                    for name, r in v["region"].items()},
        "region_names": REGION_NAMES,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT.name}: 그룹 {len(out['groups'])}, 유형 {len(out['clusters'])}, 시·도 {len(out['regions'])}, "
          f"{OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
