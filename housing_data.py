"""CNT3054 청약 인식 프로젝트(B안): 주택시장 데이터 수집·정리 (보고서 Ⅱ-ⅰ-3, 표 3)

(1) 국토교통부 아파트 매매 실거래가 상세 자료 — 오픈API, 자동 수집
    데이터셋 : https://www.data.go.kr/data/15126468/openapi.do
    엔드포인트: https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev
    파라미터 : serviceKey, LAWD_CD(법정동코드 5자리), DEAL_YMD(YYYYMM), pageNo, numOfRows
    법정동코드: https://www.code.go.kr/stdcode/regCodeL.do

(2) 한국부동산원 파일데이터 — 포털에서 내려받아 data/manual/ 에 저장한 뒤 이 스크립트가 읽는다
    - 청약통장 전체 가입현황      https://www.data.go.kr/data/15088657/fileData.do
    - 청약통장 가입기간별 가입현황  https://www.data.go.kr/data/15088656/fileData.do
    - 지역별 청약 신청자 정보      https://www.data.go.kr/data/15110975/fileData.do
    - 지역별 청약 당첨자 정보      https://www.data.go.kr/data/15110976/fileData.do
    - 중위매매가격                 https://www.data.go.kr/data/15112206/fileData.do
    - 중위단위매매가격              https://www.data.go.kr/data/15112207/fileData.do

(3) 한국부동산원 청약홈 청약통장 통계 조회 서비스 — 오픈API (선택)
    https://www.data.go.kr/data/15114369/openapi.do
    요청 주소는 포털의 '활용명세(Swagger)'에서 확인해 .env 의 SUBSCRIPTION_API_URL 에 넣는다.

(4) 보고서에 인용한 최신 지표(분양가·대출규제 등)는 언론 보도에서 가져왔고,
    각 수치의 출처 링크를 data/market_indicators.csv 의 source_url 열에 적어 두었다.

실행 : python src/03_collect_housing_data.py --start 202101 --end 202608
       python src/03_collect_housing_data.py --skip-api      # 파일데이터 정리만
출력 : output/housing/ 폴더 (apt_trades.csv, apt_trade_monthly.csv, <데이터이름>_clean.csv)
.env : DATA_GO_KR_SERVICE_KEY (공공데이터포털 인증키), SUBSCRIPTION_API_URL (선택)
"""
import argparse
import os
import sys
import time
import xml.etree.ElementTree as ET

import pandas as pd
import requests
from dotenv import load_dotenv

from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "output" / "housing"

# 실거래가 수집 지역 (법정동 코드 앞 5자리) — 권역 비교용 예시, 필요하면 추가
# 전체 코드표: https://www.code.go.kr/stdcode/regCodeL.do
LAWD_CODES = {
    "서울 강남구": "11680", "서울 노원구": "11350", "서울 중랑구": "11260",
    "경기 수원 영통구": "41117", "경기 용인 기흥구": "41463", "경기 안산 상록구": "41271",
    "대구 수성구": "27260", "대전 서구": "30170", "부산 해운대구": "26350",
}

# 파일데이터 (포털에서 내려받아 data/manual/ 에 넣는다)
MANUAL_SOURCES = {
    "subscription_total": ("한국부동산원 청약통장 전체 가입현황", "https://www.data.go.kr/data/15088657/fileData.do"),
    "subscription_period": ("한국부동산원 청약통장 가입기간별 가입현황", "https://www.data.go.kr/data/15088656/fileData.do"),
    "applicants": ("한국부동산원 지역별 청약 신청자 정보", "https://www.data.go.kr/data/15110975/fileData.do"),
    "winners": ("한국부동산원 지역별 청약 당첨자 정보", "https://www.data.go.kr/data/15110976/fileData.do"),
    "median_unit_price": ("한국부동산원 중위단위매매가격", "https://www.data.go.kr/data/15112207/fileData.do"),
    "median_price": ("한국부동산원 중위매매가격", "https://www.data.go.kr/data/15112206/fileData.do"),
}

APT_API = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
# data.go.kr 는 기본 스크립트 User-Agent 요청을 거부하는 경우가 있어 브라우저 UA를 사용한다
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
MANUAL_DIR = BASE / "data" / "manual"


def months(start: str, end: str):
    return [p.strftime("%Y%m") for p in pd.period_range(pd.Period(start, "M"), pd.Period(end, "M"), freq="M")]


