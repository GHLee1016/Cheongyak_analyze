"""CNT3054: 유튜브 최상위 댓글 수집 실습.
참고: 111usionBin/jtbc-2025의 data_scrape.py. 수업용으로 별도 작성.

[청약 인식 프로젝트(B안)에서 사용한 방법]
  분석 영상 : 크랩, 「청약통장 다들 왜 깨고 있을까?」
              https://www.youtube.com/watch?v=g4h29mJufpc
  사용 API  : YouTube Data API v3 · CommentThreads: list
              https://developers.google.com/youtube/v3/docs/commentThreads/list
  실행      : python collect_comments.py --video g4h29mJufpc --all --start 2026-09-13 --end 2026-09-19
              (--all: 다음 페이지가 없을 때까지 모두 수집. 수업 원본 기본값은 1페이지=100개)
              (--start/--end: 한국 시간 기준 작성일로 거른다. 원본 로그의 comment_date_filter 에 기록)
  다음 단계 : python classify_comments.py   (LLM 분류, OpenRouter · gpt-oss-120b)

  수정 내역 (수업 원본 대비)
    - --all 옵션 추가 (전체 댓글 수집)
    - --start/--end 옵션 추가 (작성일 필터, 한국 시간). 최신순(order=time)으로 받으므로
      시작일보다 오래된 댓글이 나오면 그 페이지에서 수집을 멈춘다 (API 할당량 절약)
    - 나머지 수집·저장 방식(output/<영상ID>_<시각>/comments.csv, collection_log.json)은 원본 그대로
"""
import argparse
import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))   # 작성일 필터는 한국 시간 기준
COLUMNS = ["video_id", "comment_id", "text_raw", "published_at",
           "like_count", "reply_count", "collected_at"]


def parse_video_id(value):
    """영상 ID 또는 일반 영상/공유/Shorts/live URL에서 ID를 읽는다."""
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    u = urlparse(value)
    host = (u.hostname or "").lower()
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = u.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        pieces = u.path.strip("/").split("/")
        candidate = (parse_qs(u.query).get("v", [""])[0]
                     if u.path == "/watch" else
                     pieces[1] if len(pieces) > 1 and pieces[0] in {"shorts", "live", "embed"} else "")
    else:
        candidate = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        raise ValueError("영상 ID 11자리 또는 유튜브 영상 URL을 입력하세요. 재생목록 URL은 사용할 수 없습니다.")
    return candidate


def make_youtube_client():
    """코드와 같은 폴더의 .env에서 키를 읽고 API 클라이언트를 만든다."""
    from dotenv import load_dotenv
    from googleapiclient.discovery import build
    import httplib2
    load_dotenv(BASE / ".env", override=False)
    api_key = (os.getenv("google_cloud_api_key") or "").strip()
    if not api_key or api_key == "YOUR_API_KEY":
        raise ValueError(".env의 google_cloud_api_key에 본인 API 키를 입력하세요.")
    return build("youtube", "v3", developerKey=api_key,
                 http=httplib2.Http(timeout=30), cache_discovery=False)


def get_video_info(youtube, video_id):
    response = youtube.videos().list(part="snippet", id=video_id).execute()
    items = response.get("items", [])
    if not items:
        raise ValueError("조회 가능한 영상이 없습니다. 영상 URL과 공개 여부를 확인하세요.")
    s = items[0]["snippet"]
    return {"video_id": video_id, "title": s["title"],
            "channel_title": s["channelTitle"], "channel_id": s["channelId"],
            "video_published_at": s["publishedAt"]}


def parse_comment(item, video_id, collected_at):
    """중첩 딕셔너리에서 CSV 한 행에 필요한 값만 선택한다."""
    top = item["snippet"]["topLevelComment"]
    comment = top["snippet"]
    return {
        "video_id": video_id,
        "comment_id": top["id"],
        "text_raw": comment["textDisplay"],
        "published_at": comment["publishedAt"],
        "like_count": comment["likeCount"],
        "reply_count": item["snippet"].get("totalReplyCount", 0),
        "collected_at": collected_at,
    }


def error_info(exc):
    """키가 포함될 수 있는 요청 URL 대신 상태 코드와 오류 이유만 반환한다."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    reason = type(exc).__name__
    try:
        body = json.loads(exc.content)
        reason = body["error"]["errors"][0]["reason"]
    except (AttributeError, KeyError, IndexError, ValueError, TypeError):
        pass
    return {"http_status": status, "reason": reason}


def kst_date(iso):
    """'2026-09-13T15:00:00Z' 같은 UTC 시각을 한국 날짜로 바꾼다."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KST).date()


def collect_comments(youtube, video_id, max_pages=1, page_size=100, date_filter=None):
    """date_filter=(시작일, 종료일) 이면 그 기간(한국 시간)에 작성된 댓글만 저장한다."""
    rows, seen = [], set()
    page_token = None
    log = {"pages_requested": 0, "pages_received": 0,
           "received_items": 0, "duplicates_skipped": 0, "date_excluded": 0,
           "stop_reason": "page_limit", "has_more": None,
           "error": None, "collected_at": datetime.now(timezone.utc).isoformat()}
    for _ in range(max_pages):
        try:
            log["pages_requested"] += 1
            response = youtube.commentThreads().list(
                part="snippet", videoId=video_id,
                maxResults=page_size, order="time",
                textFormat="plainText", pageToken=page_token,
            ).execute()
        except Exception as exc:
            log.update(stop_reason="error", has_more=None, error=error_info(exc))
            break
        log["pages_received"] += 1
        for item in response.get("items", []):
            log["received_items"] += 1
            row = parse_comment(item, video_id, log["collected_at"])
            if row["comment_id"] in seen:
                log["duplicates_skipped"] += 1
                continue
            seen.add(row["comment_id"])
            if date_filter:
                day = kst_date(row["published_at"])
                if not date_filter[0] <= day <= date_filter[1]:
                    log["date_excluded"] += 1
                    continue
            rows.append(row)
        page_token = response.get("nextPageToken")
        items = response.get("items", [])
        if date_filter and page_token and items and \
                kst_date(items[-1]["snippet"]["topLevelComment"]["snippet"]["publishedAt"]) < date_filter[0]:
            # 최신순이므로 이 뒤로는 모두 시작일보다 오래된 댓글이다
            log.update(stop_reason="reached_start_date", has_more=True)
            break
        log["has_more"] = bool(page_token)
        if not page_token:
            log["stop_reason"] = "no_next_page"
            break
    log["saved_rows"] = len(rows)
    return rows, log


