"""
init 명령어 구현
"""

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

    # .gitignore 업데이트
    _update_gitignore(workspace_path)

    config_path = workspace_path / args.config
    env_path = workspace_path / ".env"

    missing_items: list[str] = []

    if config_path.exists():
        print(f"✓ 기존 설정 파일을 사용합니다: {config_path}")
    else:
        missing_items.append("config.yaml")
        print("⚠️ config.yaml 파일이 존재하지 않습니다. 프로젝트에 맞는 설정 파일을 준비해주세요.")

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
