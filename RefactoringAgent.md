# Refactoring Agent 작동 설계

## 역할 개요
- Test Agent가 완료한 `.commitly_hub_{프로젝트명}` 코드를 기반으로 리팩토링을 수행합니다.
- 허브의 `commitly/refactor/{pipeline_id}` 브랜치를 생성하여 작업을 격리합니다.
- 리팩토링 완료 후 사용자 승인을 받아 Sync Agent로 제어를 넘깁니다.

---

### **2. Refactoring Agent: 코드 품질 개선**
**목표:** 커밋된 파일의 코드를 분석하여 중복 제거, 예외 처리 추가 등 자동으로 리팩토링을 수행합니다.
**2.1. 입력 데이터 형식**
- **`commitFileList` (JSON Array):** 커밋된 파일의 절대 경로 목록 (허브 기준).
```json
[
  "/workspace/my_project/.commitly_hub_Commitly/app/service.py",
  "/workspace/my_project/.commitly_hub_Commitly/app/utils.py"
]
```
**2.2. 동작 순서 및 구현 지침**
1.  **파일 순회 (Iterate Files)**
    - `commitFileList`의 각 파일 경로에 대해 아래 2~4단계를 순차적으로 실행합니다.
2.  **리팩토링 항목 식별 및 수정**
    - **(a) 중복 코드 제거:**
        - **구현:** Python의 `ast` 모듈을 사용하여 파일 내 모든 함수와 메서드를 AST(Abstract Syntax Tree)로 파싱합니다. 구조적으로 유사한 AST 노드를 찾아내어 중복을 식별하고, 가능한 경우 공통 함수로 추출하여 대체합니다. (복잡도가 높으므로, 초기에는 5줄 이상의 동일 코드 블록을 문자열 기반으로 찾는 것으로 간소화할 수 있음)
    - **(b) 예외 처리 추가:**
        - **구현:** `try...except` 블록으로 감싸여 있지 않은 I/O 호출(`open()`), 네트워크 요청(`requests.get()`), DB 호출 등을 식별합니다. 식별된 코드 블록을 `try...except Exception as e:`로 감싸고, 간단한 로깅(`print(f"An error occurred: {e}")`)을 추가합니다.
    - **(c) 기타 리팩토링 (using `ruff`):**
        - **구현:** `ruff --fix {file_path}` 명령어를 실행하여 사용하지 않는 import 제거, 코드 포맷팅 등 `ruff`가 제공하는 자동 수정 기능을 적용합니다.
3.  **변경 사항 검증 (Verify Changes)**
    - `config.yaml`에 명시된 `test_command`를 실행합니다.
    - **테스트 실패 시:**
        - 작업 중단 함수 호출
    - **테스트 성공 시:**
        - 변경된 코드를 유지하고 다음 파일로 넘어갑니다.
4.  **변경사항 커밋**
    - 모든 리팩토링이 완료되면 `git commit -m "Refactoring Agent: 코드 품질 개선"`으로 변경사항을 커밋합니다.
5.  **사용자 승인**
    - 사용자에게 "리팩토링이 완료되었습니다. Sync Agent를 진행할까요? (y/n)" 질문을 표시합니다.
    - `y`: Sync Agent로 제어를 넘깁니다.
    - `n`: 롤백 & 파이프라인 종료합니다.
6.  **에이전트 종료**
    - `commitFileList`의 모든 파일에 대한 작업이 완료되면, "모든 리팩토링 작업을 완료했습니다." 로그를 남기고 Sync Agent로 제어를 넘깁니다.
