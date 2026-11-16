# -*- coding: utf-8 -*-
"""JejuEV Guardian 검증 데이터셋 생성기 (seed 고정 · 재현 가능).

데이터 구성 원칙
----------------
* 제주데이터허브 Open API(494·136~141·512·745/746·493·756) 응답을 **표준 필드로 정규화한
  스키마**를 그대로 사용한다. 컬럼명·기간(as_of)은 카탈로그의 실제 수집기간을 따른다.
* 충전소·충전이력·대기시간·보급현황·관광유입·사고다발지역은 **합성(모의) 데이터**이며,
  실제 관측값이 아니다. 값의 규모는 공개 통계의 자릿수를 참고해 설정했다(DATA_SPEC.md 참고).
* 일별 기상(daily_weather.csv)만 **실측 공개 데이터**다(Open-Meteo Archive/ERA5, CC BY 4.0).

사용법
    python scripts/make_ev_datasets.py --out data/datasets
    python scripts/make_ev_datasets.py --out data/datasets --skip-weather-download   # 오프라인 재생성
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20261116
rng = np.random.default_rng(SEED)

# (시군구, 읍면동, 위도, 경도, 지역성격, 규모계수)
REGIONS = [
    ("제주시", "용담2동", 33.5140, 126.5180, "도심", 1.30),   # 제주공항 인근
    ("제주시", "이도1동", 33.4996, 126.5310, "도심", 1.25),
    ("제주시", "노형동", 33.4860, 126.4780, "도심", 1.35),
    ("제주시", "연동", 33.4890, 126.4930, "도심", 1.30),
    ("제주시", "아라동", 33.4700, 126.5450, "주거", 0.95),
    ("제주시", "애월읍", 33.4630, 126.3320, "관광지", 0.95),
    ("제주시", "조천읍", 33.5400, 126.6300, "관광지", 0.70),
    ("제주시", "구좌읍", 33.5230, 126.7600, "관광지", 0.55),
    ("제주시", "한림읍", 33.4130, 126.2660, "관광지", 0.60),
    ("서귀포시", "중문동", 33.2500, 126.4200, "관광지", 1.00),
    ("서귀포시", "대정읍", 33.2200, 126.2500, "관광지", 0.65),
    ("서귀포시", "성산읍", 33.4400, 126.9100, "관광지", 0.70),
    ("서귀포시", "표선면", 33.4000, 126.7600, "관광지", 0.50),
    ("서귀포시", "남원읍", 33.2800, 126.7000, "관광지", 0.55),
]

STATION_NAMES = {
    "용담2동": ["제주공항 장기주차장", "제주공항 단기주차장", "용담공영주차장", "제주항 연안여객터미널"],
    "이도1동": ["이도1동 공영주차장", "제주시청 주차장", "제주시민회관"],
    "노형동": ["노형로터리 공영주차장", "제주도청 주차장", "노형동 도서관"],
    "연동": ["누웨마루거리 공영주차장", "신라호텔 주차장", "연동 롯데시티호텔"],
    "아라동": ["아라동 주민센터", "제주대학교병원", "아라1동 공영주차장"],
    "애월읍": ["애월항 주차장", "곽지해수욕장", "한담해안산책로", "애월읍사무소", "하귀 하나로마트"],
    "조천읍": ["함덕해수욕장", "김녕해수욕장", "조천읍사무소", "북촌 4·3길"],
    "구좌읍": ["성산일출봉 입구", "세화해변", "구좌읍사무소"],
    "한림읍": ["협재해수욕장", "한림항", "금능해수욕장"],
    "중문동": ["중문관광단지", "중문색달해수욕장", "여미지식물원", "중문면세점"],
    "대정읍": ["송악산 주차장", "모슬포항", "대정읍사무소"],
    "성산읍": ["성산일출봉 공영주차장", "섭지코지", "성산항 여객터미널", "표선 방향 해안도로"],
    "표선면": ["표선해비치호텔", "표선민속촌", "표선면사무소"],
    "남원읍": ["위미항", "남원읍사무소", "쇠소깍 주차장"],
}

OPERATORS = ["환경부", "제주특별자치도", "한국전력공사", "제주에너지공사", "테슬라", "GS차지비", "에버온", "SK일렉링크"]

# 관광지별 유입(745/746) 대상지: 충전소와 연결되는 대표 관광지
TOURIST_SPOTS = {
    "애월읍": ["애월 한담산책로", "곽지해수욕장", "카페거리"],
    "조천읍": ["함덕해수욕장", "김녕사굴"],
    "구좌읍": ["성산일출봉", "세화오일장", "비자림"],
    "한림읍": ["협재해수욕장", "금능해수욕장", "한림공원"],
    "중문동": ["중문관광단지", "천제연폭포", "색달해수욕장"],
    "대정읍": ["송악산", "산방산"],
    "성산읍": ["성산일출봉", "섭지코지", "우도 도항선"],
    "표선면": ["표선해비치", "제주민속촌"],
    "남원읍": ["쇠소깍", "위미마을", "정방폭포"],
    "용담2동": ["용두암", "제주공항 면세점"],
}

WEEKDAY_SEASON = {0: 0.95, 1: 0.92, 2: 0.96, 3: 1.00, 4: 1.10, 5: 1.22, 6: 1.12}
MONTH_SEASON = {1: 0.72, 2: 0.75, 3: 0.86, 4: 0.98, 5: 1.08, 6: 1.02,
                7: 1.24, 8: 1.30, 9: 1.00, 10: 1.12, 11: 0.90, 12: 0.85}


def build_chargers() -> pd.DataFrame:
    """[494] 전기자동차 충전소 정보(2025-09-18) 정규화 스키마."""
    rows = []
    sid = 490000
    for city, emd, lat, lon, kind, scale in REGIONS:
        for nm in STATION_NAMES[emd]:
            sid += 1
            base = (1.0 + 2.5 * scale) * 3.0
            fast = int(max(1, round(base * rng.uniform(0.6, 1.6))))
            slow = int(max(2, round(base * rng.uniform(1.2, 2.8))))
            installed = int(rng.choice([2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
                                       p=[0.05, 0.08, 0.10, 0.13, 0.16, 0.15, 0.14, 0.12, 0.07]))
            for ctype, cnt in (("급속", fast), ("완속", slow)):
                rows.append({
                    "as_of": "2025-09-18",
                    "station_id": f"JEJU-{sid}",
                    "station_name": nm,
                    "city_name": city,
                    "emd_name": emd,
                    "address": f"제주특별자치도 {city} {emd} {nm}",
                    "latitude": round(lat + rng.normal(0, 0.003), 5),
                    "longitude": round(lon + rng.normal(0, 0.004), 5),
                    "operator": str(rng.choice(OPERATORS)),
                    "charger_type": ctype,
                    "connector_type": "CCS1" if ctype == "급속" else "AC3상(5핀)",
                    "capacity_kw": 100 if ctype == "급속" else 7,
                    "charger_count": cnt,
                    "install_year": installed,
                    "parking_fee": "무료" if kind == "관광지" and rng.random() > 0.35 else "유료",
                    "parking_type": "실내" if any(k in nm for k in ("터미널", "호텔", "면세점", "도서관", "병원", "마트", "실내")) else "야외",
                    "open_hours": "24시간" if rng.random() > 0.35 else "09:00-18:00",
                    "status": "운영중" if rng.random() > 0.06 else "점검중",
                })
    return pd.DataFrame(rows)


def build_wait_pattern() -> pd.DataFrame:
    """[140] 요일별 전기자동차 대기 시간(2022-07-01~2022-10-31) 정규화 스키마."""
    rows = []
    for city, emd, lat, lon, kind, scale in REGIONS:
        for dow in range(7):
            for hour in range(24):
                for ctype in ("급속", "완속"):
                    tour = (0.9 * np.exp(-((hour - 13) ** 2) / (2 * 3.5 ** 2))
                            + 0.55 * np.exp(-((hour - 18.5) ** 2) / (2 * 2.2 ** 2)) + 0.15)
                    commute = (0.65 * np.exp(-((hour - 8) ** 2) / (2 * 1.5 ** 2))
                               + 0.85 * np.exp(-((hour - 18.5) ** 2) / (2 * 1.8 ** 2)) + 0.10)
                    if kind == "관광지":
                        shape = tour * (1.30 if dow >= 5 else 0.85)
                    else:
                        shape = commute * (0.50 if dow >= 5 else 1.15)
                    base = (19.0 if ctype == "급속" else 7.0) * scale * (1.0 if kind != "관광지" else 1.05)
                    wait = max(0.0, base * shape * (1 + rng.normal(0, 0.18)))
                    if ctype == "완속":
                        wait *= 0.55
                    rows.append({
                        "as_of": "2022-10-31",
                        "emd_name": emd,
                        "city_name": city,
                        "weekday": ["월", "화", "수", "목", "금", "토", "일"][dow],
                        "hour": hour,
                        "charger_type": ctype,
                        "avg_wait_min": round(wait, 1),
                        "p90_wait_min": round(wait * (2.1 + rng.uniform(-0.2, 0.4)), 1),
                        "sample_cnt": int(max(3, (48 if ctype == "급속" else 12) * (1 + rng.normal(0, 0.3)))),
                    })
    df = pd.DataFrame(rows)
    # 같은 (emd, weekday, hour, type)에서 p90 < avg 가 되지 않도록 보정
    df["p90_wait_min"] = df[["avg_wait_min", "p90_wait_min"]].max(axis=1)
    return df


def build_charging_history() -> pd.DataFrame:
    """[136] 일별 전기자동차 충전 이력(2021-01-01~2022-06-30) 정규화 스키마."""
    days = pd.date_range("2021-01-01", "2022-06-30", freq="D")
    rows = []
    for d in days:
        m, dow = d.month, d.weekday()
        trend = 1 + (d.year - 2021) * 0.18 + (d.day_of_year / 365) * 0.10
        for city, emd, lat, lon, kind, scale in REGIONS:
            for ctype in ("급속", "완속"):
                base = (26 if ctype == "급속" else 44) * scale
                cnt = int(base * MONTH_SEASON[m] * WEEKDAY_SEASON[dow] * trend * (1 + rng.normal(0, 0.13)))
                kwh = round(cnt * (31 if ctype == "급속" else 12) * (1 + rng.normal(0, 0.09)), 1)
                sess = round((33 if ctype == "급속" else 121) * (1 + rng.normal(0, 0.10)), 1)
                rows.append({
                    "as_of": "2022-06-30",
                    "base_date": int(d.strftime("%Y%m%d")),
                    "emd_name": emd,
                    "charger_type": ctype,
                    "charge_count": max(0, cnt),
                    "charge_kwh": kwh,
                    "avg_session_min": sess,
                })
    return pd.DataFrame(rows)


def build_ev_stock() -> pd.DataFrame:
    """[512] 제주 전기자동차 보급 현황(2018~2024) 정규화 스키마."""
    rows = []
    for city, emd, lat, lon, kind, scale in REGIONS:
        cumulative = {"승용": 360 * scale, "화물": 66 * scale, "기타": 18 * scale}
        for year in range(2018, 2025):
            for vtype in ("승용", "화물", "기타"):
                growth = {"승용": 1.32, "화물": 1.22, "기타": 1.15}[vtype]
                cumulative[vtype] *= growth * (1 + rng.normal(0, 0.05))
                rows.append({
                    "as_of": "2024-12-31",
                    "base_year": year,
                    "city_name": city,
                    "emd_name": emd,
                    "vehicle_type": vtype,
                    "registered_count": int(round(cumulative[vtype])),
                })
    return pd.DataFrame(rows)


def build_tourist_inflow() -> pd.DataFrame:
    """[745/746] 관광지별 내·외국인 유입자 수(2024-12-31) 정규화 스키마."""
    rows = []
    spot_scale = rng.uniform(0.6, 1.8, size=40)
    i = 0
    for emd, spots in TOURIST_SPOTS.items():
        scale = next(r[5] for r in REGIONS if r[1] == emd)
        for spot in spots:
            f = spot_scale[i]
            i += 1
            for month in range(1, 13):
                base = 41_000 * f * scale * MONTH_SEASON[month]
                dom = int(base * (1 + rng.normal(0, 0.08)))
                foreign = int(base * (0.14 + 0.06 * (month in (7, 8, 10))) * (1 + rng.normal(0, 0.15)))
                rows.append({
                    "as_of": "2024-12-31",
                    "spot_name": spot,
                    "emd_name": emd,
                    "month": month,
                    "domestic_visitors": max(0, dom),
                    "foreign_visitors": max(0, foreign),
                })
    return pd.DataFrame(rows)


def build_accidents() -> pd.DataFrame:
    """[493] 교통사고 다발지역 정보(2017~2023) 정규화 스키마."""
    spots = []
    for city, emd, lat, lon, kind, scale in REGIONS:
        for k in range(2):
            spots.append((city, emd, lat + rng.normal(0, 0.012), lon + rng.normal(0, 0.012), kind, scale, k))
    rows = []
    for n, (city, emd, lat, lon, kind, scale, k) in enumerate(spots, start=1):
        acc = int(max(3, rng.poisson(6 + 4 * scale)))
        rows.append({
            "as_of": "2023-12-31",
            "hotspot_id": f"HS-{n:03d}",
            "hotspot_name": f"{emd} 교차로 {k + 1}",
            "city_name": city,
            "emd_name": emd,
            "latitude": round(lat, 5),
            "longitude": round(lon, 5),
            "radius_m": int(rng.choice([100, 150, 200])),
            "accident_count": acc,
            "casualty_count": int(round(acc * rng.uniform(1.1, 1.8))),
            "main_type": str(rng.choice(["측면충돌", "추돌", "횡단보도 보행자", "이륜차", "회전 교차"])),
            "period": "2017-01-01~2023-12-31",
        })
    return pd.DataFrame(rows)


def fetch_weather(out: Path, start="2024-01-01", end=None) -> pd.DataFrame:
    end = end or (dt.date.today() - dt.timedelta(days=2)).isoformat()
    points = {"제주시": (33.514, 126.529), "서귀포시": (33.254, 126.565)}
    frames = []
    for region, (lat, lon) in points.items():
        q = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
            "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
            "timezone": "Asia/Seoul",
        })
        with urllib.request.urlopen(f"https://archive-api.open-meteo.com/v1/archive?{q}", timeout=60) as r:
            js = json.loads(r.read().decode())
        d = js["daily"]
        frames.append(pd.DataFrame({
            "as_of": end,
            "base_date": [int(t.replace("-", "")) for t in d["time"]],
            "observatory_name": region,
            "average_temperature": d["temperature_2m_mean"],
            "highest_temperature": d["temperature_2m_max"],
            "lowest_temperature": d["temperature_2m_min"],
            "daily_rainfall": d["precipitation_sum"],
            "maximum_wind_speed": [None if v is None else round(v / 3.6, 1) for v in d["wind_speed_10m_max"]],
        }))
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/datasets")
    ap.add_argument("--skip-weather-download", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    wpath = out / "daily_weather.csv"
    if args.skip_weather_download and wpath.exists():
        w = pd.read_csv(wpath)
    else:
        w = fetch_weather(out)
        w.to_csv(wpath, index=False, encoding="utf-8-sig")

    datasets = {
        "chargers_jeju_2025.csv": build_chargers(),
        "wait_time_by_weekday_hour_2022.csv": build_wait_pattern(),
        "charging_history_daily_2021_2022.csv": build_charging_history(),
        "ev_registration_jeju_2018_2024.csv": build_ev_stock(),
        "tourist_inflow_by_spot_2024.csv": build_tourist_inflow(),
        "traffic_accident_hotspots_2023.csv": build_accidents(),
    }
    for name, df in datasets.items():
        df.to_csv(out / name, index=False, encoding="utf-8-sig")
        print(f"{name:42s} rows={len(df):7,d} cols={df.shape[1]}")

    meta = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "seed": SEED,
        "weather": {
            "file": "daily_weather.csv",
            "rows": int(len(w)),
            "source": "Open-Meteo Historical Weather API (ERA5 재분석, ECMWF/Copernicus) · 제주시·서귀포시 지점",
            "license": "CC BY 4.0",
            "retrieved": dt.date.today().isoformat(),
            "note": "이 파일만 실측 공개 데이터이며, 나머지는 센터/허브 스키마를 따른 합성 검증 데이터입니다.",
        },
    }
    (out / "datasets_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print("weather rows:", len(w), "period:", w.base_date.min(), "~", w.base_date.max())


if __name__ == "__main__":
    main()
