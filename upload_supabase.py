"""CNT3054 청약 인식 프로젝트(B안): 분류 결과를 Supabase(PostgreSQL)에 올린다.

원본 저장소의 llm-ev.py 와 같은 방식(psycopg2 + .env 의 SUPABASE_CONNECTION_STRING)으로 접속한다.
  원본 코드 : https://github.com/111usionBin/jtbc-2025/blob/master/llm-ev.py
  Supabase 연결 문자열 찾는 곳: 프로젝트 → Connect → Connection string (URI)
            https://supabase.com/docs/guides/database/connecting-to-postgres
  psycopg2 execute_values: https://www.psycopg.org/docs/extras.html#fast-execution-helpers

만드는 테이블 (없으면 자동 생성)
  cheongyak_comments  댓글 1개 = 1행. 원문 + LLM 분류 결과(stance, topics, outlook, action)
                      comment_id 가 같은 행은 새 값으로 덮어쓴다(upsert) → 여러 번 실행해도 중복되지 않음
  cheongyak_runs      실행(결과 폴더) 1개 = 1행. 수집·분류 조건과 stats.json 전체(jsonb)

실행
  python upload_supabase.py              # output/ 의 가장 최근 폴더, 2026-09-13~19 댓글만
  python upload_supabase.py --all-dates  # 기간 필터 없이 전체 댓글
  python upload_supabase.py --dry-run    # DB 에 쓰지 않고 올릴 행 수만 확인

올린 뒤 Supabase SQL Editor 에서 확인 예시
  select stance, count(*), sum(like_count) from cheongyak_comments
  where published_at >= '2026-09-13 00:00+09' and published_at < '2026-09-20 00:00+09'
  group by stance order by 2 desc;
"""
import argparse
import json
import os
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
PERIOD_START, PERIOD_END = "2026-09-13", "2026-09-19"   # 분석 기간 (한국 시간, 양 끝 포함)

DDL = """
CREATE TABLE IF NOT EXISTS cheongyak_comments (
    comment_id    TEXT PRIMARY KEY,
    video_id      TEXT NOT NULL,
    text_raw      TEXT,
    published_at  TIMESTAMPTZ,
    like_count    INTEGER,
    reply_count   INTEGER,
    collected_at  TIMESTAMPTZ,
    stance        TEXT,      -- N 부정·회의 / M 양가·중립 / P 긍정·유지 권장 / X 청약 무관
    topics        TEXT,      -- 관심사 코드 (A~I, 복수면 AB 처럼 붙여 씀)
    outlook       TEXT,      -- U 상승 / D 하락 / 0 없음
    action        TEXT,      -- H 해지 / K 유지 / 0 없음
    model         TEXT,      -- 분류에 쓴 모델 (예: openai/gpt-oss-120b)
    run_folder    TEXT,      -- 결과 폴더 이름 (cheongyak_runs.run_folder)
    uploaded_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS cheongyak_runs (
    run_folder      TEXT PRIMARY KEY,
    video_id        TEXT,
    video_title     TEXT,
    period_start    DATE,
    period_end      DATE,
    n_comments      INTEGER,
    model           TEXT,
    collection_log  JSONB,
    classify_log    JSONB,
    stats           JSONB,
    uploaded_at     TIMESTAMPTZ DEFAULT NOW()
);
"""

UPSERT_COMMENTS = """
INSERT INTO cheongyak_comments
  (comment_id, video_id, text_raw, published_at, like_count, reply_count, collected_at,
   stance, topics, outlook, action, model, run_folder)
VALUES %s
ON CONFLICT (comment_id) DO UPDATE SET
  text_raw = EXCLUDED.text_raw, like_count = EXCLUDED.like_count, reply_count = EXCLUDED.reply_count,
  collected_at = EXCLUDED.collected_at, stance = EXCLUDED.stance, topics = EXCLUDED.topics,
  outlook = EXCLUDED.outlook, action = EXCLUDED.action, model = EXCLUDED.model,
  run_folder = EXCLUDED.run_folder, uploaded_at = NOW()
"""

UPSERT_RUN = """
INSERT INTO cheongyak_runs
  (run_folder, video_id, video_title, period_start, period_end, n_comments, model,
   collection_log, classify_log, stats)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (run_folder) DO UPDATE SET
  video_id = EXCLUDED.video_id, video_title = EXCLUDED.video_title,
  period_start = EXCLUDED.period_start, period_end = EXCLUDED.period_end,
  n_comments = EXCLUDED.n_comments, model = EXCLUDED.model,
  collection_log = EXCLUDED.collection_log, classify_log = EXCLUDED.classify_log,
  stats = EXCLUDED.stats, uploaded_at = NOW()
"""


