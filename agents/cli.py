# -*- coding: utf-8 -*-
"""CLI — UI 없이 A2A 파이프라인을 실행한다.

    python -m agents.cli "금요일 오후 6시에 애월읍에서 급속충전 할 만한 곳 알려줘"
    python -m agents.cli "비 오는 주말 중문 충전" --date 2026-11-14 --hour 13 --mode zerokey
    python -m agents.cli --cards          # 에이전트 카드(JSON) 출력
"""
from __future__ import annotations

import argparse
import json
import sys

from . import backends, orchestrator


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="JejuEV Guardian CLI")
    ap.add_argument("query", nargs="?", help="자연어 질의")
    ap.add_argument("--date", help="YYYY-MM-DD")
    ap.add_argument("--hour", type=int, help="0-23")
    ap.add_argument("--region", help="읍면동 이름")
    ap.add_argument("--mode", default=None, choices=["zerokey", "ollama", "cloud", "auto"])
    ap.add_argument("--cards", action="store_true", help="AgentCard 목록 출력")
    ap.add_argument("--json", action="store_true", help="결과 전체를 JSON으로 출력")
    args = ap.parse_args(argv)

    if args.cards:
        bus = orchestrator.build_bus()
        print(bus.card_json())
        return 0

    if not args.query:
        ap.print_help()
        return 2

    print(f"엔진 상태: {json.dumps({k: v['ready'] for k, v in backends.backend_status().items()}, ensure_ascii=False)}")
    result = orchestrator.run(args.query, date=args.date, hour=args.hour, region=args.region, mode=args.mode)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=1))
        return 0

    print(f"\n질의: {result.query}")
    print(f"해석: {result.parsed['region']} · {result.parsed['date']} · {result.parsed['hour']:02d}시 · {result.parsed['charger_type']}")
    print(f"엔진: {result.engine_label}\n")
    print("A2A 핸드오프")
    for row in result.log:
        print(f"  hop{row['hop']:>2} {row['from']} → {row['to']} [{row['status']}] "
              f"검증 {row['validation']} · {row['latency_ms']}ms\n        {row['summary'][:100]}")
    data = result.final.get("data", {})
    print("\n결론")
    for line in data.get("summary_lines", []):
        print(f"  · {line}")
    print("\n추천 TOP3")
    for i, t in enumerate(data.get("top3", []), 1):
        print(f"  {i}. {t['station_name']} ({t['emd_name']}) — 대기 {t['wait_min']:.1f}분, 리스크 {t['risk_score']:.0f}"
              + (" [주의]" if t.get("caution") else ""))
    print(f"\n리포트: {result.report_md}")
    print(f"PDF   : {result.report_pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
