# Sync Agent 작동 설계

## 1. 역할 개요
- Refactoring Agent가 완료한 `.commitly_hub_{프로젝트명}` 변경사항을 로컬 워킹 트리와 원격 저장소에 반영합니다.
- **⚠️ 파이프라인의 유일한 사용자 승인 지점**: Clone/Code/Test/Refactoring이 모두 성공한 후에만 실행됩니다.
- 사용자 승인 후 원격 저장소에 push하고 허브 브랜치를 정리합니다.

---

## 2. 에이전트 기능 명세
- **변경사항 요약**: 허브의 최종 상태를 분석하여 커밋 메시지, 변경 파일, 통계를 사용자에게 제시합니다.
- **사용자 승인 요청**: "원격 저장소(main)에 push할까요? (y/n)" 질문을 CLI에 표시합니다.
- **원격 push**: 승인 시 허브의 변경사항을 로컬에 반영하고 원격 저장소에 push합니다.
- **브랜치 정리**: Push 성공 시 허브의 모든 `commitly/*` 브랜치를 자동 삭제합니다.
- **결과 기록**: 동기화 결과를 `.commitly/cache/sync_agent.json`에 저장합니다.

---

## 3. 입력 값 정의

### 3.1 RunContext
- `workspace_path`: 로컬 리포지터리 루트.
- `hub_path`: `{프로젝트_부모}/.commitly_hub_{프로젝트명}` 절대 경로.
- `pipeline_id`: 현재 파이프라인 실행 고유 ID (UUID).
- `refactoring_agent_branch`: Refactoring Agent가 생성한 최종 브랜치명.
- `git_remote`: 원격 저장소 이름 (기본 `origin`).
- `current_branch`: 사용자가 작업 중인 로컬 브랜치명 (예: `main`).

### 3.2 이전 에이전트 결과
- `clone_agent.json`: 변경 파일 목록 (`changed_files`).
- `code_agent.json`: 코드 실행 결과, SQL 쿼리 정보.
- `test_agent.json`: SQL 최적화 결과.
- `refactoring_agent.json`: 리팩토링 결과.

---

## 4. 출력 값 정의

`.commitly/cache/sync_agent.json`:

```json
{
  "pipeline_id": "uuid-1234",
  "agent_name": "sync_agent",
  "agent_branch": null,
  "status": "success|failed",
  "started_at": "2025-10-21T10:35:00+09:00",
  "ended_at": "2025-10-21T10:36:00+09:00",
  "data": {
    "user_approved": true,
    "pushed": true,
    "commit_sha": "abc123def456",
    "commit_message": "[hotfix] API timeout 수정",
    "remote_branch": "main",
    "sync_time": "2025-10-21T10:36:00+09:00",
    "branches_deleted": [
      "commitly/clone/uuid-1234",
      "commitly/code/uuid-1234",
      "commitly/test/uuid-1234",
      "commitly/refactor/uuid-1234"
    ]
  }
}
```

---

## 5. 작동 플로우

1. **변경사항 요약 생성**
   - 허브의 최종 브랜치와 원격 브랜치 간 diff 계산
   - 변경 파일, 추가/삭제 라인 수, 커밋 메시지 수집
   - Code/Test/Refactoring 결과 통계 집계

2. **사용자 승인 요청**
   - CLI에 변경 요약 출력 (Architecture.md 9.3 참조)
   - "원격 저장소(main)에 push할까요? (y/n)" 질문 표시
   - 사용자 입력 대기

3. **승인 시 (y) 동작**
   - (1) 허브의 최종 변경사항을 로컬 워킹 트리에 적용
   - (2) 로컬에서 `git push origin {current_branch}` 실행
   - (3) Push된 커밋 SHA 수집 (`commit_sha`)
   - (4) 허브의 모든 `commitly/*` 브랜치 삭제
   - (5) 결과를 `sync_agent.json`에 저장 (`pushed: true`)
   - (6) Slack Agent로 제어 이동

4. **거부 시 (n) 동작**
   - (1) Push 없이 로그만 저장
   - (2) 허브 상태 유지 (사용자가 수동으로 push 가능)
   - (3) 결과를 `sync_agent.json`에 저장 (`pushed: false`)
   - (4) Slack Agent로 제어 이동 (push 생략 상태 전달)

---

## 6. 예외 및 오류 처리

- **Push 실패 (권한, 네트워크)**:
  - 재시도 옵션 제공 (최대 3회)
  - 재시도 실패 시 작업 중단 함수 호출
  - 수동 push 명령어 안내: `cd {workspace_path} && git push origin {current_branch}`

- **로컬 워킹 트리 변경 충돌**:
  - 허브 → 로컬 적용 중 충돌 발생 시 사용자에게 알림
  - 수동 병합 요청 후 파이프라인 중단

- **브랜치 정리 실패**:
  - 경고 로그 남기고 계속 진행 (치명적 오류 아님)

---

## 7. 로그 및 산출물

- **sync_agent.json**: 동기화 결과, push 여부, 커밋 SHA, 삭제된 브랜치 목록.
- **sync_agent 실행 로그**: `.commitly/logs/sync_agent/{timestamp}.log`
  - Git push 명령 실행 로그
  - 사용자 승인 입력
  - 브랜치 정리 로그

---

## SyncAgent 핵심 로직 요약

- **입력**:
  - `workspace_path`, `hub_path`, `pipeline_id`, `refactoring_agent_branch`, `git_remote`, `current_branch`
  - 이전 에이전트 결과 (`clone_agent.json`, `code_agent.json`, `test_agent.json`, `refactoring_agent.json`)

- **기능**:
  1. 변경사항 요약 생성 (diff, 통계)
  2. 사용자 승인 요청 (⚠️ 유일한 승인 지점)
  3. 승인 시: 로컬 반영 → 원격 push → 브랜치 정리
  4. 거부 시: 로그만 저장, 허브 유지
  5. Slack Agent로 제어 이동

- **출력**:
  - `sync_agent.json`: `user_approved`, `pushed`, `commit_sha`, `remote_branch`, `branches_deleted`
  - 실행 로그: `.commitly/logs/sync_agent/{timestamp}.log`

---

## 중요 사항

⚠️ **Sync Agent는 파이프라인의 유일한 사용자 승인 지점입니다.**
- Clone/Code/Test/Refactoring은 오류만 없으면 자동 진행
- Sync Agent에서만 사용자가 최종 결정 (원격 push 여부)
- 거부해도 파이프라인은 계속 진행 (Slack Agent로 이동)