def fetch_apt_trades(service_key: str, lawd_cd: str, ymd: str) -> list[dict]:
    """한 지역·한 달의 아파트 매매 실거래 전체를 받아온다."""
    rows, page = [], 1
    while True:
        params = {"serviceKey": service_key, "LAWD_CD": lawd_cd, "DEAL_YMD": ymd,
                  "pageNo": page, "numOfRows": 1000}
        r = requests.get(APT_API, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        code = root.findtext(".//resultCode")
        if code not in ("00", "000"):
            raise RuntimeError(f"API 오류 {code}: {root.findtext('.//resultMsg')}")
        items = root.findall(".//item")
        for it in items:
            rows.append({child.tag: (child.text or "").strip() for child in it})
        total = int(root.findtext(".//totalCount") or 0)
        if page * 1000 >= total or not items:
            break
        page += 1
    return rows


def collect_apt(start, end):
    key = os.getenv("DATA_GO_KR_SERVICE_KEY")
    if not key:
        print("  DATA_GO_KR_SERVICE_KEY 가 없어 실거래가 수집을 건너뜁니다. (발급: https://www.data.go.kr/data/15126468/openapi.do → 활용신청)")
        return
    out = []
    for region, code in LAWD_CODES.items():
        for ymd in months(start, end):
            try:
                rows = fetch_apt_trades(key, code, ymd)
            except Exception as e:  # 네트워크·할당량 오류는 기록만 하고 계속
                print(f"  {region} {ymd} 실패: {e}")
                continue
            for r in rows:
                r.update(region=region, lawd_cd=code, ymd=ymd)
            out.extend(rows)
            print(f"  {region} {ymd}: {len(rows)}건", end="\r")
            time.sleep(0.1)
    print()
    if not out:
        return
    df = pd.DataFrame(out)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "apt_trades.csv", index=False, encoding="utf-8-sig")

    # 거래금액(만원, "82,000" 형식) → 억 원, 해제된 거래(cdealType == 'O') 제외
    df["price_eok"] = pd.to_numeric(df["dealAmount"].str.replace(",", ""), errors="coerce") / 1e4
    if "cdealType" in df:
        df = df[df["cdealType"].fillna("") != "O"]
    monthly = (df.groupby(["region", "ymd"]).price_eok
                 .agg(n="size", median="median", p25=lambda s: s.quantile(.25), p75=lambda s: s.quantile(.75))
                 .round(2).reset_index())
    monthly.to_csv(OUT / "apt_trade_monthly.csv", index=False, encoding="utf-8-sig")
    print(f"  저장: {OUT}/apt_trades.csv ({len(df):,}건), apt_trade_monthly.csv")


def collect_subscription_api():
    url, key = os.getenv("SUBSCRIPTION_API_URL"), os.getenv("DATA_GO_KR_SERVICE_KEY")
    if not (url and key):
        print("  (선택) 청약통장 통계 API: SUBSCRIPTION_API_URL 미설정 → 건너뜀. "
              "주소는 https://www.data.go.kr/data/15114369/openapi.do 의 활용명세에서 확인")
        return
    r = requests.get(url, params={"serviceKey": key, "page": 1, "perPage": 10000, "returnType": "JSON"},
                     headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json().get("data", [])
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(data).to_csv(OUT / "subscription_api.csv", index=False, encoding="utf-8-sig")
    print(f"  저장: {OUT}/subscription_api.csv ({len(data)}행)")


def read_any(path):
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    for enc in ("utf-8-sig", "cp949", "euc-kr"):   # 공공데이터 CSV는 cp949 인코딩이 많다
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩을 알 수 없음: {path}")


def tidy_manual_files():
    """data/manual/ 에 내려받은 파일데이터를 읽어 results/<이름>_clean.csv 로 저장한다.
    파일 이름에 아래 키워드가 들어 있으면 자동으로 인식한다."""
    MANUAL_DIR.mkdir(exist_ok=True)
    patterns = {
        "subscription_total": ["전체", "가입현황"],
        "subscription_period": ["가입기간"],
        "applicants": ["신청자"],
        "winners": ["당첨자"],
        "median_unit_price": ["중위단위"],
        "median_price": ["중위매매"],
    }
    files = [f for f in MANUAL_DIR.glob("*.*") if f.suffix.lower() in (".csv", ".xlsx", ".xls")]
    if not files:
        print("  data/manual/ 이 비어 있습니다. 아래 파일을 내려받아 넣으세요:")
        for k in patterns:
            name, url = MANUAL_SOURCES[k]
            print(f"   - {name}\n     {url}")
        return
    for f in files:
        key = next((k for k, kws in patterns.items() if all(w in f.stem for w in kws)), None)
        if key is None:
            print(f"  인식하지 못한 파일(무시): {f.name}")
            continue
        df = read_any(f)
        df.columns = [str(c).strip() for c in df.columns]
        OUT.mkdir(parents=True, exist_ok=True)
        df.to_csv(OUT / f"{key}_clean.csv", index=False, encoding="utf-8-sig")
        print(f"  {f.name} → output/housing/{key}_clean.csv ({len(df)}행, 열: {', '.join(df.columns[:6])}...)")


def main():
    load_dotenv(BASE / ".env")
    ap = argparse.ArgumentParser(description="주택시장 데이터 수집")
    ap.add_argument("--start", default="202101", help="시작 연월 YYYYMM (청약통장 가입자 정점인 2021년)")
    ap.add_argument("--end", default="202608", help="끝 연월 YYYYMM")
    ap.add_argument("--skip-api", action="store_true")
    args = ap.parse_args()

    print("[1] 아파트 매매 실거래가 (국토교통부 API)")
    if not args.skip_api:
        collect_apt(args.start, args.end)
    print("[2] 청약통장 통계 (한국부동산원 API, 선택)")
    if not args.skip_api:
        collect_subscription_api()
    print("[3] 파일데이터 정리 (data/manual/)")
    tidy_manual_files()
    print("[4] 보도 기반 지표: data/market_indicators.csv (출처 링크 포함)")


if __name__ == "__main__":
    main()
