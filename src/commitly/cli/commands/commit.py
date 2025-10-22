"""
commit 명령어 구현
"""

from pathlib import Path
from typing import Any

from commitly.core.git_manager import GitManager
from commitly.core.logger import CommitlyLogger
from commitly.pipeline.graph import CommitlyPipeline


def commit_command(args: Any) -> None:
    """
    Commitly 파이프라인 실행

    자동으로 git add/commit을 수행한 후 파이프라인 실행

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

    user_message = getattr(args, "message", None)

    if not user_message:
        print("❌ 커밋 메시지를 입력해주세요. (-m 옵션 사용)")
        return

    # 1단계: git add + git commit 자동 실행
    print("Git 변경사항 커밋 중...")
    try:
        logger = CommitlyLogger("commit", workspace_path, log_to_console=False)
        workspace_git = GitManager(workspace_path, logger)

        # git add .
        workspace_git.repo.git.add(A=True)
        print("✓ 변경 파일 추가 완료")

        # git commit
        commit_obj = workspace_git.repo.index.commit(user_message)
        print(f"✓ Git 커밋 완료: {commit_obj.hexsha[:8]}")
        print(f"  메시지: {user_message}")

    except Exception as e:
        print(f"❌ Git 커밋 실패: {e}")
        return

    # 2단계: Commitly 파이프라인 실행
    print("\nCommitly 파이프라인 시작...")
    print(f"워크스페이스: {workspace_path}")
    print(f"설정 파일: {config_path}")
    print()

    try:
        # 파이프라인 생성 및 실행
        pipeline = CommitlyPipeline(workspace_path, config_path, user_message=user_message)
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
                remote_branch = sync_data.get("remote_branch")
                if remote_branch:
                    print(f"  Remote Branch: {remote_branch}")

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
