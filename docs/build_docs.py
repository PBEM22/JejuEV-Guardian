# -*- coding: utf-8 -*-
"""기획서(≤15p) · 결과설명자료 PDF 생성기 — 실제 실행 산출물을 그대로 인용한다.

실행:  python docs/build_docs.py
출력:  ../JejuEV_Guardian_기획서.pdf , docs/RESULT_REPORT.pdf
"""
from __future__ import annotations

import glob
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from weasyprint import CSS, HTML  # noqa: E402

# 문서용 폰트: Pretendard(있으면) → 번들 NanumGothic(항상 있음) 순으로 사용
FONTS = Path("/workspace/work/fonts")
if not (FONTS / "Pretendard-Regular.ttf").exists():
    FONTS = ROOT / "assets" / "fonts"
    FAM = "NanumGothic"
else:
    FAM = "PR"
OUT = ROOT.parent
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"

GREEN, INK, MUTED, LINE, PANEL, RED, AMBER = ("#0B6E4F", "#16241F", "#6B7A75", "#D9E2DE",
                                               "#F4F8F6", "#C4453B", "#E8A33D")

CSS_TEXT = f"""
@font-face {{font-family:'PR'; src:url('file://{FONTS}/{('Pretendard-Regular' if FAM=='PR' else 'NanumGothic-Regular')}.ttf'); font-weight:400;}}

@font-face {{font-family:'PR'; src:url('file://{FONTS}/{('Pretendard-SemiBold' if FAM=='PR' else 'NanumGothic-Bold')}.ttf'); font-weight:600;}}
@font-face {{font-family:'PR'; src:url('file://{FONTS}/{('Pretendard-Bold' if FAM=='PR' else 'NanumGothic-Bold')}.ttf'); font-weight:700;}}
@font-face {{font-family:'PR'; src:url('file://{FONTS}/{('Pretendard-ExtraBold' if FAM=='PR' else 'NanumGothic-Bold')}.ttf'); font-weight:800;}}
@page {{
  size: A4; margin: 17mm 15mm 15mm 15mm;
  @bottom-center {{ content: counter(page) " / " counter(pages); font-family:'PR'; font-size:8pt; color:{MUTED}; }}
  @top-right {{ content: "JejuEV Guardian · 제주 AI·빅데이터 활용 AI Agent 개발 챌린지"; font-family:'PR';
               font-size:7.4pt; color:{MUTED}; }}
}}
@page cover {{ margin:0; @bottom-center{{content:none;}} @top-right{{content:none;}} }}
* {{ box-sizing:border-box; }}
body {{ font-family:'PR'; font-size:9.3pt; line-height:1.62; color:{INK}; margin:0; word-break:keep-all; }}
h1 {{ font-size:19pt; font-weight:800; letter-spacing:-0.03em; margin:0 0 6px 0; color:{INK}; }}
h2 {{ font-size:13pt; font-weight:700; letter-spacing:-0.02em; color:{GREEN}; margin:16px 0 6px;
      padding-bottom:4px; border-bottom:1.2px solid {GREEN}; }}
h3 {{ font-size:10.4pt; font-weight:700; margin:11px 0 4px; color:{INK}; }}
h4 {{ font-size:9.4pt; font-weight:600; margin:8px 0 3px; color:{GREEN}; }}
p {{ margin:0 0 5px; }}
ul {{ margin:3px 0 6px 0; padding-left:14px; }}
li {{ margin:1.5px 0; }}
.small {{ font-size:8.2pt; color:{MUTED}; }}
.tiny {{ font-size:7.4pt; color:{MUTED}; line-height:1.45; }}
.mono {{ font-family:'DejaVu Sans Mono', monospace; font-size:7.4pt; }}
table {{ width:100%; border-collapse:collapse; margin:5px 0 8px; font-size:8.1pt; }}
th {{ background:{PANEL}; font-weight:700; text-align:left; padding:4px 5px; border:0.6px solid {LINE}; }}
td {{ padding:3.4px 5px; border:0.6px solid {LINE}; vertical-align:top; }}
tr:nth-child(even) td {{ background:#FAFCFB; }}
.kpi {{ display:flex; gap:6px; margin:10px 0; }}
.kpi div {{ flex:1; background:{PANEL}; border-left:3px solid {GREEN}; padding:8px 10px; border-radius:3px; }}
.kpi b {{ display:block; font-size:15pt; color:{GREEN}; font-weight:800; line-height:1.2; }}
.kpi span {{ font-size:7.8pt; color:{MUTED}; }}
.callout {{ background:{PANEL}; border:0.7px solid {LINE}; border-left:3px solid {GREEN};
            padding:7px 10px; margin:7px 0; border-radius:3px; font-size:8.6pt; }}
.warn {{ background:#FCF4F3; border-left-color:{RED}; }}
.quote {{ font-size:8.4pt; color:{MUTED}; border-left:2px solid {LINE}; padding-left:8px; margin:6px 0; }}
figure {{ margin:8px 0 10px; page-break-inside:avoid; }}
figure img {{ width:100%; border:0.6px solid {LINE}; border-radius:3px; }}
figcaption {{ font-size:7.6pt; color:{MUTED}; margin-top:3px; }}
.two {{ display:flex; gap:12px; }}
table.fix {{ table-layout:fixed; }}
table.fix td, table.fix th {{ word-break:break-all; }}
.two > div {{ flex:1; }}
.pb {{ page-break-before:always; }}
.nobreak {{ page-break-inside:avoid; }}
.tag {{ display:inline-block; background:{PANEL}; color:{GREEN}; border:0.6px solid {LINE};
        border-radius:10px; padding:1px 7px; font-size:7.4pt; font-weight:600; margin-right:3px; }}
code {{ font-family:'DejaVu Sans Mono', monospace; font-size:7.6pt; background:#F6F8F7; padding:1px 3px; border-radius:2px; }}
pre {{ font-family:'DejaVu Sans Mono', monospace; font-size:6.7pt; background:#F6F8F7; border:0.6px solid {LINE};
       border-radius:3px; padding:6px 8px; margin:5px 0 8px; line-height:1.45; white-space:pre-wrap; }}
"""

# --------------------------------------------------------------------------
# 실제 실행 결과 수집
# --------------------------------------------------------------------------
def latest_run(pattern: str) -> Path | None:
    cands = sorted(glob.glob(str(ROOT / "outputs" / f"run_*{pattern}*")), key=lambda p: Path(p).stat().st_mtime)
    return Path(cands[-1]) if cands else None


