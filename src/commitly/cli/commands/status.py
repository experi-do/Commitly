"""
status 명령어 구현
"""

import json
from pathlib import Path
from typing import Any


def status_command(args: Any) -> None:
    """
    Commitly 상태 확인

    Args:
        args: CLI 인자
    """
    workspace_path = Path.cwd()
    commitly_dir = workspace_path / ".commitly"

    print("Commitly 상태")
    print("=" * 60)

    # .commitly 디렉토리 확인
    if not commitly_dir.exists():
        print("\n❌ Commitly가 초기화되지 않았습니다.")
        print("commitly init 명령어로 프로젝트를 초기화하세요.")
        return

    print(f"\n✓ .commitly 디렉토리: {commitly_dir}")

    # 설정 파일 확인
    config_path = workspace_path / "config.yaml"
    if config_path.exists():
        print(f"✓ 설정 파일: {config_path}")
    else:
        print(f"✗ 설정 파일 없음: {config_path}")

    # .env 파일 확인
    env_path = workspace_path / ".env"
    if env_path.exists():
        print(f"✓ .env 파일: {env_path}")
    else:
        print(f"✗ .env 파일 없음: {env_path}")

    # 최근 파이프라인 실행 확인
    cache_dir = commitly_dir / "cache"

    if cache_dir.exists():
        print(f"\n최근 파이프라인 실행:")
        _show_recent_pipelines(cache_dir)
    else:
        print("\n실행 기록 없음")

    # Hub 상태 확인
    _show_hub_status(workspace_path)

    # 로그 디렉토리 크기
    logs_dir = commitly_dir / "logs"
    if logs_dir.exists():
        log_count = len(list(logs_dir.rglob("*.log")))
        print(f"\n로그 파일: {log_count}개")


def _show_recent_pipelines(cache_dir: Path) -> None:
    """
    최근 파이프라인 실행 표시

    Args:
        cache_dir: 캐시 디렉토리
    """
    # sync_agent.json 파일들 찾기
    sync_files = sorted(
        cache_dir.glob("sync_agent*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not sync_files:
        print("  실행 기록 없음")
        return

    # 최근 5개만 표시
    for i, sync_file in enumerate(sync_files[:5], 1):
        try:
            with open(sync_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            pipeline_id = data.get("pipeline_id", "N/A")
            status = data.get("status", "N/A")
            ended_at = data.get("ended_at", "N/A")

            sync_data = data.get("data", {})
            pushed = sync_data.get("pushed", False)
            commit_msg = sync_data.get("commit_message", "N/A")

            print(f"\n  {i}. Pipeline ID: {pipeline_id}")
            print(f"     상태: {status}")
            print(f"     Push: {'✓' if pushed else '✗'}")
            print(f"     커밋: {commit_msg[:50]}...")
            print(f"     일시: {ended_at}")

        except Exception as e:
            print(f"  {i}. 파일 읽기 실패: {sync_file.name} - {e}")


def _show_hub_status(workspace_path: Path) -> None:
    """
    Hub 상태 표시

    Args:
        workspace_path: 워크스페이스 경로
    """
    project_name = workspace_path.name
    hub_path = workspace_path.parent / f".commitly_hub_{project_name}"

    print(f"\nHub 상태:")

    if hub_path.exists():
        print(f"  ✓ Hub 경로: {hub_path}")

        # Hub의 브랜치 확인
        try:
            from git import Repo

            repo = Repo(hub_path)
            branches = [b.name for b in repo.branches]

            commitly_branches = [b for b in branches if b.startswith("commitly/")]

            if commitly_branches:
                print(f"  Commitly 브랜치: {len(commitly_branches)}개")
                for branch in commitly_branches[:5]:
                    print(f"    - {branch}")
            else:
                print(f"  Commitly 브랜치 없음")

        except Exception as e:
            print(f"  브랜치 조회 실패: {e}")
    else:
        print(f"  ✗ Hub 없음: {hub_path}")
