# Commitly MVP 아키텍처 설계

## 1. 시스템 개요

Commitly는 Git 커밋 후 자동화된 검증, 테스트, 리팩토링, 동기화 파이프라인을 제공하는 로컬 멀티 에이전트 시스템입니다. LangGraph를 기반으로 한 DAG(Directed Acyclic Graph) 구조로 에이전트를 오케스트레이션하며, 모든 작업은 격리된 허브 환경에서 수행됩니다.

### 1.1 핵심 설계 원칙
- **격리된 실행 환경**: 모든 에이전트는 허브 복제본에서 작업하며 로컬 워킹 트리는 Sync 승인 전까지 불변
- **상태 기반 오케스트레이션**: LangGraph State로 RunContext를 메모리 관리하고 각 단계마다 JSON 캐싱
- **실패 시 즉시 롤백**: 에이전트 실패 시 허브 상태를 롤백하고 파이프라인 중단
- **추적 가능성**: 모든 에이전트 실행 로그와 결과를 타임스탬프 기반으로 보존

---

## 2. 디렉토리 구조

### 2.1 프로젝트 및 허브 경로

```
/workspace/my_project/
├── Commitly/                          # 사용자 프로젝트 (로컬 워킹 트리)
│   ├── .git/
│   ├── .commitly/                     # Commitly 메타데이터 (로컬)
│   │   ├── config.yaml                # 전역 설정
│   │   ├── cache/                     # 에이전트 결과 캐시
│   │   │   ├── run_context.json      # 현재 실행 컨텍스트
│   │   │   ├── clone_agent.json
│   │   │   ├── code_agent.json
│   │   │   ├── test_agent.json
│   │   │   ├── refactoring_agent.json
│   │   │   └── sync_agent.json
│   │   ├── logs/                      # 로컬 실행 로그
│   │   │   ├── clone_agent/
│   │   │   │   └── 2025-10-21T10-30-15.log
│   │   │   ├── code_agent/
│   │   │   ├── test_agent/
│   │   │   ├── refactoring_agent/
│   │   │   ├── sync_agent/
│   │   │   ├── slack_agent/
│   │   │   └── git/                   # Git 명령 실행 로그
│   │   └── report/                    # 사용자 명령으로 생성된 보고서
│   │       └── 2025-10-21-hotfix-api-timeout.md
│   ├── src/
│   ├── main.py
│   └── .env
│
└── .commitly_hub_Commitly/            # 허브 복제본 (격리된 작업 환경)
    ├── .git/                          # 원격 저장소 클론
    ├── logs/                          # 허브 기준 로그
    │   ├── clone_agent/
    │   ├── code_agent/
    │   ├── test_agent/
    │   ├── refactoring_agent/
    │   └── sync_agent/
    ├── report/                        # 허브 기준 리포트
    │   └── 2025-10-21-summary.json
    ├── src/
    ├── main.py
    └── .env                           # 로컬에서 복사된 환경 변수
```

### 2.2 허브 경로 생성 규칙

- **허브 루트**: `{프로젝트_부모_디렉토리}/.commitly_hub_{프로젝트명}`
- **예시**:
  - 프로젝트: `/workspace/my_project/Commitly`
  - 허브: `/workspace/my_project/.commitly_hub_Commitly`
- **생성 시점**: `commitly init` 실행 시 또는 첫 커밋 시 자동 생성
- **정리**: Sync Agent 성공 후 agent 브랜치들 자동 삭제

---

## 3. LangGraph 오케스트레이션

### 3.1 Agent 실행 흐름

```
┌─────────────┐
│ Git Commit  │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph Pipeline                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │
│  │ CloneAgent   │───▶│  CodeAgent   │───▶│  TestAgent   │    │
│  │              │    │              │    │              │    │
│  │ 허브 동기화    │    │ 코드 실행     │    │ SQL 최적화   │    │
│  └──────────────┘    └──────┬───────┘    └──────┬───────┘    │
│                              │                   │             │
│                              │ (실패)            │ (성공)      │
│                              ▼                   ▼             │
│                         ┌─────────┐      ┌──────────────┐     │
│                         │ Rollback│      │Refactoring   │     │
│                         │  & Exit │      │   Agent      │     │
│                         └─────────┘      └──────┬───────┘     │
│                                                  │             │
│                                                  ▼             │
│                                          ┌──────────────┐     │
│                                          │  SyncAgent   │     │
│                                          │  (사용자승인)│     │
│                                          └──────┬───────┘     │
│                                                  │             │
│                                                  ▼             │
│                                          ┌──────────────┐     │
│                                          │ SlackAgent   │     │
│                                          └──────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│ ReportAgent  │ (별도 CLI 명령: commitly report)
└──────────────┘
```

