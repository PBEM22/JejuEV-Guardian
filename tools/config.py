# -*- coding: utf-8 -*-
"""공통 설정 · 경로 · 폰트 · 엔진 감지.

이 모듈 하나만 읽으면 실행 환경(경로·폰트·추론 백엔드)을 알 수 있게 정리했다.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path

APP_NAME = "JejuEV Guardian"
APP_VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATASET_DIR = DATA_DIR / "datasets"
CATALOG_PATH = DATA_DIR / "catalog_index.json"
FONT_DIR = ROOT / "assets" / "fonts"
OUTPUT_DIR = Path(os.environ.get("JEJU_OUTPUT_DIR", ROOT / "outputs"))

# --- 폰트 ------------------------------------------------------------------
# 센터 PC(Windows)에서도 한글이 깨지지 않도록 번들 폰트를 우선 사용하고,
# 없으면 운영체제 기본 고딕으로 내려간다.
FONT_CANDIDATES = [
    FONT_DIR / "NanumGothic-Regular.ttf",
    Path("C:/Windows/Fonts/malgun.ttf"),
    Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/usr/share/fonts/pickle-hwp/NotoSansCJKkr-Regular.otf"),
]


def font_path() -> Path | None:
    for p in FONT_CANDIDATES:
        if p.exists():
            return p
    return None


def register_matplotlib_font() -> str | None:
    """matplotlib에 한글 폰트를 등록하고 family 이름을 돌려준다."""
    import matplotlib
    from matplotlib import font_manager

    p = font_path()
    if p is None:
        return None
    try:
        font_manager.fontManager.addfont(str(p))
        name = font_manager.FontProperties(fname=str(p)).get_name()
        matplotlib.rcParams["font.family"] = name
        matplotlib.rcParams["axes.unicode_minus"] = False
        return name
    except Exception:  # pragma: no cover - 폰트 파일 손상 등
        return None


def pdf_font() -> tuple[str, str | None]:
    """reportlab용 (regular, bold) 폰트 경로. TTF만 임베드 가능."""
    reg = FONT_DIR / "NanumGothic-Regular.ttf"
    bold = FONT_DIR / "NanumGothic-Bold.ttf"
    if reg.exists():
        return str(reg), (str(bold) if bold.exists() else None)
    if platform.system() == "Windows" and Path("C:/Windows/Fonts/malgun.ttf").exists():
        return "C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/malgunbd.ttf"
    p = font_path()
    return (str(p), None) if p else ("Helvetica", None)


# --- .env 로더(외부 패키지 없이) -------------------------------------------
def _load_dotenv() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


_load_dotenv()


# --- 추론 백엔드 -----------------------------------------------------------
def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def engine_mode() -> str:
    """'zerokey' | 'ollama' | 'cloud' — .env 설정으로 자동 판별."""
    forced = env("JEJU_ENGINE")
    if forced:
        return forced
    if env("OPENAI_API_KEY") or env("GEMINI_API_KEY"):
        return "cloud"
    if env("OLLAMA_BASE_URL"):
        return "ollama"
    return "zerokey"


ENGINE_LABELS = {
    "zerokey": "Zero-Key 내장 스마트 엔진 (API 키 불필요)",
    "ollama": "로컬 경량 LLM (Ollama, qwen2.5:3b)",
    "cloud": "클라우드 LLM API (OpenAI/Gemini 호환)",
}


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
