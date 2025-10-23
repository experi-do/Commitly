"""
report 명령어 구현
"""

import os
from pathlib import Path
from typing import Any

from commitly.agents.report.agent import ReportAgent
from commitly.core.config import Config
from commitly.core.context import RunContext


def _load_env_file(workspace_path: Path) -> None:
    """
    .env 파일 로드
    
    Args:
        workspace_path: 워크스페이스 경로
    """
    env_file = workspace_path / ".env"
    
    if not env_file.exists():
        return
    
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                
                # 환경 변수에 설정 (이미 있으면 덮어쓰지 않음)
                if key not in os.environ:
                    os.environ[key] = value


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

    # .env 파일 로드
    _load_env_file(workspace_path)

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
            "config_path": str(config_path),
            "config": config,
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
