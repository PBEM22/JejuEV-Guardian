# JejuEV Guardian ⚡

> 제주 도민·운전자를 위한 **전기차 충전 대기·이동 리스크 분석 A2A 멀티 에이전트**
> 충전·유입 분석 → 기상·안전 검증 → 도민 안내·리포트를 **에이전트끼리 주고받으며** 완성합니다.

- 대회: 제주 AI·빅데이터 활용 AI Agent 개발 챌린지 (제주테크노파크 · 데이콘)
- 핵심: 질문 한 줄 → **예상 대기(분) · 리스크 점수 · TOP3 충전소 · 피해야 할 시간대 · 주의사항 · 차트 · 리포트**
- 원칙: **API 키 없이 100% 동작**(Zero-Key 내장 엔진), 계산은 결정적 코드(같은 질문 = 같은 답), 모든 수치에 **근거 데이터와 기준일** 표기

---

## 1. 30초 실행

```bash
# 1) (권장) 가상환경
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2) 의존성 설치 (인터넷 필요, 최초 1회)
pip install -r requirements.txt

# 3) 실행 — 원클릭 스크립트
./run.sh                          # Windows: run.bat
#   또는 직접
streamlit run app.py
```

브라우저가 자동으로 열리지 않으면 <http://localhost:8501> 에 접속하세요.
**API 키도, GPU도, 인터넷도 필요 없습니다.** 내장 검증 데이터로 바로 결과가 나옵니다.

### CLI(웹 UI 없이)로 확인

```bash
python -m agents.cli "금요일 오후 6시에 애월읍에서 급속충전 할 만한 곳 알려줘"
python -m agents.cli "비 오는 주말에 서귀포 중문에서 안전하게 충전할 곳 찾아줘" --date 2026-11-14 --hour 13
python -m agents.cli --cards            # AgentCard(JSON) 출력
```

### 자동 검증(평가 재현용)

```bash
python tests/run_e2e_demo.py
```
→ 3개 시나리오(애월·중문·공항) + A2A 프로토콜 계약 + 재현성 검사를 실행하고,
`outputs/run_*/` 에 **PNG 차트 · Markdown · PDF 리포트 · A2A 로그(JSONL)** 를 생성합니다.
결과 요약은 `outputs/e2e_summary.json` 에 저장됩니다.

---

## 2. 무엇을 하는가 (사용자 매뉴얼)

### 2.1 화면 구성

| 영역 | 내용 |
|---|---|
| 상단 배너 | 서비스 소개·현재 선택된 추론 백엔드 |
| 사이드바 | 추론 백엔드 선택(Zero-Key/Ollama/클라우드), 데이터 연결 상태, **A2A 에이전트 카드**, 데이터 기준일 목록 |
| 질문 입력 | 예시 질문 3개 버튼 또는 직접 입력. `조건 직접 지정`에서 날짜·시각·지역을 고정할 수 있음 |
| 결과 | ① 결론 요약 카드 ② TOP3 충전소 카드 ③ 탭(차트 / A2A 로그 / 근거 데이터 / 원본 메시지) ④ 다운로드(MD·PDF·A2A 로그) |

### 2.2 질문 예시

| 하고 싶은 것 | 이렇게 물어보세요 |
|---|---|
| 퇴근길 충전 | “금요일 오후 6시에 애월읍에서 급속충전 할 만한 곳 알려줘” |
| 비 오는 날 안전 충전 | “비 오는 주말에 서귀포 중문에서 안전하게 충전할 곳 찾아줘” |
| 출근·공항 피크 | “평일 아침 출근시간 제주공항 근처 충전 대기 어때?” |
| 특정 날짜 | “2026-11-14 13시 중문 급속충전 어디가 나아?” |

인식되는 지역(읍면동)은 14곳입니다: 용담2동(공항), 이도1동, 노형동, 연동, 아라동, 애월읍, 조천읍, 좌읍, 한림읍, 중문동, 대정읍, 성산읍, 표선면, 남원읍.
시간 표현은 “오전 9시 / 오후 6시 / 18시 / 아침 / 점심 / 저녁 / 퇴근 / 밤”을 이해하고,
날짜는 “금요일 / 이번 주 토요일 / 내일 / 11월 20일 / 2026-11-14”를 이해합니다.

