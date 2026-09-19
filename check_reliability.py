"""CNT3054 청약 인식 프로젝트(B안): 분류 신뢰도 검증 (보고서 Ⅱ-ⅰ-2의 '작성 필요' 항목)

LLM(gpt-oss-120b) 분류가 사람의 판단과 얼마나 일치하는지 Cohen's κ(카파)로 확인한다.
  - κ 해석 기준 (Landis & Koch, 1977): 0.61~0.80 상당한 일치, 0.81 이상 거의 완전한 일치
    https://doi.org/10.2307/2529310
  - scikit-learn cohen_kappa_score:
    https://scikit-learn.org/stable/modules/generated/sklearn.metrics.cohen_kappa_score.html

사용법 (경로를 생략하면 output/ 의 가장 최근 classified.csv 를 쓴다)
  (1) 코딩 시트 만들기 — 분석 기간(2026-09-13~19) 댓글 중 무작위 100개, LLM 결과는 숨김
      python check_reliability.py sample
      → output/reliability_sheet.csv 를 엑셀로 열어 stance / topics / outlook / action 열을 직접 채운다
        (코드는 cy-index.txt 참고. topics 는 AB 처럼 붙여 쓰고, 없으면 비워 둔다)
        조원마다 파일 이름을 바꿔 저장한다. 예: output/reliability_sheet_kim.csv
  (2) 일치도 계산 — 사람이 채운 시트와 LLM 결과 비교
      python check_reliability.py score output/reliability_sheet_kim.csv
      python check_reliability.py score output/reliability_sheet_kim.csv output/reliability_sheet_lee.csv
"""
import argparse
from pathlib import Path

import pandas as pd
from sklearn.metrics import cohen_kappa_score

BASE = Path(__file__).resolve().parent
TOPIC_CODES = "ABCDEFGHI"   # cy-index.txt 의 관심사 코드
COLS = ["stance", "topics", "outlook", "action"]
PERIOD_START, PERIOD_END = "2026-09-13", "2026-09-19"   # 분석 기간 (한국 시간)


def latest_classified():
    runs = sorted((BASE / "output").glob("*/classified.csv"), key=lambda p: p.stat().st_mtime)
    if not runs:
        raise SystemExit("output/ 에 classified.csv 가 없습니다. classify_comments.py 를 먼저 실행하세요.")
    return runs[-1]


def sample(src, n, seed):
    d = pd.read_csv(src)
    day = pd.to_datetime(d["published_at"], utc=True).dt.tz_convert("Asia/Seoul").dt.strftime("%Y-%m-%d")
    d = d[(day >= PERIOD_START) & (day <= PERIOD_END)]
    s = d.sample(n=min(n, len(d)), random_state=seed)[["comment_id", "text_raw"]]
    for c in COLS:
        s[c] = ""
    out = BASE / "output" / "reliability_sheet.csv"
    s.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"저장: {out} ({len(s)}개, seed={seed}, 기간 {PERIOD_START}~{PERIOD_END})")
    print("빈 칸을 채우고 파일 이름을 바꿔 저장한 뒤 score 명령으로 비교하세요.")


def score(files, ref):
    base = pd.read_csv(ref, dtype=str).set_index("comment_id")
    for f in files:
        h = pd.read_csv(f, dtype=str).set_index("comment_id").dropna(subset=["stance"])
        j = h[COLS].join(base[COLS], rsuffix="_llm", how="inner").fillna("0")
        print(f"\n== {f}  (비교 {len(j)}개, 기준: {ref})")
        for c in ["stance", "outlook", "action"]:
            a, b = j[c].str.strip(), j[c + "_llm"].str.strip()
            print(f"  {c:<8} κ = {cohen_kappa_score(a, b):.3f}   단순 일치율 {(a == b).mean():.1%}")
        # 관심사는 복수 선택이므로 코드별로 있다/없다를 비교한 뒤 평균 κ 를 낸다
        ks = []
        for code in TOPIC_CODES:
            a, b = j["topics"].str.contains(code), j["topics_llm"].str.contains(code)
            if a.any() or b.any():
                ks.append(cohen_kappa_score(a, b))
        print(f"  topics   코드별 κ 평균 = {sum(ks) / len(ks):.3f}")


def main():
    ap = argparse.ArgumentParser(description="분류 신뢰도 검증")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("sample")
    a.add_argument("--input", help="classified.csv (기본: output/ 의 가장 최근 파일)")
    a.add_argument("--n", type=int, default=100)
    a.add_argument("--seed", type=int, default=42)
    b = sub.add_parser("score")
    b.add_argument("files", nargs="+", help="사람이 채운 코딩 시트")
    b.add_argument("--ref", help="LLM 분류 결과 (기본: output/ 의 가장 최근 classified.csv)")
    args = ap.parse_args()
    if args.cmd == "sample":
        sample(args.input or latest_classified(), args.n, args.seed)
    else:
        score(args.files, args.ref or latest_classified())


if __name__ == "__main__":
    main()