### 3.2 LangGraph State 스키마

```python
from typing import TypedDict, List, Dict, Optional
from datetime import datetime

class RunContext(TypedDict):
    # 프로젝트 정보
    project_name: str
    workspace_path: str              # 로컬 프로젝트 루트
    hub_path: str                    # 허브 복제본 루트

    # Git 정보
    git_remote: str                  # 기본 'origin'
    current_branch: str              # 사용자 작업 브랜치
    latest_local_commits: List[Dict] # [{sha, message, author, timestamp}]

    # 에이전트 브랜치 (허브에서만 존재)
    clone_agent_branch: Optional[str]
    code_agent_branch: Optional[str]
    test_agent_branch: Optional[str]
    refactoring_agent_branch: Optional[str]

    # 실행 상태
    pipeline_id: str                 # UUID
    started_at: datetime
    current_agent: str
    agent_status: Dict[str, str]     # {agent_name: 'pending'|'running'|'success'|'failed'}

    # 변경 사항
    commit_file_list: List[str]      # 커밋된 파일 절대 경로
    has_query: bool                  # SQL 쿼리 포함 여부
    query_file_list: Optional[List[Dict]]  # SQL 정보 [{file_path, function_name, line_start, line_end, query}]

    # 환경 설정
    python_bin: str
    env_file: str
    execution_profile: Dict          # {command, timeout, max_memory}
    llm_client: Any

    # 에러 처리
    error_log: Optional[str]
    rollback_point: Optional[str]    # 롤백 기준 커밋 SHA
```

---

## 4. Agent별 브랜치 전략

### 4.1 브랜치 생성 규칙

각 에이전트는 **허브 리포지토리**에서 독립적인 브랜치를 생성하여 작업합니다.

| Agent | 브랜치명 | 부모 브랜치 | 생성 시점 |
|-------|---------|-----------|----------|
| **CloneAgent** | `commitly/clone/{pipeline_id}` | `origin/{current_branch}` | Clone Agent 시작 시 |
| **CodeAgent** | `commitly/code/{pipeline_id}` | `commitly/clone/{pipeline_id}` | Code Agent 시작 시 |
| **TestAgent** | `commitly/test/{pipeline_id}` | `commitly/code/{pipeline_id}` | Test Agent 시작 시 |
| **RefactoringAgent** | `commitly/refactor/{pipeline_id}` | `commitly/test/{pipeline_id}` | Refactoring Agent 시작 시 |

### 4.2 브랜치 생명주기

