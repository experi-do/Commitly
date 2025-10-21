"""
commit 명령어 구현
"""

import subprocess
from pathlib import Path
from typing import Any

from commitly.pipeline.graph import CommitlyPipeline


def commit_command(args: Any) -> None:
    """
    Commitly 파이프라인 실행

    Args:
        args: CLI 인자
    """
    workspace_path = Path.cwd()
    config_path = workspace_path / args.config

    # 설정 파일 확인
    if not config_path.exists():
        print(f"❌ 설정 파일을 찾을 수 없습니다: {config_path}")
        print("commitly init 명령어로 프로젝트를 초기화하세요.")
        return

    # git commit 수행 (필요 시)
    commit_message = getattr(args, "message", None)
    if commit_message:
        print(f"git commit 실행 중: {commit_message}")
        try:
            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                check=True,
            )
            if result.stdout.strip():
                print(result.stdout.strip())
        except subprocess.CalledProcessError as error:
            print("❌ git commit 실행에 실패했습니다.")
            if error.stdout and error.stdout.strip():
                print(error.stdout.strip())
            if error.stderr and error.stderr.strip():
                print(error.stderr.strip())
            return

    print("Commitly 파이프라인 시작...")
    print(f"워크스페이스: {workspace_path}")
    print(f"설정 파일: {config_path}")
    print()

    try:
        # 파이프라인 생성 및 실행
        pipeline = CommitlyPipeline(workspace_path, config_path)
        final_state = pipeline.run()

        print("\n" + "=" * 60)
        print("✓ Commitly 파이프라인 완료!")
        print("=" * 60)

        # 결과 요약
        if "sync_output" in final_state:
            sync_data = final_state["sync_output"].get("data", {})
            if sync_data.get("pushed"):
                print("\n✓ 원격 저장소에 push되었습니다.")
                print(f"  Commit SHA: {sync_data.get('commit_sha', 'N/A')}")

        if "slack_output" in final_state:
            slack_data = final_state["slack_output"].get("data", {})
            matched_count = len(slack_data.get("matched_messages", []))
            if matched_count > 0:
                print(f"\n✓ Slack 피드백 {matched_count}개 매칭됨")

        if "report_output" in final_state:
            report_data = final_state["report_output"].get("data", {})
            report_path = report_data.get("report_path")
            if report_path:
                print(f"\n✓ 보고서 생성됨: {report_path}")

    except KeyboardInterrupt:
        print("\n\n파이프라인이 사용자에 의해 중단되었습니다.")

    except Exception as e:
        print(f"\n❌ 파이프라인 실행 중 오류 발생: {e}")
        print("\n로그를 확인하세요: .commitly/logs/")
