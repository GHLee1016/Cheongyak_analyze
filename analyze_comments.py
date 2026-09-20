"""CNT3054 청약 인식 프로젝트(B안): 분류 결과 집계 · 그림 · 통계.

classify_comments.py 가 만든 classified.csv 를 읽어 보고서(Ⅱ-ⅱ 1~3절)에 들어가는 수치와 그림을 만든다.

  분석 영상 : 크랩, 「청약통장 다들 왜 깨고 있을까?」 https://www.youtube.com/watch?v=g4h29mJufpc
  분류 기준 : cy-index.txt

  실행
    python analyze_comments.py                                   # output/ 의 가장 최근 classified.csv
    python analyze_comments.py --input output/<폴더>/classified.csv
    python analyze_comments.py --all-dates                       # 기간 필터 끄기 (기본: 2026-09-13~19)

  출력 (입력 CSV 와 같은 폴더)
    stats.json          보고서에 들어가는 모든 수치의 기준
    topic_summary.csv   관심사별 언급 비율 · 좋아요 점유율
    fig1_stance.png     그림 1. 태도 분포 (댓글 수 기준 vs 좋아요 가중)
    fig2_topics.png     그림 2. 관심사별 언급 비율과 좋아요 점유율
  그림 색은 색각이상자도 구분하기 쉬운 파랑·주황·청록을 사용했다.
"""
import argparse
import json
import os
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402

BASE = Path(__file__).resolve().parent

# 분석 기간 (한국 시간, 양 끝 포함). 팀에서 정한 1주일: 2026-09-13 ~ 2026-09-19
PERIOD_START, PERIOD_END = "2026-09-13", "2026-09-19"


def filter_period(df, start, end):
    """작성일(published_at, UTC)을 한국 날짜로 바꿔 start~end 사이의 댓글만 남긴다."""
    if not start:
        return df
    day = pd.to_datetime(df["published_at"], utc=True).dt.tz_convert("Asia/Seoul").dt.strftime("%Y-%m-%d")
    return df[(day >= start) & (day <= end)]


# 분류 코드 → 한글 이름 (cy-index.txt 와 같은 순서)
STANCE = {"N": "부정·회의", "M": "양가·중립", "P": "긍정·유지 권장", "X": "청약 무관"}
TOPICS = {
    "A": "분양가·집값 부담", "B": "대출규제·자금조달", "C": "가점·당첨확률",
    "D": "제도 불공정(1인가구·소득요건 등)", "E": "대체 투자·낮은 금리", "F": "정부·정치 불신",
    "G": "임대·대출우대 등 부가 기능", "H": "수도권 집중·지방·인구", "I": "신축 품질·하자",
}
# 정치 언급 댓글을 찾는 키워드 (보고서 “정치 언급 61개” 산출용)
POLITICAL_PATTERN = r"이재명|재명|찢|민주당|문재인|문죄|재앙|좌파|국힘|윤석|박근혜|이명박|대통령|정권"


INK, SUB = "#0b0b0b", "#52514e"
COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]   # 부정 / 양가 / 긍정


def set_korean_font():
    """설치된 한글 글꼴을 찾아 matplotlib 에 등록한다 (macOS: AppleGothic, Windows: Malgun Gothic)."""
    candidates = ["AppleGothic", "Malgun Gothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR", "Noto Sans CJK JP"]
    for path in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]:
        if os.path.exists(path):
            fm.fontManager.addfont(path)
    installed = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in installed:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def _r(x, nd=1):
    """NaN(빈 집단의 평균 등)은 0 으로 바꿔 JSON 으로 저장할 수 있게 한다."""
    return 0.0 if pd.isna(x) else round(float(x), nd)