### 2.3 결과 읽는 법

- **예상 대기(분)**: 과거 패턴 × 최신 공급 수준 × 계절 × 기상으로 계산한 값. `상위 10%`는 운이 나쁠 때의 대기(p90)입니다.
- **리스크 점수(0~100)**: `0.55·대기 + 0.20·공급압력 + 0.15·관광부하 + 0.10·안전`. 70 이상 ‘높음’, 45 이상 ‘보통’, 그 아래 ‘낮음’.
- **비고**: `권장`은 안전·기상 검증을 통과한 후보, `주의`는 통과 후보가 3곳 미만일 때 부득이 제시한 대안입니다.
- **재탐색**: 기상·안전 검증에서 위험 후보가 나오면 에이전트가 후보를 교체합니다. 화면의 `A2A 로그` 탭과 `재탐색 전후` 차트에서 확인할 수 있습니다.

### 2.4 산출물 위치

```
outputs/run_<일시>_<지역>_<시각>/
├── report.md            # 도민용 리포트(Markdown)
├── report.pdf           # 같은 내용의 PDF(한글 폰트 임베드)
├── charts/              # 01~06 PNG 차트
├── a2a_log.jsonl        # 홉별 A2A 로그(요청·검증·상태·지연·요약)
├── agent_cards.json     # 이번 실행에 참여한 에이전트 카드
└── run.json             # 전체 결과(Artifact 원문 포함)
```

---

## 3. 구조

```
JejuEV_Guardian/
├── app.py                     # Streamlit 웹 UI
├── agents/
│   ├── protocol.py            # A2A 표준 봉투(AgentCard·TaskRequest·TaskArtifact) + 버스 + 스키마 검증
│   ├── ev_demand.py           # ① 충전·유입 분석 Agent
│   ├── weather_safety.py      # ② 기상·안전 검증 Agent
│   ├── concierge.py           # ③ 도민 안내·리포트 Agent
│   ├── orchestrator.py        # 질의 해석 + 라우팅 + 재탐색 루프
│   ├── backends.py            # Zero-Key / Ollama / 클라우드 LLM 백엔드
│   └── cli.py                 # CLI 진입점
├── tools/
│   ├── datasets.py            # 7종 데이터 적재·정규화 + 제주데이터허브 Open API 커넥터
│   ├── risk.py                # 대기 곡선·리스크 점수·안전 검증 모델
│   ├── charts.py              # 차트 6종(한글 폰트 자동 등록)
│   ├── report.py              # Markdown · PDF 리포트
│   ├── catalog.py(내장)       # 카탈로그 검색(1,259건 허브 목록 + 70종 센터 스키마)
│   └── config.py              # 경로·폰트·엔진 감지
├── data/
│   ├── catalog_index.json     # 메타데이터 인덱스(원본 엑셀 미포함)
│   └── datasets/              # 검증 데이터 7종 + 생성 메타
├── scripts/
│   ├── make_ev_datasets.py    # 검증 데이터 재생성(seed 고정)
│   └── build_catalog.py       # 카탈로그 인덱스 재생성(원본 엑셀 보유 시)
├── docs/
│   ├── build_docs.py          # 기획서·결과설명자료 PDF 빌드
│   └── RESULT_REPORT.pdf
├── tests/run_e2e_demo.py
├── requirements.txt · .env.example · run.sh · run.bat
├── DATA_SPEC.md · NOTICE.md
└── assets/fonts/NanumGothic-*.ttf
```

### A2A 흐름

```
사용자 질의
   │ TaskRequest
   ▼
ev_demand_agent ──TaskArtifact──▶ weather_safety_agent
   ▲                                   │
   └──── re_route_needed (제외 목록+사유) ┘   ← 위험 후보가 있을 때 1회
                                   │ 검증 통과
                                   ▼
                        concierge_report_agent ──▶ TOP3 · 회의 시간대 · 차트 · 리포트
```

모든 요청은 수신 에이전트의 `input_schema` 검증을 통과해야 실행되고,
모든 홉은 `A2ABus` 로그에 남습니다(최대 12홉, 재탐색 최대 1회).

