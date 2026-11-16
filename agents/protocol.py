# -*- coding: utf-8 -*-
"""A2A(Agent-to-Agent) 프로토콜 구현.

표준 메시지
-----------
* ``AgentCard`` : 에이전트의 역할·능력·입출력 스키마 선언(발견/협상용)
* ``TaskRequest`` : 작업 요청 봉투. 누가(``from_agent``)→누구에게(``to_agent``),
  무엇을(``intent``) 어떤 조건(``constraints``)으로 요청하는지 담는다.
* ``TaskArtifact`` : 작업 결과 봉투. 결과 데이터(``data``), 근거 데이터와 기준일(``evidence``),
  산출 방법(``method``), 신뢰도(``confidence``), 경고(``warnings``), 다음 행동(``next_action``).

``A2ABus`` 는 요청을 받아 ① 수신 에이전트의 ``input_schema`` 로 검증하고 ② 통과하면 실행,
③ 모든 봉투를 순번(hop)·지연시간과 함께 로그로 남긴다. 로그는 UI/CLI/JSONL로 그대로 노출되어
"요청 → 검증 → 재탐색(re_route_needed) → 최종 리포트" 흐름을 추적할 수 있다.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Callable, Iterable

MAX_HOPS = 12


def _now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def _mid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# --------------------------------------------------------------------------
# 아주 작은 JSON-Schema 검증기(외부 의존성 없이 동작하도록 직접 구현)
# --------------------------------------------------------------------------
_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
}


def validate(payload: Any, schema: dict, path: str = "$") -> list[str]:
    errors: list[str] = []
    stype = schema.get("type")
    if stype:
        py = _TYPE_MAP[stype]
        if stype == "integer" and isinstance(payload, bool):
            errors.append(f"{path}: integer expected")
        elif not isinstance(payload, py):
            errors.append(f"{path}: {stype} expected, got {type(payload).__name__}")
            return errors
    if "enum" in schema and payload not in schema["enum"]:
        errors.append(f"{path}: must be one of {schema['enum']}")
    if stype == "object":
        for key in schema.get("required", []):
            if key not in payload or payload[key] in (None, ""):
                errors.append(f"{path}.{key}: required")
        for key, sub in schema.get("properties", {}).items():
            if isinstance(payload, dict) and key in payload and payload[key] is not None:
                errors += validate(payload[key], sub, f"{path}.{key}")
    if stype == "array" and isinstance(payload, list):
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(payload[:20]):
                errors += validate(item, item_schema, f"{path}[{i}]")
        if "minItems" in schema and len(payload) < schema["minItems"]:
            errors.append(f"{path}: at least {schema['minItems']} items required")
    if stype in ("number", "integer"):
        if "minimum" in schema and payload < schema["minimum"]:
            errors.append(f"{path}: >= {schema['minimum']} required")
        if "maximum" in schema and payload > schema["maximum"]:
            errors.append(f"{path}: <= {schema['maximum']} required")
    return errors


# --------------------------------------------------------------------------
# 표준 봉투
# --------------------------------------------------------------------------
@dataclass
class AgentCard:
    name: str
    display_name: str
    role: str
    version: str
    capabilities: list[str]
    input_schema: dict
    output_schema: dict
    data_sources: list[dict]
    constraints: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TaskRequest:
    from_agent: str
    to_agent: str
    intent: str
    payload: dict
    constraints: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    task_id: str = ""
    message_id: str = ""
    hop: int = 0
    reply_to: str | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        self.task_id = self.task_id or _mid("task")
        self.message_id = self.message_id or _mid("req")
        self.created_at = self.created_at or _now()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TaskArtifact:
    from_agent: str
    to_agent: str
    task_id: str
    status: str  # ok | rework_request | error
    summary: str
    data: dict = field(default_factory=dict)
    evidence: list[dict] = field(default_factory=list)
    method: str = ""
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    next_action: dict = field(default_factory=dict)
    message_id: str = ""
    hop: int = 0
    reply_to: str | None = None
    created_at: str = ""
    latency_ms: int = 0
    validation: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.message_id = self.message_id or _mid("art")
        self.created_at = self.created_at or _now()

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# 버스
# --------------------------------------------------------------------------
class A2ABus:
    """에이전트 등록·검증·라우팅·로깅."""

    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}
        self.cards: dict[str, AgentCard] = {}
        self.log: list[dict] = []
        self.hop = 0

    def register(self, agent: Any) -> AgentCard:
        card: AgentCard = agent.card
        self.agents[card.name] = agent
        self.cards[card.name] = card
        return card

    def card_json(self) -> str:
        return json.dumps([c.to_dict() for c in self.cards.values()], ensure_ascii=False, indent=2)

    def request(self, from_agent: str, to_agent: str, intent: str, payload: dict,
                constraints: dict | None = None, context: dict | None = None,
                reply_to: str | None = None, task_id: str = "") -> tuple[TaskRequest, TaskArtifact]:
        self.hop += 1
        req = TaskRequest(from_agent=from_agent, to_agent=to_agent, intent=intent, payload=payload,
                          constraints=constraints or {}, context=context or {},
                          hop=self.hop, reply_to=reply_to, task_id=task_id)
        target = self.agents.get(to_agent)
        started = time.perf_counter()
        if target is None:
            art = TaskArtifact(from_agent=to_agent, to_agent=from_agent, task_id=req.task_id,
                               status="error", summary=f"등록되지 않은 에이전트: {to_agent}",
                               hop=self.hop, reply_to=req.message_id)
            art.latency_ms = int((time.perf_counter() - started) * 1000)
            self._record(req, art, {"ok": False, "errors": ["unknown_agent"]})
            return req, art

        errors = validate(payload, self.cards[to_agent].input_schema)
        if errors or req.hop > MAX_HOPS:
            errs = errors or [f"최대 홉({MAX_HOPS}) 초과"]
            art = TaskArtifact(from_agent=to_agent, to_agent=from_agent, task_id=req.task_id,
                               status="error", summary="요청 스키마 검증 실패 → 작업 미실행",
                               warnings=errs, hop=self.hop, reply_to=req.message_id,
                               validation={"ok": False, "errors": errs})
            art.latency_ms = int((time.perf_counter() - started) * 1000)
            self._record(req, art, art.validation)
            return req, art

        art: TaskArtifact = target.handle(req)
        art.hop = self.hop
        art.reply_to = req.message_id
        art.task_id = req.task_id
        art.validation = {"ok": True, "errors": []}
        art.latency_ms = int((time.perf_counter() - started) * 1000)
        self._record(req, art, art.validation)
        return req, art

    def _record(self, req: TaskRequest, art: TaskArtifact, validation: dict) -> None:
        self.log.append({
            "hop": req.hop,
            "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "from": req.from_agent,
            "to": req.to_agent,
            "intent": req.intent,
            "request_id": req.message_id,
            "artifact_id": art.message_id,
            "status": art.status,
            "validation": "통과" if validation.get("ok") else "실패",
            "latency_ms": art.latency_ms,
            "summary": art.summary,
            "next_action": art.next_action,
            "warnings": art.warnings,
            "evidence": [e.get("dataset") for e in art.evidence],
        })

    # --- 내보내기 ---------------------------------------------------------
    def to_jsonl(self, path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for row in self.log:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def to_markdown(self) -> str:
        lines = ["| 홉 | 시각 | 보낸 곳 → 받은 곳 | 의도 | 검증 | 상태 | 지연(ms) | 요약 |",
                 "|---:|---|---|---|---|---|---:|---|"]
        for r in self.log:
            lines.append(
                f"| {r['hop']} | {r['time']} | {r['from']} → {r['to']} | {r['intent']} | "
                f"{r['validation']} | {r['status']} | {r['latency_ms']} | {r['summary'][:60]} |"
            )
        return "\n".join(lines)

    def hops(self) -> Iterable[dict]:
        return iter(self.log)