def compute_stats(d: pd.DataFrame) -> dict:
    n, likes_total = len(d), int(d.like_count.sum())
    rel = d[d.stance != "X"]                      # 청약 관련 댓글
    has = {k: d.topics.str.contains(k) for k in TOPICS}
    pol = d.comment.str.contains(POLITICAL_PATTERN, regex=True)
    pol_dates = d[pol].published_kst.dt.date.astype(str).value_counts()
    amounts = d.comment.str.findall(r"(\d+(?:\.\d+)?)\s*억").explode().dropna().astype(float)
    top_sorted = d.like_count.sort_values(ascending=False)
    rel_wo = rel.drop(index=top_sorted.index[:1], errors="ignore")   # 좋아요 1위 댓글을 뺀 관련 댓글

    def reasons(code):
        s = d[d.action == code].topics.apply(list).explode().dropna()
        return {TOPICS[k]: int(v) for k, v in s.value_counts().items()}

    st = {
        "n_comments": n,
        "likes_total": likes_total,
        "period_kst": [str(d.published_kst.min().date()), str(d.published_kst.max().date())],
        "share_zero_like": round((d.like_count == 0).mean() * 100, 1),
        "top10_like_share": _r(top_sorted.head(10).sum() / max(likes_total, 1) * 100),
        "n_irrelevant": int((d.stance == "X").sum()),
        "n_relevant": len(rel),
        "likes_relevant": int(rel.like_count.sum()),
        "stance_count": {k: int((rel.stance == k).sum()) for k in "NMP"},
        "stance_share": {k: _r((rel.stance == k).mean() * 100) for k in "NMP"},
        "stance_like_share": {k: _r(rel[rel.stance == k].like_count.sum() / max(rel.like_count.sum(), 1) * 100) for k in "NMP"},
        "stance_mean_likes": {k: _r(d[d.stance == k].like_count.mean()) for k in "NMPX"},
        "topic_share": {k: round(v.mean() * 100, 1) for k, v in has.items()},
        "topic_count": {k: int(v.sum()) for k, v in has.items()},
        "outlook_like": {k: int(d[d.outlook == k].like_count.sum()) for k in "UD"},
        "action_by_stance": {k: {s_: int(((d.action == k) & (d.stance == s_)).sum()) for s_ in "NMPX"} for k in "HK"},
        "topic_like_share": {k: _r(d[v].like_count.sum() / max(likes_total, 1) * 100) for k, v in has.items()},
        "outlook": {k: int((d.outlook == k).sum()) for k in "UD"},
        "outlook_share": round((d.outlook != "0").mean() * 100, 1),
        "action": {k: int((d.action == k).sum()) for k in "HK"},
        "reasons_cancel": reasons("H"),
        "reasons_keep": reasons("K"),
        "political_n": int(pol.sum()),
        "political_mean_likes": _r(d[pol].like_count.mean()),
        "political_by_date": pol_dates.sort_index().to_dict(),
        "amount_mentions": int(len(amounts)),
        "amount_median_eok": float(amounts.median()) if len(amounts) else None,
        # 좋아요 쏠림 점검: 가장 많이 받은 댓글 1개가 결과를 얼마나 좌우하는지
        "top1_like_share": _r(top_sorted.head(1).sum() / max(likes_total, 1) * 100),
        "stance_like_share_wo_top1": {k: _r(rel_wo[rel_wo.stance == k].like_count.sum()
                                            / max(rel_wo.like_count.sum(), 1) * 100) for k in "NMP"},
        "comments_by_date": d.published_kst.dt.strftime("%Y-%m-%d").value_counts().sort_index().to_dict(),
        "top_comments": d.sort_values("like_count", ascending=False).head(30)[["like_count", "stance", "comment"]]
                         .to_dict("records"),
    }
    return st


