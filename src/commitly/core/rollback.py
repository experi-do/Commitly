"""
롤백 및 작업 중단 함수

에이전트 실패 시 허브 상태를 롤백하고 파이프라인을 종료합니다.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from commitly.core.context import RunContext
from commitly.core.git_manager import GitManager
from commitly.core.logger import CommitlyLogger, get_logger


def get_last_success_branch(run_context: RunContext, failed_agent: str) -> str:
    """
    마지막으로 성공한 에이전트의 브랜치 반환

    Args:
        run_context: 실행 컨텍스트
        failed_agent: 실패한 에이전트 이름

    Returns:
        마지막 성공 브랜치명
    """
    # 에이전트 순서
    agent_order = [
        ("clone_agent", run_context.get("clone_agent_branch")),
        ("code_agent", run_context.get("code_agent_branch")),
        ("test_agent", run_context.get("test_agent_branch")),
        ("refactoring_agent", run_context.get("refactoring_agent_branch")),
    ]

    # 실패한 에이전트 이전까지의 브랜치 중 마지막 것 반환
    last_branch = None
    for agent_name, branch in agent_order:
        if agent_name == failed_agent:
            break
        if branch:
            last_branch = branch

    return last_branch or run_context["current_branch"]


def delete_failed_branches(
    run_context: RunContext,
    failed_agent: str,
    git_manager: GitManager,
) -> None:
    """
    실패한 에이전트 이후 생성된 브랜치 삭제

    Args:
        run_context: 실행 컨텍스트
        failed_agent: 실패한 에이전트 이름
        git_manager: Git 관리자 인스턴스
    """
    agent_order = [
        "clone_agent",
        "code_agent",
        "test_agent",
        "refactoring_agent",
    ]

    # 실패한 에이전트 포함 이후의 브랜치 삭제
    delete_started = False
    for agent_name in agent_order:
        if agent_name == failed_agent:
            delete_started = True

        if delete_started:
            branch_key = f"{agent_name}_branch"
            branch = run_context.get(branch_key)
            if branch:
                git_manager.delete_branch(branch, force=True)


def save_error_logs(
    run_context: RunContext,
    failed_agent: str,
    error_message: str,
    stack_trace: Optional[str] = None,
) -> None:
    """
    에러 로그를 허브와 로컬 양쪽에 저장

    Args:
        run_context: 실행 컨텍스트
        failed_agent: 실패한 에이전트 이름
        error_message: 에러 메시지
    """
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

    # 에러 로그 데이터
    error_data = {
        "pipeline_id": run_context["pipeline_id"],
        "failed_agent": failed_agent,
        "error_message": error_message,
        "timestamp": timestamp,
        "hub_branch": run_context.get(f"{failed_agent}_branch"),
        "rollback_branch": get_last_success_branch(run_context, failed_agent),
    }

    if stack_trace:
        error_data["stack_trace"] = stack_trace

    # 허브 로그 저장
    hub_log_dir = Path(run_context["hub_path"]) / "logs" / failed_agent
    hub_log_dir.mkdir(parents=True, exist_ok=True)
    hub_log_file = hub_log_dir / f"error_{timestamp}.log"

    with open(hub_log_file, "w", encoding="utf-8") as f:
        json.dump(error_data, f, indent=2, ensure_ascii=False)

    # 로컬 로그 저장
    local_log_dir = Path(run_context["workspace_path"]) / ".commitly" / "logs" / failed_agent
    local_log_dir.mkdir(parents=True, exist_ok=True)
    local_log_file = local_log_dir / f"error_{timestamp}.log"

    with open(local_log_file, "w", encoding="utf-8") as f:
        json.dump(error_data, f, indent=2, ensure_ascii=False)


def rollback_and_cleanup(
    run_context: RunContext,
    failed_agent: str,
    error_message: str,
    stack_trace: Optional[str] = None,
    cleanup_hub: bool = False,
) -> None:
    """
    작업 중단 및 환경 정리

    Architecture.md 7.1 작업 중단 함수 참조

    Args:
        run_context: 실행 컨텍스트
        failed_agent: 실패한 에이전트 이름
        error_message: 에러 메시지
        cleanup_hub: 허브 리포지터리 삭제 여부
    """
    logger = get_logger("rollback", Path(run_context["workspace_path"]))

    logger.info(f"작업 중단 함수 호출: {failed_agent} 실패")
    logger.info(f"에러: {error_message}")

    try:
        # 1. 마지막 성공 브랜치 식별
        last_success_branch = get_last_success_branch(run_context, failed_agent)
        logger.info(f"마지막 성공 브랜치: {last_success_branch}")

        # 2. 허브를 마지막 성공 브랜치로 복원
        hub_path = Path(run_context["hub_path"])
        if hub_path.exists():
            git_manager = GitManager(hub_path, logger)
            try:
                git_manager.checkout(last_success_branch)
            except Exception as checkout_error:
                logger.warning(f"브랜치 체크아웃에 실패했습니다: {checkout_error}")
            git_manager.reset_hard(last_success_branch)
            logger.info(f"허브 복원 완료: {last_success_branch}")

            # 3. 실패 이후 생성된 브랜치 삭제
            delete_failed_branches(run_context, failed_agent, git_manager)
            logger.info("실패 브랜치 삭제 완료")

        # 4. 에러 로그 저장
        save_error_logs(run_context, failed_agent, error_message, stack_trace)
        logger.info("에러 로그 저장 완료")

        # 5. 허브 리포지토리 삭제 (선택적)
        if cleanup_hub and hub_path.exists():
            shutil.rmtree(hub_path)
            logger.info("허브 리포지터리 삭제 완료")

        # 6. RunContext 상태 업데이트
        run_context["agent_status"][failed_agent] = "failed"
        run_context["error_log"] = error_message

        # RunContext를 파일로 저장
        context_file = (
            Path(run_context["workspace_path"]) / ".commitly" / "cache" / "run_context.json"
        )
        context_file.parent.mkdir(parents=True, exist_ok=True)

        # datetime 객체를 문자열로 변환
        context_to_save = run_context.copy()
        if "started_at" in context_to_save and isinstance(context_to_save["started_at"], datetime):
            context_to_save["started_at"] = context_to_save["started_at"].isoformat()

        with open(context_file, "w", encoding="utf-8") as f:
            json.dump(context_to_save, f, indent=2, ensure_ascii=False, default=str)

        logger.info("RunContext 저장 완료")

    except Exception as e:
        logger.error(f"롤백 중 오류 발생: {e}")
        raise

    finally:
        # 7. 사용자에게 알림
        notify_user_failure(failed_agent, error_message)


def notify_user_failure(failed_agent: str, error_message: str) -> None:
    """
    사용자에게 실패 알림

    Args:
        failed_agent: 실패한 에이전트 이름
        error_message: 에러 메시지
    """
    print("\n" + "=" * 80)
    print(f"❌ 파이프라인 실패: {failed_agent}")
    print("=" * 80)
    print(f"\n에러:\n{error_message}\n")
    print("상세한 로그는 .commitly/logs/{agent_name}/ 디렉토리를 확인하세요.")
    print("\n문제를 수정한 후 다시 커밋해주세요.")
    print("=" * 80 + "\n")
