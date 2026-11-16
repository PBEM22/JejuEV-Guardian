# -*- coding: utf-8 -*-
"""ev_demand_agent — 충전·유입 분석 Agent.

역할: 지역·요일·시간대별 충전 대기 리스크를 산출하고, 조건에 맞는 충전소 후보를 우선순위로 제시한다.
데이터: [494] 충전소 정보 · [136~141] 충전이력/대기시간 · [512] EV 보급 · [745/746] 관광 유입
출력: 후보 충전소 TOP-N(예상 대기·리스크·사유), 24시간 대기 곡선, 회피 시간대, 근거 데이터 목록
"""
from __future__ import annotations

import pandas as pd

from tools import datasets as ds
from tools import risk
from tools.util import jnum, records

from .protocol import AgentCard, TaskArtifact, TaskRequest

INPUT_SCHEMA = {
    "type": "object",
    "required": ["region", "date", "hour"],
    "properties": {
        "region": {"type": "string"},
        "date": {"type": "string"},
        "hour": {"type": "integer", "minimum": 0, "maximum": 23},
        "charger_type": {"type": "string", "enum": ["급속", "완속"]},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
        "exclude_stations": {"type": "array", "items": {"type": "string"}},
        "rework_reason": {"type": "string"},
    },
}

OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["emd_name", "candidates", "wait_min", "avoid_windows"],
    "properties": {
        "emd_name": {"type": "string"},
        "candidates": {"type": "array"},
        "wait_min": {"type": "number"},
        "avoid_windows": {"type": "array"},
    },
}


class EvDemandAgent:
    card = AgentCard(
        name="ev_demand_agent",
        display_name="충전·유입 분석 Agent",
        role="지역·요일·시간대별 충전 대기 리스크 산출 및 후보 충전소 우선순위 제시",
        version="1.0.0",
        capabilities=["wait_risk_ranking", "hourly_risk_curve", "avoid_window", "reroute_with_exclusion"],
        input_schema=INPUT_SCHEMA,
        output_schema=OUTPUT_SCHEMA,
        data_sources=[ds.DATASETS[k].to_dict() for k in ("chargers", "wait", "history", "ev", "tourist")],
        constraints={"model": "pattern(2022)×level(2024~2025)×weather(실시간)",
                     "max_candidates": 20, "deterministic": True},
    )

    def handle(self, req: TaskRequest) -> TaskArtifact:
        p = req.payload
        emd = p["region"]
        date = p["date"]
        hour = int(p["hour"])
        ctype = p.get("charger_type", "급속")
        top_k = int(p.get("top_k", 10))
        exclude = [s for s in p.get("exclude_stations", []) if s]
        rework = bool(p.get("rework_reason"))

        if emd not in ds.REGION_META:
            return TaskArtifact(
                from_agent="ev_demand_agent", to_agent=req.from_agent, task_id=req.task_id,
                status="error", summary=f"분석 대상 지역을 찾을 수 없습니다: {emd}",
                warnings=["지원 지역: " + ", ".join(ds.REGION_META.keys())],
            )

        curve = risk.wait_curve(emd, ctype, date)
        matrix = risk.hourly_matrix(date, ctype)
        matrix.attrs["weekday"] = risk.parse_weekday(date)
        stations = risk.station_risks(emd, date, hour, ctype, exclude=set(exclude), top_k=top_k)
        windows = risk.avoid_windows(emd, date, ctype, n=3)
        pres = ds.region_pressure().set_index("emd_name").loc[emd]
        wx = ds.weather_for(date, ds.REGION_META[emd]["city"])
        conf, conf_notes = risk.confidence(date, int(curve["sample_cnt"].sum()))

        fallback = pd.DataFrame()
        if exclude:
            fallback = risk.station_risks(emd, date, hour, ctype, exclude=set(), top_k=top_k)
            fallback = fallback[fallback["station_id"].isin(exclude)].copy()
            fallback["caution"] = True

        nearby_used: list[str] = []
        if 0 < len(stations) < 3:
            # 재탐색으로 후보가 말라가면 반경 10km 내 인접 읍면동 충전소를 대안으로 제시
            stations, nearby_used = _add_nearby(emd, date, hour, ctype, stations, set(exclude))

        if len(stations) == 0:
            return TaskArtifact(
                from_agent="ev_demand_agent", to_agent=req.from_agent, task_id=req.task_id,
                status="error",
                summary=f"{emd}에 {ctype} 충전소가 없습니다. 다른 지역 또는 완속 충전을 제안합니다.",
                warnings=["조건에 맞는 충전소 없음"],
            )

        best = stations.iloc[0]
        cur = curve[curve["hour"] == hour].iloc[0]
        n_excl = len(exclude)
        summary = (
            f"{emd} {date}({risk.parse_weekday(date)}) {hour:02d}시 {ctype} 기준 "
            f"지역 평균 예상 대기 {cur.wait_min:.1f}분, 최적 후보 '{best.station_name}' {best.wait_min:.1f}분"
            + (f" (재탐색: 제외 {n_excl}개소 반영)" if rework else "")
        )

        trend = _trend_note(curve, hour)
        data = {
            "emd_name": emd,
            "nearby_regions": nearby_used,
            "city_name": ds.REGION_META[emd]["city"],
            "region_kind": ds.REGION_META[emd]["kind"],
            "weekday": risk.parse_weekday(date),
            "date": date,
            "hour": hour,
            "charger_type": ctype,
            "wait_min": jnum(cur.wait_min),
            "wait_base_min": jnum(cur.wait_base_min),
            "p90_min": jnum(cur.p90_min),
            "growth_factor": jnum(cur.growth_factor),
            "tour_factor": jnum(cur.tour_factor),
            "weather_factor": jnum(cur.weather_factor),
            "pressure": {"ev_per_charger": jnum(pres.ev_per_charger),
                         "chargers_now": int(pres.chargers_now),
                         "ev_2024": int(pres.ev_2024),
                         "tourist_load": jnum(pres.tourist_load)},
            "candidates": records(stations, top_k),
            "fallback": records(fallback, top_k) if len(fallback) else [],
            "excluded_applied": exclude,
            "avoid_windows": windows,
            "hourly_curve": records(curve[["hour", "wait_min", "p90_min"]], 24),
            "trend_note": trend,
            "weather": {k: jnum(v) for k, v in wx.items()},
        }
        evidence = [
            {**ds.DATASETS["wait"].to_dict(), "used_for": "요일·시간대 대기 패턴(형태)"},
            {**ds.DATASETS["chargers"].to_dict(), "used_for": "현재 충전기 수·설치연도·충전소 속성"},
            {**ds.DATASETS["ev"].to_dict(), "used_for": "읍면동별 EV 등록대수(공급 압력)"},
            {**ds.DATASETS["tourist"].to_dict(), "used_for": "월별 관광 유입(계절 계수)"},
            {**ds.DATASETS["history"].to_dict(), "used_for": "과거 충전 수요 추세(교차 확인)"},
        ]
        warnings = list(conf_notes)
        if rework:
            warnings.append(f"weather_safety_agent 재탐색 요청 반영: {p.get('rework_reason', '안전·기상 위험')}")
        return TaskArtifact(
            from_agent="ev_demand_agent",
            to_agent=req.from_agent,
            task_id=req.task_id,
            status="ok",
            summary=summary,
            data=data,
            evidence=evidence,
            method=("예상대기 = 과거(2022) 요일×시간 대기 패턴 × (현재 EV/충전기 ÷ 2022 EV/충전기) "
                    "× 월별 관광 계절계수 × 기상 보정계수. 리스크 = 0.55·대기 + 0.20·공급압력 + 0.15·관광부하 + 0.10·안전"),
            confidence=conf,
            warnings=warnings,
            next_action={"type": "handoff", "to_agent": "weather_safety_agent",
                         "reason": "후보 충전소의 기상·사고다발지역 안전성 교차 검증"},
        )


