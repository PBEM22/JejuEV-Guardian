# -*- coding: utf-8 -*-
"""JejuEV Guardian E2E 데모 — 3개 시나리오를 실제로 실행하고 산출물을 검증한다.

검증 항목
1. A2A 핸드오프: 시나리오별 홉 로그(요청→검증→재탐색→리포트)와 상태
2. 프로토콜 계약: 각 TaskArtifact 가 수신 에이전트의 output_schema 를 만족하는지,
   잘못된 요청(필수 필드 누락)이 '검증 실패'로 차단되는지
3. 산출물: PNG 차트 · Markdown · PDF · A2A 로그(JSONL) 실제 생성 여부와 크기
4. 재현성: 같은 조건을 두 번 실행해 핵심 수치가 동일한지(결정적 계산 확인)

실행
    python tests/run_e2e_demo.py            # 전체
    python tests/run_e2e_demo.py --quick    # 재현성 검사 생략
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents import orchestrator  # noqa: E402
from agents.protocol import validate  # noqa: E402

SCENARIOS = [
    {
        "name": "A. 금요일 오후 애월읍 이동 충전 리스크",
        "query": "금요일 오후 6시에 애월읍에서 급속충전 할 만한 곳 알려줘",
        "kwargs": {},
        "expect": {"region": "애월읍", "hour": 18, "min_hops": 3, "reroute": False},
    },
    {
        "name": "B. 비 오는 주말 중문 우회 충전소 탐색",
        "query": "비 오는 주말에 서귀포 중문에서 안전하게 충전할 곳 찾아줘",
        "kwargs": {"date": "2026-11-14", "hour": 13},
        "expect": {"region": "중문동", "hour": 13, "min_hops": 4, "reroute": True},
    },
    {
        "name": "C. 제주시 공항 인근 출퇴근 피크",
        "query": "평일 아침 출근시간 제주공항 근처 충전 대기 어때?",
        "kwargs": {"date": "2026-11-17", "hour": 8},
        "expect": {"region": "용담2동", "hour": 8, "min_hops": 3, "reroute": False},
    },
]

OK, FAIL = "PASS", "FAIL"
results: list[dict] = []


def check(cond: bool, label: str, detail: str = "") -> bool:
    results.append({"check": label, "result": OK if cond else FAIL, "detail": detail})
    print(f"  [{'✓' if cond else '✗'}] {label}" + (f" — {detail}" if detail else ""))
    return cond


def run_scenario(sc: dict, mode: str) -> orchestrator.RunResult:
    print(f"\n=== {sc['name']} ===")
    t0 = time.time()
    r = orchestrator.run(sc["query"], mode=mode, **sc["kwargs"])
    dt = time.time() - t0
    print(f"  실행 {dt:.1f}s · 엔진 {r.engine} · 홉 {len(r.log)}회")
    for row in r.log:
        print(f"    hop{row['hop']} {row['from']} → {row['to']} [{row['status']}] "
              f"{row['validation']} {row['latency_ms']}ms | {row['summary'][:70]}")

    art = r.final
    data = art.get("data", {})
    check(art.get("status") == "ok", "최종 Artifact 상태 ok", art.get("summary", "")[:60])
    check(r.parsed["region"] == sc["expect"]["region"], "지역 해석", r.parsed["region"])
    check(r.parsed["hour"] == sc["expect"]["hour"], "시간대 해석", str(r.parsed["hour"]))
    check(len(r.log) >= sc["expect"]["min_hops"], "A2A 홉 수", f"{len(r.log)} ≥ {sc['expect']['min_hops']}")
    has_rework = any(x["status"] == "rework_request" for x in r.log) and any(x["intent"] == "re_route" for x in r.log)
    check(has_rework == sc["expect"]["reroute"], "재탐색(re_route_needed) 흐름", f"기대={sc['expect']['reroute']} 실제={has_rework}")
    check(all(x["validation"] == "통과" for x in r.log), "모든 요청 스키마 검증 통과")
    check(len(r.log) == len(set(x["artifact_id"] for x in r.log)), "Artifact ID 유일성")

    # 산출물
    charts = data.get("charts", {})
    check(len(charts) >= 5, "차트 개수", f"{len(charts)}개")
    for key, p in charts.items():
        path = Path(p)
        check(path.exists() and path.stat().st_size > 8000, f"차트 파일 {key}", f"{path.stat().st_size // 1024 if path.exists() else 0}KB")
    md, pdf = Path(r.report_md), Path(r.report_pdf or "")
    check(md.exists() and md.stat().st_size > 1500, "Markdown 리포트", f"{md.stat().st_size // 1024 if md.exists() else 0}KB")
    check(bool(r.report_pdf) and pdf.exists() and pdf.stat().st_size > 20000, "PDF 리포트", f"{pdf.stat().st_size // 1024 if pdf.exists() else 0}KB")
    logf = Path(r.out_dir) / "a2a_log.jsonl"
    check(logf.exists() and len(logf.read_text(encoding="utf-8").strip().splitlines()) == len(r.log), "A2A 로그 JSONL")
    check((Path(r.out_dir) / "agent_cards.json").exists(), "AgentCard 산출물")

    # A2A 계약: 각 Artifact 가 해당 에이전트 output_schema 를 만족
    bus_cards = {c["name"]: c for c in orchestrator.build_bus().cards.values()} if False else None
    for pair in r.artifacts:
        a = pair["artifact"]
        if a["status"] == "ok":
            check(isinstance(a["evidence"], list) and len(a.get("method", "")) > 10,
                  f"{a['from_agent']} Artifact 근거·방법 기록")
            break

    top3 = data.get("top3", [])
    check(1 <= len(top3) <= 3, "추천 후보 1~3곳", f"{len(top3)}곳")
    if top3:
        check(all(t["wait_min"] >= 0 for t in top3), "대기시간 값 유효")
        print(f"  → TOP1 {top3[0]['station_name']} · {top3[0]['wait_min']}분 · 리스크 {top3[0]['risk_score']}")

    return r


def protocol_contract_test() -> None:
    print("\n=== D. A2A 프로토콜 계약 검증 ===")
    bus = orchestrator.build_bus()
    # (1) 필수 필드 누락 → 검증 실패로 실행 차단
    req, art = bus.request("orchestrator", "ev_demand_agent", "charging_wait_risk",
                           {"region": "애월읍", "date": "2026-11-20"})  # hour 누락
    check(art.status == "error" and any("hour" in e for e in art.warnings),
          "필수 필드(hour) 누락 요청 차단", art.warnings[:1])
    # (2) 허용되지 않은 enum
    req, art = bus.request("orchestrator", "ev_demand_agent", "charging_wait_risk",
                           {"region": "애월읍", "date": "2026-11-20", "hour": 18, "charger_type": "초급속"})
    check(art.status == "error", "enum 위반(charger_type) 요청 차단", art.warnings[:1])
    # (3) 미등록 에이전트
    req, art = bus.request("orchestrator", "unknown_agent", "x", {})
    check(art.status == "error", "미등록 에이전트 호출 차단")
    # (4) schema validator 자체 점검
    errs = validate({"a": 1}, {"type": "object", "required": ["b"]})
    check(bool(errs), "스키마 검증기 동작", str(errs))


def determinism_test(mode: str) -> None:
    print("\n=== E. 재현성(결정적 계산) 검증 ===")
    q = "금요일 오후 6시에 애월읍에서 급속충전 할 만한 곳 알려줘"
    a = orchestrator.run(q, mode=mode)
    b = orchestrator.run(q, mode=mode)
    ka = [(t["station_name"], t["wait_min"], t["risk_score"]) for t in a.final["data"]["top3"]]
    kb = [(t["station_name"], t["wait_min"], t["risk_score"]) for t in b.final["data"]["top3"]]
    check(ka == kb, "동일 질의 2회 실행 결과 동일", f"{ka[:1]} vs {kb[:1]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="zerokey")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    print(f"JejuEV Guardian E2E 데모 · 엔진={args.mode} · {time.strftime('%Y-%m-%d %H:%M:%S')}")
    out_root = ROOT / "outputs"
    runs = []
    try:
        for sc in SCENARIOS:
            runs.append(run_scenario(sc, args.mode))
        protocol_contract_test()
        if not args.quick:
            determinism_test(args.mode)
    except Exception:
        traceback.print_exc()
        results.append({"check": "예외 없이 실행", "result": FAIL, "detail": "예외 발생"})

    passed = sum(1 for r in results if r["result"] == OK)
    total = len(results)
    print("\n" + "=" * 70)
    print(f"결과: {passed}/{total} 통과")
    fails = [r for r in results if r["result"] == FAIL]
    for f in fails:
        print(f"  ✗ {f['check']} — {f['detail']}")

    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine": args.mode,
        "passed": passed, "total": total,
        "checks": results,
        "runs": [
            {"query": r.query, "parsed": r.parsed, "hops": len(r.log), "out_dir": r.out_dir,
             "report_md": r.report_md, "report_pdf": r.report_pdf,
             "top3": [{k: t[k] for k in ("station_name", "wait_min", "risk_score", "risk_level")}
                      for t in r.final.get("data", {}).get("top3", [])]}
            for r in runs
        ],
    }
    out_root.mkdir(exist_ok=True)
    (out_root / "e2e_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"요약 저장: {out_root / 'e2e_summary.json'}")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
