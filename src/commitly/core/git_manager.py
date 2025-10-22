"""
Git 관리 모듈

Git 명령어 실행, 브랜치 관리, diff 계산 등 Git 관련 공통 기능을 제공합니다.
"""

import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from git import Repo
from git.exc import GitCommandError

from commitly.core.logger import CommitlyLogger


class GitManager:
    """
    Git 관리 클래스

    GitPython 라이브러리를 사용하여 Git 작업을 수행합니다.
    """

    def __init__(self, repo_path: Path, logger: CommitlyLogger) -> None:
        """
        Args:
            repo_path: Git 리포지터리 경로
            logger: 로거 인스턴스
        """
        self.repo_path = repo_path
        self.logger = logger

        try:
            self.repo = Repo(repo_path)
        except Exception as e:
            raise ValueError(f"유효한 Git 리포지터리가 아닙니다: {repo_path}") from e

    def get_current_branch(self) -> str:
        """현재 브랜치 이름 반환"""
        return self.repo.active_branch.name

    def create_branch(self, branch_name: str, parent_branch: Optional[str] = None) -> None:
        """
        새 브랜치 생성 및 체크아웃

        Args:
            branch_name: 생성할 브랜치 이름
            parent_branch: 부모 브랜치 (None이면 현재 브랜치)
        """
        try:
            if parent_branch:
                # 부모 브랜치에서 새 브랜치 생성
                parent = self.repo.heads[parent_branch]
                new_branch = self.repo.create_head(branch_name, parent)
            else:
                # 현재 브랜치에서 새 브랜치 생성
                new_branch = self.repo.create_head(branch_name)

            new_branch.checkout()
            self.logger.info(f"브랜치 생성 및 체크아웃: {branch_name}")

        except Exception as e:
            self.logger.error(f"브랜치 생성 실패: {branch_name}")
            raise RuntimeError(f"브랜치 생성 실패: {e}") from e

    def delete_branch(self, branch_name: str, force: bool = False) -> None:
        """
        브랜치 삭제

        Args:
            branch_name: 삭제할 브랜치 이름
            force: 강제 삭제 여부
        """
        try:
            self.repo.delete_head(branch_name, force=force)
            self.logger.info(f"브랜치 삭제: {branch_name}")
        except Exception as e:
            self.logger.warning(f"브랜치 삭제 실패: {branch_name} - {e}")

    def delete_branches_with_prefix(self, prefix: str) -> List[str]:
        """
        특정 prefix로 시작하는 모든 브랜치 삭제

        Args:
            prefix: 브랜치 이름 prefix (예: "commitly/")

        Returns:
            삭제된 브랜치 이름 리스트
        """
        deleted = []
        for branch in self.repo.heads:
            if branch.name.startswith(prefix):
                try:
                    self.repo.delete_head(branch, force=True)
                    deleted.append(branch.name)
                    self.logger.info(f"브랜치 삭제: {branch.name}")
                except Exception as e:
                    self.logger.warning(f"브랜치 삭제 실패: {branch.name} - {e}")

        return deleted

    def commit(self, message: str) -> str:
        """
        변경사항 커밋

        Args:
            message: 커밋 메시지

        Returns:
            커밋 SHA
        """
        try:
            # 모든 변경사항 stage
            self.repo.git.add(A=True)

            # 커밋
            commit = self.repo.index.commit(message)
            self.logger.info(f"커밋 생성: {commit.hexsha[:8]} - {message}")

            return commit.hexsha

        except Exception as e:
            self.logger.error(f"커밋 실패: {message}")
            raise RuntimeError(f"커밋 실패: {e}") from e

    def fetch(self, remote: str = "origin") -> None:
        """
        원격 저장소 fetch

        Args:
            remote: 원격 저장소 이름
        """
        try:
            self.repo.remotes[remote].fetch()
            self.logger.info(f"Fetch 완료: {remote}")
        except Exception as e:
            raise RuntimeError(f"Fetch 실패: {e}") from e

    def pull(self, remote: str = "origin", branch: Optional[str] = None) -> None:
        """
        원격 저장소 pull

        Args:
            remote: 원격 저장소 이름
            branch: 브랜치 이름 (None이면 현재 브랜치)
        """
        try:
            if branch is None:
                branch = self.get_current_branch()

            self.repo.remotes[remote].pull(branch)
            self.logger.info(f"Pull 완료: {remote}/{branch}")

        except Exception as e:
            raise RuntimeError(f"Pull 실패: {e}") from e

    def push(self, remote: str = "origin", branch: Optional[str] = None) -> None:
        """
        원격 저장소 push

        Args:
            remote: 원격 저장소 이름
            branch: 브랜치 이름 (None이면 현재 브랜치)
        """
        try:
            if branch is None:
                branch = self.get_current_branch()

            self.repo.remotes[remote].push(branch)
            self.logger.info(f"Push 완료: {remote}/{branch}")

        except GitCommandError as e:
            raise RuntimeError(f"Push 실패: {e}") from e

    def checkout(self, branch: str) -> None:
        """
        브랜치 체크아웃

        Args:
            branch: 체크아웃할 브랜치 이름
        """
        try:
            self.repo.git.checkout(branch)
            self.logger.info(f"브랜치 체크아웃: {branch}")
        except Exception as e:
            raise RuntimeError(f"브랜치 체크아웃 실패: {branch} - {e}") from e

    def get_diff(self, from_ref: str, to_ref: str = "HEAD") -> str:
        """
        두 ref 간의 diff 가져오기

        Args:
            from_ref: 비교 시작 ref (예: "origin/main")
            to_ref: 비교 끝 ref (기본값: HEAD)

        Returns:
            diff 텍스트
        """
        try:
            diff = self.repo.git.diff(from_ref, to_ref)
            return diff
        except Exception as e:
            raise RuntimeError(f"Diff 생성 실패: {e}") from e

    def get_changed_files(self, from_ref: str, to_ref: str = "HEAD") -> List[str]:
        """
        두 ref 간의 변경된 파일 목록 가져오기

        Args:
            from_ref: 비교 시작 ref
            to_ref: 비교 끝 ref (기본값: HEAD)

        Returns:
            변경된 파일의 절대 경로 리스트
        """
        try:
            # --name-only: 파일 이름만 출력
            files = self.repo.git.diff(from_ref, to_ref, name_only=True).split("\n")
            # 절대 경로로 변환
            abs_files = [str((self.repo_path / f).resolve()) for f in files if f]
            return abs_files

        except Exception as e:
            raise RuntimeError(f"변경 파일 목록 가져오기 실패: {e}") from e

    def clone(self, url: str, target_path: Path, shallow: bool = True) -> None:
        """
        리포지터리 클론

        Args:
            url: 원격 저장소 URL
            target_path: 클론 대상 경로
            shallow: shallow clone 여부
        """
        try:
            if shallow:
                Repo.clone_from(url, target_path, depth=1)
                self.logger.info(f"Shallow clone 완료: {url} -> {target_path}")
            else:
                Repo.clone_from(url, target_path)
                self.logger.info(f"Clone 완료: {url} -> {target_path}")

        except Exception as e:
            raise RuntimeError(f"Clone 실패: {e}") from e

    def reset_hard(self, ref: str) -> None:
        """
        Hard reset

        Args:
            ref: reset할 ref (예: "origin/main")
        """
        try:
            self.repo.git.reset("--hard", ref)
            self.logger.info(f"Hard reset 완료: {ref}")
        except Exception as e:
            raise RuntimeError(f"Reset 실패: {e}") from e

    def get_latest_commit_sha(self) -> str:
        """현재 HEAD의 커밋 SHA 반환"""
        return self.repo.head.commit.hexsha

    def get_remote_url(self, remote: str = "origin") -> str:
        """원격 저장소 URL 반환"""
        try:
            return list(self.repo.remotes[remote].urls)[0]
        except Exception:
            return ""
