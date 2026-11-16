# -*- coding: utf-8 -*-
"""데이터 접근 계층 — 데이터셋 카탈로그 · 적재 · 제주데이터허브 Open API 커넥터.

모든 분석은 이 모듈을 통해서만 데이터를 만진다. 각 데이터셋은 다음 정보를 함께 들고 다닌다.

    {"key", "dataset_id"(제주데이터허브 번호), "name", "as_of"(수집 기준일),
     "granularity", "source", "synthetic"(bool), "license"}

``as_of`` 는 결과 신뢰도 계산과 리포트의 '근거 데이터' 표에 그대로 쓰인다. 수집 시점이
서로 다른 데이터를 섞는 것이 이 프로젝트의 핵심 설계이므로, 시점 정보를 숨기지 않는다.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CATALOG_PATH, DATASET_DIR, env

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

# (시군구, 읍면동, 위도, 경도, 지역성격)
REGION_META: dict[str, dict] = {
    "용담2동": {"city": "제주시", "lat": 33.5140, "lon": 126.5180, "kind": "도심", "alias": ["공항", "제주공항", "용담"]},
    "이도1동": {"city": "제주시", "lat": 33.4996, "lon": 126.5310, "kind": "도심", "alias": ["시청", "이도"]},
    "노형동": {"city": "제주시", "lat": 33.4860, "lon": 126.4780, "kind": "도심", "alias": ["노형", "도청"]},
    "연동": {"city": "제주시", "lat": 33.4890, "lon": 126.4930, "kind": "도심", "alias": ["연동", "누웨마루"]},
    "아라동": {"city": "제주시", "lat": 33.4700, "lon": 126.5450, "kind": "주거", "alias": ["아라", "제주대"]},
    "애월읍": {"city": "제주시", "lat": 33.4630, "lon": 126.3320, "kind": "관광지", "alias": ["애월", "곽지", "한담", "하귀"]},
    "조천읍": {"city": "제주시", "lat": 33.5400, "lon": 126.6300, "kind": "관광지", "alias": ["조천", "함덕", "김녕"]},
    "구좌읍": {"city": "제주시", "lat": 33.5230, "lon": 126.7600, "kind": "관광지", "alias": ["구좌", "세화", "성산일출봉"]},
    "한림읍": {"city": "제주시", "lat": 33.4130, "lon": 126.2660, "kind": "관광지", "alias": ["한림", "협재", "금능"]},
    "중문동": {"city": "서귀포시", "lat": 33.2500, "lon": 126.4200, "kind": "관광지", "alias": ["중문", "색달", "중문관광단지"]},
    "대정읍": {"city": "서귀포시", "lat": 33.2200, "lon": 126.2500, "kind": "관광지", "alias": ["대정", "모슬포", "송악산"]},
    "성산읍": {"city": "서귀포시", "lat": 33.4400, "lon": 126.9100, "kind": "관광지", "alias": ["성산", "섭지코지", "우도"]},
    "표선면": {"city": "서귀포시", "lat": 33.4000, "lon": 126.7600, "kind": "관광지", "alias": ["표선", "해비치"]},
    "남원읍": {"city": "서귀포시", "lat": 33.2800, "lon": 126.7000, "kind": "관광지", "alias": ["남원", "위미", "쇠소깍"]},
}


@dataclass(frozen=True)
class DatasetMeta:
    key: str
    dataset_id: int
    name: str
    as_of: str
    granularity: str
    source: str
    file: str
    synthetic: bool = True
    license: str = "합성 검증 데이터(제주데이터허브 Open API 정규화 스키마 기반)"

    def to_dict(self) -> dict:
        return {
            "dataset": f"[{self.dataset_id}] {self.name}",
            "dataset_id": self.dataset_id,
            "as_of": self.as_of,
            "granularity": self.granularity,
            "source": self.source,
            "synthetic": self.synthetic,
            "license": self.license,
        }


DATASETS: dict[str, DatasetMeta] = {
    "chargers": DatasetMeta(
        "chargers", 494, "전기자동차 충전소 정보", "2025-09-18", "충전소×충전기유형",
        "제주데이터허브 Open API", "chargers_jeju_2025.csv"),
    "wait": DatasetMeta(
        "wait", 140, "요일별 전기자동차 대기 시간", "2022-10-31", "읍면동×요일×시간×충전기유형",
        "제주데이터허브 Open API", "wait_time_by_weekday_hour_2022.csv"),
    "history": DatasetMeta(
        "history", 136, "일별 전기자동차 충전 이력", "2022-06-30", "일×읍면동×충전기유형",
        "제주데이터허브 Open API", "charging_history_daily_2021_2022.csv"),
    "ev": DatasetMeta(
        "ev", 512, "제주특별자치도 전기자동차 보급 현황", "2024-12-31", "연×읍면동×차종",
        "제주데이터허브 파일데이터", "ev_registration_jeju_2018_2024.csv"),
    "tourist": DatasetMeta(
        "tourist", 745, "관광지별 내·외국인 유입자 수", "2024-12-31", "월×관광지",
        "제주데이터허브 Open API(745·746)", "tourist_inflow_by_spot_2024.csv"),
    "accident": DatasetMeta(
        "accident", 493, "교통사고 다발지역 정보", "2023-12-31", "다발지역",
        "제주데이터허브 Open API", "traffic_accident_hotspots_2023.csv"),
    "weather": DatasetMeta(
        "weather", 756, "일별 기상 정보", "실시간(Open-Meteo 재분석)", "일×관측소",
        "제주데이터허브 Open API(756) + Open-Meteo ERA5", "daily_weather.csv",
        synthetic=False, license="CC BY 4.0 (Open-Meteo/ERA5)"),
}


def meta_table() -> list[dict]:
    return [m.to_dict() for m in DATASETS.values()]


# --------------------------------------------------------------------------
# Open API 커넥터 (.env에 키가 있으면 실시간, 없으면 내장 검증 데이터)
# --------------------------------------------------------------------------
HUB_BASE = env("JEJU_HUB_BASE", "https://open.jejudatahub.net/api/proxy")

# 허브 API 응답 필드 → 표준 필드명 매핑 (dataset_id별)
_HUB_RENAME: dict[int, dict[str, str]] = {
    494: {  # 충전소 정보
        "cstId": "station_id", "cstNm": "station_name", "sido": "city_name",
        "emd": "emd_name", "emd_nm": "emd_name", "eupmyeondong": "emd_name",
        "addr": "address", "lat": "latitude", "lng": "longitude", "lon": "longitude",
        "oper": "operator", "chargerTp": "charger_type", "connTp": "connector_type",
        "cap": "capacity_kw", "cnt": "charger_count", "instYear": "install_year",
        "parkFee": "parking_fee", "parkTp": "parking_type", "openHr": "open_hours",
        "sttus": "status",
    },
    140: {  # 요일별 대기 시간
        "emd": "emd_name", "emd_nm": "emd_name", "eupmyeondong": "emd_name",
        "sido": "city_name", "wkday": "weekday", "hr": "hour",
        "chargerTp": "charger_type", "avgWaitMin": "avg_wait_min",
        "p90WaitMin": "p90_wait_min", "smplCnt": "sample_cnt",
    },
    136: {  # 일별 충전 이력
        "baseYmd": "base_date", "emd": "emd_name", "emd_nm": "emd_name",
        "chargerTp": "charger_type", "chrgCnt": "charge_count",
        "chrgKwh": "charge_kwh", "avgSsnMin": "avg_session_min",
    },
    512: {  # EV 보급 현황
        "baseYear": "base_year", "sido": "city_name",
        "emd": "emd_name", "emd_nm": "emd_name", "eupmyeondong": "emd_name",
        "vhclTp": "vehicle_type", "regCnt": "registered_count",
    },
    745: {  # 관광 유입(내국인)
        "spotNm": "spot_name", "emd": "emd_name", "emd_nm": "emd_name",
        "mth": "month", "dmstcVstr": "domestic_visitors",
    },
    746: {  # 관광 유입(외국인)
        "spotNm": "spot_name", "emd": "emd_name", "emd_nm": "emd_name",
        "mth": "month", "frgnVstr": "foreign_visitors",
    },
    756: {  # 기상 정보
        "baseYmd": "base_date", "obsrvtryNm": "observatory_name",
        "avgTa": "average_temperature", "maxTa": "highest_temperature",
        "minTa": "lowest_temperature", "sumRn": "daily_rainfall",
        "maxWs": "maximum_wind_speed",
    },
    493: {  # 사고다발지역
        "spotId": "hotspot_id", "spotNm": "hotspot_name", "sido": "city_name",
        "emd": "emd_name", "emd_nm": "emd_name",
        "lat": "latitude", "lng": "longitude", "lon": "longitude",
        "radius": "radius_m", "accdntCnt": "accident_count",
        "csltyyCnt": "casualty_count", "mainTp": "main_type",
    },
}

# 충전유형 코드 → 표준값
_CHARGER_TYPE_MAP = {"01": "급속", "02": "완속", "1": "급속", "2": "완속",
                     "급속": "급속", "완속": "완속", "fast": "급속", "slow": "완속"}

# 요일 → 한글 (API가 숫자 0-6 또는 영문으로 올 때 대비)
# 숫자는 Python weekday() 기준 0-based(0=월)로 처리 — risk.py parse_weekday()와 동일 기준
_WEEKDAY_MAP: dict[str, str] = {
    "0": "월", "1": "화", "2": "수", "3": "목", "4": "금", "5": "토", "6": "일",
    "mon": "월", "tue": "화", "wed": "수", "thu": "목", "fri": "금", "sat": "토", "sun": "일",
    "monday": "월", "tuesday": "화", "wednesday": "수", "thursday": "목",
    "friday": "금", "saturday": "토", "sunday": "일",
    "월": "월", "화": "화", "수": "수", "목": "목", "금": "금", "토": "토", "일": "일",
}


def _to_yyyymmdd(val) -> int | float:
    """'2026-11-16', '2026/11/16', '20261116', 20261116 → 20261116 정수. 변환 불가 시 NaN."""
    s = str(val).strip().replace("-", "").replace("/", "")
    try:
        return int(s)
    except ValueError:
        return float("nan")


def hub_api_available() -> bool:
    return bool(env("JEJU_HUB_API_KEY")) and env("JEJU_USE_LIVE_API", "0") == "1"


def _normalize_hub(df: pd.DataFrame, dataset_id: int) -> pd.DataFrame:
    """허브 API 응답 컬럼명을 표준 필드명으로 정규화한다."""
    rename = _HUB_RENAME.get(dataset_id, {})
    lower_map = {k.lower(): v for k, v in rename.items()}
    actual_rename = {c: lower_map[c.lower()] for c in df.columns if c.lower() in lower_map}
    df = df.rename(columns=actual_rename)
    # 충전유형 코드 → 표준값
    if "charger_type" in df.columns:
        df["charger_type"] = df["charger_type"].map(
            lambda x: _CHARGER_TYPE_MAP.get(str(x).strip(), x))
    # base_date: "2026-11-16" / "20261116" / 정수 모두 → 20261116 정수
    if "base_date" in df.columns:
        df["base_date"] = df["base_date"].map(_to_yyyymmdd)
        df["base_date"] = pd.to_numeric(df["base_date"], errors="coerce").astype("Int64")
    # weekday: 숫자(0-6, 1-7) · 영문 → 한글
    if "weekday" in df.columns:
        df["weekday"] = df["weekday"].map(
            lambda x: _WEEKDAY_MAP.get(str(x).strip().lower(), str(x).strip()))
    return df


def fetch_hub(dataset_id: int, params: dict | None = None, timeout: int = 8) -> pd.DataFrame | None:
    """제주데이터허브 Open API 호출. 실패하면 None(→ 호출부가 내장 데이터로 폴백)."""
    key = env("JEJU_HUB_API_KEY")
    if not key:
        return None
    q = urllib.parse.urlencode(params or {})
    url = f"{HUB_BASE}/{dataset_id}/{key}?{q}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            js = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    raw = None
    for k in ("data", "items", "result", "rows"):
        if isinstance(js, dict) and isinstance(js.get(k), list):
            raw = pd.DataFrame(js[k])
            break
    if raw is None:
        raw = pd.DataFrame(js) if isinstance(js, list) else None
    return _normalize_hub(raw, dataset_id) if raw is not None else None


# --------------------------------------------------------------------------
# 적재
# --------------------------------------------------------------------------
@lru_cache(maxsize=8)
def _read(key: str, path_str: str, mtime: float) -> pd.DataFrame:
    m = DATASETS[key]
    df = pd.read_csv(path_str, encoding="utf-8-sig")
    if "base_date" in df.columns:
        df["base_date"] = df["base_date"].astype(int)
    if "as_of" in df.columns:
        df = df.drop(columns=["as_of"])
    return df


def load(key: str) -> pd.DataFrame:
    """데이터셋 적재(캐시). .env에 키가 있고 JEJU_USE_LIVE_API=1이면 실시간 API를 먼저 시도."""
    if key not in DATASETS:
        raise KeyError(f"알 수 없는 데이터셋: {key}")
    m = DATASETS[key]
    if hub_api_available():
        live = fetch_hub(m.dataset_id)
        if live is not None and len(live) > 0:
            return live
    p = DATASET_DIR / m.file
    if not p.exists():
        raise FileNotFoundError(
            f"{p} 가 없습니다. `python scripts/make_ev_datasets.py` 로 검증 데이터를 생성하세요.")
    return _read(key, str(p), p.stat().st_mtime)


def dataset_usage() -> dict:
    return {
        "engine": "live-api" if hub_api_available() else "builtin-validated-dataset",
        "hub_key_present": bool(env("JEJU_HUB_API_KEY")),
        "datasets": [m.to_dict() for m in DATASETS.values()],
    }


# --------------------------------------------------------------------------
# 파생 지표
# --------------------------------------------------------------------------
def chargers_frame(emd: str | None = None, charger_type: str | None = None) -> pd.DataFrame:
    df = load("chargers")
    if emd:
        df = df[df["emd_name"] == emd]
    if charger_type:
        df = df[df["charger_type"] == charger_type]
    return df.reset_index(drop=True)


@lru_cache(maxsize=4)
def _region_pressure_cached(_token: float) -> pd.DataFrame:
    return _build_region_pressure()


def region_pressure() -> pd.DataFrame:
    """(캐시) 읍면동별 수요·공급 압력 지표."""
    return _region_pressure_cached(DATASET_DIR.stat().st_mtime).copy()


def _build_region_pressure() -> pd.DataFrame:
    """읍면동별 수요·공급 압력 지표.

    * ``ev_per_charger``  : 2024년 말 등록 EV ÷ 2025-09 충전기 수 (현재 공급 압력)
    * ``chargers_2022``   : 2022년까지 설치된 충전기 수(설치연도 기준) — 과거 패턴 당시 공급
    * ``growth_factor``   : (현재 EV/충전기) ÷ (2022년 EV/충전기). 1보다 크면 과거보다 더 붐빈다.
    * ``tourist_load``    : 월별 관광지 유입자 수 ÷ 충전기 수
    """
    ch = load("chargers")
    ev = load("ev")
    tr = load("tourist")

    ch_now = ch.groupby("emd_name")["charger_count"].sum()
    ch_2022 = ch[ch["install_year"] <= 2022].groupby("emd_name")["charger_count"].sum()
    ev_now = ev[ev["base_year"] == 2024].groupby("emd_name")["registered_count"].sum()
    ev_2022 = ev[ev["base_year"] == 2022].groupby("emd_name")["registered_count"].sum()
    tour = tr.groupby("emd_name")[["domestic_visitors", "foreign_visitors"]].sum()
    tour_total = tour["domestic_visitors"] + tour["foreign_visitors"]

    df = pd.DataFrame({
        "emd_name": ch_now.index,
        "chargers_now": ch_now.values,
        "chargers_2022": ch_2022.reindex(ch_now.index).fillna(0).values,
        "ev_2024": ev_now.reindex(ch_now.index).fillna(0).values,
        "ev_2022": ev_2022.reindex(ch_now.index).fillna(0).values,
        "tourists_2024": tour_total.reindex(ch_now.index).fillna(0).values,
    })
    df["ev_per_charger"] = df["ev_2024"] / df["chargers_now"].clip(lower=1)
    df["ev_per_charger_2022"] = df["ev_2022"] / df["chargers_2022"].clip(lower=1)
    df["growth_factor"] = (1 + ((df["ev_per_charger"] / df["ev_per_charger_2022"].clip(lower=0.1)) - 1) * 0.45).clip(0.85, 1.25)
    df["tourist_load"] = df["tourists_2024"] / df["chargers_now"].clip(lower=1)
    df["city_name"] = df["emd_name"].map(lambda e: REGION_META[e]["city"])
    df["kind"] = df["emd_name"].map(lambda e: REGION_META[e]["kind"])
    return df


@lru_cache(maxsize=512)
def weather_for(date: str, region: str = "제주시") -> dict:
    """해당 날짜의 기상. 데이터 범위를 벗어나면 (1) 실시간 API → (2) 동일 날짜 계절 평년값 순으로 폴백."""
    df = load("weather")
    target = int(date.replace("-", ""))
    sub = df[(df["base_date"] == target) & (df["observatory_name"] == region)]
    source = "내장 실측 기상(2024-01~현재)"
    if len(sub) == 0:
        live = _fetch_live_weather(date, region)
        if live:
            return live
        # 같은 날짜(월-일)의 과거 관측 평균(평년값)으로 대체
        md = target % 10000
        cand = df[(df["base_date"] % 10000 == md) & (df["observatory_name"] == region)]
        if len(cand) == 0:
            cand = df[df["observatory_name"] == region].tail(30)
            source = "최근 30일 평균(대체값)"
        sub = cand.mean(numeric_only=True).to_frame().T
        sub["base_date"] = target
        source = "동일 날짜 평년값(내장 기상 이력 평균)"
    r = sub.iloc[0]
    return {
        "date": date,
        "region": region,
        "avg_temp": float(r.get("average_temperature", np.nan)),
        "max_temp": float(r.get("highest_temperature", np.nan)),
        "min_temp": float(r.get("lowest_temperature", np.nan)),
        "rainfall_mm": float(r.get("daily_rainfall", 0) or 0),
        "wind_ms": float(r.get("maximum_wind_speed", 0) or 0),
        "source": source,
        "as_of": DATASETS["weather"].as_of,
    }


_WEATHER_POINTS = {"제주시": (33.514, 126.529), "서귀포시": (33.254, 126.565)}


def _fetch_live_weather(date: str, region: str) -> dict | None:
    """내장 기상 범위를 벗어난 날짜는 Open-Meteo 예보 API로 보완(네트워크 불가 시 None)."""
    if env("JEJU_LIVE_WEATHER", "1") == "0":
        return None
    lat, lon = _WEATHER_POINTS.get(region, _WEATHER_POINTS["제주시"])
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "start_date": date, "end_date": date,
        "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "timezone": "Asia/Seoul"})
    try:
        with urllib.request.urlopen(f"https://api.open-meteo.com/v1/forecast?{q}", timeout=2.5) as r:
            js = json.loads(r.read().decode())
        d = js["daily"]
        if not d["time"]:
            return None
        return {
            "date": date, "region": region,
            "avg_temp": float(d["temperature_2m_mean"][0]),
            "max_temp": float(d["temperature_2m_max"][0]),
            "min_temp": float(d["temperature_2m_min"][0]),
            "rainfall_mm": float(d["precipitation_sum"][0] or 0),
            "wind_ms": float((d["wind_speed_10m_max"][0] or 0) / 3.6),
            "source": "실시간 예보(Open-Meteo) — 내장 기상 범위 초과일",
            "as_of": "live",
        }
    except Exception:
        return None


def weather_series(days: int = 21, region: str = "제주시", end_date: str | None = None) -> pd.DataFrame:
    df = load("weather")
    df = df[df["observatory_name"] == region].sort_values("base_date")
    if end_date:
        end = int(end_date.replace("-", ""))
        df = df[df["base_date"] <= end]
    return df.tail(days).reset_index(drop=True)


def haversine_m(lat1, lon1, lat2, lon2) -> np.ndarray:
    r = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2) - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def catalog_search(query: str, top_k: int = 5) -> list[dict]:
    """카탈로그(1,259건 허브 목록 + 70종 센터 스키마)에서 질의어와 관련된 데이터를 찾는다."""
    if not CATALOG_PATH.exists():
        return []
    cat = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    q = [t for t in query.replace(",", " ").split() if len(t) >= 2]
    hits = []
    for item in cat.get("hub", []):
        name = item["name"]
        score = sum(2 if t in name else 0 for t in q) + sum(1 if t in item.get("category", "") else 0 for t in q)
        if score > 0:
            hits.append((score, {
                "dataset_id": item["id"], "name": name, "category": item["category"],
                "type": item["type"], "period": f'{item["period_start"]}~{item["period_end"]}',
            }))
    hits.sort(key=lambda x: (-x[0], x[1]["dataset_id"]))
    return [h[1] for h in hits[:top_k]]


def catalog_summary() -> dict:
    if not CATALOG_PATH.exists():
        return {"hub": 0, "center": 0}
    cat = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {"hub": len(cat.get("hub", [])), "center": len(cat.get("center", [])),
            "meta": cat.get("meta", {})}
