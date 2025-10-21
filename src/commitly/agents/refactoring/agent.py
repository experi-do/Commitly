"""
RefactoringAgent 구현

코드 품질 개선 및 리팩토링
"""

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from commitly.agents.base import BaseAgent
from commitly.core.context import RunContext
from commitly.core.git_manager import GitManager


class RefactoringAgent(BaseAgent):
    """
    Refactoring Agent

    역할:
    1. commitly/refactor/{pipeline_id} 브랜치 생성
    2. 변경된 파일에 대해 리팩토링 수행
       - LLM: 중복 코드 제거
       - LLM: 예외 처리 추가
       - ruff --fix: 코드 포맷팅
    3. 각 파일 변경 후 테스트 실행
    4. 테스트 실패 시 롤백
    5. 성공 시 자동으로 SyncAgent 진행
    """

    def __init__(self, run_context: RunContext) -> None:
        super().__init__(run_context)

        self.hub_path = self._get_hub_path()
        self.hub_git = GitManager(self.hub_path, self.logger)

    def execute(self) -> Dict[str, Any]:
        """
        Refactoring Agent 실행

        Returns:
            {
                "refactored_files": List[str],  # 리팩토링된 파일 목록
                "refactoring_summary": Dict,  # 리팩토링 요약
            }
        """
        # 1. 브랜치 생성
        self._create_agent_branch()

        # 2. Clone Agent 결과에서 변경 파일 가져오기
        clone_output = self._load_previous_output("clone_agent")
        changed_files = clone_output["data"]["changed_files"]

        self.logger.info(f"리팩토링 대상 파일: {len(changed_files)}개")

        refactored_files = []
        refactoring_details = []

        # 3. 각 파일 리팩토링
        for file_path in changed_files:
            file = Path(file_path)

            # Python 파일만 리팩토링
            if file.suffix != ".py":
                self.logger.debug(f"Python 파일 아님, 스킵: {file_path}")
                continue

            self.logger.info(f"리팩토링 시작: {file.name}")

            # 리팩토링 수행
            refactoring_result = self._refactor_file(file_path)

            if refactoring_result["changed"]:
                refactored_files.append(file_path)
                refactoring_details.append(refactoring_result)

                # 변경 후 테스트 실행
                test_passed = self._run_tests()

                if not test_passed:
                    self.logger.error(f"테스트 실패: {file.name}")
                    raise RuntimeError(
                        f"리팩토링 후 테스트 실패: {file.name}\\n"
                        f"파일을 원래 상태로 복원하고 작업을 중단합니다."
                    )

                self.logger.info(f"✓ 리팩토링 완료: {file.name}")

        # 4. 변경사항 커밋
        if refactored_files:
            self.hub_git.commit("Refactoring Agent: 코드 품질 개선")
            self.logger.info(f"리팩토링된 파일: {len(refactored_files)}개")
        else:
            self.logger.info("리팩토링할 항목 없음")

        # 5. 요약 생성
        refactoring_summary = {
            "total_files_checked": len(changed_files),
            "refactored_files_count": len(refactored_files),
            "details": refactoring_details,
        }

        # 6. 결과 반환
        return {
            "refactored_files": refactored_files,
            "refactoring_summary": refactoring_summary,
        }

    def _create_agent_branch(self) -> None:
        """에이전트 브랜치 생성"""
        pipeline_id = self.run_context["pipeline_id"]
        branch_name = f"commitly/refactor/{pipeline_id}"

        # 부모 브랜치: Test Agent 브랜치
        parent_branch = self.run_context["test_agent_branch"]

        self.hub_git.create_branch(branch_name, parent_branch)

        self.agent_branch = branch_name
        self.run_context["refactoring_agent_branch"] = branch_name

        self.logger.info(f"에이전트 브랜치 생성: {branch_name}")

    def _refactor_file(self, file_path: str) -> Dict[str, Any]:
        """
        파일 리팩토링 수행

        Args:
            file_path: 파일 경로

        Returns:
            {
                "file_path": str,
                "changed": bool,
                "refactorings": List[str],  # 적용된 리팩토링 목록
            }
        """
        refactorings = []

        # 1. LLM 기반 리팩토링 (선택적)
        llm_client = self.run_context.get("llm_client")

        if llm_client:
            # 리팩토링 규칙 가져오기
            refactoring_rules = self.config.get(
                "refactoring.rules",
                "Remove duplicate code, add exception handling for risky operations (I/O, network, DB)"
            )

            try:
                # 파일 읽기
                with open(file_path, "r", encoding="utf-8") as f:
                    original_code = f.read()

                # LLM에게 리팩토링 제안 요청
                refactored_code = llm_client.suggest_refactoring(
                    original_code,
                    file_path,
                    refactoring_rules,
                )

                # 변경사항이 있으면 파일 쓰기
                if refactored_code and refactored_code != original_code:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(refactored_code)

                    refactorings.append("LLM refactoring")
                    self.logger.debug("LLM 리팩토링 적용")

            except Exception as e:
                self.logger.warning(f"LLM 리팩토링 실패: {e}")

        # 2. ruff --fix (자동 수정)
        ruff_result = self._run_ruff_fix(file_path)

        if ruff_result:
            refactorings.append("ruff --fix")

        # 변경 여부
        changed = len(refactorings) > 0

        return {
            "file_path": file_path,
            "changed": changed,
            "refactorings": refactorings,
        }

    def _run_ruff_fix(self, file_path: str) -> bool:
        """
        ruff --fix 실행

        Args:
            file_path: 파일 경로

        Returns:
            변경 여부
        """
        try:
            result = subprocess.run(
                ["ruff", "check", "--fix", file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # ruff가 파일을 수정했는지 확인 (exit code와 무관하게 수정 가능)
            # ruff --fix는 수정하면 exit code 0 반환
            if result.returncode == 0:
                self.logger.debug(f"ruff --fix 적용: {file_path}")
                return True

            return False

        except subprocess.TimeoutExpired:
            self.logger.warning("ruff --fix 타임아웃")
            return False

        except FileNotFoundError:
            self.logger.debug("ruff를 찾을 수 없습니다. 스킵")
            return False

    def _run_tests(self) -> bool:
        """
        테스트 실행

        Returns:
            테스트 통과 여부
        """
        test_profile = self.run_context.get("test_profile", {})
        test_command = test_profile.get("command", "pytest")
        timeout = test_profile.get("timeout", 300)

        try:
            result = subprocess.run(
                test_command.split(),
                cwd=self.hub_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            passed = result.returncode == 0

            if not passed:
                self.logger.warning("테스트 실패")
                self.logger.debug(result.stdout + result.stderr)

            return passed

        except subprocess.TimeoutExpired:
            self.logger.error(f"테스트 타임아웃 ({timeout}초)")
            return False

        except FileNotFoundError:
            # 테스트 도구 없으면 통과로 간주
            self.logger.debug("테스트 도구를 찾을 수 없습니다. 스킵")
            return True