def fig_stance(st, path):
    rows = [(f"댓글 수 기준\n(n={st['n_relevant']:,})", st["stance_share"]),
            (f"좋아요 가중\n(좋아요 {st['likes_relevant']:,})", st["stance_like_share"])]
    labels = [("N", STANCE["N"]), ("M", STANCE["M"]), ("P", STANCE["P"])]
    fig, ax = plt.subplots(figsize=(8, 2.6), dpi=200)
    for i, (name, s) in enumerate(rows):
        left = 0
        for j, (k, _) in enumerate(labels):
            w = s[k]
            ax.barh(i, w, left=left, color=COLORS[j], height=0.55, edgecolor="#fcfcfb", linewidth=2)
            if w > 4:
                ax.text(left + w / 2, i, f"{w:.1f}%", ha="center", va="center", color="white", fontsize=10)
            left += w
    ax.set_yticks([0, 1]); ax.set_yticklabels([r[0] for r in rows], color=INK, fontsize=10)
    ax.invert_yaxis(); ax.set_xlim(0, 100)
    ax.set_xticks(range(0, 101, 25)); ax.set_xticklabels([f"{x}%" for x in range(0, 101, 25)], color=SUB, fontsize=9)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in COLORS], [l for _, l in labels],
              ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.0), frameon=False, fontsize=9)
    plt.tight_layout(); plt.savefig(path, facecolor="white"); plt.close()


def fig_topics(st, path):
    share = pd.Series(st["topic_share"]).sort_values()
    likes = pd.Series(st["topic_like_share"])[share.index]
    names = [TOPICS[k] for k in share.index]
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.2), dpi=200, sharey=True)
    for ax, s, title in [(axes[0], share, "전체 댓글 중 언급 비율"), (axes[1], likes, "전체 좋아요 중 해당 댓글 비율")]:
        ax.barh(range(len(s)), s.values, color=COLORS[0], height=0.6)
        for i, v in enumerate(s.values):
            ax.text(v + 0.8, i, f"{v:.1f}%", va="center", fontsize=8.5, color=INK)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.set_xlim(0, max(s.max() * 1.25, 10)); ax.xaxis.set_visible(False)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.tick_params(length=0)
    axes[0].set_yticks(range(len(share))); axes[0].set_yticklabels(names, fontsize=9, color=INK)
    fig.text(0.01, 0.01, f"* 한 댓글에 여러 관심사가 함께 나올 수 있어 합계는 100%를 넘음 (n={st['n_comments']:,})", fontsize=8, color=SUB)
    plt.tight_layout(rect=(0, 0.04, 1, 1)); plt.savefig(path, facecolor="white"); plt.close()


def load(path):
    d = pd.read_csv(path, dtype={"stance": str, "topics": str, "outlook": str, "action": str})
    if "text_raw" not in d.columns and "comment" in d.columns:
        d = d.rename(columns={"comment": "text_raw"})
    d["comment"] = d["text_raw"].fillna("").astype(str)
    missing = d.stance.isna().sum()
    if missing:
        print(f"경고: 분류되지 않은 댓글 {missing}개는 집계에서 뺍니다.")
        d = d[d.stance.notna()].copy()
    d["topics"] = d.topics.fillna("").replace("0", "")
    for c in ("outlook", "action"):
        d[c] = d[c].fillna("0")
    d["published_kst"] = pd.to_datetime(d.published_at, utc=True).dt.tz_convert("Asia/Seoul")
    return d


def latest_classified():
    runs = sorted((BASE / "output").glob("*/classified.csv"), key=lambda p: p.stat().st_mtime)
    if not runs:
        raise FileNotFoundError("output/ 에 classified.csv 가 없습니다. classify_comments.py 를 먼저 실행하세요.")
    return runs[-1]


# ---------------------------------------------------------------------------
# 일주일 동안의 변화 (날짜별·구간별 태도, 관심사, 행동)
# ---------------------------------------------------------------------------
# 날짜별 댓글 수가 뒤로 갈수록 크게 줄어(9/19는 12개) 하루 단위 비율은 흔들리기 쉽다.
# 그래서 비슷한 규모가 되도록 세 구간(첫날 / 둘째·셋째 날 / 나머지 나흘)으로도 묶어 비교한다.
def period_label(day):
    if day <= "2026-09-13":
        return "9/13"
    if day <= "2026-09-15":
        return "9/14~15"
    return "9/16~19"


