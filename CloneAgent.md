# Clone Agent 작동 설계

## 1. 역할 개요
- `commitly git commit -m "<msg>"` 명령이 실행된 직후 트리거되어 `.commitly/hub` 워킹 트리를 최신 원격 상태로 동기화한다.
- 로컬 커밋 내용을 허브에 안전하게 적용해 이후 에이전트(Code, Test, Refactoring, Sync)가 동일한 스냅샷을 기반으로 작업하도록 격리 실행 환경을 준비한다.

## 2. 에이전트 기능 명세
- **허브 경로 초기화**: `.commitly/hub/<repo>/<branch>` 디렉터리 존재 여부 확인, 최초 실행 시 원격 저장소를 shallow clone한다.
- **원격 최신 이력 동기화**: 원격 `origin/<branch>`의 최신 커밋을 fetch 후 허브 워킹 트리를 fast-forward한다.
- **로컬 커밋 스냅샷 수집**: 사용자가 방금 만든 커밋(들)의 SHA, 커밋 메시지, 변경 파일 목록, patch 를 RunContext에서 추출한다.
- **허브 패치 적용**: 로컬 커밋과 허브 HEAD 사이 diff 를 계산하고 순차적으로 `git apply`(또는 파일 복사)로 허브 워킹 트리에 반영한다.
- **충돌 검출 및 복구**: 패치 적용 중 reject, 삭제된 파일 등 충돌이 감지되면 허브 변경을 롤백하고 Code Agent 호출을 중단한다.
- **메타데이터 기록**: 허브 HEAD, 적용된 커밋 SHA, 변경 파일, 경고 메시지를 JSON으로 저장해 이후 단계가 참고하도록 한다.

## 3. 입력 값 정의
### 3.1 RunContext
- `workspace_path`: 사용자가 commit 한 로컬 리포지터리 루트 경로.
- `hub_path`: `.commitly/hub/<repo>/<branch>` 절대 경로. 없으면 생성.
- `git_remote`: 동기화 대상 원격 저장소 이름과 URL (`origin` 기본).
- `current_branch`: 사용자가 작업 중인 브랜치명.
- `latest_local_commits`: 직전 실행 이후 새로 생성된 커밋 목록. 각 항목은 `{sha, message, author, timestamp}` 구조.
- `diff_provider`: 로컬 vs 허브 간 변경 사항을 patch 형식으로 반환하는 유틸리티 핸들.

### 3.2 Hub Snapshot / Diff
- `hub_head_sha`: 허브 워킹 트리의 현재 HEAD.
- `remote_head_sha`: `origin/<branch>` 최신 커밋의 SHA.
- `pending_patches`: 로컬 커밋을 허브에 반영하기 위해 적용해야 할 patch 파일 리스트(적용 순서 포함).
- `tracked_files`: 허브가 관리 중인 파일 목록 및 마지막 수정 시각.

### 3.3 규칙/가이드 입력
- `config/clone_agent.yaml` (예정): 허용 파일 확장자, 제외 디렉터리, 최대 patch 크기 등 정책.
- `.commitly/hub/.gitmodules` (선택): 서브모듈 동기화가 필요한 경우 명세.
- 글로벌 Git 설정(`~/.gitconfig`): 사용자 인증/프록시 정보.

## 4. 출력 값 정의
- `.commitly/cache/clone_agent.json`: `status`, `hub_head_sha`, `applied_commits`, `changed_files`, `warnings`, `started_at`, `ended_at`.
- `.commitly/logs/clone_agent/<timestamp>.log`: fetch/apply 명령 실행 로그, 경고, 오류 메시지.
- (옵션) `.commitly/hub_snapshot/<timestamp>.json`: 허브 상태 스냅샷. 재실행 시 비교 기준으로 사용.

## 5. 작동 플로우
1. RunContext 로드: 작업 경로, 브랜치, 사용자 커밋 정보를 읽는다.
2. 허브 디렉터리 확인: 존재하지 않으면 `git clone`으로 신규 생성, 있으면 `git remote update`.
3. 원격 최신 상태 맞춤: 허브에서 `git fetch --all` 후 `git reset --hard origin/<branch>`로 정렬.
4. 로컬 커밋 diff 생성: `git diff <remote_head> <local_head>` 결과를 patch 리스트로 정리.
5. 허브에 patch 적용: 파일 추가/수정/삭제를 허브 워킹 트리에 반영하고 각 단계 상태를 기록.
6. 무결성 검증: `git status --short`로 기대한 변경만 남았는지 확인, 변칙이 있으면 롤백.
7. 결과 저장 및 보고: JSON/로그 파일로 상태를 남기고 Code Agent 실행을 허용한다.

## 6. 예외 및 오류 처리
- **원격 fetch 실패**: 네트워크 오류 시 재시도(기본 3회) 후 실패 상태 기록, 사용자에게 즉시 알림.
- **충돌/패치 실패**: 특정 파일 patch 적용이 거부되면 해당 파일 경로와 원인 로그를 저장하고 Code Agent 호출을 차단한다.
- **허브 권한 문제**: 쓰기 권한이 없거나 디스크 용량 부족 시 허브 경로를 초기화하지 않고 실패 처리.
- **서브모듈 누락**: `.gitmodules` 있는 경우 초기화 실패 시 경고를 남기고 계속 진행(필요 시 사용자 개입 요청).

## 7. 로그 및 산출물
- `clone_agent.json`: 이후 에이전트 의사결정에 필요한 허브 동기화 결과.
- `clone_agent` 실행 로그: 명령별 stdout/stderr, 재시도 횟수, 경고 목록.
- Git 명령 실행 기록: `.commitly/logs/git/<timestamp>.log`에 공통 Git 호출 로그를 남겨 감사 추적성을 확보한다.

## CloneAgent 핵심 로직 요약
- 입력
  - `workspace_path`, `hub_path`, `git_remote`, `current_branch`, `latest_local_commits`, `diff_provider`.
    - `workspace_path`: 사용자가 commit 한 로컬 리포지터리 루트 경로.
    - `hub_path`: `.commitly/hub/<repo>/<branch>` 절대 경로. 없으면 생성.
    - `git_remote`: 동기화 대상 원격 저장소 이름과 URL (`origin` 기본).
    - `current_branch`: 사용자가 작업 중인 브랜치명.
    - `latest_local_commits`: 직전 실행 이후 새로 생성된 커밋 목록. 각 항목은 `{sha, message, author, timestamp}` 구조.
    - `diff_provider`: 로컬 vs 허브 간 변경 사항을 patch 형식으로 반환하는 유틸리티 핸들.
- 기능
  1. 허브 경로 준비 → 없으면 shallow clone, 있으면 최신 원격 상태로 fast-forward.
  2. 로컬 최신 커밋 diff 추출 → patch 리스트 생성.
  3. patch 순차 적용 → 실패 시 롤백 후 오류 리포트.
  4. `git status`로 무결성 검증 → 이상 없으면 JSON/로그 기록.
- 출력
  - 허브 HEAD, 적용된 커밋, 변경 파일, 경고/오류가 담긴 `clone_agent.json`.
  - 실행 로그(`clone_agent/<timestamp>.log`)와 필요 시 허브 스냅샷.
