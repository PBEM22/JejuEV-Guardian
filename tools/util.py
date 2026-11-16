# -*- coding: utf-8 -*-
"""리포트/차트 등에서 쓰는 데이터셋·모델 접근 도구."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def jnum(v: Any) -> Any:
    """numpy/pandas 스칼라를 JSON 직렬화 가능한 기본형으로."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        v = float(v)
    if isinstance(v, float):
        return None if math.isnan(v) or math.isinf(v) else round(v, 2)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def records(df: pd.DataFrame, limit: int = 50) -> list[dict]:
    out = []
    for row in df.head(limit).to_dict(orient="records"):
        out.append({k: jnum(v) for k, v in row.items()})
    return out


def fmt_int(v: float) -> str:
    try:
        return f"{int(round(float(v))):,}"
    except Exception:
        return "-"
