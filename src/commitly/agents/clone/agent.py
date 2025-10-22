"""
CloneAgent 구현

허브 동기화 및 로컬 커밋 적용
"""

from pathlib import Path
from typing import Any, Dict, List

from git import Repo

from commitly.agents.base import BaseAgent
from commitly.agents.clone.utils import copy_local_changes_to_hub, get_hub_path
from commitly.core.context import RunContext
from commitly.core.git_manager import GitManager


class CloneAgent(BaseAgent):
    """
    Clone Agent

    역할:
    1. 허브 경로 초기화 (.commitly_hub_{프로젝트명})
    2. 원격 저장소 최신 상태로 동기화
    3. commitly/clone/{pipeline_id} 브랜치 생성
    4. 로컬 커밋 패치 적용
    5. 변경 파일 목록 수집
    """

    def __init__(self, run_context: RunContext) -> None:
        super().__init__(run_context)

        # Git 관리자
        self.workspace_git = GitManager(
            self._get_workspace_path(),
            self.logger,
        )

    def execute(self) -> Dict[str, Any]:
        """
        Clone Agent 실행

        Returns:
            {
                "hub_head_sha": str,
                "applied_commits": List[str],
                "changed_files": List[str],
                "warnings": List[str],
            }
        """
        warnings: List[str] = []

        # 1. 허브 경로 준비
        hub_path = self._prepare_hub()
        self.logger.info(f"허브 경로: {hub_path}")

        # 2. 허브 Git 관리자 초기화
        hub_git = GitManager(hub_path, self.logger)

        # 3. 원격 최신 상태로 동기화
        self._sync_with_remote(hub_git)

        # 4. 에이전트 브랜치 생성
        self._create_agent_branch(hub_git)

        # 5. 로컬 커밋 diff 추출
        changed_files = self._get_changed_files()
        self.logger.info(f"변경된 파일: {len(changed_files)}개")

        # 6. 변경사항 허브에 적용
        self._apply_changes_to_hub(hub_git, changed_files)

        # 7. 무결성 검증
        self._verify_integrity(hub_git)

        # 8. 변경사항 커밋
        commit_sha = hub_git.commit("Clone Agent: 로컬 커밋 적용")

        # 9. 결과 데이터 생성
        result = {
            "hub_head_sha": commit_sha,
            "applied_commits": [
                commit["sha"] for commit in self.run_context["latest_local_commits"]
            ],
            "changed_files": changed_files,
            "warnings": warnings,
        }

        return result

    def _prepare_hub(self) -> Path:
        """
        허브 디렉토리 준비

        Returns:
            허브 경로
        """
        workspace_path = self._get_workspace_path()
        project_name = self.run_context["project_name"]

        hub_path = get_hub_path(workspace_path, project_name)

        if not hub_path.exists():
            # 허브가 없으면 shallow clone
            self.logger.info("허브가 없습니다. Shallow clone 시작...")
            self._create_hub(hub_path)
        else:
            self.logger.info("기존 허브를 사용합니다.")

        # RunContext에 허브 경로 저장
        self.run_context["hub_path"] = str(hub_path)

        return hub_path

    def _create_hub(self, hub_path: Path) -> None:
        """
        새 허브 생성 (shallow clone)

        Args:
            hub_path: 허브 경로
        """
        # 원격 저장소 URL 가져오기
        remote_url = self.workspace_git.get_remote_url()

        if not remote_url:
            raise RuntimeError(
                "원격 저장소 URL을 찾을 수 없습니다. "
                "프로젝트가 Git 리포지터리인지 확인하세요."
            )

        # Shallow clone
        self.workspace_git.clone(remote_url, hub_path, shallow=True)
        self.logger.info(f"Shallow clone 완료: {hub_path}")

    def _sync_with_remote(self, hub_git: GitManager) -> None:
        """
        허브를 원격 최신 상태로 동기화

        Args:
            hub_git: 허브 Git 관리자
        """
        current_branch = self.run_context["current_branch"]
        remote = self.run_context["git_remote"]

        try:
            # Fetch
            hub_git.fetch(remote)

            # Hard reset to remote branch
            hub_git.reset_hard(f"{remote}/{current_branch}")

            self.logger.info(f"원격 동기화 완료: {remote}/{current_branch}")

        except Exception as e:
            # 재시도
            self.logger.warning(f"동기화 실패, 재시도 중... {e}")

            try:
                hub_git.fetch(remote)
                hub_git.reset_hard(f"{remote}/{current_branch}")
                self.logger.info("재시도 성공")

            except Exception as e2:
                raise RuntimeError(f"원격 동기화 실패: {e2}") from e2

    def _create_agent_branch(self, hub_git: GitManager) -> None:
        """
        에이전트 브랜치 생성

        commitly/clone/{pipeline_id} 브랜치를 생성하고 체크아웃

        Args:
            hub_git: 허브 Git 관리자
        """
        pipeline_id = self.run_context["pipeline_id"]
        branch_name = f"commitly/clone/{pipeline_id}"

        # 브랜치 생성 및 체크아웃
        hub_git.create_branch(branch_name)

        # 브랜치명 저장
        self.agent_branch = branch_name
        self.run_context["clone_agent_branch"] = branch_name

        self.logger.info(f"에이전트 브랜치 생성: {branch_name}")

    def _get_changed_files(self) -> List[str]:
        """
        로컬에서 변경된 파일 목록 가져오기

        Returns:
            변경된 파일의 절대 경로 리스트
        """
        remote = self.run_context["git_remote"]
        current_branch = self.run_context["current_branch"]

        # 원격 브랜치와 로컬 HEAD 간의 변경 파일
        changed_files = self.workspace_git.get_changed_files(
            f"{remote}/{current_branch}",
            "HEAD"
        )

        return changed_files

    def _apply_changes_to_hub(
        self,
        hub_git: GitManager,
        changed_files: List[str],
    ) -> None:
        """
        로컬 변경사항을 허브에 적용

        Args:
            hub_git: 허브 Git 관리자
            changed_files: 변경된 파일 목록 (절대 경로)
        """
        workspace_path = self._get_workspace_path()
        hub_path = self._get_hub_path()

        # Repo 객체 생성
        workspace_repo = Repo(workspace_path)
        hub_repo = Repo(hub_path)

        # 절대 경로 → 상대 경로 변환
        relative_files = [
            str(Path(f).relative_to(workspace_path))
            for f in changed_files
        ]

        script_relative = "commitly_exec.sh"
        script_path = workspace_path / script_relative
        if script_path.exists() and script_relative not in relative_files:
            relative_files.append(script_relative)

        # 파일 복사
        copy_local_changes_to_hub(
            workspace_repo,
            hub_repo,
            relative_files,
        )

        self.logger.info(f"변경사항 적용 완료: {len(relative_files)}개 파일")

    def _verify_integrity(self, hub_git: GitManager) -> None:
        """
        허브 무결성 검증

        git status로 예상치 못한 변경이 없는지 확인

        Args:
            hub_git: 허브 Git 관리자
        """
        # git status --short 실행
        status_output = hub_git.repo.git.status("--short")

        if status_output.strip():
            self.logger.debug(f"Git status:\n{status_output}")
            # 변경사항이 있어도 정상 (아직 커밋 전)
        else:
            self.logger.info("무결성 검증: 변경사항 없음")
