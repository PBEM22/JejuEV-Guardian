# -*- coding: utf-8 -*-
"""추론 백엔드 — 질의 해석만 LLM에 맡기고, 계산은 결정적 코드가 담당한다.

1) ZeroKeyBackend  : 규칙 기반 한국어 해석 (API 키 불필요 · 기본값 · 오프라인 100% 동작)
2) OllamaBackend   : 로컬 경량 LLM(qwen2.5:3b 등, GTX 1060 3GB VRAM) — http://localhost:11434
3) CloudBackend    : OpenAI/Gemini 호환 Chat Completions — .env의 키·base_url

LLM이 형식에 맞는 JSON을 못 주거나 응답이 없으면 조용히 Zero-Key로 폴백하고,
폴백 사실을 실행 결과에 남긴다(신뢰성·재현성 확보).
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from tools.config import env

REGION_HINT = ("지역 후보: 용담2동(공항), 이도1동, 노형동, 연동, 아라동, 애월읍, 조천읍, "
               "구좌읍, 한림읍, 중문동, 대정읍, 성산읍, 표선면, 남원읍")

SYSTEM_PROMPT = f"""너는 제주 전기차 충전 안내 시스템의 '질의 해석기'다.
사용자의 한국어 질문에서 지역·날짜·시간대·충전유형만 뽑아 JSON 하나로만 답한다.
{REGION_HINT}
출력 형식(설명·코드블록 없이 JSON만):
{{"region": "<위 지역 중 하나>", "date": "YYYY-MM-DD", "hour": <0-23 정수>, "charger_type": "급속"|"완속", "confidence": <0~1 실수>}}
오늘 날짜는 {{today}} 이다. '금요일'처럼 요일만 말하면 오늘 이후 가장 가까운 그 요일로 계산한다.
"""


class BaseBackend:
    name = "base"

    def parse(self, query: str, today, regions: list[str]) -> dict | None:  # pragma: no cover
        return None


class ZeroKeyBackend(BaseBackend):
    name = "zerokey"

    def parse(self, query, today, regions):
        return None  # 규칙 해석기는 orchestrator.parse_query 가 담당


def _extract_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        try:
            return json.loads(m.group(0).replace("'", '"'))
        except Exception:
            return None


def _validate(obj: dict | None, regions: list[str]) -> dict | None:
    if not isinstance(obj, dict):
        return None
    out = {}
    if obj.get("region") in regions or any(obj.get("region") == r for r in regions):
        out["region"] = obj["region"]
    if isinstance(obj.get("hour"), (int, float)) and 0 <= int(obj["hour"]) <= 23:
        out["hour"] = int(obj["hour"])
    d = str(obj.get("date", ""))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        out["date"] = d
    if obj.get("charger_type") in ("급속", "완속"):
        out["charger_type"] = obj["charger_type"]
    return out or None


class OllamaBackend(BaseBackend):
    name = "ollama"

    def __init__(self) -> None:
        self.base = env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.model = env("OLLAMA_MODEL", "qwen2.5:3b")

    def parse(self, query, today, regions):
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_predict": 160},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.format(today=today)},
                {"role": "user", "content": query},
            ],
        }
        try:
            req = urllib.request.Request(
                f"{self.base}/api/chat", data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=float(env("OLLAMA_TIMEOUT", "25"))) as r:
                js = json.loads(r.read().decode())
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None
        content = (js.get("message") or {}).get("content", "")
        return _validate(_extract_json(content), regions)


class CloudBackend(BaseBackend):
    name = "cloud"

    def __init__(self) -> None:
        self.base = env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.key = env("OPENAI_API_KEY") or env("GEMINI_API_KEY")
        self.model = env("OPENAI_MODEL", "gpt-4o-mini")

    def parse(self, query, today, regions):
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.format(today=today)},
                {"role": "user", "content": query},
            ],
        }
        try:
            req = urllib.request.Request(
                f"{self.base}/chat/completions", data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"},
                method="POST")
            with urllib.request.urlopen(req, timeout=25) as r:
                js = json.loads(r.read().decode())
            content = js["choices"][0]["message"]["content"]
        except Exception:
            return None
        return _validate(_extract_json(content), regions)


def get_backend(mode: str | None = None) -> BaseBackend:
    mode = (mode or "").lower()
    if mode == "ollama":
        return OllamaBackend()
    if mode == "cloud":
        return CloudBackend()
    if mode == "auto":
        b = OllamaBackend()
        if b.parse("테스트", __import__("datetime").date.today(), ["애월읍"]) is not None:
            return b
    return ZeroKeyBackend()


def backend_status() -> dict:
    """UI에 표시할 백엔드 상태."""
    out = {"zerokey": {"label": "Zero-Key 내장 엔진", "ready": True, "detail": "API 키 없이 항상 동작"}}
    ob = OllamaBackend()
    ready = False
    detail = f"연결 안 됨({ob.base})"
    try:
        with urllib.request.urlopen(f"{ob.base}/api/tags", timeout=0.8) as r:
            tags = json.loads(r.read().decode())
        names = [m.get("name", "") for m in tags.get("models", [])]
        ready = True
        detail = f"{ob.model}" + ("" if any(ob.model.split(":")[0] in n for n in names) else " (모델 미설치)")
    except Exception:
        pass
    out["ollama"] = {"label": "Ollama 로컬 LLM", "ready": ready, "detail": detail}
    cb = CloudBackend()
    out["cloud"] = {"label": "클라우드 LLM API", "ready": bool(cb.key),
                    "detail": f"{cb.model} · {cb.base}" if cb.key else ".env에 키 없음"}
    return out