def chi_square(table):
    """태도 × 구간 교차표의 카이제곱 독립성 검정 (scipy 가 있으면 p값까지)."""
    try:
        from scipy.stats import chi2_contingency
        chi2, pval, dof, _ = chi2_contingency(table)
        return {"chi2": _r(chi2, 2), "p": _r(pval, 3), "dof": int(dof)}
    except ImportError:
        return None


def compute_trend(d):
    d = d.copy()
    d["day"] = d.published_kst.dt.strftime("%Y-%m-%d")
    d["period"] = d.day.map(period_label)

    def summarize(g):
        rel = g[g.stance != "X"]
        n_rel = max(len(rel), 1)
        return {
            "n": int(len(g)), "n_relevant": int(len(rel)),
            "stance_share": {k: _r((rel.stance == k).sum() / n_rel * 100) for k in "NMP"},
            "irrelevant_share": _r((g.stance == "X").mean() * 100),
            "topic_share": {k: _r(g.topics.str.contains(k).mean() * 100) for k in TOPICS},
            "action": {k: int((g.action == k).sum()) for k in "HK"},
            "outlook": {k: int((g.outlook == k).sum()) for k in "UD"},
            "political": int(g.comment.str.contains(POLITICAL_PATTERN, regex=True).sum()),
            "likes": int(g.like_count.sum()),
        }

    rel = d[d.stance != "X"]
    return {
        "daily": {day: summarize(g) for day, g in d.groupby("day")},
        "period": {p: summarize(g) for p, g in d.groupby("period")},
        "period_test": chi_square(pd.crosstab(rel.period, rel.stance)),
        "daily_test": chi_square(pd.crosstab(rel.day, rel.stance)),
    }


def fig_trend(trend, path):
    """위: 날짜별 댓글 수 / 아래: 날짜별 태도 비중(청약 관련 댓글 기준, 100% 누적)."""
    days = sorted(trend["daily"])
    labels = [f"{int(x[5:7])}/{int(x[8:])}" for x in days]
    n = [trend["daily"][x]["n"] for x in days]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 5.2), dpi=200, sharex=True,
                                   gridspec_kw={"height_ratios": [1, 2.2]})
    ax1.bar(range(len(days)), n, color="#9fb8d9", width=0.6)
    for i, v in enumerate(n):
        ax1.text(i, v + max(n) * 0.03, f"{v}", ha="center", va="bottom", fontsize=8.5, color=INK)
    ax1.set_ylim(0, max(n) * 1.25); ax1.set_yticks([])
    ax1.set_title("날짜별 댓글 수", fontsize=10, color=INK, loc="left")
    names = [("N", STANCE["N"]), ("M", STANCE["M"]), ("P", STANCE["P"])]
    bottom = [0] * len(days)
    for j, (k, _) in enumerate(names):
        vals = [trend["daily"][x]["stance_share"][k] for x in days]
        ax2.bar(range(len(days)), vals, bottom=bottom, color=COLORS[j], width=0.6, edgecolor="#fcfcfb", linewidth=1.5)
        for i, v in enumerate(vals):
            if v >= 7:
                ax2.text(i, bottom[i] + v / 2, f"{v:.0f}%", ha="center", va="center", fontsize=8, color="white")
        bottom = [a + b for a, b in zip(bottom, vals)]
    ax2.set_ylim(0, 100); ax2.set_yticks([0, 50, 100]); ax2.set_yticklabels(["0%", "50%", "100%"], fontsize=8, color=SUB)
    ax2.set_title("날짜별 태도 비중 (청약 관련 댓글 기준)", fontsize=10, color=INK, loc="left")
    ax2.set_xticks(range(len(days))); ax2.set_xticklabels(labels, fontsize=9, color=INK)
    for ax in (ax1, ax2):
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.tick_params(length=0)
    ax2.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in COLORS], [l for _, l in names],
               ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12), frameon=False, fontsize=9)
    fig.text(0.01, 0.005, "* 9/16 이후는 하루 댓글이 12~61개로 적어 비율 변동이 큼", fontsize=7.5, color=SUB)
    plt.tight_layout(rect=(0, 0.02, 1, 1)); plt.savefig(path, facecolor="white"); plt.close()