---

## 4. 설정(.env) — 모두 선택 사항

`cp .env.example .env` 후 필요한 항목만 채우세요. **비워두면 Zero-Key 모드로 동작합니다.**

| 변수 | 기본값 | 설명 |
|---|---|---|
| `JEJU_ENGINE` | (자동) | `zerokey` / `ollama` / `cloud` 강제 지정 |
| `JEJU_HUB_API_KEY` | 없음 | 제주데이터허브 Open API 키 |
| `JEJU_USE_LIVE_API` | `0` | `1`이면 허브 API 실시간 호출(실패 시 내장 데이터로 폴백) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 서버 주소 |
| `OLLAMA_MODEL` | `qwen2.5:3b` | 로컬 모델(GTX 1060 3GB → 3B 4-bit 권장) |
| `OPENAI_API_KEY` | 없음 | OpenAI/Gemini 호환 키 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | 호환 엔드포인트 |
| `JEJU_LIVE_WEATHER` | `1` | `0`이면 기상 실시간 조회를 끔(완전 오프라인) |

> API 키는 코드·문서·로그에 남지 않습니다. `.env` 는 배포본에 포함되지 않습니다.

---

## 5. 제주빅데이터센터 PC(최소사양) 대응

| 사양 | 대응 |
|---|---|
| i7-8700 / RAM 32GB | 분석 1회 **1.9~2.7초**(실측), 피크 메모리 1.2GB 이하 |
| GTX 1060 3GB VRAM | 기본은 Zero-Key(GPU 미사용). LLM 사용 시 `qwen2.5:3b` 4-bit(≈2GB) 권장 |
| 인터넷 없음 | 내장 검증 데이터로 100% 동작(기상은 내장 실측값 사용) |
| Windows | `run.bat`, 한글 폰트 번들(NanumGothic) + `malgun.ttf` 자동 폴백 |

---

## 6. 오류 · 제약사항

| 증상 | 원인 · 조치 |
|---|---|
| `FileNotFoundError: data/datasets/...` | 검증 데이터가 없음 → `python scripts/make_ev_datasets.py` (오프라인이면 `--skip-weather-download`) |
| 차트 한글이 네모(□)로 보임 | 폰트 파일 누락 → `assets/fonts/NanumGothic-Regular.ttf` 확인, 또는 OS 기본 폰트로 자동 대체 여부 확인 |
| PDF가 생성되지 않음 | reportlab 미설치 → `pip install reportlab`. 실패해도 Markdown·차트는 정상 생성됩니다 |
| Ollama 선택 시 “연결 안 됨” | `ollama serve` 실행 여부, `OLLAMA_BASE_URL` 확인. 연결되지 않으면 Zero-Key로 자동 폴백 |
| 클라우드 모드가 조용히 Zero-Key로 동작 | 키·`OPENAI_BASE_URL` 확인. 폴백 사유는 결과의 `warnings`에 남습니다 |
| 기상이 “평년값”으로 표시됨 | 대상일이 내장 기상 범위(2024-01~) 밖이고 실시간 조회가 실패한 경우. `JEJU_LIVE_WEATHER=0`이면 항상 평년값 사용 |
| 대상 날짜가 과거(2022)에서 멀다 | 대기 패턴은 2022년 자료입니다. **형태만** 사용하고 수준은 최신 데이터로 보정하며, 신뢰도(0.74~0.9)를 함께 표시합니다 |

---

## 7. 데이터 · 라이선스

- 필수 데이터: 제주데이터허브 Open API `[494][136~141][512][745/746][756][493]` — 상세는 **DATA_SPEC.md**
- 기상 실측: Open-Meteo(ERA5, CC BY 4.0)
- 폰트: NanumGothic(OFL), 문서용 Pretendard(OFL) — 배포본에는 NanumGothic만 포함
- 대회 규칙에 따라 **DAKER 배포용 원본 엑셀은 포함하지 않습니다**(메타데이터 인덱스만).

자세한 출처·이용조건은 `DATA_SPEC.md`, 라이선스 고지는 `NOTICE.md` 를 참고하세요.
