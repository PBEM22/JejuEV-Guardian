# -*- coding: utf-8 -*-
"""concierge_report_agent — 도민 안내·리포트 Agent.

앞선 두 에이전트의 A2A Artifact 를 종합해, 비전문가 도민이 바로 쓸 수 있는 형태로 바꾼다.
* 추천 충전소 TOP3(지금 출발 기준), 피해야 할 시간대
* 기상·안전 주의사항, 대안(우회) 안내
* 비교 차트 PNG 4~5종과 다운로드용 Markdown/PDF 리포트
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from tools import charts, datasets as ds, report, risk
from tools.util import jnum

from .protocol import AgentCard, TaskArtifact, TaskRequest

INPUT_SCHEMA = {
    "type": "object",
    "required": ["region", "date", "hour", "demand", "safety"],
    "properties": {
        "region": {"type": "string"},
        "date": {"type": "string"},
        "hour": {"type": "integer", "minimum": 0, "maximum": 23},
        "charger_type": {"type": "string"},
        "demand": {"type": "object"},
        "safety": {"type": "object"},
        "previous_candidates": {"type": "array"},
        "rerouted": {"type": "boolean"},
        "excluded_records": {"type": "array"},
        "excluded_total": {"type": "integer"},
        "user_query": {"type": "string"},
        "a2a_markdown": {"type": "string"},
        "engine": {"type": "string"},
        "out_dir": {"type": "string"},
    },
}

OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["top3", "report_path"],
    "properties": {"top3": {"type": "array"}, "report_path": {"type": "string"}},
}


class ConciergeAgent:
    card = AgentCard(
        name="concierge_report_agent",
        display_name="도민 안내·리포트 Agent",
        role="분석·검증 결과를 도민용 추천(TOP3·회피 시간대·주의사항)과 차트·리포트로 종합",
        version="1.0.0",
        capabilities=["recommendation", "chart_generation", "markdown_report", "pdf_report"],
        input_schema=INPUT_SCHEMA,
        output_schema=OUTPUT_SCHEMA,
        data_sources=[ds.DATASETS[k].to_dict() for k in ("chargers", "wait", "ev", "tourist", "weather", "accident")],
        constraints={"max_recommendation": 3, "language": "ko"},
    )

    def handle(self, req: TaskRequest) -> TaskArtifact:
        p = req.payload
        emd, date, hour = p["region"], p["date"], int(p["hour"])
        ctype = p.get("charger_type", "급속")
        demand = p["demand"]
        safety = p["safety"]
        out_dir = Path(p.get("out_dir") or (Path.cwd() / "outputs" / f"run_{datetime.now():%Y%m%d_%H%M%S}"))
        out_dir.mkdir(parents=True, exist_ok=True)

        cands = pd.DataFrame(demand["candidates"])
        if len(cands) == 0:
            return TaskArtifact(from_agent="concierge_report_agent", to_agent=req.from_agent,
                                task_id=req.task_id, status="error",
                                summary="추천 후보가 없어 리포트를 만들 수 없습니다.")
        top3 = cands.sort_values("wait_min").head(3).copy()
        top3["caution"] = False
        fb = pd.DataFrame(demand.get("fallback") or [])
        if len(top3) < 3 and len(fb):
            fb = fb.sort_values("wait_min").head(3 - len(top3)).copy()
            fb["caution"] = True
            top3 = pd.concat([top3, fb], ignore_index=True)
        wx = safety["weather"]
        alerts = safety.get("alerts", [])
        weekday = demand.get("weekday", risk.parse_weekday(date))

        # --- 차트 ---------------------------------------------------------
        ch_dir = out_dir / "charts"
        ch_dir.mkdir(parents=True, exist_ok=True)
        chart_paths = {}
        matrix = risk.hourly_matrix(date, ctype)
        chart_paths["heatmap"] = charts.risk_heatmap(matrix, date, hour, ch_dir / "01_risk_heatmap.png")
        rank_df = pd.concat([cands, pd.DataFrame(demand.get("fallback") or [])], ignore_index=True)
        chart_paths["ranking"] = charts.station_ranking(rank_df, date, hour, ch_dir / "02_station_ranking.png")
        curve = risk.wait_curve(emd, ctype, date)
        chart_paths["curve"] = charts.hourly_curve(curve, hour, emd, ch_dir / "03_hourly_curve.png")
        series = ds.weather_series(days=21, region=wx["region"], end_date=date)
        chart_paths["weather"] = charts.weather_context(series, date, ch_dir / "04_weather_context.png")
        prev = p.get("previous_candidates") or []
        rerouted = bool(p.get("rerouted")) or (bool(prev) and safety.get("flagged_count", 0) > 0)
        if prev and (p.get("rerouted") or safety.get("flagged_count", 0) > 0):
            before = pd.DataFrame(prev)
            chart_paths["reroute"] = charts.reroute_compare(
                before, cands, safety.get("flagged", []) and [f["station_name"] for f in safety["flagged"]] or [],
                ch_dir / "05_reroute_compare.png")
        pressure = ds.region_pressure()
        chart_paths["supply"] = charts.supply_scatter(pressure, ch_dir / "06_supply_demand.png")

        # --- 문장 ---------------------------------------------------------
        best = top3.iloc[0]
        r1 = (f"{date}({weekday}) {hour:02d}시 {emd} 기준, 가장 유리한 곳은 "
              f"'{best.station_name}'(예상 대기 {best.wait_min:.1f}분, 리스크 {best.risk_score:.0f}/100)입니다.")
        r2 = (f"같은 시각 {emd} 평균 예상 대기는 {demand['wait_min']:.1f}분이며, "
              f"{'상위 10%는 ' + format(demand['p90_min'], '.1f') + '분까지 늘어납니다.' if demand.get('p90_min') else ''}")
        avoid = demand.get("avoid_windows", [])
        r3 = ("피해야 할 시간대는 " + ", ".join(f"{w['window']}({w['wait_min']:.0f}분)" for w in avoid) + " 입니다.") if avoid else ""
        if rerouted:
            r4 = (f"기상·안전 검증에서 위험 충전소 {int(p.get('excluded_total') or safety.get('flagged_count', 0))}곳을 후보에서 제외하고 재탐색했습니다. "
                  "아래 추천은 재탐색 이후 결과입니다.")
        else:
            r4 = "기상·안전 검증 결과 후보 충전소에서 특별한 위험 신호는 발견되지 않았습니다."

        if len(cands) < 3:
            summary_lines_extra = [f"안전 기준을 통과한 후보가 {len(cands)}곳뿐이라, 부득이한 대안은 '주의' 표시와 함께 제시합니다."]
        else:
            summary_lines_extra = []
        summary_lines = [x for x in (r1, r2, r3, r4) if x] + summary_lines_extra
        top3_records = []
        for r in top3.itertuples():
            top3_records.append({
                "station_name": r.station_name,
                "emd_name": r.emd_name,
                "charger_count": int(r.charger_count),
                "wait_min": jnum(r.wait_min),
                "p90_min": jnum(r.p90_min),
                "risk_score": jnum(r.risk_score),
                "risk_level": r.risk_level,
                "parking_type": r.parking_type,
                "parking_fee": r.parking_fee,
                "open_hours": r.open_hours,
                "operator": r.operator,
                "reasons": r.reasons if isinstance(r.reasons, list) else [str(r.reasons)],
                "caution": bool(getattr(r, "caution", False)),
            })

        content = {
            "title": "JejuEV Guardian — 충전 대기·이동 리스크 리포트",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "query": p.get("user_query", f"{emd} {date} {hour}시 충전"),
            "scenario": {"region": emd, "city": demand.get("city_name", ""), "date": date, "weekday": weekday,
                         "hour": hour, "charger_type": ctype},
            "summary_lines": summary_lines,
            "top3": top3_records,
            "avoid": avoid,
            "weather": wx,
            "alerts": alerts,
            "rerouted": rerouted,
            "excluded": p.get("excluded_records") or safety.get("flagged", []),
            "a2a": p.get("a2a_markdown", ""),
            "evidence": [
                {**ds.DATASETS["wait"].to_dict(), "used_for": "요일·시간대 대기 패턴"},
                {**ds.DATASETS["chargers"].to_dict(), "used_for": "충전소·충전기 현황"},
                {**ds.DATASETS["ev"].to_dict(), "used_for": "EV 등록대수(공급 압력)"},
                {**ds.DATASETS["tourist"].to_dict(), "used_for": "관광 유입(계절 계수)"},
                {**ds.DATASETS["weather"].to_dict(), "used_for": "대상일 기상"},
                {**ds.DATASETS["accident"].to_dict(), "used_for": "사고다발지역 안전 검증"},
            ],
            "method": demand.get("method_note", ""),
            "confidence": jnum(p.get("confidence", 0.8)),
            "engine": p.get("engine", "zerokey"),
            "warnings": list(demand.get("warnings", [])) + list(safety.get("warnings", [])),
            "charts": {k: str(v) for k, v in chart_paths.items()},
            "pressure": demand.get("pressure", {}),
            "trend_note": demand.get("trend_note", ""),
        }

        md_path = out_dir / "report.md"
        md_path.write_text(report.render_markdown(content), encoding="utf-8")
        pdf_path = out_dir / "report.pdf"
        try:
            report.render_pdf(content, pdf_path)
        except Exception as e:  # pragma: no cover - PDF 실패해도 MD/차트는 남긴다
            content["warnings"].append(f"PDF 생성 실패(마크다운은 정상): {e}")
            pdf_path = None

        return TaskArtifact(
            from_agent="concierge_report_agent", to_agent=req.from_agent, task_id=req.task_id,
            status="ok",
            summary=summary_lines[0] if summary_lines else "리포트 생성 완료",
            data={
                "top3": top3_records,
                "summary_lines": summary_lines,
                "avoid_windows": avoid,
                "alerts": alerts,
                "weather": wx,
                "rerouted": rerouted,
                "charts": {k: str(v) for k, v in chart_paths.items()},
                "report_md": str(md_path),
                "report_pdf": str(pdf_path) if pdf_path else "",
                "out_dir": str(out_dir),
            },
            evidence=content["evidence"],
            method="추천=예상대기 최소 3곳 + 리스크 등급 표기, 회피시간=대기 상위 3시간, 주의사항=기상·사고다발 검증 결과",
            confidence=jnum(p.get("confidence", 0.8)),
            warnings=content["warnings"],
            next_action={"type": "final", "to_agent": "user"},
        )
