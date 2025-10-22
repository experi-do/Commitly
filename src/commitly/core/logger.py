"""
로깅 유틸리티

.commitly/logs/{agent_name}/{timestamp}.log 형식으로 로그를 저장합니다.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class CommitlyLogger:
    """
    Commitly 로거

    각 에이전트별로 독립적인 로그 파일을 생성하고 관리합니다.
    """

    def __init__(
        self,
        agent_name: str,
        workspace_path: Path,
        log_to_console: bool = True,
    ) -> None:
        """
        Args:
            agent_name: 에이전트 이름 (예: 'clone_agent')
            workspace_path: 프로젝트 워크스페이스 경로
            log_to_console: 콘솔에도 로그 출력 여부
        """
        self.agent_name = agent_name
        self.workspace_path = workspace_path
        self.log_to_console = log_to_console

        # 로그 디렉토리 경로
        self.log_dir = workspace_path / ".commitly" / "logs" / agent_name
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 로그 파일 경로 (타임스탬프 포함)
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        self.log_file = self.log_dir / f"{timestamp}.log"

        # 로거 설정
        self.logger = logging.getLogger(f"commitly.{agent_name}")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()  # 기존 핸들러 제거

        # 파일 핸들러
        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

        # 콘솔 핸들러 (선택적)
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                "[%(name)s] %(message)s"
            )
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)

    def debug(self, message: str) -> None:
        """디버그 로그"""
        self.logger.debug(message)

    def info(self, message: str) -> None:
        """정보 로그"""
        self.logger.info(message)

    def warning(self, message: str) -> None:
        """경고 로그"""
        self.logger.warning(message)

    def error(self, message: str) -> None:
        """에러 로그"""
        self.logger.error(message)

    def critical(self, message: str) -> None:
        """치명적 에러 로그"""
        self.logger.critical(message)

    def exception(self, message: str) -> None:
        """예외 로그 (스택 트레이스 포함)"""
        self.logger.exception(message)

    def log_command(self, command: str, output: str, exit_code: int) -> None:
        """
        명령어 실행 로그

        Args:
            command: 실행한 명령어
            output: 명령어 출력
            exit_code: 종료 코드
        """
        self.info(f"Executing: {command}")
        if output:
            self.debug(f"Output:\n{output}")
        self.info(f"Exit code: {exit_code}")

    def get_log_path(self) -> Path:
        """현재 로그 파일 경로 반환"""
        return self.log_file


def get_logger(
    agent_name: str,
    workspace_path: Optional[Path] = None,
    log_to_console: bool = True,
) -> CommitlyLogger:
    """
    로거 인스턴스 생성 헬퍼 함수

    Args:
        agent_name: 에이전트 이름
        workspace_path: 워크스페이스 경로 (None이면 현재 디렉토리)
        log_to_console: 콘솔 출력 여부

    Returns:
        CommitlyLogger 인스턴스
    """
    if workspace_path is None:
        workspace_path = Path.cwd()

    return CommitlyLogger(agent_name, workspace_path, log_to_console)
