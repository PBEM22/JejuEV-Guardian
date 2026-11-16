# -*- coding: utf-8 -*-
"""제주데이터허브 데이터목록 + 제주빅데이터센터 스키마 → catalog_index.json 생성기.

원칙(대회 보안 규칙)
--------------------
* 원본 엑셀 파일은 DAKER 외 재배포가 금지되어 있으므로, 이 스크립트는 원본 엑셀을
  **제출물에 포함하지 않고**, 메타데이터(데이터명·카테고리·유형·컬럼명 등)만 뽑아
  자체 인덱스(catalog_index.json)를 만든다.
* 원본 엑셀은 사용자 로컬 경로에서만 읽는다(기본: downloads/).

사용법
    python scripts/build_catalog.py \
        --hub-xlsx "downloads/제주데이터허브 데이터목록_20261105.xlsx" \
        --schema-xlsx "downloads/제주빅데이터센터_예시데이터 및 컬럼확인용.xlsx" \
        --out data/catalog_index.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# 컬럼 한글 라벨 · 역할(role) 사전 — 센터 70종 스키마의 실제 컬럼 304종 중
# 분석에 쓰이는 핵심 컬럼을 수작업으로 정리하고, 나머지는 규칙으로 추론한다.
# role: date | datetime | geo | dim(차원) | measure(측도) | flag | id
# --------------------------------------------------------------------------
COLUMN_DICT: dict[str, tuple[str, str, str]] = {
    # (한글 라벨, 역할, 단위/설명)
    "base_year_month": ("기준연월", "date", "YYYYMM"),
    "base_date": ("기준일자", "date", "YYYYMMDD"),
    "base_hour": ("기준시간", "dim", "시"),
    "time": ("시간대", "dim", ""),
    "week": ("요일", "dim", ""),
    "day_of_week": ("요일", "dim", ""),
    "pt_year": ("기준연도", "date", ""),
    "pt_month": ("기준월", "date", ""),
    "account_year": ("결산연도", "date", ""),
    "report_year": ("보고연도", "date", ""),
    "quarter": ("분기", "dim", ""),
    "province": ("시도", "geo", ""),
    "city": ("시군구", "geo", ""),
    "city_nm": ("시군구명", "geo", ""),
    "city_cd": ("시군구코드", "id", ""),
    "city_name": ("시군구명", "geo", ""),
    "emd": ("읍면동", "geo", ""),
    "emd_nm": ("읍면동명", "geo", ""),
    "emd_cd": ("읍면동코드", "id", ""),
    "emd_name": ("읍면동명", "geo", ""),
    "eupmyeondong": ("읍면동", "geo", ""),
    "bjd": ("법정동", "geo", ""),
    "bjd_cd": ("법정동코드", "id", ""),
    "bjd_nm": ("법정동명", "geo", ""),
    "dstrct_se": ("권역구분", "dim", "제주시 동/서부 등"),
    "area_type": ("지역유형", "dim", "도심/주거/관광지"),
    "grid": ("격자", "geo", "50m 격자 ID"),
    "grid_500": ("500m 격자", "geo", ""),
    "grid_500m": ("500m 격자", "geo", ""),
    "grid_1km": ("1km 격자", "geo", ""),
    "market_type": ("업종(대분류)", "dim", ""),
    "biz_cd": ("업종코드", "id", ""),
    "biz_nm": ("업종명", "dim", ""),
    "biz_mid_cd": ("업종중분류코드", "id", ""),
    "biz_mid_nm": ("업종중분류", "dim", ""),
    "biz_small_cd": ("업종소분류코드", "id", ""),
    "biz_small_nm": ("업종소분류", "dim", ""),
    "induty": ("업종", "dim", ""),
    "user_type": ("이용자유형", "dim", "내국인/외국인 관광객·도민"),
    "tour_type": ("관광유형", "dim", ""),
    "age": ("연령대", "dim", ""),
    "age_group": ("연령대", "dim", ""),
    "sex": ("성별", "dim", ""),
    "gender": ("성별", "dim", ""),
    "nationality": ("국적", "dim", ""),
    "visit_type": ("방문유형", "dim", ""),
    "job": ("직업", "dim", ""),
    "family_type": ("가구유형", "dim", ""),
    "theme": ("관광테마", "dim", ""),
    "user_cnt": ("이용자수", "measure", "명"),
    "user_count": ("이용자수", "measure", "명"),
    "use_cnt": ("이용건수", "measure", "건"),
    "usage_count": ("이용건수", "measure", "건"),
    "usage_cost": ("이용금액", "measure", "원"),
    "usage_amount": ("이용금액", "measure", "원"),
    "use_amt": ("이용금액", "measure", "원"),
    "amount": ("금액", "measure", "원"),
    "amount_per_person": ("1인당 이용금액", "measure", "원"),
    "amount_per_case": ("1건당 이용금액", "measure", "원"),
    "store_cnt": ("매장수", "measure", "개"),
    "sale_amt": ("매출액", "measure", "원"),
    "sale_amount": ("판매금액", "measure", "원"),
    "sale_count": ("판매건수", "measure", "건"),
    "unit_price": ("객단가", "measure", "원"),
    "cnt": ("건수", "measure", "건"),
    "count": ("건수", "measure", "건"),
    "session_time": ("세션시간", "measure", "초"),
    "upload": ("업로드량", "measure", "byte"),
    "download": ("다운로드량", "measure", "byte"),
    "resd_pop_cnt": ("거주인구", "measure", "명"),
    "work_pop_cnt": ("직장인구", "measure", "명"),
    "visit_pop_cnt": ("방문인구", "measure", "명"),
    "resd": ("거주/방문 구분", "dim", ""),
    "average_temperature": ("평균기온", "measure", "℃"),
    "highest_temperature": ("최고기온", "measure", "℃"),
    "lowest_temperature": ("최저기온", "measure", "℃"),
    "daily_rainfall": ("일강수량", "measure", "mm"),
    "average_wind_speed": ("평균풍속", "measure", "m/s"),
    "maximum_wind_speed": ("최대풍속", "measure", "m/s"),
    "observatory_name": ("관측소명", "dim", ""),
    "latitude": ("위도", "geo", ""),
    "longitude": ("경도", "geo", ""),
    "bus_route_id": ("노선ID", "id", ""),
    "bus_route_name": ("노선명", "dim", ""),
    "bus_route_number": ("노선번호", "dim", ""),
    "bus_station_id": ("정류소ID", "id", ""),
    "bus_station_name": ("정류소명", "dim", ""),
    "user_category": ("이용자구분", "dim", ""),
    "get_on_off_type": ("승하차구분", "dim", ""),
    "pay_type": ("결제수단", "dim", ""),
    "average_speed": ("평균속도", "measure", "km/h"),
    "average_time": ("평균통행시간", "measure", "초"),
    "wastebag_type": ("봉투종류", "dim", ""),
    "wastebag_liter": ("봉투용량", "dim", "L"),
    "em_g": ("배출량", "measure", "g"),
    "em_amt": ("배출수수료", "measure", "원"),
    "fee_amount": ("수수료", "measure", "원"),
    "closed_biz": ("휴폐업여부", "dim", ""),
    "state": ("처리상태", "dim", ""),
    "request_type": ("신청구분", "dim", ""),
    "size": ("규격", "dim", ""),
    "ap_group_name": ("AP 그룹", "dim", ""),
    "ap_type": ("AP 유형", "dim", ""),
    "ap_category": ("AP 카테고리", "dim", ""),
    "ap_place": ("AP 설치장소", "dim", ""),
    "install_location_detail": ("설치위치", "text", ""),
    "address_emd": ("주소(읍면동)", "geo", ""),
    "category": ("분류", "dim", ""),
    "category_detail": ("분류상세", "dim", ""),
    "open_date": ("개방일자", "date", ""),
    "user_distance": ("이동거리", "measure", "m"),
    "mrkt_nm": ("시장명", "dim", ""),
    "card_nm": ("카드명", "dim", ""),
    "menu_large_nm": ("메뉴대분류", "dim", ""),
    "menu_mid_nm": ("메뉴중분류", "dim", ""),
    "menu_small_nm": ("메뉴소분류", "dim", ""),
    "menu_sub_nm": ("메뉴세분류", "dim", ""),
    "store_sale_amt": ("매장매출액", "measure", "원"),
    "store_sale_cnt": ("매장판매건수", "measure", "건"),
    "monthly_employees": ("월별입사자수", "measure", "명"),
    "monthly_retirement": ("월별퇴사자수", "measure", "명"),
    "employees_cnt": ("직원수", "measure", "명"),
    "assets_tot": ("자산총계", "measure", "원"),
    "debt_tot": ("부채총계", "measure", "원"),
    "capital_tot": ("자본총계", "measure", "원"),
    "sale_amt_total": ("매출총액", "measure", "원"),
    "operate_profit": ("영업이익", "measure", "원"),
    "net_income": ("당기순이익", "measure", "원"),
    "registration_cnt": ("등록건수", "measure", "건"),
    "registration_amt": ("등록금액", "measure", "원"),
    "overdue_amt": ("연체금액", "measure", "원"),
    "credit_grade": ("신용등급", "dim", ""),
    "lane_count": ("차로수", "measure", "개"),
    "bus_station_count": ("정류소수", "measure", "개"),
    "bus_route_length": ("노선길이", "measure", "m"),
    "turn_restricted": ("회전제한", "flag", ""),
    "road_name": ("도로명", "dim", ""),
    "road_type": ("도로유형", "dim", ""),
    "maximum_speed_limit": ("최고속도제한", "measure", "km/h"),
    "ent_nm": ("기업명", "dim", ""),
    "ent_size": ("기업규모", "dim", ""),
    "ksic10_biz_nm": ("표준산업분류", "dim", ""),
    "establishment_date": ("설립일자", "date", ""),
    "closed_biz_date": ("폐업일자", "date", ""),
}

ROLE_BY_PATTERN = [
    (r"(^|_)(temperature|rainfall|wind)", "measure"),
    (r"(_cnt|_count|_amt|_amount|_cost|_price|_rate|_tot|_sum|_qty)$", "measure"),
    (r"(_dt|_date|base_date|_datetime|_time)$", "date"),
    (r"(latitude|longitude|_lat|_lon)", "geo"),
    (r"(_cd|_code|_id|num)$", "id"),
    (r"(_yn|_flag|_se)$", "flag"),
]


def infer_role(name: str) -> str:
    if name in COLUMN_DICT:
        return COLUMN_DICT[name][1]
    n = name.lower()
    for pat, role in ROLE_BY_PATTERN:
        if re.search(pat, n):
            return role
    return "dim"


def humanize(name: str) -> str:
    if name in COLUMN_DICT:
        return COLUMN_DICT[name][0]
    return name.replace("_", " ")


def unit_of(name: str) -> str:
    return COLUMN_DICT.get(name, ("", "", ""))[2]


DOMAIN_BY_PREFIX = {
    "1": "소비·상권(카드·POS)",
    "2": "기업·산업",
    "3": "교통·이동",
    "4": "유동인구·와이파이",
    "5": "환경·기상·폐기물",
}


def build_center(schema_xlsx: str | Path) -> list[dict]:
    x = pd.ExcelFile(schema_xlsx)
    out = []
    for sheet in x.sheet_names:
        df = pd.read_excel(x, sheet_name=sheet, header=None)
        header = [c for c in list(df.iloc[0]) if str(c) != "nan"]
        if not header:  # 일부 시트는 헤더가 2행에 걸쳐 있다(1-12 등)
            header = [c for c in list(df.iloc[0]) + list(df.iloc[1]) if str(c) != "nan"]
            header = [c for c in header if not re.fullmatch(r"\d{5,8}", str(c)) and str(c) not in ("여성", "남성", "제주도민", "도민", "토요일")]
        code, name = (sheet.split(" ", 1) + [""])[:2]
        code = code.strip()
        name = name.strip()
        cols = []
        for c in header:
            cn = str(c).strip()
            cols.append({
                "name": cn,
                "label": humanize(cn),
                "role": infer_role(cn),
                "unit": unit_of(cn),
            })
        metrics = [c for c in cols if c["role"] == "measure"]
        dims = [c for c in cols if c["role"] in ("dim", "geo")]
        dates = [c for c in cols if c["role"] == "date"]
        grain_bits = [d["label"] for d in dates[:1]] + [d["label"] for d in dims[:3]]
        out.append({
            "id": code,
            "name": name,
            "domain": DOMAIN_BY_PREFIX.get(code.split("-")[0], "기타"),
            "columns": cols,
            "metrics": [m["name"] for m in metrics],
            "dimensions": [d["name"] for d in dims],
            "date_column": dates[0]["name"] if dates else None,
            "grain": " × ".join(g for g in grain_bits if g) or "-",
            "n_columns": len(cols),
        })
    return out


def build_hub(hub_xlsx: str | Path) -> list[dict]:
    df = pd.read_excel(hub_xlsx, sheet_name=0, header=1)
    df.columns = [str(c).strip() for c in df.columns]
    df["No."] = pd.to_numeric(df["No."], errors="coerce")
    df = df.dropna(subset=["No."])
    out = []
    for _, r in df.iterrows():
        name = str(r.get("데이터명", "")).strip()
        cat = str(r.get("카테고리", "")).strip()
        period = str(r.get("수집 기간", "")).strip()
        m = re.match(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})?", period)
        kw = [t for t in re.split(r"[\[\],·/()\s]+", cat) if t]
        # 데이터명에서 핵심 어휘 추출(불용어 제거)
        toks = [t for t in re.split(r"[\[\]\(\),·/_\s]+", name) if len(t) >= 2]
        out.append({
            "id": int(r["No."]),
            "name": name,
            "category": cat,
            "type": str(r.get("데이터 타입", "")).strip(),
            "period_start": m.group(1) if m else "",
            "period_end": (m.group(2) or "") if m else "",
            "updated_at": str(r.get("수정일", ""))[:10],
            "publisher": str(r.get("등록자", "")).strip(),
            "views": int(r.get("조회수", 0) or 0),
            "favorites": int(r.get("즐겨찾기수", 0) or 0),
            "keywords": kw + toks,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub-xlsx", required=True)
    ap.add_argument("--schema-xlsx", required=True)
    ap.add_argument("--out", default="data/catalog_index.json")
    args = ap.parse_args()

    hub = build_hub(args.hub_xlsx)
    center = build_center(args.schema_xlsx)
    doc = {
        "meta": {
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "note": "원본 엑셀(DAKER 배포용)은 포함하지 않고, 데이터명·카테고리·컬럼명 등 메타데이터만 인덱싱했습니다.",
            "hub_source": "제주데이터허브 데이터목록(2026-11-05 기준)",
            "center_source": "제주빅데이터센터 예시데이터 및 컬럼확인용(70종)",
            "n_hub": len(hub),
            "n_center": len(center),
        },
        "hub": hub,
        "center": center,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}  hub={len(hub)} center={len(center)}  size={out.stat().st_size/1024:.0f}KB")


if __name__ == "__main__":
    main()