def latest_run():
    runs = sorted((BASE / "output").glob("*/classified.csv"), key=lambda p: p.stat().st_mtime)
    if not runs:
        raise SystemExit("output/ 에 classified.csv 가 없습니다. classify_comments.py 를 먼저 실행하세요.")
    return runs[-1].parent


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_rows(run, start, end):
    d = pd.read_csv(run / "classified.csv", dtype={"topics": str, "outlook": str, "action": str})
    if start:
        day = pd.to_datetime(d["published_at"], utc=True).dt.tz_convert("Asia/Seoul").dt.strftime("%Y-%m-%d")
        d = d[(day >= start) & (day <= end)]
    d = d[d["stance"].notna()]                      # 분류에 실패한 댓글은 올리지 않는다
    d["topics"] = d["topics"].fillna("")
    d["outlook"] = d["outlook"].fillna("0")
    d["action"] = d["action"].fillna("0")
    if "collected_at" not in d.columns:
        d["collected_at"] = None
    return d


def main():
    parser = argparse.ArgumentParser(description="분류 결과를 Supabase 에 올립니다.")
    parser.add_argument("--run", help="결과 폴더 (기본: output/ 의 가장 최근 폴더)")
    parser.add_argument("--start", default=PERIOD_START, help="작성일 시작 (한국 시간)")
    parser.add_argument("--end", default=PERIOD_END, help="작성일 끝 (한국 시간, 포함)")
    parser.add_argument("--all-dates", action="store_true", help="기간 필터 없이 전체 댓글")
    parser.add_argument("--dry-run", action="store_true", help="DB 에 쓰지 않고 확인만")
    args = parser.parse_args()
    start, end = (None, None) if args.all_dates else (args.start, args.end)

    run = Path(args.run) if args.run else latest_run()
    collection_log = read_json(run / "collection_log.json") or {}
    classify_log = read_json(run / "classify_log.json") or {}
    stats = read_json(run / "stats.json")
    model = classify_log.get("model")
    d = load_rows(run, start, end)
    print(f"결과 폴더: {run.name} / 올릴 댓글 {len(d):,}개"
          + (f" ({start}~{end}, 한국 시간)" if start else " (전체 기간)") + f" / 모델: {model}")
    if stats and stats.get("period_filter") != ([start, end] if start else None):
        print("참고: stats.json 의 기간과 올리는 기간이 다릅니다. analyze_comments.py 를 같은 기간으로 다시 실행하세요.")
    if args.dry_run:
        print("--dry-run: DB 에 쓰지 않았습니다.")
        return 0

    import psycopg2
    from dotenv import load_dotenv
    from psycopg2.extras import Json, execute_values
    load_dotenv(BASE / ".env", override=False)
    db_url = (os.getenv("SUPABASE_CONNECTION_STRING") or "").strip().strip('"')
    if not db_url:
        raise SystemExit(".env 의 SUPABASE_CONNECTION_STRING 에 Supabase 연결 문자열을 넣으세요.")

    rows = [(r.comment_id, r.video_id, r.text_raw, r.published_at, int(r.like_count), int(r.reply_count),
             r.collected_at if isinstance(r.collected_at, str) else None,
             r.stance, r.topics, r.outlook, r.action, model, run.name)
            for r in d.itertuples(index=False)]
    with psycopg2.connect(db_url) as conn:          # 블록이 정상 종료되면 commit, 오류면 rollback
        with conn.cursor() as cur:
            cur.execute(DDL)
            execute_values(cur, UPSERT_COMMENTS, rows, page_size=500)
            cur.execute(UPSERT_RUN, (
                run.name, collection_log.get("video_id"), collection_log.get("title"),
                start, end, len(rows), model,
                Json(collection_log), Json(classify_log), Json(stats) if stats else None))
            cur.execute("SELECT count(*) FROM cheongyak_comments WHERE run_folder = %s", (run.name,))
            total = cur.fetchone()[0]
    print(f"완료: cheongyak_comments 에 {len(rows):,}행 저장(덮어쓰기 포함), 이 폴더의 행은 모두 {total:,}개")
    print("      cheongyak_runs 에 실행 정보 1행 저장")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
