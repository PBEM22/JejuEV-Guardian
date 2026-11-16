# -*- coding: utf-8 -*-
"""JejuEV Guardian — Streamlit 웹 UI.

실행:  streamlit run app.py      (또는 run.sh / run.bat)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agents import backends, orchestrator  # noqa: E402
from tools import datasets as ds  # noqa: E402
from tools.config import ENGINE_LABELS, env  # noqa: E402

st.set_page_config(page_title="JejuEV Guardian", page_icon="⚡", layout="wide",
                   initial_sidebar_state="expanded")

CSS = """
<style>
.block-container {padding-top: 1.4rem; padding-bottom: 2rem; max-width: 1180px;}
h1, h2, h3 {letter-spacing: -0.02em;}
.hero {background: linear-gradient(120deg,#0B6E4F 0%,#12805C 55%,#1C9A70 100%);
       color:#fff; padding:20px 24px; border-radius:14px; margin-bottom:14px;}
.hero h1 {color:#fff; font-size:1.55rem; margin:0 0 6px 0;}
.hero p {color:#DDF3EA; margin:0; font-size:.92rem;}
.card {background:#F6FAF8; border:1px solid #D9E2DE; border-left:4px solid #0B6E4F;
       border-radius:10px; padding:12px 14px; margin-bottom:8px;}
.card.warn {border-left-color:#C4453B; background:#FCF4F3;}
.card.amber {border-left-color:#E8A33D; background:#FDF8F1;}
.card b {font-size:.98rem;}
.small {color:#6B7A75; font-size:.82rem;}
.hop {font-family: ui-monospace, Menlo, monospace; font-size:.82rem;}
div[data-testid="stMetricValue"] {font-size:1.4rem;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>⚡ JejuEV Guardian</h1>
  <p>제주 도민·운전자를 위한 <b>전기차 충전 대기·이동 리스크 분석 A2A 멀티 에이전트</b> ·
  충전·유입 분석 → 기상·안전 검증 → 도민 안내 리포트를 에이전트끼리 주고받으며 완성합니다.</p>
</div>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _catalog():
    return ds.catalog_summary()


@st.cache_data(show_spinner=False)
def _cards():
    bus = orchestrator.build_bus()
    return [c.to_dict() for c in bus.cards.values()]


with st.sidebar:
    st.markdown("### 실행 설정")
    mode_label = st.radio("추론 백엔드", ["Zero-Key 내장 엔진", "Ollama 로컬 LLM", "클라우드 LLM API"],
                          index=0, help="Zero-Key는 API 키 없이 100% 동작합니다. LLM은 질의 해석에만 쓰이고 계산은 결정적 코드가 합니다.")
    mode = {"Zero-Key 내장 엔진": "zerokey", "Ollama 로컬 LLM": "ollama", "클라우드 LLM API": "cloud"}[mode_label]
    status = backends.backend_status()
    for key in ("zerokey", "ollama", "cloud"):
        s = status[key]
        icon = "🟢" if s["ready"] else "⚪"
        st.markdown(f"{icon} **{s['label']}**<br><span class='small'>{s['detail']}</span>", unsafe_allow_html=True)

    st.divider()
    st.markdown("### 데이터 연결")
    live = ds.hub_api_available()
    st.markdown(("🟢 **제주데이터허브 Open API** (실시간)" if live else
                 "🟡 **내장 검증 데이터셋** (Zero-Key)") +
                f"<br><span class='small'>{'키 설정됨' if env('JEJU_HUB_API_KEY') else '.env에 키를 넣으면 실시간 연동'}</span>",
                unsafe_allow_html=True)
    cat = _catalog()
    st.markdown(f"<span class='small'>카탈로그: 허브 {cat.get('hub',0):,}건 · 센터 스키마 {cat.get('center',0)}종</span>",
                unsafe_allow_html=True)
    for k, m in ds.DATASETS.items():
        st.markdown(f"<span class='small'>· [{m.dataset_id}] {m.name} <b>{m.as_of}</b></span>", unsafe_allow_html=True)

    st.divider()
    with st.expander("A2A 에이전트 카드"):
        for c in _cards():
            st.markdown(f"**{c['display_name']}** (`{c['name']}`)<br>"
                        f"<span class='small'>{c['role']}<br>능력: {', '.join(c['capabilities'])}</span>",
                        unsafe_allow_html=True)
            st.markdown("<span class='small'>입력: " + ", ".join(c['input_schema'].get('required', [])) + "</span>",
                        unsafe_allow_html=True)

# ---------------------------------------------------------------------------
EXAMPLES = [
    "금요일 오후 6시에 애월읍에서 급속충전 할 만한 곳 알려줘",
    "비 오는 주말에 서귀포 중문에서 안전하게 충전할 곳 찾아줘",
    "평일 아침 출근시간 제주공항 근처 충전 대기 어때?",
]

# 딥링크(?q=질문&auto=1)로 실행 결과 화면을 바로 열 수 있다(데모·스크린샷용)
_qp = st.query_params
_deeplink_q = _qp.get("q") if hasattr(_qp, "get") else None
_auto = str(_qp.get("auto", "0")) == "1" if hasattr(_qp, "get") else False

st.markdown("#### 무엇이 궁금하신가요?")
c1, c2, c3 = st.columns(3)
picked = None
for col, ex in zip((c1, c2, c3), EXAMPLES):
    if col.button(ex, use_container_width=True):
        picked = ex

query = st.text_input("질문", value=picked or _deeplink_q or st.session_state.get("query", EXAMPLES[0]),
                      label_visibility="collapsed", placeholder="예: 금요일 오후 6시 애월읍 급속충전 대기 어때?")
st.session_state["query"] = query

with st.expander("조건 직접 지정(선택)"):
    d1, d2, d3 = st.columns(3)
    today = dt.date.today()
    qdate = d1.date_input("날짜", value=today + dt.timedelta(days=(4 - today.weekday()) % 7 or 7))
    qhour = d2.slider("시각", 0, 23, 18)
    qregion = d3.selectbox("지역", list(ds.REGION_META.keys()),
                           index=list(ds.REGION_META.keys()).index("애월읍"))
    use_override = st.checkbox("위 조건을 질문보다 우선", value=False)

run = st.button("분석 실행", type="primary", use_container_width=True)
if _auto and _deeplink_q and "result" not in st.session_state:
    run = True

if run and query.strip():
    kwargs = {}
    if use_override:
        kwargs = {"date": qdate.isoformat(), "hour": int(qhour), "region": qregion}
    with st.spinner("A2A 에이전트들이 데이터를 주고받는 중입니다…"):
        result = orchestrator.run(query, mode=mode, **kwargs)
    st.session_state["result"] = result

result = st.session_state.get("result")

if result is not None:
    st.divider()
    art = result.final
    data = art.get("data", {})
    if art.get("status") != "ok":
        st.error(f"분석을 완료하지 못했습니다: {art.get('summary')}")
        st.json(art)
        st.stop()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("대상", f"{result.parsed['region']} · {result.parsed['date'][5:]}")
    m2.metric("평균 예상 대기", f"{result.artifacts[0]['artifact']['data']['wait_min']:.1f}분")
    best = data["top3"][0]
    m3.metric("최적 후보", f"{best['wait_min']:.1f}분", best["station_name"], delta_color="off")
    m4.metric("A2A 홉", f"{len(result.log)}회", f"재탐색 {'있음' if data.get('rerouted') else '없음'}")

    for line in data["summary_lines"]:
        st.markdown(f"<div class='card'>{line}</div>", unsafe_allow_html=True)

    st.markdown("#### 추천 충전소 TOP3")
    cols = st.columns(3)
    for col, t in zip(cols, data["top3"]):
        cls = "card warn" if t.get("caution") else "card"
        badge = " ⚠ 주의" if t.get("caution") else ""
        col.markdown(f"""<div class="{cls}">
            <b>{t['station_name']}</b>{badge}<br>
            <span class="small">{t['emd_name']} · {t['parking_type']} · {t['parking_fee']} · {t['operator']}</span><br>
            <span style="font-size:1.35rem;font-weight:700;color:#0B6E4F">대기 {t['wait_min']:.0f}분</span>
            <span class="small"> / 상위10% {(t['p90_min'] or 0):.0f}분</span><br>
            <span class="small">리스크 {t['risk_score']:.0f}/100 ({t['risk_level']}) · 충전기 {t['charger_count']}기</span><br>
            <span class="small">{t['reasons'][0]}</span>
        </div>""", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["📊 차트", "🔁 A2A 로그", "📚 근거 데이터", "🧾 원본 메시지"])
    with tab1:
        g1, g2 = st.columns(2)
        if "heatmap" in result.charts:
            g1.image(result.charts["heatmap"], caption="읍면동 × 시간대 리스크")
        if "ranking" in result.charts:
            g2.image(result.charts["ranking"], caption="충전소 예상 대기")
        if "curve" in result.charts:
            g1.image(result.charts["curve"], caption="24시간 대기 곡선")
        if "weather" in result.charts:
            g2.image(result.charts["weather"], caption="대상일 전후 기상")
        if "reroute" in result.charts:
            st.image(result.charts["reroute"], caption="재탐색 전후 비교")
        if "supply" in result.charts:
            st.image(result.charts["supply"], caption="읍면동 공급압력 × 관광부하")
    with tab2:
        st.markdown(f"**엔진**: {result.engine_label} · **홉**: {len(result.log)}회")
        st.dataframe(pd.DataFrame(result.log)[["hop", "time", "from", "to", "intent", "validation",
                                                "status", "latency_ms", "summary"]],
                     use_container_width=True, hide_index=True)
        for row in result.log:
            st.markdown(f"<span class='hop'>hop {row['hop']:>2} · {row['from']} → {row['to']} · "
                        f"{row['intent']} · {row['validation']} · {row['status']} · {row['latency_ms']}ms</span>",
                        unsafe_allow_html=True)
    with tab3:
        st.dataframe(pd.DataFrame(data["_evidence"] if "_evidence" in data else art["evidence"]),
                     use_container_width=True, hide_index=True)
        st.caption("수집 시점(as_of)이 서로 다른 데이터를 결합합니다 — 과거 패턴은 '형태', 최신 데이터는 '수준'으로만 사용합니다.")
    with tab4:
        for i, pair in enumerate(result.artifacts, start=1):
            with st.expander(f"{i}. {pair['request']['from_agent']} → {pair['request']['to_agent']} "
                             f"({pair['request']['intent']})"):
                st.markdown("**TaskRequest**")
                st.json(pair["request"], expanded=False)
                st.markdown("**TaskArtifact**")
                st.json(pair["artifact"], expanded=False)

    st.markdown("#### 내려받기")
    d1, d2, d3 = st.columns(3)
    if Path(result.report_md).exists():
        d1.download_button("Markdown 리포트", Path(result.report_md).read_bytes(), "JejuEV_report.md",
                           use_container_width=True)
    if result.report_pdf and Path(result.report_pdf).exists():
        d2.download_button("PDF 리포트", Path(result.report_pdf).read_bytes(), "JejuEV_report.pdf",
                           use_container_width=True)
    log_path = Path(result.out_dir) / "a2a_log.jsonl"
    if log_path.exists():
        d3.download_button("A2A 로그(JSONL)", log_path.read_bytes(), "a2a_log.jsonl", use_container_width=True)

    if result.warnings:
        with st.expander("한계·주의"):
            for w in result.warnings:
                st.markdown(f"- {w}")
