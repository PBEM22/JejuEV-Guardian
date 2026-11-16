# -*- coding: utf-8 -*-
"""리포트 렌더러 — Markdown(항상) + PDF(reportlab, 번들 한글 폰트)."""
from __future__ import annotations

from pathlib import Path

from .config import pdf_font
from .util import fmt_int

INK = "#16241F"
GREEN = "#0B6E4F"
MUTED = "#6B7A75"
LINE = "#D9E2DE"
PANEL = "#F4F8F6"
RED = "#C4453B"


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------
def render_markdown(c: dict) -> str:
    s = c["scenario"]
    L: list[str] = []
    L.append(f"# {c['title']}")
    L.append("")
    L.append(f"- 생성: {c['generated_at']} · 분석 엔진: `{c.get('engine','zerokey')}` · 신뢰도: {c.get('confidence','-')}")
    L.append(f"- 질의: “{c['query']}”")
    L.append(f"- 시나리오: {s['city']} {s['region']} · {s['date']}({s['weekday']}) {s['hour']:02d}시 · {s['charger_type']}")
    L.append("")
    L.append("## 1. 한눈에 보는 결론")
    for line in c["summary_lines"]:
        L.append(f"- {line}")
    L.append("")
    L.append("## 2. 추천 충전소 TOP3")
    L.append("")
    L.append("| 순위 | 충전소 | 충전기 | 예상 대기 | 상위10% | 리스크 | 주차 | 운영시간 |")
    L.append("|---:|---|---:|---:|---:|---:|---|---|")
    for i, r in enumerate(c["top3"], 1):
        L.append(f"| {i} | {r['station_name']} | {r['charger_count']}기 | {r['wait_min']:.1f}분 | "
                 f"{(r['p90_min'] or 0):.1f}분 | {r['risk_score']:.0f}({r['risk_level']}) | "
                 f"{r['parking_type']}/{r['parking_fee']} | {r['open_hours']} |")
    L.append("")
    if c["avoid"]:
        L.append("## 3. 피해야 할 시간대")
        L.append("")
        for w in c["avoid"]:
            L.append(f"- **{w['window']}** — 예상 대기 {w['wait_min']:.1f}분")
        L.append("")
    L.append("## 4. 기상·안전")
    wx = c["weather"]
    L.append("")
    L.append(f"- 기상: 강수 {wx['rainfall_mm']:.1f}mm · 최대풍속 {wx['wind_ms']:.1f}m/s · 평균기온 {wx['avg_temp']:.1f}°C "
             f"({wx['source']}, {wx['region']})")
    for a in c["alerts"]:
        L.append(f"- {a}")
    if c["excluded"]:
        L.append("")
        L.append("**재탐색(re_route_needed)으로 제외된 충전소**")
        for e in c["excluded"]:
            why = "; ".join(e["reasons"]) if isinstance(e["reasons"], list) else str(e["reasons"])
            L.append(f"- {e['station_name']} — {why}")
    L.append("")
    L.append("## 5. 차트")
    for k, v in c["charts"].items():
        name = Path(v).name
        L.append("")
        L.append(f"![{k}](charts/{name})")
    L.append("")
    L.append("## 6. A2A 핸드오프 로그")
    L.append("")
    L.append(c["a2a"] or "_(로그 없음)_")
    L.append("")
    L.append("## 7. 근거 데이터 (수집 시점 포함)")
    L.append("")
    L.append("| 데이터 | 기준일 | 단위/입도 | 활용 |")
    L.append("|---|---|---|---|")
    for e in c["evidence"]:
        L.append(f"| {e['dataset']} | {e['as_of']} | {e['granularity']} | {e['used_for']} |")
    L.append("")
    if c["warnings"]:
        L.append("## 8. 한계·주의")
        for w in c["warnings"]:
            L.append(f"- {w}")
        L.append("")
    L.append("---")
    L.append("JejuEV Guardian · 제주데이터허브 Open API 기반 · 계산은 결정적 코드, 문장은 규칙/LLM 보조")
    return "\n".join(L)


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
def render_pdf(c: dict, path: str | Path) -> str:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    reg, bold = pdf_font()
    pdfmetrics.registerFont(TTFont("KR", reg))
    if bold:
        pdfmetrics.registerFont(TTFont("KRB", bold))
        fam = "KRB"
    else:
        fam = "KR"

    body = ParagraphStyle("body", fontName="KR", fontSize=9.3, leading=14.5, textColor=colors.HexColor(INK),
                          alignment=TA_LEFT, spaceAfter=2)
    h1 = ParagraphStyle("h1", fontName=fam, fontSize=17, leading=22, textColor=colors.HexColor(GREEN), spaceAfter=6)
    h2 = ParagraphStyle("h2", fontName=fam, fontSize=11.5, leading=16, textColor=colors.HexColor(GREEN),
                        spaceBefore=10, spaceAfter=4)
    small = ParagraphStyle("small", fontName="KR", fontSize=7.8, leading=11.5, textColor=colors.HexColor(MUTED))
    cell = ParagraphStyle("cell", fontName="KR", fontSize=8.2, leading=11.5, textColor=colors.HexColor(INK))
    cell_b = ParagraphStyle("cellb", fontName=fam, fontSize=8.2, leading=11.5, textColor=colors.HexColor(INK))

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=15 * mm, bottomMargin=14 * mm,
                            title="JejuEV Guardian 분석 리포트", author="JejuEV Guardian")
    W = A4[0] - 32 * mm
    story: list = []

    def table(data, widths, header=True, zebra=True):
        t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
        style = [
            ("FONTNAME", (0, 0), (-1, -1), "KR"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.2),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(INK)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PANEL)),
                      ("FONTNAME", (0, 0), (-1, 0), fam)]
        if zebra:
            for i in range(1, len(data)):
                if i % 2 == 0:
                    style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FAFCFB")))
        t.setStyle(TableStyle(style))
        return t

    s = c["scenario"]
    story.append(Paragraph(c["title"], h1))
    story.append(Paragraph(
        f"생성 {c['generated_at']} · 엔진 {c.get('engine','zerokey')} · 신뢰도 {c.get('confidence','-')} · "
        f"질의 “{c['query']}”", small))
    story.append(Spacer(1, 6))
    story.append(table([
        ["지역", f"{s['city']} {s['region']}", "일시", f"{s['date']} ({s['weekday']}) {s['hour']:02d}시", "충전유형", s['charger_type']],
    ], [16 * mm, 40 * mm, 14 * mm, 46 * mm, 18 * mm, 22 * mm], header=False, zebra=False))
    story.append(Spacer(1, 8))

    story.append(Paragraph("1. 한눈에 보는 결론", h2))
    for line in c["summary_lines"]:
        story.append(Paragraph(f"• {line}", body))

    story.append(Paragraph("2. 추천 충전소 TOP3", h2))
    rows = [["순위", "충전소", "충전기", "예상 대기", "상위 10%", "리스크", "주차", "비고"]]
    for i, r in enumerate(c["top3"], 1):
        note = "주의(안전·기상)" if r.get("caution") else "권장"
        rows.append([str(i), r["station_name"], f"{r['charger_count']}기", f"{r['wait_min']:.1f}분",
                     f"{(r['p90_min'] or 0):.1f}분", f"{r['risk_score']:.0f} ({r['risk_level']})",
                     f"{r['parking_type']}/{r['parking_fee']}", note])
    story.append(table(rows, [10 * mm, 46 * mm, 14 * mm, 18 * mm, 17 * mm, 24 * mm, 22 * mm, 26 * mm]))

    if c["avoid"]:
        story.append(Paragraph("3. 피해야 할 시간대", h2))
        story.append(table([["시간대", "예상 대기"]] + [[w["window"], f"{w['wait_min']:.1f}분"] for w in c["avoid"]],
                           [30 * mm, 30 * mm]))
    if c["excluded"]:
        story.append(Paragraph("재탐색으로 제외된 충전소", h2))
        rows = [["충전소", "제외 사유"]]
        for e in c["excluded"]:
            why = "; ".join(e["reasons"]) if isinstance(e["reasons"], list) else str(e["reasons"])
            rows.append([e["station_name"], Paragraph(why, cell)])
        story.append(table(rows, [45 * mm, 117 * mm]))

    story.append(Paragraph("4. 기상·안전", h2))
    wx = c["weather"]
    story.append(Paragraph(
        f"강수 {wx['rainfall_mm']:.1f}mm · 최대풍속 {wx['wind_ms']:.1f}m/s · 평균기온 {wx['avg_temp']:.1f}°C "
        f"({wx['region']}, 출처: {wx['source']})", body))
    for a in c["alerts"]:
        story.append(Paragraph(f"• {a}", body))

    story.append(PageBreak())
    story.append(Paragraph("5. 차트", h2))
    for k, v in c["charts"].items():
        p = Path(v)
        if not p.exists():
            continue
        from PIL import Image as PILImage
        with PILImage.open(p) as im:
            w, h = im.size
        width = W
        height = width * h / w
        if height > 110 * mm:
            height = 110 * mm
            width = height * w / h
        story.append(KeepTogether([Image(str(p), width=width, height=height), Spacer(1, 4)]))

    story.append(PageBreak())
    story.append(Paragraph("6. A2A 핸드오프 로그", h2))
    log_rows = [["홉", "보낸 곳 → 받은 곳", "의도", "검증", "상태", "지연(ms)", "요약"]]
    for r in c.get("a2a_rows", []):
        log_rows.append([str(r["hop"]), f"{r['from']} → {r['to']}", r["intent"], r["validation"],
                         r["status"], str(r["latency_ms"]), Paragraph(r["summary"][:90], cell)])
    if len(log_rows) > 1:
        story.append(table(log_rows, [8 * mm, 42 * mm, 24 * mm, 11 * mm, 16 * mm, 13 * mm, 48 * mm]))
    else:
        story.append(Paragraph("(로그 없음)", small))

    story.append(Paragraph("7. 근거 데이터 (수집 시점 포함)", h2))
    rows = [["데이터", "기준일", "입도", "활용"]]
    for e in c["evidence"]:
        rows.append([Paragraph(e["dataset"], cell), e["as_of"], Paragraph(e["granularity"], cell), Paragraph(e["used_for"], cell)])
    story.append(table(rows, [58 * mm, 21 * mm, 32 * mm, 51 * mm]))

    if c["warnings"]:
        story.append(Paragraph("8. 한계·주의", h2))
        for w in c["warnings"]:
            story.append(Paragraph(f"• {w}", small))

    story.append(Spacer(1, 8))
    story.append(Paragraph("JejuEV Guardian · 제주데이터허브 Open API 기반 · 계산은 결정적 코드(재현 가능), "
                           "문장 생성은 규칙 엔진 또는 경량 LLM 보조", small))
    doc.build(story)
    return str(path)