def main():
    parser = argparse.ArgumentParser(description="분류 결과를 집계합니다.")
    parser.add_argument("--input", help="classified.csv 경로")
    parser.add_argument("--start", default=PERIOD_START, help="작성일 시작 (한국 시간, 기본 2026-09-13)")
    parser.add_argument("--end", default=PERIOD_END, help="작성일 끝 (한국 시간, 포함, 기본 2026-09-19)")
    parser.add_argument("--all-dates", action="store_true", help="기간 필터 없이 전체 댓글 사용")
    args = parser.parse_args()
    src = Path(args.input) if args.input else latest_classified()
    out_dir = src.parent

    set_korean_font()
    d = load(src)
    n_all, n_all_replies = len(d), int(d.reply_count.sum())      # 기간 필터 전 전체 수집량
    if not args.all_dates:
        d = filter_period(d, args.start, args.end).copy()
        print(f"기간 필터 {args.start}~{args.end} (한국 시간) → {len(d):,}개")
    st = compute_stats(d)
    st["source"] = src.name
    st["n_collected"], st["n_collected_with_replies"] = n_all, n_all + n_all_replies
    st["period_filter"] = None if args.all_dates else [args.start, args.end]
    # 분류 조건 (classify_comments.py 가 남긴 classify_log.json). 없으면 보고서 초안에 쓴 Claude 분류로 본다.
    log_path = out_dir / "classify_log.json"
    if log_path.exists():
        log = json.loads(log_path.read_text(encoding="utf-8"))
        st["model_label"] = f"{log['model']} (OpenRouter 경유)"
        st["batch_size"] = log["batch_size"]
    else:
        st["model_label"] = "Claude (Anthropic)"
        st["batch_size"] = 150
    st["trend"] = compute_trend(d)
    (out_dir / "stats.json").write_text(json.dumps(st, ensure_ascii=False, indent=2, default=str, allow_nan=False), encoding="utf-8")
    pd.DataFrame({"관심사": list(TOPICS.values()),
                  "언급비율(%)": [st["topic_share"][k] for k in TOPICS],
                  "좋아요점유율(%)": [st["topic_like_share"][k] for k in TOPICS]}) \
      .sort_values("언급비율(%)", ascending=False) \
      .to_csv(out_dir / "topic_summary.csv", index=False, encoding="utf-8-sig")
    fig_stance(st, out_dir / "fig1_stance.png")
    fig_topics(st, out_dir / "fig2_topics.png")
    trend = compute_trend(d)
    fig_trend(trend, out_dir / "fig4_daily_trend.png")

    s = st
    print(f"입력: {src} — 댓글 {s['n_comments']:,}개 (관련 {s['n_relevant']}, 무관 {s['n_irrelevant']})")
    print(f"태도(댓글 수)  부정 {s['stance_share']['N']}% · 양가 {s['stance_share']['M']}% · 긍정 {s['stance_share']['P']}%")
    print(f"태도(좋아요)   부정 {s['stance_like_share']['N']}% · 양가 {s['stance_like_share']['M']}% · 긍정 {s['stance_like_share']['P']}%")
    for k in sorted(TOPICS, key=lambda k: -s["topic_share"][k]):
        print(f"  {TOPICS[k]:<22} 언급 {s['topic_share'][k]:>5}%  좋아요 {s['topic_like_share'][k]:>5}%")
    print(f"집값 전망 언급 {s['outlook_share']}% (상승 {s['outlook']['U']}, 하락 {s['outlook']['D']})")
    print(f"통장 행동 해지 {s['action']['H']} · 유지 {s['action']['K']} / 정치 언급 {s['political_n']}개(평균 좋아요 {s['political_mean_likes']})")
    print(f"저장 폴더: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
