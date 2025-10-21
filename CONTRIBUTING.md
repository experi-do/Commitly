# Commitly Contributing Guide (MVP)

Commitly는 로컬 Git 리포지터리에서 커밋 직후 에이전트 파이프라인(Cloning → Code → Test → Refactor → Sync → Slack → Report)을 자동 실행해 보고서를 만들어 주는 도구입니다. 아래 지침은 MVP 단계 개발 방식을 정리한 것입니다.

---

## 1) 리포지터리 구조

| 경로 | 용도 |
|------|------|
| `commitly/` | CLI, LangGraph 플로우, 에이전트 구현 (추가 예정) |
| `docs/` | PRD, 아키텍처, 에이전트 설계 문서 |
| `.commitly/` | 런타임 캐시, 허브 스냅샷, 로그/리포트 (자동 생성) |
| `tests/` | 단위 및 통합 테스트 (추가 예정) |
| `vscode-extension/` | VS Code 확장(MVP 이후) |

> 현재는 문서 위주지만, 코드 추가 시 상기 구조를 따릅니다.

---

## 2) 브랜치 전략

| 브랜치 | 용도 | 규칙 |
|--------|------|------|
| `main` | 안정 버전, 배포 아티팩트 | PR 머지만 허용 |
| `develop` | 통합 테스트 | 모든 기능 브랜치가 머지되는 기본 대상 |
| `feat/<설명>` | 기능/문서 작업 | 예: `feat/clone-agent-runner` |
| `fix/<설명>` | 버그/핫픽스 | 예: `fix/sql-parser-bug` |

```bash
git switch develop
git switch -c feat/agent-config
```

---

## 3) 커밋 컨벤션

Gitmoji + 간결한 설명을 사용합니다.

| 타입 | 예시 | 목적 |
|------|------|------|
| ✨ `:sparkles: feat:` | `:sparkles: feat: add clone agent runner` | 기능 추가 |
| 🐛 `:bug: fix:` | `:bug: fix: handle empty query list` | 버그 수정 |
| 📝 `:memo: docs:` | `:memo: docs: update CodeAgent spec` | 문서 |
| ♻️ `:recycle: refactor:` | `:recycle: refactor: unify hub path util` | 리팩터링 |
| ✅ `:white_check_mark: test:` | `:white_check_mark: test: cover sql planner` | 테스트 |
| 🚀 `:rocket: release:` | `:rocket: release: cut v0.1.0` | 릴리즈 태그 |

커밋 본문엔 변경 사유, 영향, 테스트 결과를 짧게 기록하세요.

---

## 4) 개발 환경

- Python 3.11 이상 권장
- 패키지 관리: `uv` 또는 `pip` (MVP에서는 `pip install -e .` 기준)
- 포맷터/린터: `ruff`, `black`, `mypy` (추후 `pyproject.toml`에 정의)
- 환경 변수는 `.env`에 저장하고 `python-dotenv`로 로드 예정

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

---

## 5) 로컬 실행 & 검증

| 단계 | 명령 | 비고 |
|------|------|------|
| CLI 준비 | `python -m commitly.cli --help` | Typer/Click 예정 |
| 그래프 실행 | `python -m commitly.run_flow --dry-run` | 허브 없이 시뮬레이션 |
| VS Code 확장 | `code --extensionDevelopmentPath ./vscode-extension` | 선택 |
| 테스트 | `pytest -q` | Test Agent, Refactoring Agent 검증 |

RunContext/허브와 연동되는 기능은 `.commitly/hub`를 미리 만들어두고 실험하세요.

---

## 6) 작업 절차

1. `commitly init` 실행 → `.commitly/` 디렉터리 생성 확인
2. 기능 개발 후 `commitly git add .`
3. `commitly git commit -m "<msg>"` 실행 → Clone Agent가 허브 스냅샷 준비
4. Code Agent가 `python main.py` 실행, 실패 시 즉시 수정
5. Test Agent에서 SQL 최적화 → Refactoring Agent → Sync Agent 순으로 승인
6. Slack/Report Agent 산출물 확인
7. 모든 로그·리포트 확인 후 PR 생성

---

## 7) 문서 업데이트 원칙

- 기능 추가/수정 시 PRD, Architecture, Agent 사양 문서를 동기화합니다.
- 에이전트 동작 변경 시 해당 `<Agent>.md` 파일과 `docs/`의 흐름도를 업데이트합니다.
- 로그 형식 또는 JSON 스키마가 바뀔 경우 `docs/logging.md`(추가 예정)에 예시를 남깁니다.

---

## 8) 코드 품질

- 타입 힌트 필수, `mypy --strict` 통과 목표
- 공통 경로/상수는 `commitly/config.py` 등 중앙 모듈에서 관리
- Git/Subprocess 호출은 `commitly/utils/git.py` 유틸을 통해서만 수행
- SQL 파서는 Test Agent 모듈에 캡슐화하고 재사용 가능 API로 노출
- LLM 호출은 Rate Limit 대비 재시도 로직을 포함해야 합니다.

---

## 9) 보안 & 비밀정보

- `.env`에 API 키(`OPENAI_API_KEY`, `SLACK_BOT_TOKEN`, DB DSN 등)를 저장하고 절대 커밋하지 않습니다.
- 허브 디렉터리는 로컬 전용이며, 외부 공유 금지.
- 슬랙/보고용으로 수집된 데이터는 민감 정보 마스킹을 필수로 합니다.
- 타사 API 호출 시 이용 약관과 Rate Limit을 준수하세요.

---

## 🪣 10) 로그 및 리포트 저장 경로

허브(Hub)와 로컬 프로젝트 양쪽에 자동으로 동기화됩니다.

| 구분 | 경로 | 설명 |
|------|------|------|
| **허브 로그** | `.commitly/hub/log/<agent_name>/` | 에이전트별 실행 로그 |
| **허브 리포트** | `.commitly/hub/report/` | 허브 기준 통합 리포트 |
| **로컬 로그** | `.commitly/log/<agent_name>/` | 로컬 환경 실행 로그 |
| **로컬 리포트** | `.commitly/report/` | 최종 보고서/요약본 |

> 로그/리포트 경로 구조는 변경하지 마세요. 모든 에이전트가 동일한 레이아웃을 전제로 산출물을 교환합니다.

---

## 11) PR 체크리스트

- [ ] `python main.py` 수동 실행으로 런타임 에러 없음
- [ ] `pytest -q` 또는 해당 모듈 테스트 통과
- [ ] `.commitly/` 산출물 확인 (필요 시 캡처/요약 포함)
- [ ] 문서 동기화 (PRD, Agent spec 등)
- [ ] 커밋 컨벤션 준수, 의미 있는 메시지
- [ ] 민감 정보 미포함, 로그 정리 완료

---

## 12) 커뮤니케이션

- 주요 변경사항은 Slack `#commitly-dev` 채널 공지
- 장애/핫픽스는 Jira 티켓 생성 후 `fix/` 브랜치로 대응
- 주간 리포트는 Report Agent 산출물을 공유하고, 회고 시 개선 포인트 기록

---

## 13) 요약

작은 단위로 브랜치를 생성하여 작업 → 커밋 컨벤션 지키기 → Code/Test/Refactor 에이전트가 모두 통과하는지 검증 → 로그/리포트를 확인 후 PR 작성 → 문서와 규칙은 항상 최신 상태로 유지합니다. Commitly의 가치는 “커밋 직후 보고서 자동 생성”에 있으므로, 파이프라인 안정성과 로그/리포트 신뢰도를 최우선으로 삼아 주세요.
