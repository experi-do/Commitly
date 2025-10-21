"""
init 명령어 구현
"""

from pathlib import Path
from typing import Any, Optional


def init_command(args: Any) -> None:
    """
    Commitly 프로젝트 초기화

    Args:
        args: CLI 인자
    """
    print("Commitly 프로젝트 초기화 중...")

    workspace_path = Path.cwd()

    # .commitly 디렉토리 생성
    commitly_dir = workspace_path / ".commitly"
    commitly_dir.mkdir(exist_ok=True)

    # 하위 디렉토리 생성
    (commitly_dir / "cache").mkdir(exist_ok=True)
    (commitly_dir / "logs").mkdir(exist_ok=True)
    (commitly_dir / "slack").mkdir(exist_ok=True)
    (commitly_dir / "reports").mkdir(exist_ok=True)

    print(f"✓ .commitly 디렉토리 생성 완료: {commitly_dir}")

    # .gitignore 업데이트
    _update_gitignore(workspace_path)

    config_path = workspace_path / args.config
    env_path = workspace_path / ".env"

    missing_items: list[str] = []

    if config_path.exists():
        print(f"✓ 기존 설정 파일을 사용합니다: {config_path}")
    else:
        command = _discover_main_command(workspace_path)
        if command:
            _write_config_with_command(config_path, command)
            print(f"✓ 실행 커맨드를 자동 설정하여 config.yaml을 생성했습니다: {command}")
        else:
            missing_items.append("config.yaml")
            print(
                "⚠️ config.yaml 파일이 존재하지 않으며, 실행할 main.py 파일을 찾지 못했습니다."
                " 프로젝트에 맞는 설정 파일을 직접 준비해주세요."
            )

    if env_path.exists():
        print(f"✓ 기존 .env 파일을 사용합니다: {env_path}")
    else:
        missing_items.append(".env")
        print("⚠️ .env 파일이 존재하지 않습니다. 필요한 환경 변수를 포함한 .env 파일을 준비해주세요.")

    if missing_items:
        print(
            "\n⚠️ 위 파일을 프로젝트 루트에 준비한 뒤 다시 'commitly init'을 실행하거나,"
            " 수동으로 설정을 마친 후 커맨드를 사용해주세요."
        )
        return

    print("\n✓ Commitly 초기화가 완료되었습니다!")
    print("\n다음 단계:")
    print("1. config.yaml 내용을 확인하고 필요한 값이 정확한지 검증하세요")
    print("2. .env 파일에 필요한 API 키와 환경 변수가 설정되어 있는지 확인하세요")
    print("3. commitly commit 명령어로 파이프라인을 실행하세요")


def _update_gitignore(workspace_path: Path) -> None:
    """
    .gitignore에 Commitly 관련 항목 추가

    Args:
        workspace_path: 워크스페이스 경로
    """
    gitignore_path = workspace_path / ".gitignore"

    commitly_entries = [
        "",
        "# Commitly",
        ".commitly/cache/",
        ".commitly/logs/",
        ".commitly_hub_*/",
        ".env",
    ]

    # 기존 .gitignore 읽기
    existing_lines = []
    if gitignore_path.exists():
        with open(gitignore_path, "r", encoding="utf-8") as f:
            existing_lines = f.read().splitlines()

    # Commitly 항목이 없으면 추가
    if "# Commitly" not in existing_lines:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write("\n".join(commitly_entries) + "\n")
        print(f"✓ .gitignore 업데이트 완료")
    else:
        print(".gitignore에 Commitly 항목이 이미 존재합니다")


def _discover_main_command(workspace_path: Path) -> Optional[str]:
    """
    프로젝트 내 main.py 위치를 기반으로 실행 커맨드를 추론합니다.

    Args:
        workspace_path: 워크스페이스 경로
    """
    candidates: list[Path] = []
    for main_path in workspace_path.rglob("main.py"):
        if any(part.startswith(".") for part in main_path.relative_to(workspace_path).parts[:-1]):
            continue
        if main_path.is_file():
            candidates.append(main_path)

    if not candidates:
        return None

    candidates.sort(key=lambda path: (len(path.relative_to(workspace_path).parts), str(path)))
    best = candidates[0]
    relative = best.relative_to(workspace_path)
    return f"python {relative.as_posix()}"


def _write_config_with_command(config_path: Path, command: str) -> None:
    """
    감지된 실행 커맨드를 사용해 config.yaml을 생성합니다.

    Args:
        config_path: 설정 파일 경로
        command: 실행 커맨드
    """
    default_config = f"""# Commitly 설정 파일

# Git 설정
git:
  remote: origin

# LLM 설정
llm:
  enabled: true
  provider: openai
  model: gpt-4o-mini
  api_key: ${{OPENAI_API_KEY}}

# 실행 프로필
execution:
  command: {command}
  timeout: 300

# 테스트 프로필
test:
  command: pytest
  timeout: 300

# 데이터베이스 설정 (SQL 최적화용)
database:
  host: localhost
  port: 5432
  user: ${{DB_USER}}
  password: ${{DB_PASSWORD}}
  dbname: ${{DB_NAME}}

# 리팩토링 규칙
refactoring:
  rules: |
    Remove duplicate code
    Add exception handling for risky operations (I/O, network, DB)

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
  filter:
    labels: []
    authors: []
  privacy:
    anonymize_user: false
    redact_patterns: []
"""

    config_path.write_text(default_config, encoding="utf-8")
