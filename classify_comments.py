"""CNT3054 청약 인식 프로젝트(B안): LLM 댓글 분류.

collect_comments.py 가 저장한 comments.csv 를 읽어 댓글마다
태도(stance) · 관심사(topics) · 집값 전망(outlook) · 통장 행동(action)을 붙인다.

  분석 영상  : 크랩, 「청약통장 다들 왜 깨고 있을까?」
               https://www.youtube.com/watch?v=g4h29mJufpc
  분류 기준  : cy-index.txt  (ev-run.py 가 ev-index.txt 를 읽는 방식과 같음)
  사용 모델  : gpt-oss-120b (OpenRouter 경유)
               모델 소개 https://openrouter.ai/openai/gpt-oss-120b
               API 문서  https://openrouter.ai/docs/quickstart
  API 호출   : openai 파이썬 라이브러리 + base_url 만 OpenRouter 로 변경 (llm-ev.py 와 같은 방식)

  .env 에 필요한 값 (기존 .env 그대로 사용)
    OPENAI_API_KEY       = OpenRouter 키 (https://openrouter.ai/settings/keys)
    OPENAI_API_BASE_URL  = https://openrouter.ai/api/v1
    OPENAI_MODEL_NAME    = openai/gpt-oss-120b   (없으면 이 값을 기본으로 사용)

  실행
    python classify_comments.py                               # output/ 의 가장 최근 수집 폴더
    python classify_comments.py --input output/g4h29mJufpc_20260919T.../comments.csv
    python classify_comments.py --limit 40                    # 앞 40개만 시험
    python classify_comments.py --all-dates                   # 기간 필터 끄기 (기본: 2026-09-13~19 댓글만 분류)

  출력 (입력 CSV 와 같은 폴더)
    classified.csv      댓글별 분류 결과 (원문 열 + stance, topics, outlook, action)
    classify_log.json   모델·배치 크기·실패 건수 등 실행 조건

  llm-ev.py 대비 달라진 점
    - Supabase 대신 CSV 를 읽고 CSV 로 저장 (수업 수집 코드의 출력과 바로 연결)
    - 배치마다 댓글 번호를 붙여 보내고, 응답을 번호로 맞춰 순서가 밀리지 않게 함
    - 빠진 번호·형식 오류는 그 댓글만 다시 요청 (llm-ev.py 는 파싱 실패 시 기본값으로 채움)
    - API 키를 화면에 출력하지 않음
"""
import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
VALID = {
    "stance": set("NMPX"),
    "topics": set("ABCDEFGHI"),
    "outlook": set("UD0"),
    "action": set("HK0"),
}

# 분석 기간 (한국 시간, 양 끝 포함). 팀에서 정한 1주일: 2026-09-13 ~ 2026-09-19
PERIOD_START, PERIOD_END = "2026-09-13", "2026-09-19"


def filter_period(df, start, end):
    """작성일(published_at, UTC)을 한국 날짜로 바꿔 start~end 사이의 댓글만 남긴다."""
    if not start:
        return df
    day = pd.to_datetime(df["published_at"], utc=True).dt.tz_convert("Asia/Seoul").dt.strftime("%Y-%m-%d")
    return df[(day >= start) & (day <= end)]


SYSTEM_PROMPT = (
    "당신은 한국 부동산 정책 여론을 분석하는 연구 보조원입니다. "
    "주어진 분류 기준만 사용해 유튜브 댓글을 분류하고, JSON만 출력합니다."
)


def load_comments(path):
    """수업 수집 코드(text_raw)와 기존 데이터(comment) 두 형식을 모두 읽는다."""
    df = pd.read_csv(path)
    if "text_raw" not in df.columns and "comment" in df.columns:
        df = df.rename(columns={"comment": "text_raw"})
    if "text_raw" not in df.columns:
        raise ValueError(f"댓글 본문 열(text_raw 또는 comment)이 없습니다: {path}")
    df["text_raw"] = df["text_raw"].fillna("").astype(str)
    return df.reset_index(drop=True)


def latest_comments_csv():
    runs = sorted((BASE / "output").glob("*/comments.csv"), key=lambda p: p.stat().st_mtime)
    if not runs:
        raise FileNotFoundError("output/ 에 comments.csv 가 없습니다. collect_comments.py 를 먼저 실행하세요.")
    return runs[-1]


def make_client():
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(BASE / ".env", override=False)
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise ValueError(".env 의 OPENAI_API_KEY 에 OpenRouter 키를 넣으세요.")
    base_url = (os.getenv("OPENAI_API_BASE_URL") or DEFAULT_BASE_URL).strip()
    model = (os.getenv("OPENAI_MODEL_NAME") or DEFAULT_MODEL).strip().strip('"')
    return OpenAI(api_key=key, base_url=base_url), model, base_url


