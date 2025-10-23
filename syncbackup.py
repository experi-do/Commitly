"""
SyncAgent 구현

허브 변경사항을 로컬 및 원격 저장소에 동기화
"""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from commitly.agents.base import BaseAgent
from commitly.core.context import RunContext
from commitly.core.git_manager import GitManager


class SyncAgent(BaseAgent):
    """
    Sync Agent

    역할:
    1. 허브의 최종 변경사항 요약 생성
    2. 사용자 승인 요청 (⚠️ 파이프라인의 유일한 승인 지점)
    3. 승인 시:
       - 허브 변경사항을 로컬 워킹 트리에 적용
       - 원격 저장소에 push
       - 허브 브랜치 정리
    4. 거부 시:
       - 로그만 저장, 허브 상태 유지
    5. 자동으로 SlackAgent 진행
    """

    def __init__(self, run_context: RunContext) -> None:
        super().__init__(run_context)

        self.hub_path = self._get_hub_path()
        self.workspace_path = self._get_workspace_path()

        self.hub_git = GitManager(self.hub_path, self.logger)
        self.workspace_git = GitManager(self.workspace_path, self.logger)

    def execute(self) -> Dict[str, Any]:
        """
        Sync Agent 실행

        Returns:
            {
                "user_approved": bool,
                "pushed": bool,
                "commit_sha": str,
                "commit_message": str,
                "remote_branch": str,
                "sync_time": str,
                "branches_deleted": List[str],
            }
        """
        # 1. 변경사항 요약 생성
        summary = self._generate_change_summary()
        sync_started_at = datetime.now()
        target_branch = self._build_remote_branch_name(sync_started_at)
        self.run_context["sync_agent_branch"] = target_branch

        # 2. 사용자 승인 요청
        user_approved = self._request_user_approval(summary, target_branch)

        # 결과 초기화
        result = {
            "user_approved": user_approved,
            "pushed": False,
            "commit_sha": "",
            "commit_message": "",
            "remote_branch": target_branch,
            "sync_time": sync_started_at.isoformat(),
            "branches_deleted": [],
        }

        # 3. 승인 시 동작
        if user_approved:
            self.logger.info("사용자 승인됨, 동기화 시작")

            # 허브 → 로컬 적용
            self._apply_hub_to_local()

            user_message = self.run_context.get("user_commit_message")
            if user_message:
                self._create_summary_commit(user_message)

            # 허브 커밋 내역 출력
            self._print_commit_history(summary["base_branch"], summary["final_branch"])

            # 원격 push
            commit_sha = self._push_to_remote(target_branch, summary["final_branch"])

            # 브랜치 정리
            deleted_branches = self._cleanup_hub_branches()

            # 결과 업데이트
            result["pushed"] = True
            result["commit_sha"] = commit_sha
            result["commit_message"] = user_message or summary["commit_message"]
            result["branches_deleted"] = deleted_branches

            self.logger.info(f"✓ 원격 동기화 완료: {commit_sha}")

        else:
            # 4. 거부 시 동작
            self.logger.info("사용자가 push를 거부했습니다. 허브 상태 유지")
            self.logger.info(
                "수동 push: cd {hub} && git push {remote} {source}:{branch}".format(
                    hub=self.hub_path,
                    remote=self.run_context["git_remote"],
                    source=summary["final_branch"],
                    branch=target_branch,
                )
            )

        # 5. 결과 반환
        return result

    def _generate_change_summary(self) -> Dict[str, Any]:
        """
        변경사항 요약 생성

        Returns:
            {
                "commit_message": str,
                "changed_files": List[str],
                "stats": Dict[str, int],  # additions, deletions
                "agent_results": Dict,  # Code/Test/Refactoring 통계
            }
        """
        self.logger.info("변경사항 요약 생성")

        # 최종 브랜치: Refactoring Agent 브랜치
        final_branch = self.run_context["refactoring_agent_branch"]

        # 원격 브랜치
        remote = self.run_context["git_remote"]
        current_branch = self.run_context["current_branch"]
        base_branch = f"{remote}/{current_branch}"

        # Hub에서 변경 파일 가져오기
        changed_files = self.hub_git.get_changed_files(base_branch, final_branch)

        # Git diff stats
        stats = self._get_diff_stats(base_branch, final_branch)

        # 커밋 메시지 결정
        latest_commits = self.run_context.get("latest_local_commits", [])
        commit_message = (
            latest_commits[0]["message"] if latest_commits else "Commitly: 변경사항 적용"
        )
        user_message = self.run_context.get("user_commit_message")
        if user_message:
            commit_message = user_message

        # 이전 에이전트 결과 집계
        agent_results = self._collect_agent_results()

        return {
            "commit_message": commit_message,
            "changed_files": changed_files,
            "stats": stats,
            "agent_results": agent_results,
            "base_branch": base_branch,
            "final_branch": final_branch,
        }

    def _get_diff_stats(self, base: str, head: str) -> Dict[str, int]:
        """
        Git diff 통계 가져오기

        Args:
            base: 베이스 브랜치
            head: 비교 브랜치

        Returns:
            {"additions": int, "deletions": int, "files_changed": int}
        """
        try:
            # git diff --shortstat
            result = self.hub_git.repo.git.diff("--shortstat", base, head)

            # 파싱 (예: "3 files changed, 120 insertions(+), 45 deletions(-)")
            import re

            match = re.search(
                r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?",
                result,
            )

            if match:
                files_changed = int(match.group(1))
                additions = int(match.group(2) or 0)
                deletions = int(match.group(3) or 0)

                return {
                    "files_changed": files_changed,
                    "additions": additions,
                    "deletions": deletions,
                }

            return {"files_changed": 0, "additions": 0, "deletions": 0}

        except Exception as e:
            self.logger.warning(f"diff stats 조회 실패: {e}")
            return {"files_changed": 0, "additions": 0, "deletions": 0}

    def _collect_agent_results(self) -> Dict[str, Any]:
        """
        이전 에이전트 결과 수집

        Returns:
            각 에이전트의 주요 통계
        """
        results = {}

        # Code Agent
        try:
            code_output = self._load_previous_output("code_agent")
            results["code_agent"] = {
                "has_query": code_output["data"].get("hasQuery", False),
                "query_count": len(code_output["data"].get("queryFileList", [])),
            }
        except Exception:
            results["code_agent"] = {}

        # Test Agent
        try:
            test_output = self._load_previous_output("test_agent")
            opt_summary = test_output["data"].get("optimization_summary", {})
            results["test_agent"] = {
                "optimized_queries": opt_summary.get("improved_queries", 0),
                "total_queries": opt_summary.get("total_queries", 0),
            }
        except Exception:
            results["test_agent"] = {}

        # Refactoring Agent
        try:
            refactor_output = self._load_previous_output("refactoring_agent")
            refactor_summary = refactor_output["data"].get("refactoring_summary", {})
            results["refactoring_agent"] = {
                "refactored_files": refactor_summary.get("refactored_files_count", 0),
                "total_files": refactor_summary.get("total_files_checked", 0),
            }
        except Exception:
            results["refactoring_agent"] = {}

        return results

    def _request_user_approval(self, summary: Dict[str, Any], target_branch: str) -> bool:
        """
        사용자 승인 요청

        Args:
            summary: 변경사항 요약
            target_branch: push 대상 브랜치 이름

        Returns:
            승인 여부
        """
        # 간결한 요약 출력
        print("\n📋 변경사항 요약")
        print(f"커밋: \"{summary['commit_message']}\"")

        files_changed = summary['stats']['files_changed']
        additions = summary['stats']['additions']
        deletions = summary['stats']['deletions']
        print(f"파일: {files_changed}개 변경 (+{additions}/-{deletions} 라인)")

        # 에이전트 결과 요약
        agent_results = summary["agent_results"]
        highlights = []

        if agent_results.get("code_agent", {}).get("has_query"):
            highlights.append(f"SQL 쿼리 {agent_results['code_agent']['query_count']}개")

        if agent_results.get("test_agent", {}).get("optimized_queries", 0) > 0:
            highlights.append(f"SQL 최적화 {agent_results['test_agent']['optimized_queries']}개")

        if agent_results.get("refactoring_agent", {}).get("refactored_files", 0) > 0:
            highlights.append(f"리팩토링 {agent_results['refactoring_agent']['refactored_files']}개 파일")

        if highlights:
            print(", ".join(highlights))

        # 승인 요청 (상세 보기 옵션 포함)
        remote_branch = f"{self.run_context['git_remote']}/{target_branch}"
        while True:
            response = input(
                f"\nPush 하시겠습니까? (y/n/d[상세보기]): "
            ).strip().lower()

            if response == "d":
                # 상세 정보 표시
                self._show_detailed_summary(summary, agent_results)
                continue
            elif response in ["y", "n"]:
                approved = response == "y"
                self.logger.info(f"사용자 입력: {response} (승인: {approved})")
                return approved
            else:
                print("올바른 입력이 아닙니다. y, n, 또는 d를 입력하세요.")

    def _show_detailed_summary(self, summary: Dict[str, Any], agent_results: Dict[str, Any]) -> None:
        """
        상세한 변경사항 표시

        Args:
            summary: 변경사항 요약
            agent_results: 에이전트 결과
        """
        print("\n" + "=" * 60)
        print("📋 상세 변경사항")
        print("=" * 60)

        print(f"\n커밋 메시지: {summary['commit_message']}")
        print(f"변경 파일: {summary['stats']['files_changed']}개")
        print(f"추가: +{summary['stats']['additions']} 라인")
        print(f"삭제: -{summary['stats']['deletions']} 라인")

        # Code Agent 결과
        if agent_results.get("code_agent"):
            code_data = agent_results["code_agent"]
            print("\n[Code Agent]")
            if code_data.get("has_query"):
                print(f"  - SQL 쿼리: {code_data['query_count']}개 발견")
            if code_data.get("static_check_passed"):
                print("  - 정적 검사: 통과")

        # Test Agent 결과
        if agent_results.get("test_agent"):
            test_data = agent_results["test_agent"]
            print("\n[Test Agent]")
            if test_data.get("optimized_queries", 0) > 0:
                print(f"  - SQL 최적화: {test_data['optimized_queries']}개 쿼리 개선")
            if test_data.get("test_passed"):
                print("  - 테스트: 통과")

        # Refactoring Agent 결과
        if agent_results.get("refactoring_agent"):
            refactor_data = agent_results["refactoring_agent"]
            print("\n[Refactoring Agent]")
            if refactor_data.get("refactored_files", 0) > 0:
                print(f"  - 리팩토링: {refactor_data['refactored_files']}개 파일 개선")

        print("\n" + "=" * 60)

    def _apply_hub_to_local(self) -> None:
        """
        허브 변경사항을 로컬 워킹 트리에 적용
        """
        self.logger.info("허브 변경사항을 로컬에 적용 중...")

        # Clone Agent 결과에서 변경 파일 가져오기
        clone_output = self._load_previous_output("clone_agent")
        changed_files = clone_output["data"]["changed_files"]

        # 파일 복사 (허브 → 로컬)
        for local_file_path in changed_files:
            local_file = Path(local_file_path)

            # 상대 경로 계산 (로컬 기준)
            try:
                rel_path = local_file.relative_to(self.workspace_path)
            except ValueError:
                # 이미 상대 경로인 경우
                rel_path = Path(local_file_path)

            # 허브에서의 파일 경로
            hub_file = self.hub_path / rel_path

            # 파일 복사
            try:
                # 디렉토리 생성
                local_file.parent.mkdir(parents=True, exist_ok=True)

                # 파일이 허브에 존재하면 복사
                if hub_file.exists():
                    import shutil

                    # 같은 파일인지 확인
                    if hub_file.resolve() != local_file.resolve():
                        shutil.copy2(hub_file, local_file)
                        self.logger.debug(f"복사: {rel_path}")
                    else:
                        self.logger.debug(f"이미 최신: {rel_path}")

            except Exception as e:
                self.logger.warning(f"파일 복사 실패: {rel_path} - {e}")

        # Git add
        self.workspace_git.repo.git.add(".")

        self.logger.info("✓ 로컬 반영 완료")

    def _push_to_remote(self, branch: str, source_branch: str) -> str:
        """
        원격 저장소에 push

        Returns:
            커밋 SHA
        """
        self.logger.info("원격 저장소에 push 중...")

        remote = self.run_context["git_remote"]

        max_retries = 3

        for attempt in range(1, max_retries + 1):
            try:
                result = subprocess.run(
                    ["git", "push", remote, f"{source_branch}:{branch}"],
                    cwd=self.hub_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if result.returncode == 0:
                    commit_sha = self.hub_git.repo.commit(source_branch).hexsha

                    self.logger.info(f"✓ Push 성공: {remote}/{branch} ({commit_sha})")
                    self.logger.log_command(
                        f"git push {remote} {source_branch}:{branch}",
                        result.stdout,
                        result.returncode,
                    )

                    return commit_sha

                else:
                    self.logger.warning(f"Push 실패 (시도 {attempt}/{max_retries})")
                    self.logger.debug(result.stderr)

                    if attempt == max_retries:
                        raise RuntimeError(f"Push 실패: {result.stderr}")

            except subprocess.TimeoutExpired:
                self.logger.error("Push 타임아웃")
                raise RuntimeError("Push 타임아웃")

            except Exception as e:
                if attempt == max_retries:
                    raise RuntimeError(f"Push 실패: {e}")

                self.logger.warning(f"재시도 {attempt}/{max_retries}")

        raise RuntimeError("Push 실패")

    def _create_summary_commit(self, message: str) -> None:
        """사용자 지정 메시지를 허브에 빈 커밋으로 기록"""
        try:
            self.hub_git.repo.git.commit("--allow-empty", "-m", message)
            self.logger.info(f"사용자 지정 커밋 메시지 적용: {message}")
        except Exception as exc:
            self.logger.warning(f"사용자 커밋 메시지 작성 실패: {exc}")

    def _cleanup_hub_branches(self) -> List[str]:
        """
        허브의 모든 commitly/* 브랜치 삭제

        Returns:
            삭제된 브랜치 목록
        """
        self.logger.info("허브 브랜치 정리 중...")

        try:
            # 1단계: 안전한 브랜치로 체크아웃 (main 또는 origin/main)
            remote = self.run_context["git_remote"]
            current_branch = self.run_context["current_branch"]

            try:
                self.hub_git.checkout(current_branch)
                self.logger.debug(f"체크아웃: {current_branch}")
            except Exception:
                # 브랜치가 없으면 origin/main으로 reset
                try:
                    self.hub_git.reset_hard(f"{remote}/{current_branch}")
                    self.logger.debug(f"Reset: {remote}/{current_branch}")
                except Exception as e:
                    self.logger.warning(f"브랜치 전환 실패: {e}")

            # 2단계: commitly/* 브랜치 삭제
            deleted_branches = self.hub_git.delete_branches_with_prefix("commitly/")

            self.logger.info(f"✓ {len(deleted_branches)}개 브랜치 삭제")

            return deleted_branches

        except Exception as e:
            self.logger.warning(f"브랜치 정리 실패: {e}")
            # 치명적 오류 아님, 계속 진행
            return []

    def _print_commit_history(self, base_branch: str, head_branch: str) -> None:
        """허브에 누적된 커밋 기록 출력"""
        try:
            log_output = self.hub_git.repo.git.log("--oneline", f"{base_branch}..{head_branch}")
            if log_output.strip():
                self.logger.info("허브 커밋 내역 (push 예정):")
                for line in log_output.splitlines():
                    self.logger.info(f"  {line}")
            else:
                self.logger.info("허브 커밋 내역: 새로운 커밋 없음")
        except Exception as exc:
            self.logger.warning(f"허브 커밋 로그 조회 실패: {exc}")

    def _build_remote_branch_name(self, sync_time: datetime) -> str:
        """
        원격으로 push할 새 브랜치 이름 생성

        Args:
            sync_time: 동기화 시작 시각

        Returns:
            새 원격 브랜치 이름
        """
        base_branch = self.run_context["current_branch"]
        pipeline_id = self.run_context.get("pipeline_id", "")
        short_pipeline_id = pipeline_id.split("-")[0] if pipeline_id else "pipeline"
        timestamp = sync_time.strftime("%Y%m%d%H%M%S")

        return f"commitly/sync/{base_branch}-{timestamp}-{short_pipeline_id}"
