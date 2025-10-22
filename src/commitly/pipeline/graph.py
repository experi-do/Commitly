"""
LangGraph 파이프라인 구현

모든 에이전트를 오케스트레이션
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from langgraph.graph import StateGraph, END

from commitly.agents.clone.agent import CloneAgent
from commitly.agents.code.agent import CodeAgent
from commitly.agents.refactoring.agent import RefactoringAgent
from commitly.agents.report.agent import ReportAgent
from commitly.agents.slack.agent import SlackAgent
from commitly.agents.sync.agent import SyncAgent
from commitly.agents.test.agent import TestAgent
from commitly.core.config import Config
from commitly.core.context import RunContext
from commitly.core.git_manager import GitManager
from commitly.core.llm_client import LLMClient
from commitly.core.logger import CommitlyLogger
from commitly.core.rollback import rollback_and_cleanup


class CommitlyPipeline:
    """
    Commitly 파이프라인

    LangGraph를 사용하여 모든 에이전트를 순차적으로 실행
    """

    def __init__(self, workspace_path: Path, config_path: Path) -> None:
        """
        Args:
            workspace_path: 프로젝트 루트 경로
            config_path: 설정 파일 경로
        """
        self.workspace_path = workspace_path
        self.config = Config(config_path)

        # 로거 초기화
        self.logger = CommitlyLogger("pipeline", workspace_path)

        # LLM 클라이언트 초기화
        self.llm_client = self._init_llm_client()

        # Git 관리자 초기화
        self.workspace_git = GitManager(workspace_path, self.logger)

        # RunContext 초기화
        self.run_context: RunContext = self._init_run_context()

    def _init_llm_client(self) -> LLMClient:
        """LLM 클라이언트 초기화"""
        llm_enabled = self.config.get("llm.enabled", True)

        if not llm_enabled:
            self.logger.warning("LLM 비활성화")
            return None

        try:
            return LLMClient(self.config, self.logger)
        except Exception as e:
            self.logger.warning(f"LLM 클라이언트 초기화 실패: {e}")
            return None

    def _init_run_context(self) -> RunContext:
        """RunContext 초기화"""
        # Pipeline ID 생성
        pipeline_id = str(uuid.uuid4())

        # Git 정보
        project_name = self.workspace_path.name
        current_branch = self.workspace_git.repo.active_branch.name
        git_remote = self.config.get("git.remote", "origin")

        # 최근 로컬 커밋 가져오기
        latest_commits = self._get_latest_local_commits()

        return {
            "pipeline_id": pipeline_id,
            "project_name": project_name,
            "workspace_path": str(self.workspace_path),
            "hub_path": "",  # Clone Agent에서 설정
            "config_path": str(self.config.config_path),
            "git_remote": git_remote,
            "current_branch": current_branch,
            "latest_local_commits": latest_commits,
            "clone_agent_branch": None,
            "code_agent_branch": None,
            "test_agent_branch": None,
            "refactoring_agent_branch": None,
            "agent_status": {},
            "commit_file_list": [],
            "has_query": False,
            "query_file_list": None,
            "llm_client": self.llm_client,
            "execution_profile": self.config.get("execution", {}),
            "test_profile": self.config.get("test", {}),
        }

    def _get_latest_local_commits(self) -> list:
        """
        최근 로컬 커밋 가져오기

        Returns:
            커밋 정보 리스트
        """
        try:
            # origin/main과 HEAD 사이의 커밋들
            remote = self.config.get("git.remote", "origin")
            current_branch = self.workspace_git.repo.active_branch.name
            base_ref = f"{remote}/{current_branch}"

            commits = list(self.workspace_git.repo.iter_commits(f"{base_ref}..HEAD"))

            return [
                {
                    "sha": commit.hexsha,
                    "message": commit.message.strip(),
                    "author": str(commit.author),
                    "timestamp": datetime.fromtimestamp(commit.committed_date).isoformat(),
                }
                for commit in commits
            ]

        except Exception as e:
            self.logger.warning(f"로컬 커밋 조회 실패: {e}")
            return []

    def build_graph(self) -> StateGraph:
        """
        LangGraph 그래프 구축

        Returns:
            StateGraph
        """
        # StateGraph 생성
        workflow = StateGraph(dict)

        # 노드 추가
        workflow.add_node("clone", self._run_clone_agent)
        workflow.add_node("code", self._run_code_agent)
        workflow.add_node("test", self._run_test_agent)
        workflow.add_node("refactoring", self._run_refactoring_agent)
        workflow.add_node("sync", self._run_sync_agent)
        workflow.add_node("slack", self._run_slack_agent)
        workflow.add_node("report", self._run_report_agent)

        # 엣지 추가 (순차적 실행)
        workflow.set_entry_point("clone")
        workflow.add_edge("clone", "code")
        workflow.add_edge("code", "test")
        workflow.add_edge("test", "refactoring")
        workflow.add_edge("refactoring", "sync")
        workflow.add_edge("sync", "slack")

        # Slack → Report (조건부)
        workflow.add_conditional_edges(
            "slack",
            self._should_create_report,
            {
                "create_report": "report",
                "end": END,
            },
        )

        # Report → END
        workflow.add_edge("report", END)

        return workflow.compile()

    def _run_clone_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Clone Agent 실행"""
        self.logger.info("=" * 60)
        self.logger.info("Clone Agent 시작")
        self.logger.info("=" * 60)

        try:
            agent = CloneAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Clone Agent 실패: {output.get('error')}")

            state["clone_output"] = output
            return state

        except Exception as e:
            self.logger.error(f"Clone Agent 오류: {e}")
            rollback_and_cleanup(self.run_context, "clone_agent", str(e))
            raise

    def _run_code_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Code Agent 실행"""
        self.logger.info("=" * 60)
        self.logger.info("Code Agent 시작")
        self.logger.info("=" * 60)

        try:
            agent = CodeAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Code Agent 실패: {output.get('error')}")

            state["code_output"] = output
            return state

        except Exception as e:
            self.logger.error(f"Code Agent 오류: {e}")
            rollback_and_cleanup(self.run_context, "code_agent", str(e))
            raise

    def _run_test_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Test Agent 실행"""
        self.logger.info("=" * 60)
        self.logger.info("Test Agent 시작")
        self.logger.info("=" * 60)

        try:
            agent = TestAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Test Agent 실패: {output.get('error')}")

            state["test_output"] = output
            return state

        except Exception as e:
            self.logger.error(f"Test Agent 오류: {e}")
            rollback_and_cleanup(self.run_context, "test_agent", str(e))
            raise

    def _run_refactoring_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Refactoring Agent 실행"""
        self.logger.info("=" * 60)
        self.logger.info("Refactoring Agent 시작")
        self.logger.info("=" * 60)

        try:
            agent = RefactoringAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Refactoring Agent 실패: {output.get('error')}")

            state["refactoring_output"] = output
            return state

        except Exception as e:
            self.logger.error(f"Refactoring Agent 오류: {e}")
            rollback_and_cleanup(self.run_context, "refactoring_agent", str(e))
            raise

    def _run_sync_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Sync Agent 실행"""
        self.logger.info("=" * 60)
        self.logger.info("Sync Agent 시작")
        self.logger.info("=" * 60)

        try:
            agent = SyncAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Sync Agent 실패: {output.get('error')}")

            state["sync_output"] = output
            return state

        except Exception as e:
            self.logger.error(f"Sync Agent 오류: {e}")
            rollback_and_cleanup(self.run_context, "sync_agent", str(e))
            raise

    def _run_slack_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Slack Agent 실행"""
        self.logger.info("=" * 60)
        self.logger.info("Slack Agent 시작")
        self.logger.info("=" * 60)

        try:
            agent = SlackAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Slack Agent 실패: {output.get('error')}")

            state["slack_output"] = output
            return state

        except Exception as e:
            self.logger.error(f"Slack Agent 오류: {e}")
            # Slack 실패는 치명적 오류 아님, 계속 진행
            self.logger.warning("Slack Agent 실패, 계속 진행")
            state["slack_output"] = {
                "status": "failed",
                "data": {"create_report": False},
            }
            return state

    def _run_report_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Report Agent 실행"""
        self.logger.info("=" * 60)
        self.logger.info("Report Agent 시작")
        self.logger.info("=" * 60)

        try:
            agent = ReportAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Report Agent 실패: {output.get('error')}")

            state["report_output"] = output
            return state

        except Exception as e:
            self.logger.error(f"Report Agent 오류: {e}")
            # Report 실패는 치명적 오류 아님
            self.logger.warning("Report Agent 실패, 계속 진행")
            state["report_output"] = {"status": "failed"}
            return state

    def _should_create_report(self, state: Dict[str, Any]) -> str:
        """
        보고서 생성 여부 결정

        Args:
            state: 그래프 상태

        Returns:
            "create_report" 또는 "end"
        """
        slack_output = state.get("slack_output", {})
        create_report = slack_output.get("data", {}).get("create_report", False)

        if create_report:
            return "create_report"
        else:
            return "end"

    def run(self) -> Dict[str, Any]:
        """
        파이프라인 실행

        Returns:
            최종 상태
        """
        self.logger.info("Commitly 파이프라인 시작")
        self.logger.info(f"Pipeline ID: {self.run_context['pipeline_id']}")

        # 그래프 빌드
        graph = self.build_graph()

        # 초기 상태
        initial_state = {}

        try:
            # 그래프 실행
            final_state = graph.invoke(initial_state)

            self.logger.info("=" * 60)
            self.logger.info("✓ 파이프라인 완료")
            self.logger.info("=" * 60)

            return final_state

        except Exception as e:
            self.logger.error(f"파이프라인 실패: {e}")
            raise
