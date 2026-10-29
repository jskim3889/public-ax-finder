"""과제 1 임베딩을 웹앱이 읽는 색인으로 바꾼다.

과제 1 산출물(../data/embeddings/<이름>.*)과 중복 정리본(../data/order_plans_dedup.csv)을 읽어
앞쪽 --dim 차원만 남기고 길이를 1로 맞춘 float16 벡터와 화면에 보일 사업 정보를 만든다.

사용 예:
    python build_index.py --source all --dim 1024
결과:
    data/vectors.f16     float16 벡터 (행 = 사업, 길이 1로 정규화)
    data/docs.json       행 순서대로 화면용 사업 정보 (담당자 정보 없음)
    data/index.meta.json 모델, 차원, 건수, 원본
"""

import argparse
import csv
import datetime
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
COURSE_DATA = ROOT.parent / "data"
OUT_DIR = ROOT / "data"


def load_vectors(source):
    meta = json.loads((COURSE_DATA / "embeddings" / f"{source}.meta.json").read_text(encoding="utf-8"))
    raw = np.fromfile(COURSE_DATA / "embeddings" / f"{source}.f32", dtype=np.float32)
    vectors = raw.reshape(meta["count"], meta["dimension"])
    with (COURSE_DATA / "embeddings" / f"{source}.ids.csv").open(encoding="utf-8-sig") as f:
        ids = [row["orderPlanUntyNo"] for row in csv.DictReader(f)]
    return meta, vectors, ids


def truncate(vectors, dim):
    # 앞쪽 dim차원만 남기고 다시 길이 1로 맞춘다. 질의 벡터도 search_core에서 같은 방식으로 자른다
    cut = vectors[:, :dim]
    return cut / np.linalg.norm(cut, axis=1, keepdims=True)


def load_docs(ids):
    with (COURSE_DATA / "order_plans_dedup.csv").open(encoding="utf-8-sig") as f:
        by_id = {row["orderPlanUntyNo"]: row for row in csv.DictReader(f)}
    docs = []
    for plan_id in ids:
        row = by_id[plan_id]
        docs.append({
            "id": plan_id,
            "name": row["bizNm"].replace("\\n", " "),
            "agency": row["orderInsttNm"],
            "agency_type": row["jrsdctnDivNm"],
            "year_month": f"{row['orderYear']}-{int(row['orderMnth']):02d}",
            "amount": int(float(row["amount"] or 0)),
            "type": row["ax_type"],
            "url": row["orderPlanDtlUrl"],
        })
    return docs


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default="all", help="../data/embeddings 안의 이름 (all, test_5 등)")
    parser.add_argument("--dim", type=int, default=1024, help="남길 차원 수")
    args = parser.parse_args()

    meta, vectors, ids = load_vectors(args.source)
    index = truncate(vectors, args.dim).astype(np.float16)
    docs = load_docs(ids)

    OUT_DIR.mkdir(exist_ok=True)
    index.tofile(OUT_DIR / "vectors.f16")
    (OUT_DIR / "docs.json").write_text(json.dumps(docs, ensure_ascii=False), encoding="utf-8")
    index_meta = {
        "created_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "model": meta["model"],
        "source": f"../data/embeddings/{args.source}",
        "count": len(docs),
        "dimension": args.dim,
        "original_dimension": meta["dimension"],
    }
    (OUT_DIR / "index.meta.json").write_text(json.dumps(index_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    size_mb = (OUT_DIR / "vectors.f16").stat().st_size / 1e6
    print(f"{len(docs)}건, {args.dim}차원, 벡터 파일 {size_mb:.1f}MB")


if __name__ == "__main__":
    main()
