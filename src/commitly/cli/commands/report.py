"""
report 명령어 구현
"""

from pathlib import Path
from typing import Any

from commitly.agents.report.agent import ReportAgent
from commitly.core.config import Config
from commitly.core.context import RunContext


def report_command(args: Any) -> None:
    """
    작업 보고서 생성

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

    print("Commitly 보고서 생성 중...")
    print()

    try:
        # Config 로드
        config = Config(config_path)

        # 기간 설정 오버라이드
        if args.from_date:
            config._config["report"]["period"]["from"] = args.from_date

        if args.to_date:
            config._config["report"]["period"]["to"] = args.to_date

        # RunContext 생성 (최소한으로)
        run_context: RunContext = {
            "pipeline_id": "report-only",
            "project_name": workspace_path.name,
            "workspace_path": str(workspace_path),
            "hub_path": "",
            "git_remote": "origin",
            "current_branch": "main",
            "latest_local_commits": [],
            "clone_agent_branch": None,
            "code_agent_branch": None,
            "test_agent_branch": None,
            "refactoring_agent_branch": None,
            "agent_status": {},
            "commit_file_list": [],
            "has_query": False,
            "query_file_list": None,
            "llm_client": None,
            "execution_profile": {},
            "test_profile": {},
        }

        # ReportAgent 실행
        agent = ReportAgent(run_context)
        output = agent.run()

        if output["status"] == "success":
            report_path = output["data"]["report_path"]
            print(f"\n✓ 보고서 생성 완료: {report_path}")
        else:
            print(f"\n❌ 보고서 생성 실패: {output.get('error')}")

    except Exception as e:
        print(f"\n❌ 보고서 생성 중 오류 발생: {e}")
