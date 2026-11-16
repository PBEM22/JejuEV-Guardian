# NOTICE — 라이선스 및 데이터 출처

## 폰트
- **NanumGothic** (Regular/Bold) — SIL Open Font License 1.1, © Naver Corp.
  배포본 `assets/fonts/` 에 포함되어 차트·PDF 한글 표시에 사용됩니다.
- **Pretendard** — SIL Open Font License 1.1, © Kil Hyung-jin.
  기획서·결과설명자료(PDF) 제작에만 사용하며 배포본에는 포함하지 않습니다.

## 데이터
- **제주데이터허브 Open API** `[493][494][512][745][746][756][136~141]`
  출처: 제주특별자치도 제주데이터허브(https://www.jejudatahub.net)
  · 본 제출물에는 허브 응답 스키마를 따른 검증용 재현 데이터만 포함합니다.
- **기상 실측** — Open-Meteo Historical Weather API (ERA5 재분석, ECMWF/Copernicus), **CC BY 4.0**
  https://open-meteo.com/ · 제주시·서귀포시 지점 일별 기온·강수·최대풍속
- 대회 주최 측이 제공한 **DAKER 배포용 원본 엑셀 3종은 재배포 금지** 자료로, 제출 ZIP에 포함하지
  않았습니다. 대신 코드로 파싱한 메타데이터 인덱스(`data/catalog_index.json`)만 사용합니다.

## 오픈소스
| 패키지 | 라이선스 |
|---|---|
| pandas | BSD-3-Clause |
| numpy | BSD-3-Clause |
| matplotlib | PSF 기반 (Matplotlib License) |
| Streamlit | Apache-2.0 |
| reportlab | BSD |
| Pillow | HPND |
| adjustText (선택) | MIT |

## AI 모델 (선택 기능)
- Ollama `qwen2.5:3b` (Apache-2.0) / `llama3.2:3b` (Llama 3.2 Community License) — **로컬 실행**, 외부 전송 없음
- OpenAI / Gemini 호환 API — 사용자가 `.env`에 설정한 키로만 호출, 질의 해석에만 사용

## 검증 데이터 고지
`data/datasets/` 의 충전소·충전이력·대기시간·EV보급·관광유입·사고다발 데이터는
**실제 관측값이 아닌 모의(합성) 데이터**이며, seed 고정 생성기(`scripts/make_ev_datasets.py`)로
재생성됩니다. 기상 데이터(`daily_weather.csv`)만 실측입니다.
