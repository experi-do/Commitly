# Code Agent 작동 설계

## 1. 역할 개요
- Clone Agent가 준비한 `.commitly_hub_{프로젝트명}` 스냅샷을 기반으로 변경 파일을 분석하고 프로젝트를 실행해 런타임 오류를 사전에 차단한다.
- 허브의 `commitly/code/{pipeline_id}` 브랜치를 생성하여 작업을 격리한다.
- 정상 동작이 확인되면 Test Agent에 제어를 넘기고, 실패 시 허브 변경을 유지한 채 사용자에게 오류 원인을 공유하고 플로우를 중단한다.

## 2. 에이전트 기능 명세
- **허브 상태 로드**: Clone Agent가 기록한 `clone_agent.json`을 읽어 허브 경로, 변경 파일, 커밋 메타데이터를 확보한다.
- **환경 검증 및 초기화**: `.env`, 가상환경, 필수 도구(Node, Python 등) 버전을 확인하고 부족하면 사용자에게 안내한다.
- **정적 분석**: Lint, 타입 체크, import 간 의존성 확인 등 빠르게 실패 가능한 검사를 우선 수행한다.
- **동적 실행**: MVP 기준으로 허브에서 `python main.py`를 실행해 런타임 예외를 확인한다(추후 프로젝트별 명령으로 확장 예정).
- **결과 요약**: 로그, stdout/stderr, 종료 코드, 감지된 스택트레이스를 구조화해 사용자와 Test Agent가 이해할 수 있도록 정리한다.
- **사용자 피드백 루프**: 오류가 발생한 경우 작업 중단 함수를 호출한다.

## 3. 입력 값 정의
### 3.1 RunContext
- `workspace_path`: 로컬 리포지터리 루트.
- `hub_path`: `{프로젝트_부모}/.commitly_hub_{프로젝트명}` 절대 경로.
- `pipeline_id`: 현재 파이프라인 실행 고유 ID (UUID).
- `clone_agent_branch`: Clone Agent가 생성한 브랜치명 (`commitly/clone/{pipeline_id}`).
- `python_bin`, `node_bin`, `npm_bin`: 실행에 사용할 바이너리 경로.
- `env_file`: `.env` 위치. 허브로 복사된 환경 변수를 참조한다.
- `execution_profile`: 프로젝트별 기본 실행 명령, 타임아웃, 허용 메모리 등 설정.
- `llm_client`: 오류 로그를 요약할 때 사용할 LLM 핸들.

### 3.2 Hub Snapshot / Diff
- `clone_agent.json`:
  - `applied_commits`: 허브에 적용된 커밋 SHA 리스트.
  - `changed_files`: 파일별 변경 유형(`added/modified/deleted`).
  - `hub_head_sha`: 허브 HEAD.
- `hub_diff_summary`: 허브와 원격 간 diff 통계(코드/문서/SQL 등 카테고리 분류).
- `run_artifacts/previous_code_agent.json`(선택): 직전 실행의 결과. 회귀 여부 판단에 사용.

### 3.3 규칙/가이드 입력
- `config/code_agent.yaml`: 실행 우선순위, 스킵할 검사, 타임아웃, 사용자 승인 필요 조건.

## 4. 작동 플로우
1. **컨텍스트 로딩**: RunContext, clone_agent 출력, 프로젝트 설정을 읽는다.
2. **환경 준비**: 허브 경로로 이동해 `.env`를 로드하고 의존 도구 버전을 확인한다.
3. **정적 검사 실행**: 린트/타입/포맷 검사를 순차적으로 실행하고 실패 시 즉시 보고한다.
4. **동적 실행**: 허브에서 `python main.py`를 실행해 런타임 예외를 감지한다(타임아웃 기본 5분).
5. **결과 해석**: stdout/stderr를 파싱해 오류 메시지를 구조화하고 필요 시 LLM에게 요약을 요청한다.
6. **사용자 상호작용**: 실패 시 작업 중단 함수를 호출하고 CLI에 로그 경로 및 요약을 출력한다.

## 5. 예외 및 오류 처리
- **환경 준비 실패**: 가상환경 누락, 패키지 설치 안 됨 등은 `blocked` 상태로 기록하고 사용자에게 패키지 설치 명령을 안내한다.
- **검사 타임아웃**: 각 검사에 기본 타임아웃을 적용하며 초과 시 강제 종료 후 실패로 표기한다.
- **예상치 못한 프로세스 종료**: 실행 명령이 비정상 종료되면 종료 코드와 시그널을 기록하고 재시도는 1회만 허용한다.
- **로그 파싱 실패**: 로그가 너무 크거나 비정형이면 원본 로그 경로만 공유하고 요약은 생략한다.
- **사용자 거부**: 사용자가 `n`을 선택하면 Test Agent 호출 없이 플로우를 중단


## CodeAgent 핵심 로직 요약
- **입력**: `hub_path`, `workspace_path`, `pipeline_id`, `clone_agent_branch`, `clone_agent.json`, `python_bin`, `env_file`, `execution_profile`(기본값 `python main.py`), `llm_client`
   - `workspace_path`: 로컬 리포지터리 루트.
   - `hub_path`: `{프로젝트_부모}/.commitly_hub_{프로젝트명}` 절대 경로.
   - `pipeline_id`: 현재 파이프라인 실행 고유 ID (UUID).
   - `clone_agent_branch`: Clone Agent가 생성한 브랜치명 (`commitly/clone/{pipeline_id}`).
   - `python_bin`, `node_bin`, `npm_bin`: 실행에 사용할 바이너리 경로.
   - `env_file`: `.env` 위치. 허브로 복사된 환경 변수를 참조한다.
   - `execution_profile`: 프로젝트별 기본 실행 명령, 타임아웃, 허용 메모리 등 설정.
   - `llm_client`: 오류 로그를 요약할 때 사용할 LLM 핸들

- **기능**: (1) 허브에서 `commitly/code/{pipeline_id}` 브랜치 생성 (부모: Clone Agent 브랜치) → (2) 허브 스냅샷과 환경 확인 → (3) 정적 검사 실행 → (4) `python main.py` 동적 실행 및 로그 요약 → (5) `git commit -m "Code Agent: 코드 검증 완료"`로 커밋 → (6) 사용자 승인 여부에 따라 Test Agent 진행 결정.
- **출력**: 실행 상태, 에이전트 브랜치명을 담은 `code_agent.json`, 상세 로그(`code_agent/<timestamp>.log`), 사용자용 요약 리포트.