def save_results(rows, log, video_info, max_pages, page_size, output_root, demo=False, date_filter=None):
    """실행마다 새 폴더에 원문 CSV와 수집 조건 JSON을 함께 저장한다."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = output_root / f"{video_info['video_id']}_{stamp}"
    folder.mkdir(parents=True, exist_ok=False)
    with (folder / "comments.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    metadata = {"mode": "DEMO_FICTIONAL" if demo else "LIVE_API", **video_info,
                "order": "time", "scope": "top_level_only",
                "max_pages": max_pages, "page_size": page_size,
                "comment_date_filter": ({"start": str(date_filter[0]), "end": str(date_filter[1]),
                                         "timezone": "Asia/Seoul"} if date_filter else None), **log}
    (folder / "collection_log.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return folder


class DemoRequest:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class DemoYouTube:
    """실제 API를 호출하지 않는 가상 응답. JTBC 실제 댓글이 아니다."""
    def __init__(self):
        self.pages = json.loads((BASE / "demo_pages.json").read_text(encoding="utf-8"))

    def commentThreads(self):
        return self

    def list(self, **kwargs):
        index = 1 if kwargs.get("pageToken") == "DEMO_PAGE_2" else 0
        return DemoRequest(self.pages[index])


def main():
    parser = argparse.ArgumentParser(description="유튜브 최상위 댓글을 CSV로 저장합니다.")
    parser.add_argument("--video", help="영상 URL 또는 영상 ID")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--all", action="store_true",
                        help="다음 페이지가 없을 때까지 전부 수집 (최대 1000페이지)")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--start", type=date.fromisoformat, help="작성일 시작 (예: 2026-09-13, 한국 시간)")
    parser.add_argument("--end", type=date.fromisoformat, help="작성일 끝 (예: 2026-09-19, 한국 시간, 포함)")
    parser.add_argument("--check", action="store_true", help="키와 영상 조회만 확인")
    parser.add_argument("--demo", action="store_true", help="가상 응답으로 실행")
    args = parser.parse_args()
    if args.all:
        args.max_pages = 1000  # 페이지당 100개 → 최대 10만 개. 보통 no_next_page 에서 먼저 멈춘다
    if args.max_pages < 1 or not 1 <= args.page_size <= 100:
        parser.error("max-pages는 1 이상, page-size는 1~100이어야 합니다.")
    if bool(args.start) != bool(args.end) or (args.start and args.start > args.end):
        parser.error("--start 와 --end 는 함께, 시작일 <= 종료일 로 입력하세요.")
    date_filter = (args.start, args.end) if args.start else None
    if args.demo and args.check:
        parser.error("--demo와 --check는 함께 사용하지 않습니다.")
    if not args.demo and not args.video:
        parser.error("--video에 영상 URL 또는 ID를 입력하세요.")
    try:
        if args.demo:
            youtube = DemoYouTube()
            info = {"video_id": "DEMO_VIDEO", "title": "가상 뉴스 영상: 수업용",
                    "channel_title": "가상 채널", "channel_id": "DEMO_CHANNEL",
                    "video_published_at": "2026-09-01T00:00:00Z"}
            print("[DEMO] 실제 JTBC 댓글이 아닌 가상 응답입니다. API 호출 없음.")
            print("데모는 페이지당 2개, 총 2페이지로 고정되어 있습니다.")
            page_size = 2
        else:
            video_id = parse_video_id(args.video)
            youtube = make_youtube_client()
            info = get_video_info(youtube, video_id)
            page_size = args.page_size
        print(f"채널: {info['channel_title']} / 제목: {info['title']}")
        if args.check:
            print("API 연결 및 영상 조회 성공. 선택한 JTBC 뉴스룸 영상인지 확인하세요.")
            return 0
        rows, log = collect_comments(youtube, info["video_id"], args.max_pages, page_size, date_filter)
        folder = save_results(rows, log, info, args.max_pages, page_size, BASE / "output", args.demo, date_filter)
        print(f"저장: {len(rows)}개 / 받은 페이지: {log['pages_received']}"
              + (f" / 기간 밖이라 제외: {log['date_excluded']}개 ({args.start}~{args.end})" if date_filter else ""))
        print(f"종료 이유: {log['stop_reason']} / 다음 페이지 존재: {log['has_more']}")
        print(f"저장 폴더: {folder}")
        if log["error"]:
            print(f"오류: {log['error']} / 지금까지 받은 댓글만 저장했습니다.")
            return 1
        return 0
    except (ValueError, ModuleNotFoundError) as exc:
        print(f"설정 확인: {exc}")
        return 1
    except Exception as exc:
        print(f"요청 실패: {error_info(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