1. **생성**: 각 에이전트 시작 시 이전 에이전트 브랜치에서 파생
2. **작업**: 에이전트는 자신의 브랜치에서 변경사항 적용
3. **커밋**: 에이전트 성공 시 `git commit -m "{Agent명} 작업내용 요약"`
4. **정리**: Sync Agent가 원격 push 성공하면 **모든 commitly/* 브랜치 자동 삭제**

### 4.3 브랜치 정리 시점

- **Sync 성공 시**: 모든 `commitly/*` 브랜치 자동 삭제
- **실패/롤백 시**: 에러 발생 직전 브랜치는 보존, 이후 브랜치는 삭제
- **재실행 시**: 새로운 `pipeline_id`로 새 브랜치 세트 생성

---

## 5. commitFileList 저장 규칙

### 5.1 데이터 구조

```json
{
  "commit_file_list": [
    "/workspace/my_project/Commitly/app/service.py",
    "/workspace/my_project/Commitly/app/utils.py"
  ]
}
```

- **절대 경로**: 로컬 워킹 트리 기준 절대 경로 사용
- **저장 위치**:
  - LangGraph State: `RunContext.commit_file_list`
  - JSON 캐시: `.commitly/cache/run_context.json`
  - Clone Agent 결과: `.commitly/cache/clone_agent.json`

### 5.2 파일 목록 수집 시점

- **Clone Agent**: `git diff --name-only {remote_head}..{local_head}` 실행하여 변경 파일 추출
- **로컬 경로 → 허브 경로 변환**:
  ```python
  hub_file_path = file_path.replace(workspace_path, hub_path)
  ```

---

## 6. 데이터 흐름

### 6.1 Agent 간 데이터 전달

```
CloneAgent
    ├─ 출력: clone_agent.json
    │   └─ {status, hub_head_sha, applied_commits, changed_files, warnings}
    ▼
CodeAgent
    ├─ 입력: clone_agent.json, RunContext
    ├─ 출력: code_agent.json
    │   └─ {status, execution_result, static_check_result, user_approved}
    ▼
TestAgent
    ├─ 입력: code_agent.json, RunContext (hasQuery, queryFileList)
    ├─ 출력: test_agent.json
    │   └─ {status, optimized_queries, test_results, rollback_occurred}
    ▼
RefactoringAgent
    ├─ 입력: test_agent.json, RunContext (commitFileList)
    ├─ 출력: refactoring_agent.json
    │   └─ {status, refactored_files, improvements, test_passed}
    ▼
SyncAgent
    ├─ 입력: refactoring_agent.json, RunContext
    ├─ 출력: sync_agent.json
    │   └─ {status, pushed, commit_message, sync_time, user_approved}
    ▼
SlackAgent
    ├─ 입력: sync_agent.json + 모든 이전 에이전트 결과
    ├─ 출력: slack_agent.json
    │   └─ {status, matched_messages, sent_messages, channel_id}
```

### 6.2 RunContext 공유 방식

1. **LangGraph State (메모리)**: 파이프라인 실행 중 State 객체로 관리
2. **JSON 캐싱**: 각 에이전트 종료 시 `.commitly/cache/run_context.json` 업데이트
3. **복원 메커니즘**:
   - 파이프라인 재시작 시 캐시에서 RunContext 로드
   - 실패한 단계 이전까지의 상태 복원 가능

---

## 7. 에러 처리 및 롤백 전략

### 7.1 작업 중단 함수 (Rollback & Cleanup)

에이전트 실패 또는 사용자 거부 시 호출되는 중단 함수입니다.

#### 호출 조건
1. 에이전트 실행 중 오류 발생 (예외, 타임아웃, 검증 실패)
2. Code/Test/Refactoring Agent에서 사용자가 `n` 입력
3. Sync Agent 종료 (오류 또는 사용자 거부)

#### 실행 단계

```python
def rollback_and_cleanup(run_context: RunContext, failed_agent: str):
    """
    작업 중단 및 환경 정리
    """
    # 1. 마지막 성공 브랜치 식별
    last_success_branch = get_last_success_branch(run_context)

    # 2. 허브를 마지막 성공 브랜치로 복원
    hub_path = run_context['hub_path']
    subprocess.run(['git', 'checkout', last_success_branch], cwd=hub_path)

    # 3. 실패 이후 생성된 브랜치 삭제
    delete_failed_branches(run_context, failed_agent)

    # 4. 에러 로그 저장
    save_error_logs(run_context, failed_agent)
    #   - 허브: {hub_path}/logs/{agent_name}/error_{timestamp}.log
    #   - 로컬: {workspace_path}/.commitly/logs/{agent_name}/error_{timestamp}.log

    # 5. 허브 리포지토리 삭제 (선택적)
    # 재시도를 위해 보존할 수도 있음 - config 설정에 따라 결정
    if config.get('cleanup_hub_on_failure', False):
        shutil.rmtree(hub_path)

    # 6. RunContext 상태 업데이트
    run_context['agent_status'][failed_agent] = 'failed'
    run_context['pipeline_status'] = 'failed'
    save_run_context(run_context)

    # 7. 사용자에게 알림
    notify_user_failure(failed_agent, run_context['error_log'])
```

### 7.2 에러 로그 저장 경로

| 위치 | 경로 | 용도 |
|------|------|------|
| **허브 로그** | `{hub_path}/logs/{agent_name}/error_{timestamp}.log` | 허브 환경에서 발생한 에러 원본 |
| **로컬 로그** | `.commitly/logs/{agent_name}/error_{timestamp}.log` | 로컬 프로젝트에 복사된 에러 로그 (사용자 접근 용이) |

**로그 내용**:
```json
{
  "pipeline_id": "uuid-1234",
  "failed_agent": "code_agent",
  "error_type": "RuntimeError",
  "error_message": "ModuleNotFoundError: No module named 'requests'",
  "stack_trace": "...",
  "timestamp": "2025-10-21T10:45:30+09:00",
  "hub_branch": "commitly/code/uuid-1234",
  "rollback_branch": "commitly/clone/uuid-1234"
}
```

### 7.3 재시도 정책

- **자동 재시도 없음**: 에이전트 실패 시 즉시 중단 후 롤백
- **사용자 주도 재시도**:
  - 에러 로그 확인 후 문제 수정
  - 새로운 커밋 생성
  - `commitly git commit -m "fix: ..."` 재실행 → 새 파이프라인 시작

---

## 8. 로그 및 리포트 관리

### 8.1 로그 저장 규칙

#### 허브 로그 (Hub Logs)
- **경로**: `{hub_path}/logs/{agent_name}/{timestamp}.log`
- **내용**: 허브 환경에서 실행된 명령어, stdout/stderr, Git 조작 내역
- **보존 기간**: Sync 성공 시 삭제 또는 압축

#### 로컬 로그 (Local Logs)
- **경로**: `.commitly/logs/{agent_name}/{timestamp}.log`
- **내용**: 허브 로그의 복사본 + 사용자 상호작용 기록
- **보존 기간**: 30일 (설정 가능)

#### Git 명령 로그
- **경로**: `.commitly/logs/git/{timestamp}.log`
- **내용**: 모든 Git 명령어 실행 이력 (fetch, apply, commit, push 등)

### 8.2 리포트 생성

#### Report Agent (CLI 전용)

**실행 명령**:
```bash
commitly report --from 2025-10-14 --to 2025-10-21 --format markdown
```

**입력**:
- `.commitly/cache/sync_agent.json` (각 커밋별 결과)
- `.commitly/logs/slack_agent/*.json` (Slack 매칭 결과)
- 기간 필터, 포맷 옵션

**출력**:
- `.commitly/report/{yyyy-mm-dd}-{issue}-{description}.md`
- 허브 리포트는 생성하지 않음 (로컬에만 저장)

**보고서 구조**:
```markdown
# Commitly 활동 보고서
**기간**: 2025-10-14 ~ 2025-10-21

## 1. 커밋 요약
- 총 커밋: 15건
- 성공: 12건
- 실패: 3건

## 2. SQL 최적화
- 최적화된 쿼리: 8개
- 평균 성능 개선: 35%

## 3. 리팩토링
- 수정된 파일: 20개
- 중복 코드 제거: 12건
- 예외 처리 추가: 8건

## 4. Slack 피드백
- 매칭된 메시지: 5건
- 해결 완료 응답: 3건

## 5. 주요 이슈
- [hotfix] DB 연결 타임아웃 (2025-10-15)
- [feature] 사용자 인증 추가 (2025-10-18)
```

---

## 9. 사용자 승인 플로우

### 9.1 승인이 필요한 에이전트

| Agent | 승인 시점 | 질문 | 승인 시 동작 | 거부 시 동작 |
|-------|----------|------|------------|------------|
| **CodeAgent** | 정적/동적 검사 완료 후 | "코드 실행 결과를 확인했습니다. Test Agent를 진행할까요? (y/n)" | Test Agent 실행 | 롤백 & 파이프라인 종료 |
| **TestAgent** | SQL 최적화 완료 후 | "SQL 최적화가 완료되었습니다. Refactoring Agent를 진행할까요? (y/n)" | Refactoring Agent 실행 | 롤백 & 파이프라인 종료 |
| **RefactoringAgent** | 리팩토링 완료 후 | "리팩토링이 완료되었습니다. Sync Agent를 진행할까요? (y/n)" | Sync Agent 실행 | 롤백 & 파이프라인 종료 |
| **SyncAgent** | Push 준비 완료 후 | "원격 저장소(main)에 push할까요? (y/n)" | Push 실행 & Slack Agent 진행 | 로그 저장 & Slack Agent로 이동 (push 생략) |

### 9.2 CLI 출력 예시

```
[CodeAgent] ✓ 정적 검사 완료
[CodeAgent] ✓ python main.py 실행 성공
[CodeAgent]
결과 요약:
  - 린트 오류: 0건
  - 타입 오류: 0건
  - 실행 시간: 2.3초
  - 종료 코드: 0

코드 실행 결과를 확인했습니다. Test Agent를 진행할까요? (y/n): _
```

---

## 10. 환경 설정

### 10.1 전역 설정 파일

**경로**: `.commitly/config.yaml`

```yaml
# 프로젝트 설정
project_language: "python"
project_name: "Commitly"

# 실행 환경
execution:
  command: "python main.py"
  timeout: 300  # 초
  max_memory: 2048  # MB

# 데이터베이스
database:
  type: "postgresql"
  host: "localhost"
  port: 5432
  user: "dev_user"
  password: "${DB_PASSWORD}"  # .env에서 로드
  dbname: "test_db"

# 테스트
test_command: "pytest"

# Git 설정
git:
  remote: "origin"
  auto_cleanup_branches: true  # Sync 성공 시 agent 브랜치 자동 삭제

# LLM 설정
llm:
  provider: "openai"
  model: "gpt-4"
  temperature: 0.2
  max_tokens: 2048
  api_key: "${OPENAI_API_KEY}"  # .env에서 로드

# Slack 설정
slack:
  token: "${SLACK_TOKEN}"
  channel_id: "C1234567890"
  enable_notifications: true

# 로그 관리
logging:
  retention_days: 30
  max_log_size_mb: 5
  cleanup_hub_on_failure: false  # 실패 시 허브 보존 여부

# 리팩토링 규칙
refactoring:
  rules_file: "config/refactoring_rules.yaml"
  enable_duplicate_removal: true
  enable_exception_handling: true
  enable_ruff_fixes: true
```

### 10.2 환경 변수 (.env)

```bash
# API 키
OPENAI_API_KEY=sk-...
SLACK_TOKEN=xoxb-...

# 데이터베이스
DB_PASSWORD=secure_password

# 허브 설정
COMMITLY_HUB_ROOT=/workspace/my_project  # 허브 생성 위치 (기본: 프로젝트 부모 디렉토리)
```

---

## 11. 초기화 및 실행

### 11.1 프로젝트 초기화

```bash
cd /workspace/my_project/Commitly
commitly init
```

**실행 결과**:
1. `.commitly/` 디렉토리 생성
2. `config.yaml` 템플릿 생성
3. `.commitly/cache/`, `.commitly/logs/` 디렉토리 생성
4. 허브 경로 계산 및 출력: `.commitly_hub_Commitly`

### 11.2 커밋 및 파이프라인 실행

```bash
# 변경사항 커밋
git add .
commitly git commit -m "[hotfix] API timeout 수정"

# 파이프라인 자동 시작
# → CloneAgent → CodeAgent → TestAgent → RefactoringAgent → SyncAgent → SlackAgent
```

### 11.3 보고서 생성

```bash
# 일주일 치 보고서
commitly report --from 2025-10-14 --to 2025-10-21 --format markdown

# 특정 이슈 보고서
commitly report --issue "hotfix-api-timeout" --format json
```

---

## 12. 보안 및 제약사항

### 12.1 보안
- **로컬 전용**: 모든 데이터는 로컬 디스크에만 저장
- **민감 정보 보호**: `.env` 파일은 `.gitignore`에 포함, 허브로 복사 시 권한 확인
- **API 키 관리**: 향후 OS 키체인 연동 옵션 제공

### 12.2 제약사항
- **단일 프로젝트**: MVP는 한 번에 하나의 프로젝트만 지원
- **Python 전용**: 다른 언어는 추후 확장
- **Postgres 전용**: 다른 DB는 추후 확장
- **Git 의존**: Git 리포지토리가 아닌 프로젝트는 지원 불가

---

## 13. 확장 고려사항

### 13.1 Phase 2 로드맵
- 멀티 프로젝트 동시 실행 (허브 경로 충돌 해결)
- Node.js, Java 지원
- MySQL, MongoDB 지원
- VS Code Extension (GUI 기반 승인, 로그 스트리밍)

### 13.2 향후 개선 방향
- Agent별 실행 시간 최적화 (병렬 처리)
- 증분 분석 (변경된 파일만 검사)
- 사용자 피드백 기반 자동 승인 정책
- 지식 베이스 구축 (SQL 최적화 패턴 축적)

---

## 14. 참조 문서

- **PRD**: `PRD.md` - 제품 요구사항 및 목표
- **Agent 설계**:
  - `CloneAgent.md` - 허브 동기화 로직
  - `CodeAgent.md` - 코드 검증 및 실행
  - `TestAgent.md` - SQL 최적화
  - `RefactoringAgent.md` - 코드 품질 개선
  - `SyncAgent.md` - 원격 저장소 동기화
  - `SlackAgent.md` - 피드백 매칭 및 알림
  - `ReportAgent.md` - 보고서 생성