def _add_nearby(emd: str, date: str, hour: int, ctype: str, current: pd.DataFrame,
                exclude: set[str], radius_km: float = 8.0, want: int = 6):
    """인접 읍면동까지 넓혀 대안 충전소를 채운다(우회 안내용)."""
    me = ds.REGION_META[emd]
    used = []
    frames = [current]
    for other, meta in ds.REGION_META.items():
        if other == emd:
            continue
        dist = float(ds.haversine_m(me["lat"], me["lon"], meta["lat"], meta["lon"])) / 1000.0
        if dist > radius_km:
            continue
        extra = risk.station_risks(other, date, hour, ctype, exclude=exclude, top_k=3)
        if len(extra) == 0:
            continue
        extra = extra.copy()
        extra["nearby"] = True
        extra["distance_km"] = round(dist, 1)
        frames.append(extra)
        used.append(f"{other}({dist:.1f}km)")
        if sum(len(f) for f in frames) >= want:
            break
    if len(frames) == 1:
        return current, []
    base = current.copy()
    base["nearby"] = False
    base["distance_km"] = 0.0
    out = pd.concat(frames, ignore_index=True).sort_values("wait_min").head(want)
    return out.reset_index(drop=True), used


def _trend_note(curve: pd.DataFrame, hour: int) -> str:
    """질의 시각 전후 3시간 흐름을 한 문장으로."""
    lo, hi = max(0, hour - 3), min(23, hour + 3)
    sub = curve[(curve["hour"] >= lo) & (curve["hour"] <= hi)]
    if len(sub) < 3:
        return ""
    rising = sub["wait_min"].iloc[-1] > sub["wait_min"].iloc[0]
    return (f"{lo:02d}~{hi:02d}시 구간에서 대기가 {'증가' if rising else '감소'}하는 흐름"
            f"({sub['wait_min'].iloc[0]:.1f}분 → {sub['wait_min'].iloc[-1]:.1f}분)")
