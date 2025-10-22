"""
BaseAgent 추상 클래스

모든 에이전트가 상속받는 기본 클래스
"""

import json
import traceback
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from commitly.core.config import Config
from commitly.core.context import AgentOutput, ErrorInfo, RunContext
from commitly.core.logger import CommitlyLogger, get_logger
from commitly.core.rollback import rollback_and_cleanup


class BaseAgent(ABC):
    """
    에이전트 기본 클래스

    모든 에이전트는 이 클래스를 상속받아 execute() 메서드를 구현합니다.
    공통 기능:
    - 표준 출력 구조 생성
    - 에러 처리 및 롤백
    - 로깅
    """

    def __init__(self, run_context: RunContext) -> None:
        """
        Args:
            run_context: 파이프라인 실행 컨텍스트
        """
        self.run_context = run_context
        self.agent_name = self.__class__.__name__.lower().replace("agent", "_agent")

        # 로거 초기화
        workspace_path = Path(run_context["workspace_path"])
        self.logger = get_logger(self.agent_name, workspace_path)

        # 설정 로드
        config_path = run_context.get("config_path")
        if not config_path:
            raise RuntimeError("RunContext에 config_path가 없습니다. commitly init을 먼저 실행하세요.")
        self.config = Config(Path(config_path))

        # 시작 시간 기록
        self.started_at = datetime.now()
        self.ended_at: Optional[datetime] = None

        # 에이전트 브랜치 (허브에서 생성)
        self.agent_branch: Optional[str] = None

        self.logger.info(f"{self.agent_name} 시작")

    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        """
        에이전트 실행 로직

        각 에이전트는 이 메서드를 구현해야 합니다.

        Returns:
            에이전트별 고유 데이터 (AgentOutput의 data 필드에 들어갈 내용)

        Raises:
            Exception: 실행 중 오류 발생 시
        """
        pass

    def run(self) -> AgentOutput:
        """
        에이전트 실행 및 결과 반환

        execute() 메서드를 호출하고 표준 출력 구조로 감싸서 반환합니다.
        에러 발생 시 작업 중단 함수를 호출합니다.

        Returns:
            표준 AgentOutput 구조
        """
        try:
            # RunContext 상태 업데이트
            self.run_context["current_agent"] = self.agent_name
            self.run_context["agent_status"][self.agent_name] = "running"

            # 에이전트 실행
            data = self.execute()

            # 종료 시간 기록
            self.ended_at = datetime.now()

            # 상태 업데이트
            self.run_context["agent_status"][self.agent_name] = "success"

            # 표준 출력 생성
            output = self._create_output(status="success", data=data)

            # 결과 저장
            self._save_output(output)

            self.logger.info(f"{self.agent_name} 완료")

            return output

        except Exception as e:
            # 종료 시간 기록
            self.ended_at = datetime.now()

            # 상태 업데이트
            self.run_context["agent_status"][self.agent_name] = "failed"

            # 에러 정보 생성
            stack_trace = traceback.format_exc()
            error_info: ErrorInfo = {
                "type": type(e).__name__,
                "message": f"{type(e).__name__}: {e}",
                "log_path": str(self.logger.get_log_path()),
            }

            # 에러 로그
            self.logger.exception(f"{self.agent_name} 실패: {e}")

            # 표준 출력 생성 (실패)
            output = self._create_output(
                status="failed",
                data={},
                error=error_info,
            )

            # 결과 저장
            self._save_output(output)

            # 작업 중단 함수 호출
            self._handle_failure(str(e), stack_trace)

            # 에러 전파
            raise

    def _create_output(
        self,
        status: str,
        data: Dict[str, Any],
        error: Optional[ErrorInfo] = None,
    ) -> AgentOutput:
        """
        표준 AgentOutput 생성

        Args:
            status: 'success' | 'failed'
            data: 에이전트별 고유 데이터
            error: 에러 정보 (실패 시)

        Returns:
            표준 AgentOutput
        """
        output: AgentOutput = {
            "pipeline_id": self.run_context["pipeline_id"],
            "agent_name": self.agent_name,
            "agent_branch": self.agent_branch,
            "status": status,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else "",
            "error": error,
            "data": data,
        }

        return output

    def _save_output(self, output: AgentOutput) -> None:
        """
        에이전트 출력을 JSON 파일로 저장

        .commitly/cache/{agent_name}.json 에 저장

        Args:
            output: 저장할 AgentOutput
        """
        cache_dir = Path(self.run_context["workspace_path"]) / ".commitly" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        output_file = cache_dir / f"{self.agent_name}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        self.logger.debug(f"출력 저장: {output_file}")

    def _handle_failure(self, error_message: str, stack_trace: Optional[str] = None) -> None:
        """
        실패 처리 및 롤백

        Args:
            error_message: 에러 메시지
        """
        self.logger.error("작업 중단 함수 호출")

        # 롤백 및 정리
        cleanup_hub = False
        if self.config:
            cleanup_hub = bool(self.config.get("pipeline.cleanup_hub_on_failure", False))

        rollback_and_cleanup(
            run_context=self.run_context,
            failed_agent=self.agent_name,
            error_message=error_message,
            stack_trace=stack_trace,
            cleanup_hub=cleanup_hub,
        )

    def _load_previous_output(self, agent_name: str) -> Dict[str, Any]:
        """
        이전 에이전트의 출력 로드

        Args:
            agent_name: 이전 에이전트 이름 (예: 'clone_agent')

        Returns:
            이전 에이전트의 AgentOutput

        Raises:
            FileNotFoundError: 출력 파일이 없을 때
        """
        cache_file = (
            Path(self.run_context["workspace_path"])
            / ".commitly"
            / "cache"
            / f"{agent_name}.json"
        )

        if not cache_file.exists():
            raise FileNotFoundError(
                f"{agent_name}의 출력을 찾을 수 없습니다: {cache_file}"
            )

        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _get_hub_path(self) -> Path:
        """허브 경로 반환"""
        return Path(self.run_context["hub_path"])

    def _get_workspace_path(self) -> Path:
        """워크스페이스 경로 반환"""
        return Path(self.run_context["workspace_path"])
