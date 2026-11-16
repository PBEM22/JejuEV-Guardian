# -*- coding: utf-8 -*-
"""차트 생성 — 리포트·기획서·UI에 쓰이는 PNG를 만든다. (한글 폰트 자동 등록)"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from .config import register_matplotlib_font

FONT = register_matplotlib_font() or "sans-serif"

C = {
    "ink": "#16241F",
    "muted": "#6B7A75",
    "line": "#D9E2DE",
    "green": "#0B6E4F",
    "green_l": "#8FD3B8",
    "amber": "#E8A33D",
    "red": "#C4453B",
    "blue": "#2E5EAA",
    "bg": "#FFFFFF",
    "panel": "#F4F8F6",
}

plt.rcParams.update({
    "font.family": FONT,
    "axes.edgecolor": C["line"],
    "axes.labelcolor": C["ink"],
    "axes.titlecolor": C["ink"],
    "text.color": C["ink"],
    "xtick.color": C["muted"],
    "ytick.color": C["muted"],
    "figure.facecolor": C["bg"],
    "axes.facecolor": C["bg"],
    "axes.grid": True,
    "grid.color": C["line"],
    "grid.linewidth": 0.7,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 9.5,
})


def _save(fig, path: str | Path, dpi: int = 170) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, dpi=dpi, bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    return str(p)


def _risk_color(v: float) -> str:
    if v >= 70:
        return C["red"]
    if v >= 45:
        return C["amber"]
    return C["green"]


# --------------------------------------------------------------------------
def risk_heatmap(matrix: pd.DataFrame, date: str, hour: int | None, path: str | Path) -> str:
    piv = matrix.pivot_table(index="emd_name", columns="hour", values="risk", aggfunc="mean")
    order = piv.mean(axis=1).sort_values(ascending=False).index
    piv = piv.loc[order]
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    im = ax.imshow(piv.values, aspect="auto", cmap="RdYlGn_r", vmin=15, vmax=80)
    ax.set_yticks(range(len(piv.index)))
    ax.set_yticklabels(piv.index, fontsize=9)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)])
    ax.set_xlabel("시간대(시)")
    ax.grid(False)
    if hour is not None:
        ax.axvline(hour, color=C["ink"], lw=1.6, ls="--")
    cb = fig.colorbar(im, ax=ax, pad=0.01, shrink=0.9)
    cb.set_label("대기 리스크 점수(0~100)", fontsize=8.5)
    ax.set_title(f"읍면동 × 시간대 충전 대기 리스크 — {date}({matrix.attrs.get('weekday','')}) · 급속"
                 + (f" · 점선 = 질의 시각 {hour:02d}시" if hour is not None else ""),
                 fontsize=10.5, loc="left", pad=10)
    return _save(fig, path)


def station_ranking(df: pd.DataFrame, date: str, hour: int, path: str | Path,
                    title_suffix: str = "") -> str:
    d = df.sort_values("wait_min", ascending=True).tail(8)
    fig, ax = plt.subplots(figsize=(8.2, 0.52 * len(d) + 1.4))
    colors = [_risk_color(v) for v in d["risk_score"]]
    bars = ax.barh(d["station_name"], d["wait_min"], color=colors, height=0.62)
    for b, (_, r) in zip(bars, d.iterrows()):
        ax.text(b.get_width() + 0.4, b.get_y() + b.get_height() / 2,
                f"{r.wait_min:.1f}분 · 리스크 {r.risk_score:.0f}({r.risk_level})",
                va="center", fontsize=8.5, color=C["ink"])
    ax.set_xlabel("예상 대기시간(분)")
    ax.set_xlim(0, max(d["wait_min"].max() * 1.55, 5))
    ax.set_title(f"{d['emd_name'].iloc[0]} 충전소 예상 대기 — {date} {hour:02d}시{title_suffix}",
                 fontsize=11, loc="left", pad=10)
    ax.grid(axis="y", visible=False)
    return _save(fig, path)


def reroute_compare(before: pd.DataFrame, after: pd.DataFrame, excluded: list[str],
                    path: str | Path) -> str:
    """재탐색 전후 비교 — 충전소 이름 기준으로 정렬해 길이가 달라도 안전하게 그린다."""
    b = before.sort_values("wait_min").head(6)[["station_name", "wait_min"]].rename(columns={"wait_min": "before"})
    a = after.sort_values("wait_min").head(6)[["station_name", "wait_min"]].rename(columns={"wait_min": "after"})
    m = b.merge(a, on="station_name", how="outer")
    m["order"] = m["before"].fillna(m["after"])
    m = m.sort_values("order").head(7)
    y = np.arange(len(m))
    fig, ax = plt.subplots(figsize=(8.4, 0.5 * len(m) + 1.6))
    ax.barh(y - 0.19, m["before"].fillna(0).values, height=0.34, color=C["amber"], label="재탐색 전")
    ax.barh(y + 0.19, m["after"].fillna(0).values, height=0.34, color=C["green"], label="재탐색 후")
    ax.set_yticks(y)
    ax.set_yticklabels([n + ("  [제외]" if n in excluded else "") for n in m["station_name"]], fontsize=8.6)
    ax.invert_yaxis()
    ax.set_xlabel("예상 대기시간(분)")
    for i, (nm, row) in enumerate(m.iterrows()):
        if nm in excluded and pd.isna(row["after"]):
            ax.text(0.8, i + 0.19, "제외(안전·기상 위험)", fontsize=7.8, color=C["red"], va="center")
    ax.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)
    ax.set_title("A2A 재탐색(re_route_needed) 전후 추천 후보 비교", fontsize=11, loc="left", pad=10)
    ax.grid(axis="y", visible=False)
    return _save(fig, path)


def demand_pattern(history: pd.DataFrame, emd: str, path: str | Path) -> str:
    h = history[(history["emd_name"] == emd) & (history["charger_type"] == "급속")].copy()
    h["date"] = pd.to_datetime(h["base_date"].astype(str), format="%Y%m%d")
    h["dow"] = h["date"].dt.weekday
    h["month"] = h["date"].dt.month
    piv = h.pivot_table(index="dow", columns="month", values="charge_count", aggfunc="mean")
    fig, ax = plt.subplots(figsize=(7.6, 2.9))
    im = ax.imshow(piv.values, aspect="auto", cmap="YlGn")
    ax.set_yticks(range(len(piv.index)))
    ax.set_yticklabels([["월", "화", "수", "목", "금", "토", "일"][i] for i in piv.index], fontsize=8.5)
    ax.set_xticks(range(len(piv.columns)))
    ax.set_xticklabels([f"{m}월" for m in piv.columns], fontsize=8.5)
    ax.grid(False)
    fig.colorbar(im, ax=ax, pad=0.01, shrink=0.85).set_label("일평균 충전건수(건)", fontsize=8)
    ax.set_title(f"{emd} 과거 충전 수요 패턴 (2021-01~2022-06 · 요일×월)", fontsize=10.5, loc="left", pad=8)
    return _save(fig, path)


def weather_context(series: pd.DataFrame, target_date: str, path: str | Path) -> str:
    s = series.copy()
    s["dt"] = pd.to_datetime(s["base_date"].astype(str), format="%Y%m%d")
    fig, ax = plt.subplots(figsize=(8.4, 2.9))
    ax.bar(s["dt"], s["daily_rainfall"].fillna(0), color=C["blue"], alpha=0.55, width=0.75, label="일강수량(mm)")
    ax2 = ax.twinx()
    ax2.plot(s["dt"], s["average_temperature"], color=C["red"], lw=1.6, label="평균기온(°C)")
    ax2.set_ylabel("평균기온(°C)", color=C["red"], fontsize=8.5)
    ax2.tick_params(axis="y", colors=C["red"], labelsize=8)
    ax2.grid(False)
    ax.set_ylabel("일강수량(mm)", color=C["blue"], fontsize=8.5)
    td = pd.to_datetime(target_date)
    ax.axvline(td, color=C["ink"], ls="--", lw=1.4)
    ax.annotate("대상일", xy=(td, ax.get_ylim()[1] * 0.86), xytext=(-6, 0), textcoords="offset points",
                fontsize=8, color=C["ink"], ha="right")
    ax.set_title(f"대상일 전후 기상(실측 · {series['observatory_name'].iloc[-1] if 'observatory_name' in series else '제주시'} 관측소)",
                 fontsize=10.5, loc="left", pad=8)
    ax.tick_params(axis="x", labelsize=8)
    return _save(fig, path)


def supply_scatter(pressure: pd.DataFrame, path: str | Path) -> str:
    """공급 압력 × 관광 부하 산점도. 라벨은 adjustText가 있으면 자동 회피, 없으면 단순 배치."""
    fig, ax = plt.subplots(figsize=(7.6, 3.9))
    size = 46 + pressure["chargers_now"] * 0.35
    color = [C["green"] if k != "관광지" else C["amber"] for k in pressure["kind"]]
    ax.scatter(pressure["ev_per_charger"], pressure["tourist_load"], s=size, c=color, alpha=0.78,
               edgecolor="white", linewidth=0.8, zorder=3)
    texts = []
    for _, r in pressure.iterrows():
        texts.append(ax.text(r.ev_per_charger, r.tourist_load, r.emd_name, fontsize=7.0, color=C["muted"]))
    xr = pressure["ev_per_charger"].max() - pressure["ev_per_charger"].min()
    yr = pressure["tourist_load"].max() - pressure["tourist_load"].min()
    ax.set_xlim(pressure["ev_per_charger"].min() - xr * 0.10, pressure["ev_per_charger"].max() + xr * 0.18)
    ax.set_ylim(-yr * 0.08, pressure["tourist_load"].max() + yr * 0.12)
    try:
        from adjustText import adjust_text
        adjust_text(texts, ax=ax, only_move={"text": "y"},
                    arrowprops=dict(arrowstyle="-", color="#C7D2CD", lw=0.6))
    except Exception:
        for t in texts:
            t.set_position((t.get_position()[0] + xr * 0.01, t.get_position()[1] + yr * 0.02))
    ax.set_xlabel("EV 1대당 충전기 수(대/기) — 높을수록 공급 부족", fontsize=8.6)
    ax.set_ylabel("충전기 1기당 연간 관광 유입(명)", fontsize=8.6)
    ax.set_title("읍면동별 공급 압력 × 관광 부하 (버블 = 충전기 수)", fontsize=10.5, loc="left", pad=8)
    ax.grid(True, color=C["line"], lw=0.6)
    ax.tick_params(labelsize=8)
    return _save(fig, path)


def supply_bars(pressure: pd.DataFrame, path: str | Path) -> str:
    """공급 압력(EV/충전기)과 관광 부하를 두 패널 막대로 — 산점도보다 읽기 쉽다."""
    d = pressure.copy()
    d["label"] = d["emd_name"] + "  (" + d["kind"] + ")"
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 4.6))
    a = d.sort_values("ev_per_charger")
    kind_color = {"도심": C["green"], "주거": C["muted"], "관광지": C["amber"]}
    axes[0].barh(a["label"], a["ev_per_charger"], color=[kind_color.get(k, C["green"]) for k in a["kind"]], height=0.68)
    for y, v in enumerate(a["ev_per_charger"]):
        axes[0].text(v + 0.4, y, f"{v:.1f}", va="center", fontsize=7, color=C["muted"])
    axes[0].set_title("EV 1대당 충전기 수(대/기)\n낮을수록 공급 부족", fontsize=9.2, loc="left")
    axes[0].set_xlim(0, a["ev_per_charger"].max() * 1.18)
    axes[0].tick_params(labelsize=7.4)
    b = d.sort_values("tourist_load")
    axes[1].barh(b["label"], b["tourist_load"] / 1000, color=[C["amber"] if k == "관광지" else C["line"] for k in b["kind"]], height=0.68)
    for y, v in enumerate(b["tourist_load"] / 1000):
        axes[1].text(v + 0.2 if v > 0 else 0.2, y, f"{v:.1f}" if v > 0 else "관광 유입 없음",
                     va="center", fontsize=6.8, color=C["muted"])
    axes[1].set_title("충전기 1기당 연간 관광 유입(천 명)\n높을수록 관광 수요 집중", fontsize=9.2, loc="left")
    axes[1].set_xlim(0, (b["tourist_load"].max() / 1000) * 1.2)
    axes[1].tick_params(labelsize=7.4)
    for ax in axes:
        ax.grid(axis="y", visible=False)
    fig.suptitle("읍면동별 공급 압력 · 관광 부하 (초록=도심, 회색=주거, 주황=관광지)", fontsize=10.5, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return _save(fig, path)


def a2a_workflow(path: str | Path, used_rework: bool = True) -> str:
    fig, ax = plt.subplots(figsize=(9.4, 4.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.4)
    ax.axis("off")

    def box(x, y, w, h, title, sub, color):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.06,rounding_size=0.12",
                                    linewidth=1.2, edgecolor=color, facecolor="#FFFFFF"))
        ax.text(x + w / 2, y + h - 0.32, title, ha="center", va="center", fontsize=9.8, color=color, weight="bold")
        ax.text(x + w / 2, y + h / 2 - 0.18, sub, ha="center", va="center", fontsize=7.6, color=C["muted"], linespacing=1.5)

    box(0.15, 2.5, 2.1, 1.35, "사용자 질의", "지역·요일·시간대\n(예: 금 18시 애월읍)", C["ink"])
    box(2.75, 2.35, 2.5, 1.65, "ev_demand_agent", "충전·유입 분석\n[494][136~141][512][745/746]", C["green"])
    box(5.85, 2.35, 2.4, 1.65, "weather_safety_agent", "기상·안전 검증\n[756][493]", C["blue"])
    box(2.75, 0.25, 2.5, 1.45, "concierge_report_agent", "도민 안내·리포트\nTOP3 · 시간대 · 차트", C["amber"])

    def arrow(x1, y1, x2, y2, label, color=C["muted"], style="-|>", rad=0.0, ls="-"):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=11,
                                     color=color, lw=1.3, connectionstyle=f"arc3,rad={rad}", linestyle=ls))
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.10, label, fontsize=7.4, color=color, ha="center")

    arrow(2.25, 3.18, 2.72, 3.18, "TaskRequest")
    arrow(5.25, 3.18, 5.82, 3.18, "TaskArtifact")
    if used_rework:
        arrow(6.05, 2.33, 4.55, 2.31, "re_route_needed(재탐색 요청)", color=C["red"], rad=0.28)
    arrow(4.05, 2.33, 4.05, 1.72, "검증 통과 Artifact", color=C["green"])
    arrow(5.28, 1.0, 5.95, 2.30, "Artifact 종합", color=C["amber"], rad=-0.25)
    ax.text(0.15, 0.55, "A2A 표준 봉투: AgentCard · TaskRequest · TaskArtifact\n모든 홉은 로그(hop·검증·지연)로 남아 UI/CLI에서 추적", fontsize=7.6, color=C["muted"])
    ax.set_title("JejuEV Guardian A2A 멀티 에이전트 워크플로", fontsize=11.5, loc="left", pad=6)
    return _save(fig, path, dpi=200)


def hourly_curve(curve: pd.DataFrame, hour: int, emd: str, path: str | Path) -> str:
    fig, ax = plt.subplots(figsize=(7.8, 2.9))
    ax.plot(curve["hour"], curve["wait_min"], color=C["green"], lw=2, label="예상 대기(분)")
    ax.fill_between(curve["hour"], curve["wait_min"], color=C["green"], alpha=0.10)
    ax.plot(curve["hour"], curve["p90_min"], color=C["muted"], lw=1, ls=":", label="상위 10% 대기(p90)")
    ax.axvline(hour, color=C["red"], lw=1.5, ls="--")
    ax.text(hour + 0.3, max(curve["wait_min"]) * 0.9, f"{hour:02d}시", color=C["red"], fontsize=8.5)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlabel("시간대(시)")
    ax.set_ylabel("분")
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_title(f"{emd} 급속충전 예상 대기 곡선", fontsize=10.5, loc="left", pad=8)
    return _save(fig, path)
