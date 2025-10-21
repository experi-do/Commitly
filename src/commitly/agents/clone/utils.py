"""
CloneAgent 유틸리티 함수
"""

from pathlib import Path
from typing import List

from git import Repo


def get_hub_path(workspace_path: Path, project_name: str) -> Path:
    """
    허브 경로 계산

    Args:
        workspace_path: 로컬 워크스페이스 경로
        project_name: 프로젝트 이름

    Returns:
        허브 경로 ({프로젝트_부모}/.commitly_hub_{프로젝트명})
    """
    project_parent = workspace_path.parent
    hub_name = f".commitly_hub_{project_name}"
    return project_parent / hub_name


def apply_patches_to_hub(
    hub_repo: Repo,
    patch_files: List[Path],
) -> None:
    """
    패치 파일들을 허브에 순차적으로 적용

    Args:
        hub_repo: 허브 Git 리포지터리
        patch_files: 패치 파일 경로 리스트

    Raises:
        RuntimeError: 패치 적용 실패 시
    """
    for patch_file in patch_files:
        try:
            # git apply 명령 실행
            hub_repo.git.apply(str(patch_file))
        except Exception as e:
            raise RuntimeError(
                f"패치 적용 실패: {patch_file.name}\n{e}"
            ) from e


def copy_local_changes_to_hub(
    workspace_repo: Repo,
    hub_repo: Repo,
    changed_files: List[str],
) -> None:
    """
    로컬 변경사항을 허브로 복사

    패치 적용 대신 파일을 직접 복사하는 방식

    Args:
        workspace_repo: 로컬 워크스페이스 리포지터리
        hub_repo: 허브 리포지터리
        changed_files: 변경된 파일 상대 경로 리스트
    """
    import shutil

    workspace_path = Path(workspace_repo.working_dir)
    hub_path = Path(hub_repo.working_dir)

    for relative_path in changed_files:
        src_file = workspace_path / relative_path
        dst_file = hub_path / relative_path

        if src_file.exists():
            # 디렉토리 생성
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            # 파일 복사
            shutil.copy2(src_file, dst_file)
        else:
            # 파일 삭제 (로컬에서 삭제된 경우)
            if dst_file.exists():
                dst_file.unlink()
