# Test Agent 작동 설계

## 역할 개요
- Code Agent가 검증한 `.commitly_hub_{프로젝트명}` 코드를 기반으로 SQL 쿼리를 최적화합니다.
- 허브의 `commitly/test/{pipeline_id}` 브랜치를 생성하여 작업을 격리합니다.
- SQL 쿼리가 없으면 즉시 Refactoring Agent로 제어를 넘깁니다.

---

### **전역 설정 (Configuration)**
에이전트 실행에 필요한 설정은 프로젝트 루트의 `.commitly/config.yaml` 파일로 관리합니다.
```yaml
# .commitly/config.yaml
project_language: "python" # 현재 지원 언어: python
database:
  type: "postgresql" # DB 종류
  host: "localhost"
  port: 5432
  user: "username"
  password: "password"
  dbname: "test_db"
test_command: "pytest" # 프로젝트 테스트 실행 명령어
```
---
### **1. Test Agent: SQL 쿼리 최적화**
**목표:** 커밋된 파일 내의 비효율적인 SQL 쿼리를 자동으로 식별하고, 더 효율적인 쿼리로 대체하여 시스템 성능을 향상시킵니다.
**1.1. 입력 데이터 형식**
- **`hasQuery` (Boolean):** Git 커밋에 SQL 쿼리(.sql 파일 또는 코드 내 문자열)를 포함하는 파일이 있는지 여부.
- **`queryFileList` (JSON Array):** `hasQuery`가 `True`일 경우, 쿼리 위치 정보를 담은 객체 배열.
```json
[
  {
    "file_path": "/workspace/my_project/.commitly_hub_Commitly/app/repository.py",
    "function_name": "get_active_users",
    "line_start": 25,
    "line_end": 28,
    "query": "SELECT * FROM users WHERE status = 'active' AND last_login > '2024-01-01';"
  }
]
```
**1.2. 동작 순서 및 구현 지침**
1.  **에이전트 실행 조건 확인**
    - `hasQuery`가 `False`이면, "최적화할 SQL 쿼리가 없습니다." 로그를 남기고 즉시 `Refactoring Agent`로 제어를 넘깁니다.
2.  **쿼리 순회 및 최적화 (Iterate and Optimize)**
    - `queryFileList`의 각 쿼리 객체에 대해 아래 3~7단계를 순차적으로 실행합니다.
3.  **후보 쿼리 생성 (Generate Candidates)**
    - **(a) 스키마 정보 추출:** 최적화 대상 쿼리에 언급된 모든 테이블(`FROM`, `JOIN` 등)의 `CREATE TABLE` 구문을 DB에서 추출합니다.
    - **(b) LLM 호출:** 아래와 같은 프롬프트를 구성하여 LLM(ChatGPT, Gemini 등)을 호출하고, 3개의 후보 쿼리를 생성합니다.
        - **Prompt Template:**
          ```
          # CONTEXT
          You are a database performance expert. Your task is to rewrite the given SQL query to be more performant. The database is {database.type}.
          # SCHEMA
          Here are the schemas for the relevant tables:
          {schema_info}
          # ORIGINAL QUERY
          ```sql
          {original_query}
          ```
          # INSTRUCTION
          Based on the schema and the original query, generate 3 alternative, functionally identical, but potentially more performant SQL queries.
          - Do not suggest adding or dropping indexes.
          - Ensure the output columns and types are identical to the original query.
          - Return the queries as a JSON array of strings.
          ```
    - **(c) LLM 응답 파싱:** LLM으로부터 받은 JSON 응답을 파싱하여 3개의 후보 쿼리를 문자열 변수로 저장합니다.
4.  **성능 분석 (Performance Analysis)**
    - **(a) DB 연결:** `config.yaml`의 정보로 데이터베이스에 연결합니다. (e.g., `psycopg2` for Python/PostgreSQL)
    - **(b) 실행 계획 수집:** 원본 쿼리와 3개의 후보 쿼리 각각에 대해 `EXPLAIN (ANALYZE, COSTS, VERBOSE, BUFFERS)` 쿼리를 실행하고, 그 결과를 텍스트로 저장합니다.
    - **(c) 최적 쿼리 선정:** 각 실행 계획에서 `Total Cost` 또는 `Execution Time`을 파싱하여 비교합니다. 가장 낮은 비용/시간을 기록한 쿼리를 "최적 쿼리(best_query)"로 선정합니다.
5.  **코드 대체 (Replace Code)**
    - 원본 쿼리(`original_query`)와 최적 쿼리(`best_query`)가 다를 경우, `file_path`의 파일을 열어 `line_start`부터 `line_end`까지의 내용을 `best_query`로 대체합니다.
    - 이때, 원본 코드의 들여쓰기(indentation)를 유지해야 합니다.
6.  **변경 사항 검증 (Verify Changes)**
    - `config.yaml`에 명시된 `test_command` (e.g., `pytest`)를 셸 명령으로 실행합니다.
    - **테스트 실패 시:**
        - 작업 중단 함수 호출을 요청합니다.
    - **테스트 성공 시:**
        - 변경된 코드를 그대로 유지하고 다음 쿼리로 넘어갑니다.
7.  **변경사항 커밋**
    - 모든 쿼리 최적화가 완료되면 `git commit -m "Test Agent: SQL 최적화 완료"`로 변경사항을 커밋합니다.
8.  **에이전트 종료**
    - `queryFileList`의 모든 쿼리에 대한 작업이 성공적으로 완료되면, `Refactoring Agent`로 제어를 넘깁니다.
