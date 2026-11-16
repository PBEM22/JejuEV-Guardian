# -*- coding: utf-8 -*-
"""weather_safety_agent — 기상·안전 검증 Agent.

역할: ev_demand_agent 가 올린 후보 충전소를 ① 대상일 기상([756]) ② 교통사고 다발지역([493]) 으로 교차 검증한다.
판단: 후보 상위권에 고위험 충전소(사고다발 반경 내, 야외+호우/강풍, 점검중)가 포함되면
      ev_demand_agent 에 **re_route_needed** A2A 요청을 보내 우회 후보를 다시 받는다.
"""
from __future__ import annotations

import pandas as pd

from tools import datasets as ds
from tools import risk
from tools.util import jnum, records

from .protocol import AgentCard, TaskArtifact, TaskRequest

INPUT_SCHEMA = {
    "type": "object",
    "required": ["region", "date", "hour", "candidates"],
    "properties": {
        "region": {"type": "string"},
        "date": {"type": "string"},
        "hour": {"type": "integer", "minimum": 0, "maximum": 23},
        "candidates": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["station_id", "station_name", "emd_name", "wait_min"],
                "properties": {
                    "station_id": {"type": "string"},
                    "station_name": {"type": "string"},
                    "emd_name": {"type": "string"},
                    "wait_min": {"type": "number"},
                    "parking_type": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
        },
        "check_top_n": {"type": "integer", "minimum": 1, "maximum": 10},
    },
}

OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["flags", "weather", "verdict"],
    "properties": {"flags": {"type": "array"}, "weather": {"type": "object"}, "verdict": {"type": "string"}},
}


class WeatherSafetyAgent:
    card = AgentCard(
        name="weather_safety_agent",
        display_name="기상·안전 검증 Agent",
        role="대상일 기상과 교통사고 다발지역으로 후보 충전소의 안전성을 교차 검증하고, 위험 시 재탐색을 요청",
        version="1.0.0",
        capabilities=["weather_lookup", "accident_proximity_check", "reroute_decision"],
        input_schema=INPUT_SCHEMA,
        output_schema=OUTPUT_SCHEMA,
        data_sources=[ds.DATASETS["weather"].to_dict(), ds.DATASETS["accident"].to_dict()],
        constraints={"flag_threshold": 0.6, "check_top_n_default": 5},
    )

    def handle(self, req: TaskRequest) -> TaskArtifact:
        p = req.payload
        cands = pd.DataFrame(p["candidates"])
        date = p["date"]
        check_n = int(p.get("check_top_n", min(5, len(cands))))
        emd = p["region"]
        city = ds.REGION_META.get(emd, {}).get("city", "제주시")

        top = cands.sort_values("wait_min").head(check_n).reset_index(drop=True)
        flags, wx = risk.safety_flags(top, date, city)

        merged = top.merge(flags, on="station_id", how="left", suffixes=("", "_flag"))
        flagged = merged[merged["flagged"] == True]  # noqa: E712
        verdict = "통과"
        next_action: dict
        if len(flagged) > 0:
            verdict = "재탐색 필요"
            exclude = flagged["station_id"].tolist()
            reasons = []
            for r in flagged.itertuples():
                reasons.append(f"{r.station_name}: " + "; ".join(r.reasons if isinstance(r.reasons, list) else [str(r.reasons)]))
            next_action = {
                "type": "re_route_needed",
                "to_agent": "ev_demand_agent",
                "exclude_stations": exclude,
                "reason": " / ".join(reasons)[:300],
            }
        else:
            next_action = {"type": "handoff", "to_agent": "concierge_report_agent",
                           "reason": "후보 충전소 안전·기상 검증 통과"}

        alerts = []
        if wx["rainfall_mm"] >= 30:
            alerts.append(f"호우 경보 수준({wx['rainfall_mm']:.1f}mm) — 해안도로·저지대 진입 주의")
        elif wx["rainfall_mm"] >= 10:
            alerts.append(f"비({wx['rainfall_mm']:.1f}mm) — 야외 충전기 대기 중 젖음·미끄럼 주의")
        if wx["wind_ms"] >= 14:
            alerts.append(f"강풍({wx['wind_ms']:.1f}m/s) — 개방형 충전기 이용 시 문 개방 주의")
        if wx["avg_temp"] <= 0:
            alerts.append("영하권 — 배터리 충전 효율 저하, 여유 있게 출발")
        if not alerts:
            alerts.append("특이 기상 없음 — 통상 운행 조건")

        summary = (f"{date} {wx['region']} 기상: 강수 {wx['rainfall_mm']:.1f}mm·최대풍속 {wx['wind_ms']:.1f}m/s·"
                   f"평균 {wx['avg_temp']:.1f}°C → 후보 {check_n}곳 중 위험 {len(flagged)}곳, 판정 '{verdict}'")

        data = {
            "verdict": verdict,
            "checked": int(check_n),
            "flagged_count": int(len(flagged)),
            "flagged": records(flagged[["station_id", "station_name", "severity", "reasons"]]),
            "flags": records(merged[["station_id", "station_name", "severity", "flagged", "reasons"]]),
            "weather": {k: jnum(v) for k, v in wx.items()},
            "alerts": alerts,
        }
        evidence = [
            {**ds.DATASETS["weather"].to_dict(), "used_for": "대상일 강수·강풍·기온"},
            {**ds.DATASETS["accident"].to_dict(), "used_for": "사고다발지역 반경 내 여부"},
        ]
        warnings = ["사고다발지역 자료는 2023-12 기준이며, 이후 도로 구조 변경은 반영되지 않았습니다."]
        return TaskArtifact(
            from_agent="weather_safety_agent", to_agent=req.from_agent, task_id=req.task_id,
            status="rework_request" if verdict == "재탐색 필요" else "ok",
            summary=summary, data=data, evidence=evidence,
            method="후보 상위 N개에 대해 (사고다발지역 중심거리 ≤ 반경+100m AND 사고 ≥7건) OR (야외 AND 강수≥20mm OR 풍속≥14m/s) OR 점검중 이면 위험(severity ≥ 0.6)",
            confidence=0.82 if verdict == "통과" else 0.78,
            warnings=warnings, next_action=next_action,
        )
