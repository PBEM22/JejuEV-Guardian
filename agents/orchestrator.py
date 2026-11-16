# -*- coding: utf-8 -*-
"""오케스트레이터 — 질의 해석 → A2A 라우팅(재탐색 루프 포함) → 최종 리포트.

Zero-Key 모드에서는 규칙 기반 한국어 해석기(``parse_query``)가 동작하고,
Ollama/클라우드 모드에서는 LLM이 같은 해석 작업을 맡는다(숫자 계산은 항상 결정적 코드).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from tools import datasets as ds
from tools.config import ENGINE_LABELS, OUTPUT_DIR, engine_mode, ensure_dirs

from . import backends
from .concierge import ConciergeAgent
from .ev_demand import EvDemandAgent
from .protocol import A2ABus
from .weather_safety import WeatherSafetyAgent

HOUR_WORDS = {
    "새벽": 4, "아침": 8, "출근": 8, "오전": 10, "점심": 12, "낮": 14,
    "오후": 15, "저녁": 18, "퇴근": 18, "밤": 21, "자정": 0, "심야": 23,
}
MAX_REWORK = 1


@dataclass
class RunResult:
    query: str
    parsed: dict
    engine: str
    engine_label: str
    artifacts: list[dict] = field(default_factory=list)
    log: list[dict] = field(default_factory=list)
    final: dict = field(default_factory=dict)
    report_md: str = ""
    report_pdf: str = ""
    charts: dict = field(default_factory=dict)
    out_dir: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query": self.query, "parsed": self.parsed, "engine": self.engine,
            "engine_label": self.engine_label, "artifacts": self.artifacts, "log": self.log,
            "final": self.final, "report_md": self.report_md, "report_pdf": self.report_pdf,
            "charts": self.charts, "out_dir": self.out_dir, "warnings": self.warnings,
        }


# --------------------------------------------------------------------------
# 규칙 기반 한국어 질의 해석 (Zero-Key 기본 경로)
# --------------------------------------------------------------------------
def _resolve_region(q: str) -> str | None:
    best, best_len = None, 0
    for emd, meta in ds.REGION_META.items():
        for token in [emd] + meta["alias"]:
            if token in q and len(token) > best_len:
                best, best_len = emd, len(token)
    return best


def _resolve_hour(q: str) -> int | None:
    m = re.search(r"(오전|오후|밤|저녁|아침)?\s*(\d{1,2})\s*시", q)
    if m:
        h = int(m.group(2))
        if m.group(1) in ("오후", "밤", "저녁") and h < 12:
            h += 12
        if m.group(1) == "오전" and h == 12:
            h = 0
        return min(23, max(0, h))
    for word, h in HOUR_WORDS.items():
        if word in q:
            return h
    return None


def _resolve_date(q: str, today: dt.date) -> tuple[str, str]:
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", q)
    if m:
        d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d.isoformat(), "명시된 날짜"
    m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", q)
    if m:
        d = dt.date(today.year, int(m.group(1)), int(m.group(2)))
        return d.isoformat(), "명시된 날짜"
    for i, wd in enumerate(ds.WEEKDAYS):
        if f"{wd}요일" in q:
            delta = (i - today.weekday()) % 7
            if delta == 0:
                delta = 7
            if "다음 주" in q:
                delta += 7 if delta < 7 else 0
            return (today + dt.timedelta(days=delta)).isoformat(), f"{wd}요일"
    if "내일" in q:
        return (today + dt.timedelta(days=1)).isoformat(), "내일"
    if "모레" in q:
        return (today + dt.timedelta(days=2)).isoformat(), "모레"
    if "오늘" in q or "지금" in q:
        return today.isoformat(), "오늘"
    return (today + dt.timedelta(days=(4 - today.weekday()) % 7 or 7)).isoformat(), "가장 가까운 금요일(기본값)"


def parse_query(query: str, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    q = query.strip()
    region = _resolve_region(q)
    date, date_basis = _resolve_date(q, today)
    hour = _resolve_hour(q)
    ctype = "완속" if "완속" in q else "급속"
    notes = []
    if region is None:
        # 지역 미지정 → 현재 공급압력이 가장 큰 지역을 임시 제안
        pressure = ds.region_pressure().sort_values("ev_per_charger", ascending=False)
        region = pressure.iloc[0]["emd_name"]
        notes.append(f"질의에 지역이 없어 공급압력이 가장 높은 '{region}'을(를) 기준으로 안내합니다.")
    if hour is None:
        hour = 18
        notes.append("시간대가 없어 퇴근 시간대(18시)를 기본값으로 사용했습니다.")
    return {
        "region": region, "date": date, "hour": hour, "charger_type": ctype,
        "date_basis": date_basis, "notes": notes, "raw": query,
    }


# --------------------------------------------------------------------------
def build_bus() -> A2ABus:
    bus = A2ABus()
    bus.register(EvDemandAgent())
    bus.register(WeatherSafetyAgent())
    bus.register(ConciergeAgent())
    return bus


def run(query: str, *, date: str | None = None, hour: int | None = None,
        region: str | None = None, mode: str | None = None, out_dir: Path | None = None) -> RunResult:
    ensure_dirs()
    today = dt.date.today()
    mode = mode or engine_mode()
    planner = backends.get_backend(mode)

    parsed = parse_query(query, today)
    engine_used, engine_reason = "zerokey", ""
    if planner.name != "zerokey":
        llm = planner.parse(query, today, list(ds.REGION_META.keys()))
        if llm:
            parsed.update({k: v for k, v in llm.items() if v not in (None, "")})
            engine_used = planner.name
        else:
            engine_reason = f"{planner.name} 해석 실패 → Zero-Key 규칙 해석으로 폴백"
    # 명시적 인자 우선
    if region:
        parsed["region"] = region
    if date:
        parsed["date"] = date
    if hour is not None:
        parsed["hour"] = int(hour)

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(out_dir or OUTPUT_DIR / f"run_{stamp}_{parsed['region']}_{parsed['hour']:02d}h")
    out.mkdir(parents=True, exist_ok=True)

    bus = build_bus()
    result = RunResult(query=query, parsed=parsed, engine=engine_used,
                       engine_label=ENGINE_LABELS.get(engine_used, engine_used), out_dir=str(out))
    if engine_reason:
        result.warnings.append(engine_reason)

    # ---- 1) ev_demand_agent -------------------------------------------
    req, art = bus.request(
        "orchestrator", "ev_demand_agent", "charging_wait_risk",
        {"region": parsed["region"], "date": parsed["date"], "hour": parsed["hour"],
         "charger_type": parsed["charger_type"], "top_k": 6},
        constraints={"max_latency_ms": 4000},
        context={"user_query": query},
    )
    result.artifacts.append({"request": req.to_dict(), "artifact": art.to_dict()})
    if art.status == "error":
        result.final = art.to_dict()
        result.warnings += art.warnings
        _persist(bus, result)
        return result

    demand_art = art
    previous_candidates = list(art.data["candidates"])
    excluded_all: list[str] = []
    rework_done = False
    flagged_records: list[dict] = []

    # ---- 2) weather_safety_agent ↔ ev_demand_agent 재탐색 루프 ----------
    for attempt in range(MAX_REWORK + 1):
        req, art = bus.request(
            "orchestrator", "weather_safety_agent", "safety_weather_check",
            {"region": parsed["region"], "date": parsed["date"], "hour": parsed["hour"],
             "candidates": demand_art.data["candidates"], "check_top_n": 5},
            context={"task": demand_art.task_id, "attempt": attempt},
        )
        result.artifacts.append({"request": req.to_dict(), "artifact": art.to_dict()})
        if art.status == "error":
            result.final = art.to_dict()
            _persist(bus, result)
            return result
        safety_art = art
        if art.next_action.get("type") != "re_route_needed":
            break
        if attempt == MAX_REWORK:
            result.warnings.append("재탐색 최대 횟수 도달 — 남은 후보로 리포트를 생성했습니다.")
            break
        flagged_records += [f for f in art.data.get("flagged", []) if f not in flagged_records]
        exclude = art.next_action.get("exclude_stations", [])
        excluded_all += [e for e in exclude if e not in excluded_all]
        req, art = bus.request(
            "weather_safety_agent", "ev_demand_agent", "re_route",
            {"region": parsed["region"], "date": parsed["date"], "hour": parsed["hour"],
             "charger_type": parsed["charger_type"], "top_k": 6,
             "exclude_stations": excluded_all,
             "rework_reason": art.next_action.get("reason", "안전·기상 위험")},
            reply_to=art.message_id, task_id=demand_art.task_id, context={"trigger": "re_route_needed"},
        )
        result.artifacts.append({"request": req.to_dict(), "artifact": art.to_dict()})
        if art.status == "error":
            result.final = art.to_dict()
            _persist(bus, result)
            return result
        demand_art = art
        rework_done = True

    # ---- 3) concierge_report_agent -------------------------------------
    req, art = bus.request(
        "orchestrator", "concierge_report_agent", "compose_report",
        {"region": parsed["region"], "date": parsed["date"], "hour": parsed["hour"],
         "charger_type": parsed["charger_type"], "demand": demand_art.data, "safety": safety_art.data,
         "previous_candidates": previous_candidates, "user_query": query,
         "a2a_markdown": bus.to_markdown(), "engine": engine_used,
         "confidence": demand_art.confidence, "out_dir": str(out), "rerouted": rework_done, "excluded_total": len(excluded_all), "excluded_records": flagged_records},
        context={"demand_task": demand_art.task_id, "safety_task": safety_art.task_id},
    )
    result.artifacts.append({"request": req.to_dict(), "artifact": art.to_dict()})
    result.final = art.to_dict()
    if art.status == "ok":
        result.report_md = art.data["report_md"]
        result.report_pdf = art.data["report_pdf"]
        result.charts = art.data["charts"]
    result.warnings += art.warnings
    _persist(bus, result)
    return result


def _persist(bus: A2ABus, result: RunResult) -> None:
    out = Path(result.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bus.to_jsonl(out / "a2a_log.jsonl")
    (out / "agent_cards.json").write_text(bus.card_json(), encoding="utf-8")
    (out / "run.json").write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    result.log = bus.log
