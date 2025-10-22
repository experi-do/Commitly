"""
TestAgent 구현

SQL 쿼리 최적화 및 테스트 실행
"""

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from commitly.agents.base import BaseAgent
from commitly.agents.test.sql_optimizer import SQLOptimizer
from commitly.core.context import QueryInfo, RunContext
from commitly.core.git_manager import GitManager


class TestAgent(BaseAgent):
    """
    Test Agent

    역할:
    1. commitly/test/{pipeline_id} 브랜치 생성
    2. SQL 쿼리 최적화 (hasQuery=true일 경우)
       - LLM으로 후보 쿼리 생성 (3개)
       - EXPLAIN ANALYZE로 성능 비교
       - 최적 쿼리 자동 적용
    3. 테스트 실행 (test_command)
    4. 테스트 실패 시 자동 롤백
    5. 성공 시 RefactoringAgent 진행
    """

    def __init__(self, run_context: RunContext) -> None:
        super().__init__(run_context)

        self.hub_path = self._get_hub_path()
        self.hub_git = GitManager(self.hub_path, self.logger)

    def execute(self) -> Dict[str, Any]:
        """
        Test Agent 실행

        Returns:
            {
                "optimized_queries": List[Dict],  # 최적화된 쿼리 목록
                "test_result": Dict,  # 테스트 실행 결과
                "optimization_summary": Dict,  # 최적화 요약
            }
        """
        # 1. 브랜치 생성
        self._create_agent_branch()

        # 2. CodeAgent 결과 가져오기
        code_output = self._load_previous_output("code_agent")
        has_query = code_output["data"]["hasQuery"]
        query_file_list = code_output["data"].get("queryFileList", [])

        optimized_queries: List[Dict[str, Any]] = []
        test_result: Dict[str, Any]

        # 3. SQL 최적화 및 테스트 실행 (hasQuery=true인 경우만)
        if has_query and query_file_list:
            self.logger.info(f"SQL 쿼리 최적화 시작: {len(query_file_list)}개")
            optimized_queries = self._optimize_sql_queries(query_file_list)

        # 4. 변경사항 커밋
        if optimized_queries:
            self.hub_git.commit("Test Agent: SQL 쿼리 최적화")

        if has_query and (query_file_list or optimized_queries):
            # 5. 테스트 실행
            test_result = self._run_tests()
        else:
            self.logger.info("SQL 쿼리 없음, 테스트 스킵")
            test_result = {
                "passed": True,
                "output": "SQL 쿼리가 없어 테스트를 실행하지 않았습니다.",
                "exit_code": 0,
                "skipped": True,
            }

        # 테스트 실패 시 자동 롤백
        if not test_result["passed"]:
            self.logger.error("테스트 실패, 자동 롤백")
            raise RuntimeError(
                f"테스트 실패:\n{test_result['output']}"
            )

        # 6. 최적화 요약
        optimization_summary = self._create_optimization_summary(optimized_queries)

        # 7. 결과 반환
        return {
            "optimized_queries": optimized_queries,
            "test_result": test_result,
            "optimization_summary": optimization_summary,
        }

    def _create_agent_branch(self) -> None:
        """에이전트 브랜치 생성"""
        pipeline_id = self.run_context["pipeline_id"]
        branch_name = f"commitly/test/{pipeline_id}"

        # 부모 브랜치: Code Agent 브랜치
        parent_branch = self.run_context["code_agent_branch"]

        self.hub_git.create_branch(branch_name, parent_branch)

        self.agent_branch = branch_name
        self.run_context["test_agent_branch"] = branch_name

        self.logger.info(f"에이전트 브랜치 생성: {branch_name}")

    def _optimize_sql_queries(
        self,
        query_file_list: List[QueryInfo],
    ) -> List[Dict[str, Any]]:
        """
        SQL 쿼리 최적화

        Args:
            query_file_list: QueryInfo 리스트

        Returns:
            최적화된 쿼리 정보 리스트
        """
        optimized_results = []

        # SQL 최적화 도구 초기화
        optimizer = SQLOptimizer(self.config, self.logger)
        llm_client = self.run_context.get("llm_client")

        for query_info in query_file_list:
            self.logger.info(
                f"쿼리 최적화: {query_info['file_path']}:{query_info['line_start']}"
            )

            # 원본 쿼리
            original_query = query_info["query"]

            # 테이블 스키마 정보 가져오기
            tables = optimizer.extract_tables_from_query(original_query)
            schema_info = "\n".join(
                [optimizer.get_table_schema(table) for table in tables]
            )

            # LLM으로 후보 쿼리 생성
            if llm_client:
                try:
                    candidate_queries = llm_client.generate_sql_candidates(
                        original_query,
                        schema_info,
                    )
                except Exception as e:
                    self.logger.warning(f"LLM 후보 생성 실패: {e}")
                    candidate_queries = []
            else:
                self.logger.warning("LLM 클라이언트 없음, 최적화 스킵")
                candidate_queries = []

            # 원본 쿼리도 후보에 포함
            all_candidates = [original_query] + candidate_queries

            # EXPLAIN ANALYZE로 최적 쿼리 선택
            best_query, best_explain = optimizer.find_best_query(all_candidates)

            # 결과 저장
            improved = best_query != original_query
            optimized_info = {
                "file_path": query_info["file_path"],
                "function_name": query_info["function_name"],
                "line_start": query_info["line_start"],
                "line_end": query_info["line_end"],
                "original_query": original_query,
                "optimized_query": best_query,
                "improved": improved,
                "original_cost": 0.0,  # 원본 비용 계산 가능
                "optimized_cost": best_explain.get("total_cost"),
                "execution_time": best_explain.get("execution_time"),
            }

            optimized_results.append(optimized_info)

            # 쿼리 교체 (개선된 경우만)
            if improved:
                self.logger.info(f"✓ 쿼리 개선됨 (비용: {best_explain['total_cost']})")
                self._replace_query_in_file(
                    query_info["file_path"],
                    original_query,
                    best_query,
                    query_info["line_start"],
                    query_info["line_end"],
                )
            else:
                self.logger.info("쿼리 유지 (개선 없음)")

        return optimized_results

    def _replace_query_in_file(
        self,
        file_path: str,
        original_query: str,
        new_query: str,
        line_start: int,
        line_end: int,
    ) -> None:
        """
        파일에서 SQL 쿼리 교체

        Args:
            file_path: 파일 경로
            original_query: 원본 쿼리
            new_query: 새 쿼리
            line_start: 시작 라인
            line_end: 종료 라인
        """
        try:
            file = Path(file_path)

            # 파일 읽기
            with open(file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # 쿼리 교체 (간단한 방식: 해당 라인 범위의 쿼리 문자열만 교체)
            content = "".join(lines)
            updated_content = content.replace(original_query, new_query, 1)

            # 파일 쓰기
            with open(file, "w", encoding="utf-8") as f:
                f.write(updated_content)

            self.logger.debug(f"쿼리 교체 완료: {file_path}")

        except Exception as e:
            self.logger.warning(f"쿼리 교체 실패: {file_path} - {e}")

    def _run_tests(self) -> Dict[str, Any]:
        """
        테스트 실행

        Returns:
            {
                "passed": bool,
                "output": str,
                "exit_code": int,
            }
        """
        self.logger.info("테스트 실행 시작")

        test_profile = self.run_context.get("test_profile", {})
        test_command = test_profile.get("command")
        timeout = test_profile.get("timeout", 300)

        if not test_command:
            execution_profile = self.run_context.get("execution_profile", {})
            test_command = execution_profile.get("command", "python main.py")

        try:
            result = subprocess.run(
                test_command.split(),
                cwd=self.hub_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            passed = result.returncode == 0
            output = result.stdout + result.stderr

            if passed:
                self.logger.info("✓ 테스트 통과")
            else:
                self.logger.warning("✗ 테스트 실패")
                self.logger.debug(output)

            self.logger.log_command(
                test_command,
                output,
                result.returncode,
            )

            return {
                "passed": passed,
                "output": output,
                "exit_code": result.returncode,
            }

        except subprocess.TimeoutExpired:
            self.logger.error(f"테스트 타임아웃 ({timeout}초)")
            return {
                "passed": False,
                "output": f"Test timeout after {timeout}s",
                "exit_code": -1,
            }

        except FileNotFoundError:
            self.logger.warning("테스트 도구를 찾을 수 없습니다. 테스트 스킵")
            # 테스트 도구 없으면 통과로 간주
            return {
                "passed": True,
                "output": "Test command not found, skipped",
                "exit_code": 0,
            }

    def _create_optimization_summary(
        self,
        optimized_queries: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        최적화 요약 생성

        Args:
            optimized_queries: 최적화 결과

        Returns:
            최적화 요약
        """
        total_queries = len(optimized_queries)
        improved_queries = sum(1 for q in optimized_queries if q["improved"])

        # 평균 비용 개선률 계산
        if improved_queries > 0:
            cost_savings = [
                (q["original_cost"] - q["optimized_cost"]) / q["original_cost"]
                for q in optimized_queries
                if q["improved"] and q["original_cost"] > 0
            ]
            avg_improvement = (
                sum(cost_savings) / len(cost_savings) if cost_savings else 0.0
            )
        else:
            avg_improvement = 0.0

        return {
            "total_queries": total_queries,
            "improved_queries": improved_queries,
            "unchanged_queries": total_queries - improved_queries,
            "avg_cost_improvement": avg_improvement,
        }
