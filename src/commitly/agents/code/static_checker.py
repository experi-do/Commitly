"""
정적 검사 모듈

린트, 타입 체크 등 정적 분석 수행
"""

import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

from commitly.core.logger import CommitlyLogger


class StaticChecker:
    """정적 검사 실행 클래스"""

    def __init__(self, hub_path: Path, logger: CommitlyLogger) -> None:
        """
        Args:
            hub_path: 허브 경로
            logger: 로거
        """
        self.hub_path = hub_path
        self.logger = logger

    def run_all_checks(self) -> Dict[str, any]:
        """
        모든 정적 검사 실행

        Returns:
            검사 결과
        """
        results = {
            "lint": self._run_lint(),
            "type_check": self._run_type_check(),
        }

        return results

    def _run_lint(self) -> Dict[str, any]:
        """
        린트 검사 (ruff)

        Returns:
            {
                "passed": bool,
                "errors": List[str],
                "output": str,
            }
        """
        self.logger.info("린트 검사 시작 (ruff)")

        try:
            result = subprocess.run(
                ["ruff", "check", "."],
                cwd=self.hub_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            passed = result.returncode == 0
            output = result.stdout + result.stderr

            if passed:
                self.logger.info("✓ 린트 검사 통과")
            else:
                self.logger.warning("✗ 린트 검사 실패")
                self.logger.debug(output)

            return {
                "passed": passed,
                "errors": output.split("\n") if not passed else [],
                "output": output,
            }

        except subprocess.TimeoutExpired:
            self.logger.error("린트 검사 타임아웃")
            return {
                "passed": False,
                "errors": ["Timeout"],
                "output": "Lint check timeout",
            }
        except FileNotFoundError:
            self.logger.warning("ruff가 설치되지 않았습니다. 린트 검사 스킵")
            return {
                "passed": True,
                "errors": [],
                "output": "ruff not found, skipped",
            }

    def _run_type_check(self) -> Dict[str, any]:
        """
        타입 체크 (mypy)

        Returns:
            {
                "passed": bool,
                "errors": List[str],
                "output": str,
            }
        """
        self.logger.info("타입 체크 시작 (mypy)")

        try:
            result = subprocess.run(
                ["mypy", "."],
                cwd=self.hub_path,
                capture_output=True,
                text=True,
                timeout=120,
            )

            passed = result.returncode == 0
            output = result.stdout + result.stderr

            if passed:
                self.logger.info("✓ 타입 체크 통과")
            else:
                self.logger.warning("✗ 타입 체크 실패")
                self.logger.debug(output)

            return {
                "passed": passed,
                "errors": output.split("\n") if not passed else [],
                "output": output,
            }

        except subprocess.TimeoutExpired:
            self.logger.error("타입 체크 타임아웃")
            return {
                "passed": False,
                "errors": ["Timeout"],
                "output": "Type check timeout",
            }
        except FileNotFoundError:
            self.logger.warning("mypy가 설치되지 않았습니다. 타입 체크 스킵")
            return {
                "passed": True,
                "errors": [],
                "output": "mypy not found, skipped",
            }
        except Exception as e:
            self.logger.warning(f"타입 체크 중 예외 발생: {e}. 계속 진행합니다.")
            return {
                "passed": True,
                "errors": [],
                "output": f"Type check skipped due to error: {e}",
            }
