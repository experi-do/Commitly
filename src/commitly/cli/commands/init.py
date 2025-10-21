"""
init 명령어 구현
"""

import shutil
from pathlib import Path
from typing import Any


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

    # 설정 파일 템플릿 복사
    config_path = workspace_path / args.config

    if not config_path.exists():
        # 템플릿에서 복사
        template_path = Path(__file__).parent.parent.parent / "templates" / "config.yaml"

        if template_path.exists():
            shutil.copy(template_path, config_path)
            print(f"✓ 설정 파일 생성 완료: {config_path}")
        else:
            # 템플릿 없으면 기본 설정 생성
            _create_default_config(config_path)
            print(f"✓ 기본 설정 파일 생성 완료: {config_path}")
    else:
        print(f"설정 파일이 이미 존재합니다: {config_path}")

    # .env 파일 생성 (없으면)
    env_path = workspace_path / ".env"

    if not env_path.exists():
        _create_default_env(env_path)
        print(f"✓ .env 파일 생성 완료: {env_path}")
    else:
        print(f".env 파일이 이미 존재합니다: {env_path}")

    # .gitignore 업데이트
    _update_gitignore(workspace_path)

    print("\n✓ Commitly 초기화 완료!")
    print("\n다음 단계:")
    print("1. config.yaml 파일을 프로젝트에 맞게 수정하세요")
    print("2. .env 파일에 API 키를 입력하세요")
    print("3. commitly commit 명령어로 파이프라인을 실행하세요")


def _create_default_config(config_path: Path) -> None:
    """
    기본 설정 파일 생성

    Args:
        config_path: 설정 파일 경로
    """
    default_config = """# Commitly 설정 파일

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
  timeout: 300

# 테스트 프로필
test:
  command: pytest
  timeout: 300

# 데이터베이스 설정 (SQL 최적화용)
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

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(default_config)


def _create_default_env(env_path: Path) -> None:
    """
    기본 .env 파일 생성

    Args:
        env_path: .env 파일 경로
    """
    default_env = """# Commitly 환경 변수

# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key_here

# Database Configuration
DB_USER=postgres
DB_PASSWORD=your_db_password_here
DB_NAME=your_database_name

# Slack Configuration (optional)
SLACK_BOT_TOKEN=your_slack_bot_token_here
SLACK_CHANNEL_ID=your_slack_channel_id_here
"""

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(default_env)


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