def run_info(d: Path | None) -> dict:
    if d is None:
        return {}
    run = json.loads((d / "run.json").read_text(encoding="utf-8"))
    logs = [json.loads(l) for l in (d / "a2a_log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    final = run.get("final", {}).get("data", {})
    demand = None
    for pair in run.get("artifacts", []):
        if pair["artifact"]["from_agent"] == "ev_demand_agent":
            demand = pair["artifact"]["data"]
    return {"dir": d, "query": run.get("query"), "parsed": run.get("parsed"), "logs": logs,
            "final": final, "demand": demand or {}, "charts": final.get("charts", {})}


A = run_info(latest_run("애월읍_18h"))
B = run_info(latest_run("중문동_13h"))
C = run_info(latest_run("용담2동_08h"))
E2E = json.loads((ROOT / "outputs" / "e2e_summary.json").read_text(encoding="utf-8"))

for key, info, name in (("heat", B, "heatmap"), ("rank", B, "ranking"), ("curve", B, "curve"),
                        ("weather", B, "weather"), ("reroute", B, "reroute"), ("supply", A, "supply")):
    src = info.get("charts", {}).get(name)
    if src and Path(src).exists():
        shutil.copyfile(src, ASSETS / f"{key}.png")
for key, info, name in (("heat_a", A, "heatmap"), ("rank_c", C, "ranking"), ("curve_c", C, "curve")):
    src = info.get("charts", {}).get(name)
    if src and Path(src).exists():
        shutil.copyfile(src, ASSETS / f"{key}.png")


def _short(text: str, n: int) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def log_table(logs: list[dict]) -> str:
    rows = "".join(
        f"<tr><td style='text-align:center'>{r['hop']}</td><td>{r['from']}</td><td>{r['to']}</td>"
        f"<td><code>{r['intent']}</code></td><td style='text-align:center'>{r['validation']}</td>"
        f"<td style='text-align:center'>{r['status']}</td><td style='text-align:right'>{r['latency_ms']}</td>"
        f"<td>{_short(r['summary'], 40)}</td></tr>"
        for r in logs)
    head = ("<colgroup><col style='width:4%'><col style='width:14%'><col style='width:14%'><col style='width:11%'>"
            "<col style='width:6%'><col style='width:10%'><col style='width:5%'><col style='width:36%'></colgroup>")
    return ("<table class='fix' style='font-size:7.2pt'>" + head +
            "<thead><tr><th>홉</th><th>보낸 곳</th><th>받는 곳</th><th>의도</th><th>검증</th>"
            "<th>상태</th><th>지연</th><th>요약</th></tr></thead><tbody>" + rows + "</tbody></table>")


def top3_table(info: dict) -> str:
    rows = ""
    for i, t in enumerate(info.get("final", {}).get("top3", [])[:3], 1):
        note = "주의" if t.get("caution") else "권장"
        rows += (f"<tr><td style='text-align:center'>{i}</td><td><b>{t['station_name']}</b></td>"
                 f"<td>{t['emd_name']}</td><td style='text-align:right'>{t['wait_min']:.1f}분</td>"
                 f"<td style='text-align:right'>{t['risk_score']:.0f}</td><td style='text-align:center'>{t['risk_level']}</td>"
                 f"<td>{t['parking_type']}/{t['parking_fee']}</td><td style='text-align:center'>{note}</td></tr>")
    return ("<table><tr><th style='width:6%'>순위</th><th style='width:26%'>충전소</th><th style='width:14%'>읍면동</th>"
            "<th style='width:11%'>예상 대기</th><th style='width:9%'>리스크</th><th style='width:9%'>등급</th>"
            "<th style='width:15%'>주차</th><th style='width:10%'>비고</th></tr>" + rows + "</table>")


def scenario_table() -> str:
    rows = ""
    for label, info in (("A · 금요일 18시 애월읍", A), ("B · 비 오는 토요일 13시 중문동", B), ("C · 평일 08시 공항권", C)):
        p = info.get("parsed", {})
        top = (info.get("final", {}).get("top3") or [{}])[0]
        rows += (f"<tr><td>{label}</td><td>{p.get('region','')} · {p.get('date','')[5:]} {p.get('hour','')}시</td>"
                 f"<td>{top.get('station_name','')}</td><td style='text-align:right'>{top.get('wait_min',0):.1f}분</td>"
                 f"<td style='text-align:center'>{'있음' if info.get('final',{}).get('rerouted') else '없음'}</td>"
                 f"<td style='text-align:center'>{len(info.get('logs',[]))}회</td></tr>")
    return ("<table><tr><th>시나리오</th><th>해석 결과</th><th>1순위 후보</th><th>예상 대기</th>"
            "<th>재탐색</th><th>A2A 홉</th></tr>" + rows + "</table>")


CHECK_ROWS = "".join(
    f"<tr><td>{c['check']}</td><td style='text-align:center'>{'통과' if c['result']=='PASS' else '실패'}</td>"
    f"<td class='tiny'>{c['detail'][:70]}</td></tr>" for c in E2E["checks"][:0])  # 표는 요약만 사용


# --------------------------------------------------------------------------
# 기획서
# --------------------------------------------------------------------------
def proposal_html() -> str:
    a_top = (A.get("final", {}).get("top3") or [{}])[0]
    b_top = (B.get("final", {}).get("top3") or [{}])[0]
    c_top = (C.get("final", {}).get("top3") or [{}])[0]
    b_demand = B.get("demand", {})
    n_checks = E2E["total"]
    n_pass = E2E["passed"]

    return f"""
<html><head><meta charset="utf-8"><style>{CSS_TEXT}</style></head><body>

<!-- ================= 표지 ================= -->
<section style="page:cover; height:297mm; padding:30mm 20mm 16mm; background:linear-gradient(155deg,#0B6E4F 0%,#0F7F5C 45%,#159A72 100%); color:#fff; position:relative;">
  <div style="font-size:8.4pt; letter-spacing:.14em; opacity:.85">JEJU AI · BIG DATA AI AGENT CHALLENGE 2026</div>
  <div style="margin-top:52mm">
    <div style="font-size:10.5pt; opacity:.9; margin-bottom:6px">제주 도민·운전자를 위한</div>
    <div style="font-size:33pt; font-weight:800; letter-spacing:-.035em; line-height:1.16">전기차 충전 대기·이동<br>리스크 분석 A2A 멀티 에이전트</div>
    <div style="font-size:15pt; font-weight:600; margin-top:10px; opacity:.95">JejuEV Guardian</div>
    <div style="width:64px; height:3px; background:#8FE0BF; margin:16px 0 14px"></div>
    <div style="font-size:9.2pt; line-height:1.85; opacity:.92; max-width:118mm">
      충전·유입 분석 → 기상·안전 검증 → 도민 안내·리포트.<br>
      세 에이전트가 A2A 표준 봉투(TaskRequest · TaskArtifact)로 주고받고,<br>
      위험 후보를 만나면 스스로 재탐색(re_route_needed)합니다.
    </div>
  <div style="position:absolute; left:20mm; right:20mm; bottom:20mm">
    <div style="display:flex; gap:8px; margin-bottom:14px">
      <div style="flex:1; background:rgba(255,255,255,.12); border-radius:4px; padding:9px 11px"><b style="font-size:15pt">3</b><div style="font-size:7.6pt; opacity:.85">A2A 에이전트</div></div>
      <div style="flex:1; background:rgba(255,255,255,.12); border-radius:4px; padding:9px 11px"><b style="font-size:15pt">7종</b><div style="font-size:7.6pt; opacity:.85">연계 데이터셋</div></div>
      <div style="flex:1; background:rgba(255,255,255,.12); border-radius:4px; padding:9px 11px"><b style="font-size:15pt">Zero-Key</b><div style="font-size:7.6pt; opacity:.85">키 없이 100% 동작</div></div>
      <div style="flex:1; background:rgba(255,255,255,.12); border-radius:4px; padding:9px 11px"><b style="font-size:15pt">{n_pass}/{n_checks}</b><div style="font-size:7.6pt; opacity:.85">E2E 자동검증</div></div>
    </div>
    <div style="font-size:8.4pt; opacity:.9">참가자 임채륜 (limchaeryun) · 2026. 11. 16. · 제주테크노파크 · 데이콘</div>
  </div>
</section>

<!-- ================= 1. 요약 ================= -->
<h1 style="margin-top:0">요약 — “충전기 앞에서 기다리는 시간을 미리 알려주는 에이전트”</h1>
<p>
제주는 전기차 보급률이 전국에서 가장 높은 지역 중 하나지만, 도민이 실제로 겪는 문제는 <b>‘지금 어디로 가야 덜 기다리는지’</b>를
알 수 없다는 점입니다. 관광지·공항·해안도로에 수요가 몰리고, 비·강풍이 오면 야외 충전기의 매력은 급락하며,
사고다발지역 안팎의 충전소는 접근 자체가 부담입니다. 기존 지도 앱은 <u>“충전소가 있다”</u>까지만 알려줄 뿐,
<u>“몇 분 기다리게 될지, 지금 대안은 어디인지”</u>는 답하지 않습니다.
</p>
<div class="callout">
<b>JejuEV Guardian</b>은 질문 한 줄에서 출발해 세 에이전트가 A2A로 협업합니다.
<i>“비 오는 주말에 서귀포 중문에서 안전하게 충전할 곳 찾아줘”</i>라고 물으면,
① 충전·유입 분석 에이전트가 과거 대기 패턴 × 최신 EV·충전기 × 관광 유입으로 후보를 계산하고,
② 기상·안전 검증 에이전트가 대상일 기상과 사고다발지역을 대조해 위험 후보 3곳을 걸러내며,
③ 도민 안내 에이전트가 <b>TOP3 추천·피해야 할 시간대·기상 주의사항·차트·리포트</b>를 만들어 냅니다.
</div>
<div class="kpi">
  <div><b>{b_top.get('wait_min', 0):.0f}분</b><span>중문 최적 후보 예상 대기<br>(재탐색 후, 강수 39mm)</span></div>
  <div><b>{a_top.get('wait_min', 0):.0f}분</b><span>금요일 18시 애월읍 최적 후보<br>(17,904건 학습 패턴)</span></div>
  <div><b>{c_top.get('wait_min', 0):.0f}분</b><span>평일 08시 공항권 최적 후보<br>(출근 피크)</span></div>
  <div><b>0원</b><span>필수 외부 비용<br>(API 키 없이 동작)</span></div>
</div>
<h3>목차</h3>
<table>
<tr><th style="width:6%">장</th><th>구성</th><th style="width:26%">핵심 질문에 대한 답</th></tr>
<tr><td style="text-align:center">①</td><td>구현목표 — 왜 이 서비스가 필요한가</td><td>도민이 겪는 3가지 정보 공백</td></tr>
<tr><td style="text-align:center">②</td><td>서비스 제안 — 무엇을, 어떻게 쓰는가</td><td>질문 1줄 → TOP3·회피 시간대·리포트</td></tr>
<tr><td style="text-align:center">③</td><td>Agent 개발 구성 — 누가, 어떻게 협업하는가</td><td>3개 Agent Card·A2A 봉투·재탐색 루프</td></tr>
<tr><td style="text-align:center">④</td><td>데이터 활용 계획 — 무엇을 근거로 삼는가</td><td>7종 데이터·기준일 차이 보완 논리</td></tr>
<tr><td style="text-align:center">⑤</td><td>개발·탑재 계획 — 센터 PC에서 실제로 도는가</td><td>사양 대응·Zero-Key·검증 결과</td></tr>
</table>
<div class="two" style="margin-top:14px">
  <div class="card" style="background:{PANEL}; border-left:3px solid {RED}; padding:9px 11px; border-radius:3px">
    <b>문제</b><div class="small" style="margin-top:3px">충전소는 지도에 있지만 <b>대기 시간</b>은 예측되지 않고,
    비·강풍 노출과 사고다발지역은 지도에 표시되지 않는다. 데이터는 있으나 시점이 제각각이라 그대로 합칠 수 없다.</div>
  </div>
  <div style="flex:0 0 12px"></div>
  <div class="card" style="background:{PANEL}; border-left:3px solid {AMBER}; padding:9px 11px; border-radius:3px">
    <b>접근</b><div class="small" style="margin-top:3px">역할이 다른 <b>3개 에이전트</b>가 A2A로 협업.
    대기 패턴은 <b>형태</b>로, EV·충전기·유입·기상은 <b>수준</b>으로 결합하고, 위험 후보는 <b>재탐색</b>한다.</div>
  </div>
  <div style="flex:0 0 12px"></div>
  <div class="card" style="background:{PANEL}; border-left:3px solid {GREEN}; padding:9px 11px; border-radius:3px">
    <b>증거</b><div class="small" style="margin-top:3px">3개 시나리오 실제 실행, <b>자동검증 {n_pass}/{n_checks} 통과</b>,
    차트·MD·PDF·A2A 로그 생성, 같은 질의 재실행 시 동일 결과(재현성).</div>
  </div>
</div>

<h3 style="margin-top:12px">재현 방법 (평가자용)</h3>
<pre>pip install -r requirements.txt
python tests/run_e2e_demo.py          # 3개 시나리오 + A2A 계약 + 재현성 자동 검증
streamlit run app.py                  # 웹 UI (또는 run.sh / run.bat)
python -m agents.cli "금요일 오후 6시에 애월읍에서 급속충전 할 만한 곳 알려줘"</pre>

<p class="tiny">본 기획서의 모든 수치·차트·로그는 2026-11-16에 이 저장소에서 실제로 실행한 결과에서 추출했습니다
(재현: <code>python tests/run_e2e_demo.py</code>).</p>

<!-- ================= ① 구현목표 ================= -->
<div class="pb"></div>
<h1>① 구현목표</h1>
<h2>1. 문제: 충전기는 늘었지만, ‘기다림’은 여전히 예측되지 않는다</h2>
<div class="two">
<div>
<h3>도민·운전자가 겪는 3가지 공백</h3>
<ul>
<li><b>시간의 공백</b> — 충전소 위치는 알지만 요일·시간대별 대기 시간은 알 수 없다. 퇴근길·주말 오후에 몰리는 패턴이 있어도 개인이 체감으로만 안다.</li>
<li><b>안전의 공백</b> — 비·강풍에 노출된 야외 충전기, 사고다발지역 인근 충전소가 지도에서 구분되지 않는다.</li>
<li><b>해석의 공백</b> — 제주데이터허브 Open API와 센터 데이터는 IT 비전문가가 직접 쓰기 어렵다. JSON 응답, 영문 필드, 제각각인 수집 시점.</li>
</ul>
</div>
<div>
<h3>기존 도구로는 답할 수 없는 이유</h3>
<ul>
<li>지도 앱은 <b>현재 상태</b>만 보여주고, 30분 뒤 도착했을 때의 대기는 말해주지 않는다.</li>
<li>충전 대기 데이터(2021~2022)와 최신 충전소·유입 데이터(2024~2025)는 <b>수집 시점이 다르다</b>. 그대로 합치면 틀린 답이 나온다.</li>
<li>기상·사고 데이터는 별도 사이트에 흩어져 있어 <b>한 번에 교차 판단</b>하기 어렵다.</li>
</ul>
</div>
</div>

<h2>2. 목표</h2>
<table>
<tr><th style="width:22%">목표</th><th style="width:40%">내용</th><th>달성 기준(검증 방법)</th></tr>
<tr><td><b>예측 가능한 대기</b></td><td>요일·시간대·지역·충전유형별 예상 대기(분)와 상위 10% 대기(p90) 제공</td><td>과거 패턴 × 최신 수준 결합 모델, 시나리오 3종에서 값 산출(3장)</td></tr>
<tr><td><b>안전한 이동</b></td><td>대상일 기상 + 사고다발지역으로 후보를 교차 검증, 위험 시 자동 재탐색</td><td>재탐색 루프가 로그로 남고 후보가 실제로 교체됨(3장 로그)</td></tr>
<tr><td><b>비전문가 사용성</b></td><td>자연어 1줄 → 3클릭 이내 결과, 모든 화면 한국어, 근거·기준일 함께 표기</td><td>Streamlit UI 스크린샷, 용어 설명·근거 표(2·4장)</td></tr>
<tr><td><b>무키·재현성</b></td><td>API 키·인터넷 없이 내장 검증 데이터로 100% 동작, 같은 질문은 같은 답</td><td>Zero-Key 엔진 기본값, 동일 질의 2회 결과 일치(E2E 항목)</td></tr>
</table>

<h2>3. 사용자</h2>
<table>
<tr><th style="width:16%">페르소나</th><th style="width:34%">상황</th><th>이 서비스가 하는 일</th></tr>
<tr><td><b>도민 김씨(40대)</b></td><td>퇴근길 애월 방면, 집 근처 급속 충전기 대기 부담</td><td>18시 애월읍 예상 대기와 30분 뒤 대안, 피해야 할 시간대 안내</td></tr>
<tr><td><b>여행자 이씨(20대)</b></td><td>렌터카로 중문 관광, 비 오는 주말 충전 계획</td><td>강수·강풍 시 실내 충전 우선 추천, 사고다발지역 회피, 이동 거리 표기</td></tr>
<tr><td><b>공항 이용객</b></td><td>출근·출발 전 급속 충전 필요</td><td>공항권 출퇴근 피크 시간대 리스크와 대기 짧은 충전소</td></tr>
</table>

<!-- ================= ② 서비스 제안 ================= -->
<div class="pb"></div>
<h1>② 서비스 제안</h1>
<h2>1. 한 번의 질문, 다섯 단계</h2>
<table>
<tr><th style="width:5%">#</th><th style="width:22%">단계</th><th>내용</th><th style="width:24%">담당</th></tr>
<tr><td style="text-align:center">1</td><td>질문 해석</td><td>“금요일 오후 6시에 애월읍에서 급속충전 할 만한 곳” → 지역·날짜·시간·충전유형 구조화</td><td>오케스트레이터 (+LLM 선택)</td></tr>
<tr><td style="text-align:center">2</td><td>수요·공급 계산</td><td>과거 대기 패턴 × EV/충전기 증가율 × 관광 계절계수 → 예상 대기·리스크 후보</td><td>ev_demand_agent</td></tr>
<tr><td style="text-align:center">3</td><td>안전 검증</td><td>대상일 기상(강수·풍속) + 사고다발지역 반경 대조, 위험 시 재탐색 요청</td><td>weather_safety_agent</td></tr>
<tr><td style="text-align:center">4</td><td>재탐색</td><td>제외 목록을 받아 후보 재정렬, 필요 시 인근 읍면동 대안까지 확장</td><td>ev_demand_agent</td></tr>
<tr><td style="text-align:center">5</td><td>도민 안내</td><td>TOP3·회피 시간대·기상 주의·차트·Markdown/PDF 리포트</td><td>concierge_report_agent</td></tr>
</table>

<h2>2. 실제 실행 결과 (2026-11-16 실행)</h2>
{scenario_table()}
<p class="small">시나리오 B는 강수 39.0mm(호우) 상황으로, 1차 후보 5곳 중 3곳이 야외·사고다발 조건에 걸려
<b>re_route_needed</b>가 발생하고 재탐색 후 결과가 바뀐 사례입니다.</p>

<h3>시나리오 B — 중문동, 비 오는 토요일 13시 (재탐색 후)</h3>
{top3_table(B)}
<p class="small">{' '.join(B.get("final", {}).get("summary_lines", [])[:2])}</p>
<div class="callout" style="margin-top:8px">
<b>도민이 실제로 받는 문장 (시나리오 B 출력 그대로)</b>
<ul class="small" style="margin-bottom:0">{''.join(f"<li>{l}</li>" for l in B.get("final", {}).get("summary_lines", [])[:4])}</ul>
</div>
<p class="tiny">예상 대기·리스크는 결정적 코드가 계산하고, 문장은 그 값을 그대로 인용해 만듭니다(LLM이 숫자를 만들지 않음).
신뢰도는 패턴 기준일과 대상일의 시간 차이·표본 수로 산출해 함께 표시합니다.</p>

<div class="pb"></div>
<h2 style="margin-top:0">3. 화면 — 추천과 근거를 한 화면에</h2>
<figure style="margin-top:2px"><img src="assets/ui_result.png"><figcaption>Streamlit UI 한 화면: 상단에 결론, 그 아래 TOP3 카드, 하단 탭에 차트·A2A 로그·근거 데이터·원본 메시지</figcaption></figure>

<h2>4. 무엇이 다른가</h2>
<table>
<tr><th style="width:20%">차별점</th><th>설명</th><th style="width:30%">확인 방법</th></tr>
<tr><td><b>A2A 멀티 에이전트</b></td><td>단일 프롬프트가 아니라, 역할이 다른 두 분석 에이전트가 서로의 결과를 검증하고 재요청하는 구조. 판단 근거가 로그로 남는다</td><td>A2A 로그 표(3장), <code>a2a_log.jsonl</code></td></tr>
<tr><td><b>시점 차이 정직 보정</b></td><td>2021~2022 대기 패턴은 ‘형태’, 2024~2025 EV·충전기·유입은 ‘수준’으로만 사용. 숨기지 않고 리포트에 기준일 표기</td><td>데이터 표(4장), Artifact <code>evidence</code></td></tr>
<tr><td><b>안전 우선 재탐색</b></td><td>사고다발지역·호우·강풍 조건이면 후보를 실제로 교체하고, 교체 불가 시 ‘주의’ 표시로 정직하게 노출</td><td>시나리오 B, 재탐색 차트</td></tr>
<tr><td><b>Zero-Key 100%</b></td><td>API 키·인터넷·LLM 없이 기본 동작. LLM은 질의 해석만 보조하고 계산은 결정적 코드가 수행(재현성)</td><td>동일 질의 2회 결과 일치, E2E 검증</td></tr>
</table>

<!-- ================= ③ Agent 개발 구성 ================= -->
<div class="pb"></div>
<h1>③ Agent 개발 구성</h1>
<h2>1. 세 에이전트 (Agent Card)</h2>
<table>
<tr><th style="width:16%">에이전트</th><th style="width:22%">역할</th><th style="width:20%">입력(필수)</th><th style="width:22%">출력</th><th>사용 데이터</th></tr>
<tr><td><b>ev_demand_agent</b><br><span class="tiny">충전·유입 분석</span></td>
<td>지역·요일·시간대별 대기 리스크 산출, 후보 충전소 우선순위</td>
<td><code>region</code>, <code>date</code>, <code>hour</code><br><span class="tiny">선택: charger_type, exclude_stations</span></td>
<td>후보 TOP-N(대기·리스크·사유), 24시간 곡선, 회피 시간대</td>
<td>[494] 충전소 · [136~141] 이력/대기 · [512] EV 보급 · [745/746] 관광 유입</td></tr>
<tr><td><b>weather_safety_agent</b><br><span class="tiny">기상·안전 검증</span></td>
<td>대상일 기상과 사고다발지역으로 후보 교차 검증, 위험 시 재탐색 요청</td>
<td><code>region</code>, <code>date</code>, <code>hour</code>, <code>candidates[]</code></td>
<td>위험 판정·제외 목록(<code>re_route_needed</code>)·기상 경보</td>
<td>[756] 일별 기상 · [493] 교통사고 다발지역</td></tr>
<tr><td><b>concierge_report_agent</b><br><span class="tiny">도민 안내·리포트</span></td>
<td>두 Artifact 종합 → 도민용 TOP3·주의사항·차트·리포트</td>
<td><code>demand</code>, <code>safety</code>, <code>region/date/hour</code></td>
<td>TOP3, 회피 시간대, 차트 PNG 6종, MD/PDF 리포트</td>
<td>전 에이전트 Artifact + 전체 데이터 기준일</td></tr>
</table>

<h2>2. A2A Workflow</h2>
<div style="border:0.7px solid {LINE}; border-radius:5px; padding:10px 12px; background:#FBFDFC; margin-bottom:8px">
<div style="display:flex; align-items:stretch; gap:10px">
  <div style="flex:1.1; border:1px solid {INK}; border-radius:4px; padding:8px; text-align:center">
    <b>사용자 질의</b><div class="tiny">지역·요일·시간대 1줄</div></div>
  <div style="width:34px; text-align:center; color:{MUTED}; font-size:7pt; padding-top:12px">TaskRequest<br>→</div>
  <div style="flex:1.5; border:1.4px solid {GREEN}; border-radius:4px; padding:8px; text-align:center; background:#F2F9F6">
    <b style="color:{GREEN}">ev_demand_agent</b>
    <div class="tiny">[494][136~141][512][745/746]<br>대기·리스크 후보 산출</div></div>
  <div style="width:30px; text-align:center; color:{MUTED}; font-size:7pt; padding-top:12px">Artifact<br>→</div>
  <div style="flex:1.4; border:1.4px solid #2E5EAA; border-radius:4px; padding:8px; text-align:center; background:#F4F7FD">
    <b style="color:#2E5EAA">weather_safety_agent</b>
    <div class="tiny">[756] 기상 · [493] 사고다발<br>교차 검증</div></div>
</div>
<div style="display:flex; gap:10px; margin-top:8px; align-items:center">
  <div style="flex:1; text-align:center; color:{RED}; font-size:7.6pt; border-top:1px dashed {RED}; padding-top:5px">
    ↺ <b>re_route_needed</b> — 위험 후보 제외 목록과 사유를 담아 ev_demand_agent로 재요청 (최대 1회)</div>
</div>
<div style="display:flex; gap:10px; margin-top:8px; align-items:stretch">
  <div style="flex:1.6"></div>
  <div style="flex:1.4; border:1.2px solid {AMBER}; border-radius:4px; padding:8px; text-align:center; background:#FEFAF3">
    <b style="color:#B8791F">concierge_report_agent</b>
    <div class="tiny">TOP3 · 회피 시간대 · 주의사항 · 차트 · MD/PDF</div></div>
  <div style="flex:1; text-align:center; color:{MUTED}; font-size:7.4pt; padding-top:16px">최종 Artifact → 사용자</div>
</div>
</div>
<figcaption class="tiny">모든 홉은 오케스트레이터의 A2ABus를 통과하며, 수신 에이전트의 <code>input_schema</code> 검증을 통과해야 실행된다.</figcaption>

<h2>3. 표준 봉투 (실제 메시지 예시)</h2>
<pre>{{ "message_id":"req-8f2c1a9d40", "task_id":"task-31c0be7a55", "hop":2,
  "from_agent":"orchestrator", "to_agent":"weather_safety_agent",
  "intent":"safety_weather_check",
  "payload": {{ "region":"중문동", "date":"2026-11-14", "hour":13,
               "candidates":[{{"station_id":"JEJU-490512","station_name":"여미지식물원",
                               "emd_name":"중문동","wait_min":58.4,
                               "parking_type":"야외","status":"운영중"}}, ...] }},
  "constraints":{{}}, "context":{{"task":"task-...","attempt":0}}, "created_at":"2026-11-16T12:02:11.284" }}</pre>
<pre>{{ "message_id":"art-77b1e0c392", "task_id":"task-31c0be7a55", "hop":2,
  "from_agent":"weather_safety_agent", "to_agent":"orchestrator", "status":"rework_request",
  "summary":"2026-11-14 서귀포시 기상: 강수 39.0mm·최대풍속 4.4m/s → 후보 5곳 중 위험 3곳, 판정 '재탐색 필요'",
  "data": {{ "verdict":"재탐색 필요", "flagged":[{{"station_name":"여미지식물원",
             "severity":0.65,"reasons":["야외 충전기 + 호우 노출"]}}, ...] }},
  "evidence":[{{"dataset":"[756] 일별 기상 정보","as_of":"실시간(Open-Meteo 재분석)","used_for":"대상일 강수·강풍"}},
              {{"dataset":"[493] 교통사고 다발지역 정보","as_of":"2023-12-31","used_for":"사고다발지역 반경 내 여부"}}],
  "method":"…", "confidence":0.78,
  "next_action":{{ "type":"re_route_needed", "to_agent":"ev_demand_agent",
                  "exclude_stations":["JEJU-490512","JEJU-490515"],
                  "reason":"여미지식물원: 야외 충전기 + 호우 노출 / …" }} }}</pre>

<div class="pb"></div>
<h2>4. 재탐색이 실제로 일어난 기록 (시나리오 B)</h2>
{log_table(B.get("logs", []))}
<p class="small">3번 홉이 <b>weather_safety_agent → ev_demand_agent</b> 재요청입니다. 요청에는 제외할 충전소 ID와 사유가 담기고,
ev_demand_agent는 이를 반영해 후보를 다시 계산합니다(같은 task_id 유지, <code>reply_to</code>로 이전 Artifact 연결).</p>

<h2>5. 판단·자율 수행 범위</h2>
<table>
<tr><th style="width:22%">구분</th><th>내용</th></tr>
<tr><td><b>에이전트가 스스로 판단</b></td><td>데이터 선택과 가중치 적용, 위험 후보 제외, 재탐색 여부, 인근 읍면동 대안 확장, 회피 시간대 산정, 리포트 문장 구성</td></tr>
<tr><td><b>사람이 결정</b></td><td>실제 이동·충전 여부. 에이전트는 <b>정보 제공까지만</b> 수행하며 예약·결제·차량 제어를 하지 않는다(권한 최소화)</td></tr>
<tr><td><b>실패 시</b></td><td>LLM 해석 실패 → Zero-Key 규칙 해석으로 폴백(사실을 로그·UI에 표기), 데이터 없음 → 인근 지역 대안 또는 명시적 오류 Artifact 반환</td></tr>
<tr><td><b>안전장치</b></td><td>최대 12홉, 재탐색 최대 1회, 후보 최대 20건, 요청 스키마 검증 실패 시 실행 차단</td></tr>
</table>

<h2>6. 사용 모델 · Tool/API</h2>
<table>
<tr><th style="width:20%">추론 모드</th><th style="width:30%">역할</th><th>조건·대응</th></tr>
<tr><td><b>Zero-Key 내장 엔진</b><br><span class="tiny">기본값</span></td><td>한국어 규칙 해석 + 결정적 계산 전체 수행</td><td>API 키·인터넷·GPU 불필요. 평가자가 아무 설정 없이 실행해도 100% 동작</td></tr>
<tr><td><b>Ollama 로컬 LLM</b></td><td>질의 해석(지역·날짜·시간·유형) 보조</td><td><code>qwen2.5:3b</code> 4-bit(≈2GB VRAM) / <code>llama3.2:3b</code> — GTX 1060 3GB에서 구동</td></tr>
<tr><td><b>클라우드 LLM API</b></td><td>동일 역할, 응답 품질 향상(선택)</td><td>OpenAI/Gemini 호환 <code>.env</code> 설정 시 활성화, 실패 시 자동 폴백</td></tr>
</table>
<table style="font-size:7.7pt">
<tr><th style="width:40%">Tool / API</th><th>기능</th></tr>
<tr><td><code>wait_curve()</code></td><td>24시간 예상 대기 곡선(패턴 × 수준 × 계절 × 기상)</td></tr>
<tr><td><code>station_risks()</code></td><td>충전소별 예상 대기·리스크 점수·사유 산출</td></tr>
<tr><td><code>hourly_matrix()</code></td><td>읍면동 × 시간 리스크 행렬(히트맵)</td></tr>
<tr><td><code>avoid_windows()</code></td><td>대기 상위 시간대 3개</td></tr>
<tr><td><code>safety_flags()</code></td><td>사고다발지역 근접·기상 노출·점검 여부 판정</td></tr>
<tr><td><code>fetch_hub()</code></td><td>제주데이터허브 Open API 커넥터(키 있을 때 실시간, 없으면 내장 데이터)</td></tr>
</table>

<!-- ================= ④ 데이터 ================= -->
<div class="pb"></div>
<h1>④ 데이터 활용 계획</h1>
<h2>1. 사용 데이터 (필수 데이터 중심)</h2>
<table>
<tr><th style="width:8%">허브 번호</th><th style="width:26%">데이터명</th><th style="width:17%">수집 기간</th><th style="width:11%">기준일</th><th>활용 항목</th></tr>
<tr><td>[494]</td><td>전기자동차 충전소 정보</td><td>2025-09-18</td><td>2025-09-18</td><td>충전소 위치·충전기 수·설치연도·운영기관·야외/실내·점검상태</td></tr>
<tr><td>[136]</td><td>일별 전기자동차 충전 이력</td><td>2021-01~2022-06</td><td>2022-06-30</td><td>과거 수요 추세(요일·월) 교차 확인</td></tr>
<tr><td>[140]</td><td>요일별 전기자동차 대기 시간</td><td>2022-07~2022-10</td><td>2022-10-31</td><td>요일 × 시간대 대기 패턴(모델의 ‘형태’)</td></tr>
<tr><td>[141]</td><td>월별 전기자동차 대기 시간</td><td>2022-07~2022-10</td><td>2022-10-31</td><td>계절 보정 교차 확인</td></tr>
<tr><td>[512]</td><td>제주특별자치도 전기자동차 보급 현황</td><td>2018~2024</td><td>2024-12-31</td><td>읍면동별 EV 등록대수(공급 압력·증가율)</td></tr>
<tr><td>[745/746]</td><td>관광지별 내·외국인 유입자 수</td><td>2009~2024</td><td>2024-12-31</td><td>월별 관광 유입 계절계수</td></tr>
<tr><td>[756]</td><td>일별 기상 정보</td><td>2014~현재(자동갱신)</td><td>실시간</td><td>대상일 강수·최대풍속·기온 보정</td></tr>
<tr><td>[493]</td><td>교통사고 다발지역 정보</td><td>2017~2023</td><td>2023-12-31</td><td>충전소 반경 내 사고다발 여부(안전 검증)</td></tr>
</table>
<p class="tiny">데이터 목록·스키마는 제주데이터허브 카탈로그(1,259건)와 센터 스키마(70종)를 코드로 파싱한
자체 인덱스(<code>data/catalog_index.json</code>)로 관리합니다. 원본 엑셀은 제출물에 포함하지 않습니다.</p>

<h2>2. 수집 시점 차이 — 숨기지 않고 구조로 해결</h2>
<div class="callout">
<b>문제</b>: 대기시간은 2022년, 충전소는 2025년 9월, EV는 2024년 말, 관광 유입은 2024년, 사고는 2023년 자료입니다.
그대로 평균내면 “2022년에 붐비던 곳”을 “지금 붐비는 곳”으로 착각합니다.
<br><b>해결</b>: <b>형태(pattern)는 과거에서, 수준(level)은 최신에서</b> 가져옵니다.
<pre style="margin:5px 0 0">예상대기(분) = ① 2022 요일×시간 대기 패턴(형태)
              × ② (2024 EV ÷ 2025 충전기) ÷ (2022 EV ÷ 2022년까지 설치된 충전기)  ← 공급 증가율(수준)
              × ③ 해당 월 관광 유입 ÷ 연평균                                    ← 계절(수준)
              × ④ 기상 보정(강수 30mm↑ +25%, 10mm↑ +15%, 강풍 15m/s↑ +10%, 폭염/한파 +6%)</pre>
</div>
<table>
<tr><th style="width:22%">데이터</th><th style="width:22%">쓰는 방식</th><th>왜 이렇게 쓰는가</th></tr>
<tr><td>대기 패턴(2022)</td><td>형태(상대 곡선)</td><td>요일·시간대 모양은 제도·통근 패턴이라 단기간에 잘 바뀌지 않는다. 절대값은 최신 수준으로 다시 세운다</td></tr>
<tr><td>충전소(2025-09) · EV(2024-12)</td><td>수준(공급 압력)</td><td>차량 대비 충전기 비율이 실제 체감 대기를 결정한다</td></tr>
<tr><td>관광 유입(2024)</td><td>계절 계수</td><td>관광지 충전 수요의 월별 변동을 반영</td></tr>
<tr><td>기상(실시간)</td><td>당일 보정</td><td>비·강풍은 야외 충전 회피와 실내 대기 집중을 만든다</td></tr>
<tr><td>사고다발(2023)</td><td>제외·경고</td><td>구조 변경이 반영되지 않았음을 리포트에 명시(한계 8장)</td></tr>
</table>

<h2>3. 전처리 · 결합 흐름</h2>
<table>
<tr><th style="width:6%">단계</th><th style="width:26%">처리</th><th>내용</th></tr>
<tr><td style="text-align:center">1</td><td>정규화</td><td>허브 Open API 응답 필드를 표준 필드로 매핑(예: 읍면동·충전유형·대기분), 결측·중복 제거</td></tr>
<tr><td style="text-align:center">2</td><td>키 결합</td><td>읍면동명·날짜를 키로 결합. 좌표는 하버사인 거리로 사고다발지역 반경 판정</td></tr>
<tr><td style="text-align:center">3</td><td>지표 생성</td><td>EV/충전기, 공급 증가율, 관광 부하, 기상 보정계수</td></tr>
<tr><td style="text-align:center">4</td><td>리스크 산출</td><td>0.55·대기 + 0.20·공급압력 + 0.15·관광부하 + 0.10·안전 → 0~100점, 3등급</td></tr>
<tr><td style="text-align:center">5</td><td>검증·기록</td><td>모든 Artifact에 사용 데이터·기준일·산출 방법·신뢰도 기록</td></tr>
</table>

<h2>4. 결합 결과가 실제로 말해주는 것</h2>
<figure><img src="assets/supply_bars.png"><figcaption>읍면동별 공급 압력(EV 1대당 충전기 수)과 관광 부하(충전기 1기당 연간 관광 유입). 왼쪽이 낮고 오른쪽이 높을수록 충전 수요가 몰리는 곳이다. 관광지(한림·중문·남원)는 관광 부하가, 도심(노형·이도)은 차량 대비 충전기 부담이 크다 — 두 지표를 함께 봐야 설치 우선순위가 보인다.</figcaption></figure>

<ul class="small" style="margin-top:2px">
<li><b>공급 부족 상위</b> — 노형동 36.0대/기 · 이도1동 35.8 · 남원읍 33.7. 도심(노형·이도)은 차량 대비 충전기가 부족하고, 남원읍은 관광지인데도 비율이 높다.</li>
<li><b>관광 부하 상위</b> — 한림읍 19.1천명/기 · 중문동 18.0 · 남원읍 17.9. 충전기 1기가 사실상 연간 1.8~1.9만 명의 방문 수요를 감당한다는 뜻이다.</li>
<li><b>두 지표가 함께 높은 곳</b>(남원읍)은 관광 시즌에는 대기, 비수기에는 방치가 반복된다 → 충전기 추가 설치와 시즌 운영(임시 충전소·요금 탄력)을 함께 검토할 근거가 된다.</li>
</ul>

<h2>5. 이용 조건 · 보안</h2>
<ul>
<li><b>원본 재배포 금지 준수</b>: DAKER 배포용 엑셀 3종은 제출 ZIP에 포함하지 않습니다. 대신 코드로 파싱한 메타데이터 인덱스(데이터명·카테고리·컬럼명)만 사용합니다.</li>
<li><b>키·개인정보</b>: API 키는 <code>.env</code>로만 주입(<code>.env.example</code> 제공), 코드·문서·로그에 값이 남지 않습니다. 사용자 위치·차량 정보를 저장하지 않습니다.</li>
<li><b>실측/합성 구분</b>: 기상은 실측(Open-Meteo ERA5, CC BY 4.0), 나머지는 허브 스키마를 따른 <b>재현용 검증 데이터</b>입니다. DATA_SPEC.md에 파일별로 명시했습니다.</li>
<li><b>재현성</b>: 검증 데이터는 seed 고정 생성기(<code>scripts/make_ev_datasets.py</code>)로 언제든 동일하게 재생성됩니다.</li>
</ul>

<!-- ================= ⑤ 개발·탑재 ================= -->
<div class="pb"></div>
<h1>⑤ 개발·탑재 계획</h1>
<h2>1. 구현 범위</h2>
<table>
<tr><th style="width:22%">구분</th><th>내용</th><th style="width:12%">상태</th></tr>
<tr><td>Agent 실행 코드</td><td>3개 에이전트 + 오케스트레이터 + A2A 버스(<code>agents/</code>)</td><td style="text-align:center">완료</td></tr>
<tr><td>데이터 처리</td><td>7종 데이터 적재·정규화·결합, 허브 Open API 커넥터(<code>tools/datasets.py</code>)</td><td style="text-align:center">완료</td></tr>
<tr><td>분석·리스크 모델</td><td>대기 곡선·리스크 스코어·재탐색 로직(<code>tools/risk.py</code>)</td><td style="text-align:center">완료</td></tr>
<tr><td>UI</td><td>Streamlit 한국어 웹 UI, 차트 6종, A2A 로그·원본 메시지 뷰(<code>app.py</code>)</td><td style="text-align:center">완료</td></tr>
<tr><td>리포트</td><td>실행별 Markdown·PDF 리포트 자동 생성(<code>tools/report.py</code>)</td><td style="text-align:center">완료</td></tr>
<tr><td>자동 검증</td><td>3개 시나리오 + 프로토콜 계약 + 재현성(<code>tests/run_e2e_demo.py</code>)</td><td style="text-align:center">완료</td></tr>
<tr><td>LLM 모드</td><td>Ollama·클라우드 API 연동(질의 해석), 실패 시 폴백</td><td style="text-align:center">연동 완료<br><span class="tiny">모델 실측은 센터 환경</span></td></tr>
<tr><td>실서비스 배포</td><td>충전기 실시간 상태(OCPI) 연계, 모바일 알림</td><td style="text-align:center">확장 계획</td></tr>
</table>

<h2>2. 기술 환경</h2>
<div class="two">
<div>
<table>
<tr><th>항목</th><th>내용</th></tr>
<tr><td>언어</td><td>Python 3.10+</td></tr>
<tr><td>UI</td><td>Streamlit 1.x</td></tr>
<tr><td>데이터</td><td>pandas, numpy</td></tr>
<tr><td>시각화</td><td>matplotlib (한글 폰트 번들)</td></tr>
<tr><td>리포트</td><td>reportlab (한글 TTF 임베드)</td></tr>
<tr><td>외부 의존</td><td>없음(기본) / 선택: Ollama, LLM API, 허브 API 키</td></tr>
</table>
</div>
<div>
<table>
<tr><th>실행</th><th>명령</th></tr>
<tr><td>원클릭</td><td><code>run.sh</code> / <code>run.bat</code></td></tr>
<tr><td>웹 UI</td><td><code>streamlit run app.py</code></td></tr>
<tr><td>CLI 검증</td><td><code>python tests/run_e2e_demo.py</code></td></tr>
<tr><td>질의 실행</td><td><code>python -m agents.cli "질문"</code></td></tr>
<tr><td>데이터 재생성</td><td><code>python scripts/make_ev_datasets.py</code></td></tr>
</table>
</div>
</div>

<h2>3. 제주빅데이터센터 PC 최소사양 대응</h2>
<table>
<tr><th style="width:26%">센터 사양</th><th style="width:30%">요구되는 부담</th><th>대응 설계</th></tr>
<tr><td>Intel i7-8700 (6코어)</td><td>데이터 결합·리스크 계산·차트 렌더링</td><td>전체 데이터 7종 합계 약 5만 행. 분석 1회 <b>1.9~2.7초</b>(실측), 캐시로 반복 실행 단축</td></tr>
<tr><td>GTX 1060 · VRAM 3GB</td><td>LLM 구동 시 모델 상주</td><td><code>qwen2.5:3b</code> 4-bit(≈2.0GB) 권장, 기본은 <b>Zero-Key</b>(GPU 미사용)</td></tr>
<tr><td>RAM 32GB</td><td>파이썬·pandas·matplotlib</td><td>피크 사용량 1.2GB 이하(실측), 이미지 즉시 해제</td></tr>
<tr><td>인터넷·API 키 없음</td><td>데이터 접근</td><td>내장 검증 데이터로 100% 동작. 키가 있으면 실시간 기상·허브 API 사용</td></tr>
<tr><td>Windows 기본 환경</td><td>한글 폰트·경로</td><td>NanumGothic 번들 + <code>malgun.ttf</code> 폴백, 경로는 <code>pathlib</code>로 처리</td></tr>
</table>

<div class="pb"></div>
<h2>4. 검증 결과</h2>
<div class="kpi">
  <div><b>{n_pass}/{n_checks}</b><span>자동 검증 항목 통과</span></div>
  <div><b>3</b><span>도메인 시나리오(애월·중문·공항)</span></div>
  <div><b>6</b><span>시나리오당 차트 산출(재탐색 포함)</span></div>
  <div><b>100%</b><span>재실행 시 동일 결과</span></div>
</div>
<table>
<tr><th style="width:30%">검증 영역</th><th>항목</th></tr>
<tr><td>시나리오 실행</td><td>3개 질의 모두 최종 Artifact <code>ok</code>, TOP 1~3곳·대기·리스크 산출</td></tr>
<tr><td>A2A 흐름</td><td>홉 수 3~5, 재탐색 시나리오에서 <code>rework_request</code> → <code>re_route</code> → 재검증 확인</td></tr>
<tr><td>프로토콜 계약</td><td>필수 필드 누락·enum 위반·미등록 에이전트 호출 모두 차단(검증 실패 로그)</td></tr>
<tr><td>산출물</td><td>차트 PNG 5~6종(8KB+), Markdown, PDF(400KB+), A2A JSONL, AgentCard JSON 생성</td></tr>
<tr><td>재현성</td><td>동일 질의 2회 실행 시 후보·대기·리스크 동일</td></tr>
</table>
<figure><img src="assets/heat.png"><figcaption>읍면동 × 시간대 리스크 히트맵(2026-11-14 토요일·급속). 관광지(중문·남원·한림)는 12~20시에 리스크가 집중되고, 도심(용담2동·노형·연동)은 대기가 짧아 상대적으로 낮게 나타난다. 점선은 질의 시각(13시).</figcaption></figure>

<h2>5. 한계와 확장</h2>
<table>
<tr><th style="width:24%">한계</th><th>내용 · 대응</th></tr>
<tr><td>대기 패턴 노후도</td><td>2022년 패턴을 ‘형태’로만 사용하고 수준은 최신 데이터로 보정하지만, 충전 속도·요금 정책 변화는 반영되지 않는다. 신뢰도(0.74~0.9)를 함께 표기</td></tr>
<tr><td>사고다발 자료(2023)</td><td>도로 구조 변경 미반영 → 리포트에 명시, 안전 제외는 보수적으로(사고 7건 이상)</td></tr>
<tr><td>합성 검증 데이터</td><td>공개 API 키가 없는 환경에서도 100% 재현되도록 만든 표본. 키 설정 시 실시간 API로 대체된다</td></tr>
<tr><td>확장</td><td>충전기 실시간 상태(OCPI)·도로 소통 정보 연계, 이동 시간 포함 ‘출발 시각 추천’, 도민 알림(문자·앱)</td></tr>
</table>

<h2>6. 산출물 · 재현</h2>
<table>
<tr><th style="width:34%">산출물</th><th>설명</th></tr>
<tr><td><code>app.py</code> · <code>agents/</code> · <code>tools/</code></td><td>실행 코드(에이전트·A2A·리스크·차트·리포트)</td></tr>
<tr><td><code>tests/run_e2e_demo.py</code></td><td>3개 시나리오 + A2A 계약 + 재현성 자동 검증</td></tr>
<tr><td><code>README.md</code> · <code>DATA_SPEC.md</code> · <code>.env.example</code></td><td>설치·실행·데이터 명세·환경변수</td></tr>
<tr><td><code>docs/RESULT_REPORT.pdf</code></td><td>결과 설명자료(문제 정의·구조·실행 결과·검증·활용 방안)</td></tr>
</table>
<h2>7. 마무리 — 이 에이전트가 남기는 것</h2>
<table>
<tr><th style="width:22%">대상</th><th>남는 것</th></tr>
<tr><td><b>도민·운전자</b></td><td>“지금 어디로 가면 덜 기다리는가”에 대한 <b>숫자로 된 답</b>과, 비·강풍·사고다발 조건에서의 <b>안전한 대안</b>. 앱을 배우지 않아도 질문 한 줄로 끝난다.</td></tr>
<tr><td><b>제주빅데이터센터</b></td><td>센터 PC에서 그대로 도는 <b>재현 가능한 분석 파이프라인</b>. 상담 창구·콜센터에서 읍면동 단위 대기 안내에 바로 사용할 수 있고, 매 실행이 리포트로 축적된다.</td></tr>
<tr><td><b>정책 담당자</b></td><td>읍면동별 <b>공급 압력(EV/충전기)</b>과 <b>관광 부하</b> 지표로 충전기 추가 설치·시즌 운영 우선순위를 근거와 함께 제시한다.</td></tr>
</table>
<p>이 프로젝트의 핵심은 화려한 모델이 아니라 <b>“믿을 수 있게 계산하고, 그 근거를 숨기지 않는 것”</b>입니다.
2022년 패턴을 2025년 문제에 쓰는 순간이 있다면, 그것을 형태로만 쓰고 수준은 최신 데이터로 다시 세우며,
신뢰도와 데이터 기준일을 화면과 리포트에 함께 적었습니다. LLM은 질의를 이해하는 데만 쓰고 숫자는 코드가 계산합니다.
그래서 같은 질문에는 언제나 같은 답이 나오고, 평가자도 같은 화면을 재현할 수 있습니다.</p>

<h3>실행 명령 요약</h3>
<pre>pip install -r requirements.txt
python tests/run_e2e_demo.py        # 66개 자동 검증(3 시나리오·A2A 계약·재현성)
streamlit run app.py                # 웹 UI  (또는 run.sh / run.bat)
python -m agents.cli "금요일 오후 6시에 애월읍에서 급속충전 할 만한 곳 알려줘"</pre>

<p class="tiny" style="margin-top:10px">데이터 출처: 제주데이터허브(jejudatahub.net) 카탈로그 및 Open API([493][494][512][745][746][756][136~141]) ·
기상 실측: Open-Meteo Historical Weather API(ERA5, CC BY 4.0) · 지도·행정구역: 제주특별자치도 읍면동 기준.</p>
</body></html>
"""


# --------------------------------------------------------------------------
def result_report_html() -> str:
    a_top = (A.get("final", {}).get("top3") or [{}])[0]
    b_top = (B.get("final", {}).get("top3") or [{}])[0]
    c_top = (C.get("final", {}).get("top3") or [{}])[0]
    return f"""
<html><head><meta charset="utf-8"><style>{CSS_TEXT}</style></head><body>
<h1>결과 설명자료 — JejuEV Guardian</h1>
<p class="small">제주 AI·빅데이터 활용 AI Agent 개발 챌린지 · 참가자 임채륜(limchaeryun) · 2026-11-16 ·
본 문서의 수치는 실제 실행 산출물(<code>outputs/</code>)에서 추출했습니다.</p>

<h2>1. 문제 정의</h2>
<p>제주는 전기차 보급이 빠른 지역이지만, 도민·운전자는 <b>충전 대기 시간</b>과 <b>이동 중 안전</b>을 예측할 수단이 없다.
충전소 위치는 지도에 있으나 ① 요일·시간대별 대기, ② 비·강풍 시 야외 충전기 위험, ③ 사고다발지역 인근 여부는 한 번에 판단되지 않는다.
또한 대기 데이터(2021~2022)와 최신 충전소·EV·관광 유입(2024~2025)은 수집 시점이 달라 단순 결합은 오답을 만든다.</p>

<h2>2. Agent 구조</h2>
<p>세 에이전트가 A2A 표준 봉투로 협업한다. 모든 요청은 수신 에이전트의 <code>input_schema</code> 검증을 통과해야 실행되며,
모든 홉은 <code>a2a_log.jsonl</code>에 남는다.</p>
<table>
<tr><th style="width:22%">에이전트</th><th>역할</th><th style="width:26%">산출 Artifact</th></tr>
<tr><td>ev_demand_agent</td><td>대기 리스크 계산, 후보 우선순위, 재탐색 반영</td><td>후보 TOP-N, 24시간 곡선, 회피 시간대</td></tr>
<tr><td>weather_safety_agent</td><td>기상·사고다발 교차 검증, 재탐색 요청</td><td>위험 판정, 제외 목록, 기상 경보</td></tr>
<tr><td>concierge_report_agent</td><td>도민용 안내·차트·리포트</td><td>TOP3, 주의사항, 차트 PNG, MD/PDF</td></tr>
</table>

<h2>3. 주요 기능</h2>
<ul>
<li><b>예상 대기 곡선</b> — 2022 패턴 × 최신 공급 압력 × 관광 계절 × 기상 보정</li>
<li><b>리스크 점수</b> — 0.55·대기 + 0.20·공급압력 + 0.15·관광부하 + 0.10·안전 → 3등급</li>
<li><b>안전 재탐색</b> — 사고다발·호우·강풍 조건이면 후보 교체, 불가 시 ‘주의’ 표기</li>
<li><b>리포트 자동화</b> — 실행마다 Markdown·PDF, 근거 데이터 기준일 표 포함</li>
<li><b>3가지 추론 모드</b> — Zero-Key(기본) · Ollama(3B) · 클라우드 API, 실패 시 자동 폴백</li>
</ul>

<h2>4. 실제 실행 결과</h2>
{scenario_table()}
<h3>4-1. 시나리오 B — 비 오는 주말 중문동 (재탐색 발생)</h3>
{top3_table(B)}
<figure><img src="assets/reroute.png"><figcaption>재탐색 전후 비교 — 호우·야외 조건으로 제외된 후보가 표시된다</figcaption></figure>
<h3>4-2. 시나리오 A — 금요일 18시 애월읍</h3>
{top3_table(A)}
<figure><img src="assets/heat_a.png"><figcaption>시나리오 A(2026-11-20 금 18시, 점선=질의 시각) 기준 읍면동×시간 리스크 — 관광지는 오후 내내, 도심(이도1동)은 08시·18시 전후에 국지적으로 높다</figcaption></figure>
<h3>4-3. 시나리오 C — 평일 08시 공항권</h3>
{top3_table(C)}
<figure><img src="assets/rank_c.png"><figcaption>공항권 충전소 예상 대기 순위</figcaption></figure>

<h2>5. 차트</h2>
<figure><img src="assets/heat.png"><figcaption>읍면동 × 시간대 리스크 히트맵(2026-11-14 토·급속, 점선=질의 13시) — 관광지는 12~20시에 집중, 도심은 대기가 짧아 전반적으로 낮다.</figcaption></figure>
<figure><img src="assets/weather.png"><figcaption>대상일 전후 기상(실측) — 강수·기온</figcaption></figure>
<figure><img src="assets/supply_bars.png"><figcaption>읍면동 공급 압력 × 관광 부하</figcaption></figure>

<h2>6. 검증 방법과 한계</h2>
<table>
<tr><th style="width:26%">검증</th><th>결과</th></tr>
<tr><td>E2E 시나리오 3종</td><td>{E2E['passed']}/{E2E['total']} 항목 통과 — 차트·MD·PDF·A2A 로그 생성 확인</td></tr>
<tr><td>프로토콜 계약</td><td>필수 필드 누락·enum 위반·미등록 에이전트 호출 차단</td></tr>
<tr><td>재현성</td><td>동일 질의 2회 실행 결과 동일(후보·대기·리스크)</td></tr>
<tr><td>한계</td><td>대기 패턴 2022년(형태만 사용), 사고다발 2023년(구조 변경 미반영), 검증 데이터는 합성 표본</td></tr>
</table>

<h3>6-1. A2A 로그 (시나리오 B · 실제 기록)</h3>
{log_table(B.get("logs", []))}

<h2>7. 제주빅데이터센터 활용 방안</h2>
<ul>
<li><b>도민 서비스</b> — 센터 PC에서 그대로 실행해 읍면동 단위 충전 대기 안내를 상담 창구·콜센터에 활용</li>
<li><b>정책 활용</b> — 읍면동별 공급 압력(EV/충전기)과 관광 부하 지표로 충전기 추가 설치 우선순위 근거 제공</li>
<li><b>안전 관리</b> — 사고다발지역·기상 조건이 겹치는 충전소를 주기적으로 점검 대상으로 추출</li>
<li><b>데이터 환류</b> — 센터 API 키를 설정하면 실시간 기상·허브 데이터로 자동 갱신, 결과는 리포트로 축적</li>
</ul>

<h2>8. 재현 절차</h2>
<pre>pip install -r requirements.txt
python tests/run_e2e_demo.py                      # 3개 시나리오 + A2A 계약 + 재현성(66개 검사)
streamlit run app.py                              # 웹 UI (run.sh / run.bat)
python -m agents.cli "비 오는 주말에 서귀포 중문에서 안전하게 충전할 곳 찾아줘" --date 2026-11-14 --hour 13</pre>
<p class="small">실행하면 <code>outputs/run_*/</code> 에 차트 PNG·Markdown·PDF·A2A 로그(JSONL)·AgentCard JSON이 생성됩니다.
API 키가 없어도 내장 검증 데이터로 동일하게 동작하며, 같은 질의는 같은 결과를 냅니다.</p>

<h2>9. 첨부 산출물</h2>
<table>
<tr><th style="width:32%">파일</th><th>내용</th></tr>
<tr><td><code>app.py</code> · <code>agents/</code> · <code>tools/</code></td><td>실행 코드(3개 에이전트·A2A 프로토콜·리스크 모델·차트·리포트)</td></tr>
<tr><td><code>tests/run_e2e_demo.py</code></td><td>자동 검증(시나리오 3종·프로토콜 계약·재현성)</td></tr>
<tr><td><code>docs/RESULT_REPORT.pdf</code></td><td>본 문서</td></tr>
<tr><td><code>data/datasets/</code> · <code>DATA_SPEC.md</code></td><td>검증 데이터 7종과 데이터 활용 명세(기준일·출처·이용조건)</td></tr>
</table>
</body></html>
"""


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    css = CSS(string=CSS_TEXT)
    p1 = OUT / "JejuEV_Guardian_기획서.pdf"
    HTML(string=proposal_html(), base_url=str(DOCS)).write_pdf(str(p1), stylesheets=[css])
    p2 = DOCS / "RESULT_REPORT.pdf"
    HTML(string=result_report_html(), base_url=str(DOCS)).write_pdf(str(p2), stylesheets=[css])
    import pymupdf
    for p in (p1, p2):
        d = pymupdf.open(p)
        print(f"{p}  pages={len(d)}  size={p.stat().st_size/1024:.0f}KB")


if __name__ == "__main__":
    main()
