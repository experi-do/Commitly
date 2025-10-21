# Commitly 테스트 가이드

이 문서는 Commitly를 설치한 뒤 주요 기능을 검증하는 방법을 정리한 간단한 체크리스트입니다. 로컬 환경에서 순차적으로 따라 하면서 파이프라인이 정상 동작하는지 확인하세요.

---

## 1. 환경 준비

- Poetry 또는 pip로 패키지를 설치합니다.
  ```bash
  poetry install  # 또는 pip install .
  ```
- 테스트용 레포지토리를 하나 준비하고 루트에서 명령을 실행합니다.
  ```bash
  cd /path/to/your/project
  ```

---

## 2. `commitly init` 확인

1. 초기화 명령 실행
   ```bash
   commitly init
   ```
2. 다음 항목을 확인합니다.
   - `.commitly/` 디렉터리 안에 `cache/`, `logs/`, `slack/`, `reports/`가 생성됐는가?
   - 지정한 `config.yaml`이 생성됐는가?
   - `.env`, `.gitignore`가 필요한 항목을 포함하는가?

---

## 3. `commitly git commit` 흐름 확인

1. 테스트용 변경을 만든 뒤 스테이징합니다.
   ```bash
   echo "# dummy" >> README.md
   git add README.md
   ```
2. 아래 명령으로 commit + 파이프라인을 실행합니다.
   ```bash
   commitly git commit -m "test: verify pipeline"
   ```
3. 정상이라면
   - `git commit`이 성공적으로 실행되고,
   - 파이프라인 로그가 출력되며,
   - `.commitly/logs/`와 `.commitly/cache/`에 에이전트별 파일이 생성됩니다.
4. 실패 시에는 출력된 로그를 확인하거나, `--config` 경로와 의존 도구(ruff, mypy 등)가 설치되어 있는지 점검합니다.

> 참고: Pure `commitly commit` 명령도 동일하게 동작해야 합니다. (단, `-m` 옵션을 주면 내부에서 `git commit`을 실행합니다.)

---

## 4. 보고서 및 상태 명령 확인

- 보고서 생성
  ```bash
  commitly report --from 2025-01-01 --to 2025-01-31
  ```
  - `.commitly/reports/commitly_report_*.md`가 생성되는지 확인합니다.

- 상태 출력
  ```bash
  commitly status
  ```
  - 최근 파이프라인, 허브 상태, 로그 파일 개수가 정상적으로 표시되는지 확인합니다.

---

## 5. 추가 점검 사항

- BaseAgent에서 `self.config` 주입을 보완하지 않았다면 일부 에이전트가 설정 접근 시 예외를 발생할 수 있습니다. 테스트 도중 오류가 나면 해당 부분을 먼저 해결하세요.
- SQL 최적화나 Slack 연동을 사용하려면 `.env`에 필요한 비밀 키를 채워 넣고, 의존 패키지와 서비스 접근 권한이 준비되어 있어야 합니다.
- 테스트 후 생성된 `.commitly_hub_*` 디렉터리와 `.commitly` 내부 캐시가 필요 없으면 정리합니다.

---

이 가이드를 기반으로 기능이 정상 동작하는지 확인하고, 문제가 있다면 로그 및 캐시 내용을 참고해 원인을 추적하세요.
