"""
CodeAgent 구현

코드 검증 및 실행
"""

import subprocess
from pathlib import Path
from typing import Any, Dict

from commitly.agents.base import BaseAgent
from commitly.agents.code.sql_parser import parse_sql_from_files
from commitly.agents.code.static_checker import StaticChecker
from commitly.core.context import RunContext
from commitly.core.git_manager import GitManager


class CodeAgent(BaseAgent):
    """
    Code Agent

    역할:
    1. commitly/code/{pipeline_id} 브랜치 생성
    2. 환경 확인 및 정적 검사 (lint, type)
    3. python main.py 동적 실행
    4. SQL 쿼리 파싱 (hasQuery, queryFileList 생성)
    5. 로그 요약 (선택적으로 LLM 사용)
    6. 자동으로 TestAgent 진행 (오류 없을 시)
    """

    def __init__(self, run_context: RunContext) -> None:
        super().__init__(run_context)

        self.hub_path = self._get_hub_path()
        self.hub_git = GitManager(self.hub_path, self.logger)

    def execute(self) -> Dict[str, Any]:
        """
        Code Agent 실행

        Returns:
            {
                "execution_result": Dict,
                "static_check_result": Dict,
                "hasQuery": bool,
                "queryFileList": List[QueryInfo],
            }
        """
        # 1. 브랜치 생성
        self._create_agent_branch()

        # 2. 환경 확인
        self._verify_environment()

        # 3. 정적 검사
        static_result = self._run_static_checks()

        # 정적 검사 실패 시 중단
        if not self._all_checks_passed(static_result):
            raise RuntimeError(
                f"정적 검사 실패:\n"
                f"Lint: {static_result['lint']['passed']}\n"
                f"Type: {static_result['type_check']['passed']}"
            )

        # 4. 동적 실행
        execution_result = self._run_dynamic_execution()

        # 실행 실패 시 중단
        if execution_result["exit_code"] != 0:
            # 선택적 LLM 요약
            summary = self._summarize_error_if_needed(execution_result)
            raise RuntimeError(
                f"코드 실행 실패 (exit code: {execution_result['exit_code']})\n"
                f"{summary}"
            )

        # 5. SQL 파싱
        has_query, query_file_list = self._parse_sql_queries()

        # RunContext 업데이트
        self.run_context["has_query"] = has_query
        self.run_context["query_file_list"] = query_file_list

        # 6. 변경사항 커밋
        self.hub_git.commit("Code Agent: 코드 검증 완료")

        # 7. 결과 반환
        return {
            "execution_result": execution_result,
            "static_check_result": static_result,
            "hasQuery": has_query,
            "queryFileList": query_file_list,
        }

    def _create_agent_branch(self) -> None:
        """에이전트 브랜치 생성"""
        pipeline_id = self.run_context["pipeline_id"]
        branch_name = f"commitly/code/{pipeline_id}"

        # 부모 브랜치: Clone Agent 브랜치
        parent_branch = self.run_context["clone_agent_branch"]

        self.hub_git.create_branch(branch_name, parent_branch)

        self.agent_branch = branch_name
        self.run_context["code_agent_branch"] = branch_name

        self.logger.info(f"에이전트 브랜치 생성: {branch_name}")

    def _verify_environment(self) -> None:
        """환경 검증"""
        self.logger.info("환경 검증 시작")

        # Python 버전 확인
        python_bin = self.run_context.get("python_bin", "python")

        try:
            result = subprocess.run(
                [python_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.logger.info(f"Python: {result.stdout.strip()}")

        except Exception as e:
            raise RuntimeError(f"Python 실행 실패: {e}")

    def _run_static_checks(self) -> Dict[str, Any]:
        """정적 검사 실행"""
        self.logger.info("정적 검사 시작")

        checker = StaticChecker(self.hub_path, self.logger)
        results = checker.run_all_checks()

        return results

    def _all_checks_passed(self, static_result: Dict[str, Any]) -> bool:
        """모든 정적 검사가 통과했는지 확인"""
        return (
            static_result["lint"]["passed"]
            and static_result["type_check"]["passed"]
        )

    def _run_dynamic_execution(self) -> Dict[str, Any]:
        """동적 실행 (python main.py)"""
        self.logger.info("동적 실행 시작")

        profile = self.run_context.get("execution_profile", {})
        command = profile.get("command", "python main.py")
        timeout = profile.get("timeout", 300)

        try:
            result = subprocess.run(
                command.split(),
                cwd=self.hub_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            self.logger.log_command(
                command,
                result.stdout + result.stderr,
                result.returncode,
            )

            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "execution_time": 0,  # TODO: 실제 실행 시간 측정
            }

        except subprocess.TimeoutExpired:
            self.logger.error(f"실행 타임아웃 ({timeout}초)")
            raise RuntimeError(f"실행 타임아웃: {timeout}초")

    def _summarize_error_if_needed(self, execution_result: Dict[str, Any]) -> str:
        """
        에러 로그 요약 (선택적으로 LLM 사용)

        Args:
            execution_result: 실행 결과

        Returns:
            요약된 에러 메시지
        """
        error_log = execution_result["stderr"]

        # 로그가 짧으면 LLM 없이 그대로 반환
        if len(error_log) < 500:
            return error_log

        # LLM 사용 여부는 설정에 따라 결정 (여기서는 사용하지 않음)
        # llm_client = self.run_context.get("llm_client")
        # if llm_client:
        #     return llm_client.summarize_error_log(error_log)

        # LLM 없이 앞 500자만 반환
        return error_log[:500] + "\n... (truncated)"

    def _parse_sql_queries(self) -> tuple[bool, list]:
        """
        SQL 쿼리 파싱

        Returns:
            (hasQuery, queryFileList)
        """
        self.logger.info("SQL 쿼리 파싱 시작")

        # Clone Agent 결과에서 변경 파일 가져오기
        clone_output = self._load_previous_output("clone_agent")
        changed_files = clone_output["data"]["changed_files"]

        try:
            has_query, query_list = parse_sql_from_files(changed_files)

            self.logger.info(f"SQL 쿼리 {len(query_list)}개 발견")

            return has_query, query_list

        except Exception as e:
            self.logger.warning(f"SQL 파싱 실패: {e}")
            # 파싱 실패는 경고로만 처리
            return False, []
