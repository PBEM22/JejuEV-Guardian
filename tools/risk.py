# -*- coding: utf-8 -*-
"""충전 대기·이동 리스크 스코어링 모델 (설명 가능 · 재현 가능).

모델 구조
---------
    ① 형태(shape) : 2022년 요일×시간×읍면동 대기시간 패턴  (과거 · [140])
    ② 수준(level) : 최신 EV 등록 ÷ 최신 충전기, 2022년 대비 증가율  ([512]·[494])
    ③ 계절(tour)  : 해당 월 관광지 유입 ÷ 충전기 수              ([745/746])
    ④ 기상(wx)    : 대상일 강수·강풍·기온 보정                    ([756])
    ⑤ 안전(safety): 사고다발지역 반경 내 여부                    ([493])

    예상대기(분) = ① × ② × ③ × ④
    리스크(0~100) = 100 × (0.55·대기정규화 + 0.20·공급압력 + 0.15·관광부하 + 0.10·안전)

수집 시점이 다른 데이터를 섞기 때문에 '형태'는 과거 패턴에서, '수준'은 최신 데이터에서
가져온다는 점을 기획서·DATA_SPEC·리포트에 모두 명시한다.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import datasets as ds

WEIGHTS = {"wait": 0.55, "supply": 0.20, "tour": 0.15, "safety": 0.10}
WAIT_CAP_MIN = 80.0        # 정규화 상한(분)
RISK_LEVELS = [(70, "높음"), (45, "보통"), (0, "낮음")]


# --------------------------------------------------------------------------
def parse_weekday(date: str) -> str:
    return ds.WEEKDAYS[dt.date.fromisoformat(date).weekday()]


def weather_factor(wx: dict) -> tuple[float, list[str]]:
    """기상 보정계수와 사유. (근거: 강수 시 이동수단 전환으로 충전 수요 증가, 강풍 시 개방형 충전기 이용 회피)"""
    f, notes = 1.0, []
    rain = wx.get("rainfall_mm", 0) or 0
    wind = wx.get("wind_ms", 0) or 0
    temp = wx.get("avg_temp", 15) or 15
    if rain >= 30:
        f += 0.25
        notes.append(f"강수 {rain:.1f}mm(호우) → 실내 대기·우회 수요 +25%")
    elif rain >= 10:
        f += 0.15
        notes.append(f"강수 {rain:.1f}mm → 충전 수요 +15%")
    elif rain >= 1:
        f += 0.07
        notes.append(f"약한 비 {rain:.1f}mm → +7%")
    if wind >= 15:
        f += 0.10
        notes.append(f"최대풍속 {wind:.1f}m/s → 개방형 충전기 회피 +10%")
    elif wind >= 10:
        f += 0.05
        notes.append(f"최대풍속 {wind:.1f}m/s → +5%")
    if temp >= 32:
        f += 0.06
        notes.append(f"폭염 {temp:.1f}℃ → 냉방 부하로 충전 빈도 +6%")
    elif temp <= 0:
        f += 0.06
        notes.append(f"한파 {temp:.1f}℃ → 배터리 효율 저하로 충전 빈도 +6%")
    return f, notes


def _tour_factor(emd: str, date: str) -> tuple[float, float]:
    """해당 월 관광 유입이 연평균 대비 얼마인지(계절계수)와 관광부하 절대값."""
    tr = ds.load("tourist")
    sub = tr[tr["emd_name"] == emd]
    if len(sub) == 0:
        return 1.0, 0.0
    monthly = sub.groupby("month")[["domestic_visitors", "foreign_visitors"]].sum().sum(axis=1)
    month = dt.date.fromisoformat(date).month
    mean = float(monthly.mean()) or 1.0
    return float(monthly.get(month, mean)) / mean, float(monthly.get(month, 0))


def wait_curve(emd: str, charger_type: str, date: str) -> pd.DataFrame:
    """24시간 예상 대기(분) 곡선 — 과거 패턴 × 최신 수준 × 계절 × 기상."""
    w = ds.load("wait")
    wd = parse_weekday(date)
    sub = w[(w["emd_name"] == emd) & (w["weekday"] == wd) & (w["charger_type"] == charger_type)]
    if len(sub) == 0:
        sub = w[(w["weekday"] == wd) & (w["charger_type"] == charger_type)]
    base = sub.groupby("hour").agg(avg=("avg_wait_min", "mean"), p90=("p90_wait_min", "mean"),
                                   n=("sample_cnt", "sum")).reindex(range(24)).interpolate()
    pres = ds.region_pressure().set_index("emd_name")
    growth = float(pres.loc[emd, "growth_factor"]) if emd in pres.index else 1.0
    tour_f, _ = _tour_factor(emd, date)
    wx = ds.weather_for(date, ds.REGION_META.get(emd, {}).get("city", "제주시"))
    wxf, _ = weather_factor(wx)
    out = pd.DataFrame({
        "hour": base.index,
        "wait_base_min": base["avg"].values,
        "wait_min": (base["avg"].values * growth * max(0.6, min(1.3, tour_f)) * wxf),
        "p90_min": (base["p90"].values * growth * max(0.6, min(1.3, tour_f)) * wxf),
        "sample_cnt": base["n"].values,
    })
    out["growth_factor"] = growth
    out["tour_factor"] = tour_f
    out["weather_factor"] = wxf
    return out


def _unit_hash(text: str) -> float:
    """station_id → [0,1) 결정적 값(실행마다 동일). 충전소별 고유 편차를 만들 때 사용."""
    import hashlib
    h = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    return int(h, 16) / 0xFFFFFFFF


def station_risks(emd: str, date: str, hour: int, charger_type: str = "급속",
                  exclude: set[str] | None = None, top_k: int = 8) -> pd.DataFrame:
    """읍면동 내 충전소별 리스크/예상대기 순위."""
    exclude = exclude or set()
    ch = ds.chargers_frame(emd, charger_type)
    if len(ch) == 0:
        return pd.DataFrame()
    ch = ch[~ch["station_id"].isin(exclude)]
    if len(ch) == 0:
        return pd.DataFrame()
    curve = wait_curve(emd, charger_type, date)
    row = curve[curve["hour"] == hour].iloc[0]
    region_wait = float(row["wait_min"])
    pres = ds.region_pressure().set_index("emd_name").loc[emd]
    acc = ds.load("accident")
    acc_emd = acc[acc["emd_name"] == emd]
    wx = ds.weather_for(date, ds.REGION_META[emd]["city"])

    median_count = max(1.0, float(ch["charger_count"].median()))
    rows = []
    for r in ch.itertuples():
        scale = (median_count / max(1, r.charger_count)) ** 0.45          # 규모가 큰 충전소는 대기 분산
        idio = 0.94 + 0.12 * _unit_hash(r.station_id)                      # 충전소 고유 편차(결정적)
        severe = wx["rainfall_mm"] >= 20 or wx["wind_ms"] >= 14
        outdoor = ((1.35 if severe else 1.10) if r.parking_type == "야외" else 0.95)  # 야외·비바람 노출
        free = 0.94 if r.parking_fee == "무료" else 1.03                    # 무료 주차는 회전 느림
        status = 1.0 if r.status == "운영중" else 1.6
        wait = region_wait * scale * outdoor * free * status * idio
        # 안전: 사고다발지역 반경 내 여부
        safety, hits = 0.0, []
        if len(acc_emd):
            d = ds.haversine_m(r.latitude, r.longitude, acc_emd["latitude"].values, acc_emd["longitude"].values)
            near = acc_emd[(d <= acc_emd["radius_m"].values + 100)]
            if len(near):
                worst = near.sort_values("accident_count", ascending=False).iloc[0]
                safety = min(1.0, float(worst["accident_count"]) / 12.0)
                hits.append(f'{worst["hotspot_name"]}({int(worst["accident_count"])}건, {int(worst["radius_m"])}m)')
        comp = {
            "wait": min(1.0, wait / WAIT_CAP_MIN),
            "supply": min(1.0, float(pres["ev_per_charger"]) / 40.0),
            "tour": min(1.0, float(pres["tourist_load"]) / 1200.0),
            "safety": safety,
        }
        score = 100 * sum(WEIGHTS[k] * v for k, v in comp.items())
        level = next(name for thr, name in RISK_LEVELS if score >= thr)
        reasons = [f"예상 대기 {wait:.1f}분(과거 패턴 {row['wait_base_min']:.1f}분 × 공급계수 {row['growth_factor']:.2f} × 기상 {row['weather_factor']:.2f})"]
        if r.parking_type == "야외" and (wx["rainfall_mm"] >= 10 or wx["wind_ms"] >= 12):
            reasons.append("야외 충전기 · 강수/강풍 노출")
        if hits:
            reasons.append("사고다발지역 인근: " + ", ".join(hits))
        if r.status != "운영중":
            reasons.append("점검중 상태(가용성 낮음)")
        rows.append({
            "station_id": r.station_id, "station_name": r.station_name, "emd_name": emd,
            "city_name": r.city_name, "charger_type": charger_type,
            "charger_count": int(r.charger_count), "connector_type": r.connector_type,
            "operator": r.operator, "parking_type": r.parking_type, "parking_fee": r.parking_fee,
            "open_hours": r.open_hours, "status": r.status,
            "latitude": r.latitude, "longitude": r.longitude,
            "wait_min": round(wait, 1), "p90_min": round(float(row["p90_min"]) * scale, 1),
            "risk_score": round(score, 1), "risk_level": level,
            **{f"c_{k}": round(v, 3) for k, v in comp.items()},
            "reasons": reasons,
        })
    df = pd.DataFrame(rows).sort_values("wait_min").reset_index(drop=True)
    return df.head(top_k)


def hourly_matrix(date: str, charger_type: str = "급속") -> pd.DataFrame:
    """읍면동 × 시간 리스크 행렬(히트맵용)."""
    rows = []
    for emd in ds.REGION_META:
        curve = wait_curve(emd, charger_type, date)
        pres = ds.region_pressure().set_index("emd_name").loc[emd]
        for r in curve.itertuples():
            comp_wait = min(1.0, r.wait_min / WAIT_CAP_MIN)
            score = 100 * (WEIGHTS["wait"] * comp_wait
                           + WEIGHTS["supply"] * min(1.0, pres["ev_per_charger"] / 40.0)
                           + WEIGHTS["tour"] * min(1.0, pres["tourist_load"] / 1200.0))
            rows.append({"emd_name": emd, "hour": r.hour, "risk": round(score, 1),
                         "wait_min": round(r.wait_min, 1)})
    df = pd.DataFrame(rows)
    df.attrs["weekday"] = parse_weekday(date)
    return df


def avoid_windows(emd: str, date: str, charger_type: str = "급속", n: int = 3) -> list[dict]:
    curve = wait_curve(emd, charger_type, date)
    top = curve.sort_values("wait_min", ascending=False).head(n)
    return [{"hour": int(r.hour), "window": f"{int(r.hour):02d}:00-{int(r.hour) + 1:02d}:00",
             "wait_min": round(float(r.wait_min), 1)} for r in top.itertuples()]


def safety_flags(stations: pd.DataFrame, date: str, city: str) -> tuple[pd.DataFrame, dict]:
    """weather_safety_agent 용 검증: 사고다발지역 근접 + 기상 노출을 함께 평가."""
    acc = ds.load("accident")
    wx = ds.weather_for(date, city)
    flags = []
    for r in stations.itertuples():
        reasons, severity = [], 0.0
        sub = acc[acc["emd_name"] == r.emd_name]
        if len(sub):
            d = ds.haversine_m(r.latitude, r.longitude, sub["latitude"].values, sub["longitude"].values)
            near = sub[d <= sub["radius_m"].values + 100]
            if len(near):
                worst = near.sort_values("accident_count", ascending=False).iloc[0]
                if int(worst["accident_count"]) >= 7:
                    severity = max(severity, min(1.0, int(worst["accident_count"]) / 12))
                    reasons.append(f'사고다발지역 {worst["hotspot_name"]} 반경 내(사고 {int(worst["accident_count"])}건)')
        heavy_rain = wx["rainfall_mm"] >= 20
        strong_wind = wx["wind_ms"] >= 14
        if r.parking_type == "야외" and (heavy_rain or strong_wind):
            severity = max(severity, 0.75 if heavy_rain else 0.6)
            reasons.append("야외 충전기 + " + ("호우" if heavy_rain else "강풍") + " 노출")
        if r.status != "운영중":
            severity = max(severity, 0.5)
            reasons.append("점검중")
        flags.append({"station_id": r.station_id, "station_name": r.station_name,
                      "severity": round(severity, 2), "flagged": severity >= 0.6,
                      "reasons": reasons})
    return pd.DataFrame(flags), wx


def confidence(date: str, wait_rows: int) -> tuple[float, list[str]]:
    """신뢰도: 패턴 표본 수 · 패턴 데이터 노후도 · 기상 데이터 최신성."""
    notes = []
    target = dt.date.fromisoformat(date)
    age_years = (target - dt.date(2022, 10, 31)).days / 365.25
    base = 0.86
    base -= min(0.25, max(0.0, age_years) * 0.03)
    notes.append(f"대기 패턴 기준일 2022-10-31 → 대상일 {date} (약 {age_years:.1f}년 차, 수준은 최신 EV·충전기로 보정)")
    if wait_rows < 50:
        base -= 0.10
        notes.append(f"시간대 표본 부족({wait_rows}건) — 신뢰도 하향")
    return round(max(0.45, min(0.95, base)), 2), notes