def build_prompt(criteria, batch):
    lines = [f"{i}: {text.replace(chr(10), ' / ')[:500]}" for i, text in zip(batch.index, batch.text_raw)]
    return f"""아래는 분류 기준입니다.

{criteria}

위 기준으로 댓글을 하나씩 분류하세요.
필수 규칙:
1. 모든 번호에 대해 빠짐없이 결과를 냅니다.
2. stance, outlook, action 은 기준에 있는 코드 하나만 씁니다.
3. topics 는 해당하는 코드의 목록이며, 없으면 [] 입니다.
4. JSON만 출력합니다.

JSON 스키마 예시:
{{"results": [{{"id": 12, "stance": "N", "topics": ["A", "B"], "outlook": "0", "action": "H"}}]}}

댓글 (번호: 본문):
""" + "\n".join(lines)


def parse_response(text):
    """모델 응답에서 JSON 을 꺼내 {번호: 결과} 로 만든다. 형식이 틀린 항목은 버린다."""
    m = re.search(r"\{.*\}", text or "", re.S)   # 앞뒤 설명이 붙어도 JSON 부분만 사용
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    out = {}
    for r in data.get("results", []):
        try:
            idx = int(r["id"])
            stance, outlook, action = str(r["stance"]), str(r["outlook"]), str(r["action"])
            topics = r.get("topics") or []
            topics = "".join(sorted({str(t).strip() for t in topics}))
        except (KeyError, TypeError, ValueError):
            continue
        if (stance in VALID["stance"] and outlook in VALID["outlook"] and action in VALID["action"]
                and set(topics) <= VALID["topics"]):
            out[idx] = {"stance": stance, "topics": topics, "outlook": outlook, "action": action}
    return out


def classify_batch(client, model, criteria, batch, max_retry=3):
    """배치 하나를 분류하고, 빠진 번호는 그 댓글만 다시 요청한다."""
    result, todo = {}, batch
    for attempt in range(max_retry):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": build_prompt(criteria, todo)}],
                temperature=0,
                max_tokens=8000,
                response_format={"type": "json_object"},
                extra_body={"reasoning": {"effort": "low"}},   # gpt-oss 추론 길이 (OpenRouter 옵션)
            )
            result.update(parse_response(resp.choices[0].message.content))
        except Exception as exc:  # 네트워크·할당량 오류: 잠시 쉬고 재시도
            print(f"  요청 실패({type(exc).__name__}) — {attempt + 1}번째 재시도")
        missing = [i for i in batch.index if i not in result]
        if not missing:
            break
        todo = batch.loc[missing]
        time.sleep(2 * (attempt + 1))
    return result


def main():
    parser = argparse.ArgumentParser(description="LLM으로 댓글을 분류합니다.")
    parser.add_argument("--input", help="comments.csv 경로 (기본: output/ 의 가장 최근 수집 폴더)")
    parser.add_argument("--criteria", default=str(BASE / "cy-index.txt"))
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--limit", type=int, help="앞에서부터 N개만 분류 (시험용)")
    parser.add_argument("--start", default=PERIOD_START, help="작성일 시작 (한국 시간, 기본 2026-09-13)")
    parser.add_argument("--end", default=PERIOD_END, help="작성일 끝 (한국 시간, 포함, 기본 2026-09-19)")
    parser.add_argument("--all-dates", action="store_true", help="기간 필터 없이 전체 댓글 사용")
    args = parser.parse_args()

    src = Path(args.input) if args.input else latest_comments_csv()
    df = load_comments(src)
    if not args.all_dates:
        df = filter_period(df, args.start, args.end).reset_index(drop=True)
        print(f"기간 필터 {args.start}~{args.end} (한국 시간) → {len(df)}개")
    if args.limit:
        df = df.head(args.limit)
    criteria = Path(args.criteria).read_text(encoding="utf-8")
    client, model, base_url = make_client()
    print(f"입력: {src} ({len(df)}개) / 모델: {model}")

    labels, started = {}, datetime.now(timezone.utc).isoformat()
    for start in range(0, len(df), args.batch_size):
        batch = df.iloc[start:start + args.batch_size]
        labels.update(classify_batch(client, model, criteria, batch))
        print(f"  {min(start + args.batch_size, len(df))}/{len(df)} 완료")

    lab = pd.DataFrame.from_dict(labels, orient="index")
    out = df.join(lab)
    failed = int(out["stance"].isna().sum())
    out_path = src.parent / "classified.csv"
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    log = {"input": str(src.relative_to(BASE)) if src.is_relative_to(BASE) else str(src),
           "model": model, "base_url": base_url, "criteria_file": Path(args.criteria).name,
           "batch_size": args.batch_size, "temperature": 0, "n_comments": len(df),
           "period": None if args.all_dates else {"start": args.start, "end": args.end, "timezone": "Asia/Seoul"},
           "n_failed": failed, "started_at": started,
           "finished_at": datetime.now(timezone.utc).isoformat()}
    (src.parent / "classify_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {out_path} / 분류 실패 {failed}개")
    if failed:
        print("분류 실패한 댓글은 stance 가 비어 있습니다. 다시 실행하거나 --batch-size 를 줄여 보세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
