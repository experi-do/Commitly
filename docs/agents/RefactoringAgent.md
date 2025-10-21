# Refactoring Agent 작동 설계

## 역할 개요
- Test Agent가 완료한 `.commitly_hub_{프로젝트명}` 코드를 기반으로 리팩토링을 수행합니다.
- 허브의 `commitly/refactor/{pipeline_id}` 브랜치를 생성하여 작업을 격리합니다.
- **리팩토링은 자동 적용**: 테스트 통과하면 사용자 승인 없이 자동으로 Sync Agent 진행.

---

### **2. Refactoring Agent: 코드 품질 개선**
**목표:** 커밋된 파일의 코드를 분석하여 중복 제거, 예외 처리 추가 등 자동으로 리팩토링을 수행합니다.
**2.1. 입력 데이터 형식**
- **`changed_files` (JSON Array):** Clone Agent가 생성한 변경 파일의 절대 경로 목록 (허브 기준).
- `clone_agent.json`의 `data.changed_files`에서 가져옴.
```json
[
  "/workspace/my_project/.commitly_hub_Commitly/app/service.py",
  "/workspace/my_project/.commitly_hub_Commitly/app/utils.py"
]
```
**2.2. 동작 순서 및 구현 지침**
1.  **브랜치 생성**
    - 허브에서 `commitly/refactor/{pipeline_id}` 브랜치를 생성합니다 (부모: Test Agent 브랜치).
2.  **파일 순회 (Iterate Files)**
    - `changed_files`의 각 파일 경로에 대해 아래 3~4단계를 순차적으로 실행합니다.
3.  **리팩토링 항목 식별 및 수정**
    - **(a) 중복 코드 제거 (LLM 사용):**
        - **구현:** LLM에게 파일 내용과 리팩토링 규칙을 전달하여 중복 코드를 식별하고 공통 함수로 추출.
    - **(b) 예외 처리 추가 (LLM 사용):**
        - **구현:** LLM에게 `try...except` 블록이 필요한 위험 코드(I/O, 네트워크, DB 호출)를 식별하도록 요청하고 예외 처리 추가.
    - **(c) 기타 리팩토링 (using `ruff`):**
        - **구현:** `ruff --fix {file_path}` 명령어를 실행하여 사용하지 않는 import 제거, 코드 포맷팅 등 자동 수정.
4.  **변경 사항 검증 (Verify Changes)**
    - `config.yaml`에 명시된 `test_command`를 실행합니다.
    - **테스트 실패 시:**
        - 작업 중단 함수 호출 (롤백 & 파이프라인 종료)
    - **테스트 성공 시:**
        - 변경된 코드를 유지하고 다음 파일로 넘어갑니다.
5.  **변경사항 커밋**
    - 모든 리팩토링이 완료되면 `git commit -m "Refactoring Agent: 코드 품질 개선"`으로 변경사항을 커밋합니다.
6.  **자동 진행**
    - `changed_files`의 모든 파일에 대한 작업이 성공적으로 완료되면, **자동으로 Sync Agent로 제어를 넘깁니다.**
    - 사용자 승인 없이 자동 진행됩니다.
