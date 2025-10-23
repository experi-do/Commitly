"""
LangGraph 파이프라인 구현

모든 에이전트를 오케스트레이션
"""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from langgraph.graph import StateGraph, END

from commitly.agents.clone.agent import CloneAgent
from commitly.agents.code.agent import CodeAgent
from commitly.agents.review.agent import ReviewAgent
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

    def __init__(self, workspace_path: Path, config_path: Path, user_message: Optional[str] = None) -> None:
        """
        Args:
            workspace_path: 프로젝트 루트 경로
            config_path: 설정 파일 경로
        """
        self.workspace_path = workspace_path
        self.env_file_path = self._load_env_file(self.workspace_path)
        self.config = Config(config_path)

        # 로거 초기화
        self.logger = CommitlyLogger("pipeline", workspace_path, log_to_console=False)

        # LLM 클라이언트 초기화
        self.llm_client = self._init_llm_client()

        # Git 관리자 초기화
        self.workspace_git = GitManager(workspace_path, self.logger)

        # RunContext 초기화
        self.run_context: RunContext = self._init_run_context()

        if user_message:
            self.run_context["user_commit_message"] = user_message

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

        # python_bin 감지
        python_bin = self._detect_python_bin()

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
            "python_bin": python_bin,
            "env_file": str(self.env_file_path) if self.env_file_path else "",
            "execution_profile": self.config.get("execution", {}),
            "test_profile": self.config.get("test", {}),
        }

    def _detect_python_bin(self) -> str:
        """
        Python 바이너리 경로 감지 (3단계 우선순위)

        Returns:
            python 바이너리 경로
        """
        # 우선순위 1: config.yaml의 execution.python_bin
        python_bin = self.config.get("execution.python_bin")
        if python_bin and Path(python_bin).exists():
            return python_bin

        # 우선순위 2: COMMITLY_VENV 환경 변수
        env_venv = os.getenv("COMMITLY_VENV")
        if env_venv:
            venv_path = Path(env_venv)

            # Unix/Linux/macOS
            bin_path = venv_path / "bin" / "python"
            if bin_path.exists():
                return str(bin_path)

            # Windows
            bin_path = venv_path / "Scripts" / "python.exe"
            if bin_path.exists():
                return str(bin_path)

        # 우선순위 3: 기본값
        return "python"

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

    def _load_env_file(self, workspace_path: Path) -> Path | None:
        """
        워크스페이스의 .env 파일을 로드하여 환경 변수에 주입
        """
        env_path = workspace_path / ".env"
        if not env_path.exists():
            return None

        try:
            env_data = self._parse_env_file(env_path)

            for key, value in env_data.items():
                if key not in os.environ:
                    os.environ[key] = value

            self._populate_db_env_defaults(env_data)
            return env_path

        except Exception as exc:
            self.logger.warning(f".env 파일 로드 실패: {exc}")
            return None

    def _parse_env_file(self, env_path: Path) -> Dict[str, str]:
        """
        .env 파일을 파싱하여 키-값 딕셔너리로 반환
        """
        env_data: Dict[str, str] = {}

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if line.lower().startswith("export "):
                line = line[7:].strip()

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not key:
                continue

            if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]

            env_data[key] = value

        return env_data

    def _populate_db_env_defaults(self, env_data: Dict[str, str]) -> None:
        """
        DATABASE_URL을 기반으로 DB 관련 환경 변수를 보완
        """
        db_url = env_data.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not db_url:
            return

        parsed = urlparse(db_url)
        if parsed.scheme not in {"postgresql", "postgres"}:
            return

        if parsed.username and not os.environ.get("DB_USER"):
            os.environ["DB_USER"] = parsed.username

        if parsed.password is not None:
            if not os.environ.get("DB_PASSWORD"):
                os.environ["DB_PASSWORD"] = parsed.password
        else:
            os.environ.setdefault("DB_PASSWORD", "")

        if parsed.hostname and not os.environ.get("DB_HOST"):
            os.environ["DB_HOST"] = parsed.hostname

        if parsed.port and not os.environ.get("DB_PORT"):
            os.environ["DB_PORT"] = str(parsed.port)

        db_name = parsed.path.lstrip("/")
        if db_name and not os.environ.get("DB_NAME"):
            os.environ["DB_NAME"] = db_name

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
        workflow.add_node("review", self._run_review_agent)
        workflow.add_node("sync", self._run_sync_agent)
        workflow.add_node("slack", self._run_slack_agent)

        # 엣지 추가 (순차적 실행)
        workflow.set_entry_point("clone")
        workflow.add_edge("clone", "code")
        workflow.add_edge("code", "test")
        workflow.add_edge("test", "review")
        workflow.add_edge("review", "sync")
        workflow.add_edge("sync", "slack")
        
        # Slack → END (Report는 파이프라인에서 제외)
        workflow.add_edge("slack", END)

        return workflow.compile()

    def _run_clone_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Clone Agent 실행"""
        self.logger.info("=" * 60)
        self.logger.info("Clone Agent 시작")
        self.logger.info("=" * 60)

        print("[1/6] ⏳ Clone Agent...", end="", flush=True)

        try:
            agent = CloneAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Clone Agent 실패: {output.get('error')}")

            print("\r[1/6] ✓ Clone Agent" + " " * 20)
            state["clone_output"] = output
            return state

        except Exception as e:
            print(f"\r[1/6] ❌ Clone Agent 실패: {e}")
            print(f"    로그: {self.run_context['workspace_path']}/.commitly/logs/clone_agent/")
            self.logger.error(f"Clone Agent 오류: {e}")
            rollback_and_cleanup(self.run_context, "clone_agent", str(e))
            raise

    def _run_code_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Code Agent 실행"""
        self.logger.info("=" * 60)
        self.logger.info("Code Agent 시작")
        self.logger.info("=" * 60)

        print("[2/6] ⏳ Code Agent...", end="", flush=True)

        try:
            agent = CodeAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Code Agent 실패: {output.get('error')}")

            # 추가 정보 표시
            data = output.get("data", {})
            query_file_list = data.get("queryFileList", [])
            query_count = len(query_file_list) if isinstance(query_file_list, list) else 0
            extra_info = f" (SQL 쿼리 {query_count}개 발견)" if query_count > 0 else ""

            print(f"\r[2/6] ✓ Code Agent{extra_info}" + " " * 20)
            state["code_output"] = output
            return state

        except Exception as e:
            print(f"\r[2/6] ❌ Code Agent 실패: {e}")
            print(f"    로그: {self.run_context['workspace_path']}/.commitly/logs/code_agent/")
            self.logger.error(f"Code Agent 오류: {e}")
            rollback_and_cleanup(self.run_context, "code_agent", str(e))
            raise

    def _run_test_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Test Agent 실행"""
        self.logger.info("=" * 60)
        self.logger.info("Test Agent 시작")
        self.logger.info("=" * 60)

        print("[3/6] ⏳ Test Agent...", end="", flush=True)

        try:
            agent = TestAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Test Agent 실패: {output.get('error')}")

            # 추가 정보 표시
            data = output.get("data", {})
            optimized_queries = data.get("optimized_queries", [])
            optimized_count = len(optimized_queries) if isinstance(optimized_queries, list) else 0
            extra_info = f" (SQL 최적화 {optimized_count}개)" if optimized_count > 0 else ""

            print(f"\r[3/6] ✓ Test Agent{extra_info}" + " " * 20)
            state["test_output"] = output
            return state

        except Exception as e:
            print(f"\r[3/6] ❌ Test Agent 실패: {e}")
            print(f"    로그: {self.run_context['workspace_path']}/.commitly/logs/test_agent/")
            self.logger.error(f"Test Agent 오류: {e}")
            rollback_and_cleanup(self.run_context, "test_agent", str(e))
            raise

    def _run_review_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Review Agent 실행"""
        self.logger.info("=" * 60)
        self.logger.info("Review Agent 시작")
        self.logger.info("=" * 60)

        print("[4/6] ⏳ Review Agent...", end="", flush=True)

        try:
            agent = ReviewAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Review Agent 실패: {output.get('error')}")

            # 추가 정보 표시
            data = output.get("data", {})
            issue_count = data.get("issue_count", {})
            total_issues = sum(issue_count.values()) if isinstance(issue_count, dict) else 0
            assessment = data.get("overall_assessment", "UNKNOWN")

            if total_issues > 0:
                # 심각도별 요약
                critical = issue_count.get("critical", 0)
                high = issue_count.get("high", 0)
                severity_info = ""
                if critical > 0:
                    severity_info = f", 🔴{critical} "
                if high > 0:
                    severity_info += f"🟠{high} "
                if severity_info:
                    extra_info = f" ({assessment}{severity_info}외 {total_issues - critical - high}개)"
                else:
                    extra_info = f" ({assessment}, {total_issues}개)"
            else:
                extra_info = f" ({assessment})"

            print(f"\r[4/6] ✓ Review Agent{extra_info}" + " " * 20)
            state["review_output"] = output
            return state

        except Exception as e:
            print(f"\r[4/6] ❌ Review Agent 실패: {e}")
            print(f"    로그: {self.run_context['workspace_path']}/.commitly/logs/review_agent/")
            self.logger.error(f"Review Agent 오류: {e}")
            rollback_and_cleanup(self.run_context, "review_agent", str(e))
            raise

    def _run_sync_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Sync Agent 실행"""
        self.logger.info("=" * 60)
        self.logger.info("Sync Agent 시작")
        self.logger.info("=" * 60)

        print("[5/6] ⏳ Sync Agent...", end="", flush=True)

        try:
            agent = SyncAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Sync Agent 실패: {output.get('error')}")

            # 추가 정보 표시
            data = output.get("data", {})
            if data.get("pushed"):
                print(f"\r[5/6] ✓ Sync Agent (원격 push 완료)" + " " * 20)
            else:
                print(f"\r[5/6] ✓ Sync Agent (push 취소됨)" + " " * 20)

            state["sync_output"] = output
            return state

        except Exception as e:
            print(f"\r[5/6] ❌ Sync Agent 실패: {e}")
            print(f"    로그: {self.run_context['workspace_path']}/.commitly/logs/sync_agent/")
            self.logger.error(f"Sync Agent 오류: {e}")
            rollback_and_cleanup(self.run_context, "sync_agent", str(e))
            raise

    def _run_slack_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Slack Agent 실행"""
        self.logger.info("=" * 60)
        self.logger.info("Slack Agent 시작")
        self.logger.info("=" * 60)

        print("[6/6] ⏳ Slack Agent...", end="", flush=True)

        try:
            agent = SlackAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Slack Agent 실패: {output.get('error')}")

            # 추가 정보 표시
            data = output.get("data", {})
            matched_count = len(data.get("matched_messages", []))
            extra_info = f" (피드백 {matched_count}개 매칭)" if matched_count > 0 else ""

            print(f"\r[6/6] ✓ Slack Agent{extra_info}" + " " * 20)
            state["slack_output"] = output
            return state

        except Exception as e:
            print(f"\r[6/6] ⚠ Slack Agent 실패 (계속 진행)" + " " * 20)
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

        # Report Agent는 프로그레스 바 없이 조용히 실행
        try:
            agent = ReportAgent(self.run_context)
            output = agent.run()

            if output["status"] != "success":
                raise RuntimeError(f"Report Agent 실패: {output.get('error')}")

            # 성공 시 간단한 메시지만 출력
            data = output.get("data", {})
            report_path = data.get("report_path", "")
            if report_path:
                from pathlib import Path
                try:
                    rel_path = Path(report_path).relative_to(Path.cwd())
                    print(f"\n📄 보고서 생성: {rel_path}")
                except ValueError:
                    print(f"\n📄 보고서 생성: {report_path}")

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
