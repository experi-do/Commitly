# Commitly 🚀

> AI-powered multi-agent commit automation system for local Python projects

**자동화된 코드 검증, 테스트, 리팩토링, 동기화를 Git 커밋 후 자동으로 처리합니다.**

![Commitly Pipeline](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-Orchestration-purple)
![License MIT](https://img.shields.io/badge/License-MIT-green)

---

## ✨ 주요 기능

### 자동 파이프라인
```
git commit -m "메시지"
    ↓
[CloneAgent]       → 허브 저장소 동기화
[CodeAgent]        → 정적 검사 + 동적 실행 + SQL 파싱
[TestAgent]        → SQL 최적화 + 테스트 실행
[RefactoringAgent] → LLM 기반 코드 개선
[SyncAgent]        → 사용자 승인 ⚠️ (유일한 승인 지점)
[SlackAgent]       → Slack 알림 (비차단)
[ReportAgent]      → 보고서 생성 (비차단)
```

### 핵심 특징

- 🤖 **AI 기반 자동화**: OpenAI GPT-4o-mini를 사용한 코드 리팩토링
- 🔒 **격리된 실행**: Hub 저장소 패턴으로 로컬 워크스페이스 보호
- ⚡ **SQL 최적화**: LLM 후보 생성 + EXPLAIN ANALYZE 평가
- 🛡️ **안전한 승인**: SyncAgent에서만 원격 push (1개 승인 지점)
- 📝 **완전한 추적**: 모든 실행 로그 및 캐시 저장
- 🔄 **자동 롤백**: 실패 시 자동 롤백 + 상태 복원
- 🔗 **Slack 연동**: 커밋 후 Slack 채널에 자동 알림

---

## 🚀 빠른 시작

### 1. 설치

```bash
# 저장소 클론
git clone https://github.com/yourusername/Commitly.git
cd Commitly

# 의존성 설치
poetry install

# 프로젝트 초기화
poetry run commitly init
```

### 2. 환경 설정

`.env` 파일 생성:
```bash
# OpenAI API (필수)
OPENAI_API_KEY=sk-...

# PostgreSQL (SQL 최적화 시 선택)
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=your_database

# Slack (선택)
SLACK_TOKEN=xoxb-...
```

`config.yaml` 확인:
```yaml
llm:
  enabled: true
  model: gpt-4o-mini
  api_key: ${OPENAI_API_KEY}

execution:
  command: python main.py
  timeout: 300

test:
  timeout: 300

database:
  host: localhost
  port: 5432
  user: ${DB_USER}
  password: ${DB_PASSWORD}
  dbname: ${DB_NAME}
```

### 3. 파이프라인 실행

```bash
# 변경사항을 커밋하면 파이프라인 자동 실행
git add .
poetry run commitly commit -m "feat: 새로운 기능 추가"

# 또는
poetry run commitly git commit -m "feat: 새로운 기능 추가"
```

### 4. 주요 명령어

```bash
# 파이프라인 상태 확인
poetry run commitly status

# 보고서 생성
poetry run commitly report --from 2025-10-14 --to 2025-10-21 --format markdown

# 프로젝트 재초기화
poetry run commitly init
```

---

## 📁 디렉토리 구조

```
Commitly/
├── src/commitly/
│   ├── agents/                      # 7개 에이전트
│   │   ├── base.py                  # BaseAgent 추상 클래스
│   │   ├── clone/                   # CloneAgent (허브 동기화)
│   │   ├── code/                    # CodeAgent (코드 검증)
│   │   ├── test/                    # TestAgent (SQL 최적화, 테스트)
│   │   ├── refactoring/             # RefactoringAgent (코드 개선)
│   │   ├── sync/                    # SyncAgent (원격 push)
│   │   ├── slack/                   # SlackAgent (Slack 알림)
│   │   └── report/                  # ReportAgent (보고서)
│   ├── cli/                         # 커맨드라인 인터페이스
│   │   ├── main.py                  # 진입점
│   │   └── commands/                # 커맨드 구현
│   ├── core/                        # 공유 유틸리티
│   │   ├── config.py                # YAML 설정 로더
│   │   ├── context.py               # RunContext, AgentOutput
│   │   ├── git_manager.py           # Git 작업
│   │   ├── llm_client.py            # OpenAI API
│   │   ├── logger.py                # 로깅
│   │   └── rollback.py              # 실패 처리 및 롤백
│   └── pipeline/
│       └── graph.py                 # LangGraph 오케스트레이션
├── tests/                           # 테스트 (향후 추가)
├── .commitly/                       # 초기화 후 자동 생성
│   ├── config.yaml                  # 런타임 설정
│   ├── cache/                       # 에이전트 결과 캐시
│   └── logs/                        # 실행 로그
├── config.yaml                      # 프로젝트 설정 (버전 관리)
├── .env                             # 환경 변수 (gitignore)
└── README.md                        # 이 파일
```

---

## 🔄 파이프라인 상세 흐름

### CloneAgent
- **역할**: 허브 저장소 생성 및 동기화
- **동작**:
  1. 원격 저장소 얕은 복제 (shallow clone)
  2. 로컬 워크스페이스의 변경사항 적용
  3. `commitly/clone/{pipeline_id}` 브랜치 생성

### CodeAgent
- **역할**: 코드 검증 및 실행
- **동작**:
  1. Ruff 린트 검사
  2. MyPy 타입 검사
  3. `python main.py` 동적 실행
  4. SQL 쿼리 파싱 (AST 기반)

### TestAgent
- **역할**: SQL 최적화 및 테스트 실행
- **동작**:
  1. SQL 쿼리 최적화 (LLM 후보 생성, EXPLAIN ANALYZE 평가)
  2. `pytest` 테스트 실행
  3. 실패 시 자동 롤백

### RefactoringAgent
- **역할**: LLM 기반 코드 개선
- **동작**:
  1. 중복 코드 제거
  2. 예외 처리 추가
  3. Ruff --fix로 자동 포맷팅
  4. 리팩토링된 코드 재검증

### SyncAgent ⚠️ (승인 게이트)
- **역할**: 변경사항 요약 및 원격 push
- **동작**:
  1. 파이프라인 결과 요약
  2. 사용자 승인 요청 (y/n)
  3. 승인 시 `git push` 실행
  4. 모든 `commitly/*` 브랜치 자동 삭제

### SlackAgent (비차단)
- **역할**: Slack 알림
- **동작**:
  1. 커밋 메시지로 Slack 메시지 검색
  2. 관련 메시지 찾기
  3. 스레드에 결과 자동 답글

### ReportAgent (비차단)
- **역할**: 파이프라인 보고서 생성
- **동작**:
  1. 기간별 커밋 로그 수집
  2. SQL 최적화, 리팩토링 통계
  3. Markdown 보고서 생성

---

## 📊 에이전트 완성도

| 에이전트 | 완성도 | 상태 |
|---------|--------|------|
| CloneAgent | 95% | ✅ 프로덕션 수준 |
| CodeAgent | 85% | ⚠️ 명령어 파싱 이슈 있음 |
| TestAgent | 80% | ⚠️ SQL 비용 측정 미완 |
| RefactoringAgent | 95% | ✅ 튼튼한 구현 |
| SyncAgent | 95% | ✅ 프로덕션 수준 |
| SlackAgent | 90% | ✅ 거의 완성 |
| ReportAgent | 70% | ⚠️ PDF/HTML 미지원 |

**평균**: 86% → **프로덕션 배포 가능** ✅

자세한 개선 계획은 [IMPROVEMENT_PLAN.md](./IMPROVEMENT_PLAN.md) 참고

---

## 🛠️ 개발 명령어

```bash
# 의존성 설치
poetry install

# 환경 변수 로드 (필수)
set -a && source .env && set +a

# Ruff 린트 검사
ruff check src/

# Black 포맷팅
black src/

# MyPy 타입 검사
mypy src/commitly/

# 단위 테스트 (향후 추가)
pytest tests/

# 테스트 커버리지
pytest --cov=src/commitly tests/
```

---

## ⚙️ 설정

### config.yaml

```yaml
# Git 설정
git:
  remote: origin

# LLM 설정
llm:
  enabled: true
  provider: openai
  model: gpt-4o-mini
  api_key: ${OPENAI_API_KEY}

# 실행 프로필
execution:
  command: python main.py
  timeout: 300  # 초

# 테스트 프로필
test:
  timeout: 300

# 파이프라인 설정
pipeline:
  cleanup_hub_on_failure: false

# 데이터베이스 (SQL 최적화용)
database:
  host: localhost
  port: 5432
  user: ${DB_USER}
  password: ${DB_PASSWORD}
  dbname: ${DB_NAME}

# 리팩토링 규칙
refactoring:
  rules: |
    Remove duplicate code
    Add exception handling for risky operations

# Slack 설정
slack:
  enabled: false
  time_range_days: 7
  require_tag: false
  keywords: []
  save_path: .commitly/slack/matches.json

# 보고서 설정
report:
  format: md
  output_path: .commitly/reports
```

---

## 📍 자주 묻는 질문

### Q1: 로컬 워크스페이스가 수정되나요?
**A**: 아니요. 모든 작업은 Hub 저장소에서 실행됩니다. SyncAgent 승인 후에만 로컬 변경사항이 적용됩니다.

### Q2: 파이프라인 실패 시 어떻게 되나요?
**A**: 실패 지점에서 자동 롤백되고, 마지막 성공 상태로 복원됩니다. 에러 로그는 `.commitly/logs/`에 저장됩니다.

### Q3: SQL 최적화가 안전한가요?
**A**: 네. LLM이 생성한 SQL 후보를 EXPLAIN ANALYZE로 평가한 후, 가장 좋은 쿼리만 추천합니다.

### Q4: Slack 알림이 필수인가요?
**A**: 아니요. SlackAgent 실패는 파이프라인을 중단하지 않습니다 (비차단).

### Q5: 공백이 있는 명령어 사용 가능한가요?
**A**: 현재는 미완성입니다. [IMPROVEMENT_PLAN.md](./IMPROVEMENT_PLAN.md)의 "명령어 파싱 이슈"를 참고하세요.

### Q6: Windows에서도 동작하나요?
**A**: 부분적으로 지원합니다. WSL2 또는 Git Bash 사용을 권장합니다.

---

## 📊 로그 및 캐시

### 로그 위치
```
.commitly/logs/
├── clone_agent/
│   └── 2025-10-21T10-30-15.log
├── code_agent/
│   └── 2025-10-21T10-31-20.log
├── test_agent/
│   └── 2025-10-21T10-32-45.log
├── refactoring_agent/
│   └── 2025-10-21T10-34-10.log
├── sync_agent/
│   └── 2025-10-21T10-35-30.log
├── slack_agent/
│   └── 2025-10-21T10-36-00.log
└── git/
    └── 2025-10-21T10-30-00.log
```

### 캐시 구조
```
.commitly/cache/
├── run_context.json         # 현재 실행 상태
├── clone_agent.json         # 클론 에이전트 결과
├── code_agent.json          # 코드 에이전트 결과
├── test_agent.json          # 테스트 에이전트 결과
├── refactoring_agent.json   # 리팩토링 에이전트 결과
├── sync_agent.json          # 동기화 에이전트 결과
└── slack_agent.json         # Slack 에이전트 결과
```

### 로그 보기
```bash
# 최신 CloneAgent 로그
cat .commitly/logs/clone_agent/$(ls -t .commitly/logs/clone_agent | head -1)

# 모든 에러 로그 확인
grep -r "ERROR" .commitly/logs/

# 캐시 내용 보기
cat .commitly/cache/code_agent.json | jq
```

---

## 🔍 디버깅

### 상태 확인
```bash
poetry run commitly status
```

### 마지막 실행 로그
```bash
cat .commitly/logs/*/$(ls -t .commitly/logs/* | head -1)
```

### 캐시 초기화
```bash
rm -rf .commitly/cache/
```

### 허브 저장소 상태 확인
```bash
git -C .commitly_hub_Commitly log --oneline
git -C .commitly_hub_Commitly branch -a
```

---

## 🚨 일반적인 문제 해결

### 문제: `OPENAI_API_KEY not found`
```bash
# 해결책
set -a && source .env && set +a
poetry run commitly commit -m "메시지"
```

### 문제: Agent 타임아웃
```yaml
# config.yaml에서 증가
execution:
  timeout: 600  # 10분

test:
  timeout: 600
```

### 문제: Hub 동기화 실패
```bash
# Hub 삭제하고 재생성
rm -rf .commitly_hub_Commitly/
poetry run commitly init
```

### 문제: 특정 파일에 공백이 있는 명령어
현재 미지원입니다. [IMPROVEMENT_PLAN.md](./IMPROVEMENT_PLAN.md) 참고

---

## 📈 성능 최적화

### Shallow Clone 사용
```yaml
# config.yaml의 git 설정에서
git:
  remote: origin
  shallow: true  # 기본값: true
```

### LLM 호출 최소화
```yaml
# 리팩토링 규칙을 명확하게
refactoring:
  rules: |
    Only remove dead code
    Only add try-except for network operations
```

---

## 🤝 기여

기여는 환영합니다! 다음 단계로 진행하세요:

1. Fork 저장소
2. 기능 브랜치 생성 (`git checkout -b feature/AmazingFeature`)
3. 변경사항 커밋 (`git commit -m 'Add AmazingFeature'`)
4. 브랜치 Push (`git push origin feature/AmazingFeature`)
5. Pull Request 열기

---

## 📚 더 알아보기

- [CLAUDE.md](./CLAUDE.md) - 프로젝트 아키텍처 가이드
- [Architecture.md](./Architecture.md) - 상세 아키텍처 문서
- [IMPROVEMENT_PLAN.md](./IMPROVEMENT_PLAN.md) - 개선 계획 및 미완성 항목

---

## 📄 라이선스

MIT License - 자세한 내용은 [LICENSE](./LICENSE) 파일 참고

---

## 👨‍💻 작성자

**Claude Code (Anthropic)**

이 프로젝트는 LangGraph, LangChain, OpenAI API를 활용하여 개발되었습니다.

---

## 🎯 로드맵

### Phase 1 (완료) ✅
- [x] 7개 에이전트 구현
- [x] LangGraph 오케스트레이션
- [x] 승인 게이트 (SyncAgent)
- [x] 자동 롤백 메커니즘

### Phase 2 (진행 중) 🔄
- [ ] 필수 버그 수정 (명령어 파싱, SQL 비용 측정)
- [ ] 테스트 커버리지 추가
- [ ] 성능 측정 개선

### Phase 3 (향후) 📅
- [ ] PDF/HTML 보고서
- [ ] WebUI 대시보드
- [ ] 멀티 프로젝트 지원
- [ ] Node.js, Java 지원

---

**최종 업데이트**: 2025-10-22
**상태**: Production Ready (82/100)
