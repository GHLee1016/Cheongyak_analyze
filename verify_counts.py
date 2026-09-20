"""CNT3054 청약 인식 프로젝트(B안): 단계별 건수 대조 (CSV · 로그 · Supabase DB)

수집 → 분류 → DB 저장 단계마다 댓글 수가 맞는지, 중복 저장이 없는지 한 번에 확인한다.
결과는 결과 폴더의 verify_counts.json 에 저장되고, 보고서 표 5의 근거가 된다.

  확인 항목
    1. collection_log.json 의 받은 댓글 수 · 중복 제외 수 · 저장 수  vs  comments.csv 행 수
    2. comments.csv 의 comment_id 고유 개수 (중복이 없으면 행 수와 같음)
    3. 분석 기간(2026-09-13~19, 한국 시간) 댓글 수  vs  classified.csv 의 분류 완료 수
    4. Supabase cheongyak_comments 전체 행 수 · comment_id 고유 개수 · 이 결과 폴더의 행 수 · 중복 comment_id 수
    5. cheongyak_comments 의 기본 키(PRIMARY KEY) 가 comment_id 인지

  Supabase 대시보드 (프로젝트 권한이 있어야 열림)
    https://supabase.com/dashboard/project/evfplzqpewwjtttlmvxc/editor

  실행
    python verify_counts.py            # .env 의 SUPABASE_CONNECTION_STRING 으로 DB 까지 조회
    python verify_counts.py --no-db    # 파일만 대조
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
PERIOD_START, PERIOD_END = "2026-09-13", "2026-09-19"


def latest_run():
    runs = sorted((BASE / "output").glob("*/classified.csv"), key=lambda p: p.stat().st_mtime)
    if not runs:
        raise SystemExit("output/ 에 classified.csv 가 없습니다.")
    return runs[-1].parent


def in_period(df):
    day = pd.to_datetime(df["published_at"], utc=True).dt.tz_convert("Asia/Seoul").dt.strftime("%Y-%m-%d")
    return df[(day >= PERIOD_START) & (day <= PERIOD_END)]


def file_counts(run):
    log = json.loads((run / "collection_log.json").read_text(encoding="utf-8"))
    clog = json.loads((run / "classify_log.json").read_text(encoding="utf-8"))
    com = pd.read_csv(run / "comments.csv", dtype=str)
    cls = pd.read_csv(run / "classified.csv", dtype=str)
    week = in_period(cls)
    return {
        "log_received_items": log.get("received_items"),
        "log_duplicates_skipped": log.get("duplicates_skipped"),
        "log_saved_rows": log.get("saved_rows"),
        "log_pages": log.get("pages_received"),
        "log_stop_reason": log.get("stop_reason"),
        "comments_csv_rows": len(com),
        "comments_csv_unique_ids": int(com["comment_id"].nunique()),
        "classify_log_n_comments": clog.get("n_comments"),
        "classify_log_n_failed": clog.get("n_failed"),
        "classified_csv_rows": len(cls),
        "period_rows": len(week),
        "period_classified": int(week["stance"].notna().sum()),
    }


def db_counts(run):
    import psycopg2
    from dotenv import load_dotenv
    load_dotenv(BASE / ".env", override=False)
    url = (os.getenv("SUPABASE_CONNECTION_STRING") or "").strip().strip('"')
    if not url:
        raise SystemExit(".env 에 SUPABASE_CONNECTION_STRING 이 없습니다.")
    q = {
        "db_total_rows": "SELECT count(*) FROM cheongyak_comments",
        "db_unique_ids": "SELECT count(DISTINCT comment_id) FROM cheongyak_comments",
        "db_run_rows": ("SELECT count(*) FROM cheongyak_comments WHERE run_folder = %s", (run.name,)),
        "db_duplicate_ids": "SELECT count(*) FROM (SELECT comment_id FROM cheongyak_comments "
                            "GROUP BY comment_id HAVING count(*) > 1) t",
        "db_runs_rows": "SELECT count(*) FROM cheongyak_runs",
        "db_primary_key": "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                          "WHERE conrelid = 'cheongyak_comments'::regclass AND contype = 'p'",
    }
    out = {}
    with psycopg2.connect(url, connect_timeout=15) as conn, conn.cursor() as cur:
        for k, v in q.items():
            sql, args = v if isinstance(v, tuple) else (v, None)
            cur.execute(sql, args)
            out[k] = cur.fetchone()[0]
    out["db_source"] = "live query (verify_counts.py)"
    return out


def main():
    ap = argparse.ArgumentParser(description="단계별 건수 대조")
    ap.add_argument("--run", help="결과 폴더 (기본: output/ 의 가장 최근 폴더)")
    ap.add_argument("--no-db", action="store_true")
    args = ap.parse_args()
    run = Path(args.run) if args.run else latest_run()

    res = {"run_folder": run.name, "checked_at": datetime.now(timezone.utc).isoformat(), **file_counts(run)}
    path = run / "verify_counts.json"
    if not args.no_db:
        res.update(db_counts(run))
    elif path.exists():   # 이전에 조회한 DB 값은 유지
        old = json.loads(path.read_text(encoding="utf-8"))
        res.update({k: v for k, v in old.items() if k.startswith("db_")})
    path.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = lambda b: "일치" if b else "확인 필요"
    print(f"결과 폴더: {run.name}")
    print(f"  수집 로그 받은 댓글 {res['log_received_items']} / 중복 제외 {res['log_duplicates_skipped']} / 저장 {res['log_saved_rows']}")
    print(f"  comments.csv 행 {res['comments_csv_rows']} / 고유 comment_id {res['comments_csv_unique_ids']}"
          f"  → {ok(res['comments_csv_rows'] == res['log_saved_rows'] == res['comments_csv_unique_ids'])}")
    print(f"  분석 기간 댓글 {res['period_rows']} / 분류 완료 {res['period_classified']}"
          f"  → {ok(res['period_rows'] == res['period_classified'])}")
    if "db_run_rows" in res:
        print(f"  DB 전체 {res.get('db_total_rows')} / 고유 comment_id {res.get('db_unique_ids')} / 이 폴더 {res['db_run_rows']}"
              f" / 중복 comment_id {res.get('db_duplicate_ids')}  → {ok(res['db_run_rows'] == res['period_rows'])}")
        print(f"  기본 키: {res.get('db_primary_key')}")
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
