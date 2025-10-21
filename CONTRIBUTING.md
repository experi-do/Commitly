# 🤝 Contributing Guide (v1)

3인 협업 프로젝트를 위한 일관된 **개발 · 리뷰 · 배포 규칙**입니다.  
브랜치 전략, 커밋 컨벤션(Gitmoji), 코드 스타일, PR 체크리스트를 반드시 준수해주세요.

---

## 🧱 1) Repository Structure (요약)

| 폴더 | 용도 |
|------|------|
| `agents/` | 개별 에이전트 (탐색 / 보강 / RAG / 평가 / 리포트) |
| `graph/` | 상태 · 그래프 · 실행 · 시각화 (통합 지점) |
| `data/` | 원본 및 정제 데이터 |
| `outputs/` | 보고서, 로그, 그래프 이미지 |
| `docs/` | 설계 문서, 평가표, 템플릿 등 |
> 📘 상세 구조는 `README.md` 참조

---

## 🌿 2) Branch Strategy

| 브랜치 | 용도 | 규칙 |
|--------|------|------|
| `main` | 릴리스 / 발표용 (**보호 브랜치**) | 직접 push 금지, PR만 병합 |
| `dev` | 통합 테스트 브랜치 | 모든 기능 브랜치의 머지 대상 |
| `feat/{이름}` | 개인 / 기능 단위 작업 | 예: `feat/keehoon_graph`, `feat/a_discovery` |

```bash
git switch -c feat/yourname_feature
```

## 🧩 3) Commit Convention (Gitmoji)

| 타입                           | 예시                                                 | 의미    |
| ---------------------------- | -------------------------------------------------- | ----- |
| ✨ `:sparkles: feat:`         | `:sparkles: feat: add ScoringAgent decision rule`  | 기능 추가 |
| 🐛 `:bug: fix:`              | `:bug: fix: handle empty serp results`             | 버그 수정 |
| 📝 `:memo: docs:`            | `:memo: docs: write architecture.md (v2)`          | 문서 작성 |
| ♻️ `:recycle: refactor:`     | `:recycle: refactor: split chunks by label`        | 리팩터링  |
| ✅ `:white_check_mark: test:` | `:white_check_mark: test: add chroma search tests` | 테스트   |
| 🚧 `:construction: chore:`   | `:construction: chore: add logging config`         | 빌드/설정 |

커밋 메시지 형식:
:emoji: type: subject
본문에는 변경 이유, 영향, 테스트 결과를 간단히 명시합니다.

## ⚙️ 4) Environment & Run

Python & 패키지

```
# Python 3.11 이상 권장
uv sync
python graph/run.py --query "..."
python graph/visualize.py
```

환경 변수 (.env)

```
OPENAI_API_KEY=
SERAPH_API_KEY=
```

⚠️ API Key는 절대 커밋 금지. .gitignore에 포함되어 있는지 확인하세요.

## 🧠 5) 코드 스타일 & 구조

타입힌트 필수

Pydantic 모델은 graph/state.py 단일 소스 유지

로깅: logging + rich 공용 포맷 사용

I/O 경로: outputs/ 하위 고정

Chroma 컬렉션명 규약 유지

LLM 프롬프트: prompts/ 폴더 또는 상수로 분리

## 🔁 6) 워크플로우
```
# 1️⃣ 브랜치 생성
git switch -c feat/yourname_part

# 2️⃣ 작업 및 테스트
uv run pytest -q   # (테스트가 있다면)

# 3️⃣ 커밋 및 푸시
git add .
git commit -m ":sparkles: feat: add RAGRetrieverAgent top-k filtering"
git push origin feat/yourname_part

# 4️⃣ Pull Request 생성 (base: dev)
# 5️⃣ 리뷰/수정 후 승인
# 6️⃣ dev 병합 → (릴리스 시) main 병합
```

## 🧾 7) PR 체크리스트

 로컬 실행 / 에러 없음 (run.py)

 로그/경로 준수 (outputs/...)

 타입힌트 및 Docstring 적용

 커밋 컨벤션(Gitmoji) 준수

 PDF 생성 로직 정상 작동

 데이터 및 비밀키 미노출

## 📂 8) Folder Ownership

| 폴더                 | 기본 담당          | 비고                 |
| ------------------ | -------------- | ------------------ |
| `agents/seraph_*`  | Discovery 담당   | API 키, 쿼리 정책 관리    |
| `agents/augment_*` | Augment 담당     | 크롤러, 파서, 라벨러       |
| `agents/rag_*`     | Vector/RAG 담당  | 임베딩, 검색 파라미터       |
| `agents/scoring_*` | Scoring 담당     | 가중치, Decision Rule |
| `agents/report_*`  | Report 담당      | 템플릿, 렌더링           |
| `graph/*`          | Graph/Infra 담당 | 상태 흐름 및 진행 표시      |

## 🔒 9) 데이터 & 보안 정책

* 외부 문서/링크는 출처(URL) 저장

* 민감 정보(이메일, 전화 등)는 로그 및 보고서에서 마스킹

* 크롤링 시 robots.txt 및 Rate Limit 정책 준수

## 🪣 10) 로그 및 리포트 저장 경로

허브(Hub) 및 로컬 프로젝트 리포지토리에 모두 동기화됩니다.

| 구분          | 경로                                                | 설명             |
| ----------- | ------------------------------------------------- | -------------- |
| **Hub 로그**  | `{targetproject}/.commitly/hub/log/{agent_name}/` | 각 Agent별 로그 폴더 |
| **Hub 리포트** | `{targetproject}/.commitly/hub/report/`           | 통합 리포트 저장      |
| **로컬 로그**   | `{targetproject}/commitly/log/{agent_name}/`      | 로컬 실행 로그       |
| **로컬 리포트**  | `{targetproject}/commitly/report/`                | 로컬 리포트 저장      |

| 🧩 로그 및 리포트는 자동 생성되며, 경로 구조를 임의 변경하지 마세요.
각 Agent는 동일한 구조를 공유하여 통합 리포팅 및 백업이 가능하도록 설계되었습니다.

## ✅ 11) Summary

* 기능 단위로 작게 PR

* 명확한 로그 / 타입힌트 / 테스트

* PDF 조건 로직 보존

* 공통 상수, 경로, 포맷은 문서화 후 재사용

| 모든 팀원이 같은 흐름으로 협업할 수 있도록 명시적 규칙, 일관된 로그 구조, 안전한 배포 절차를 유지합니다.
