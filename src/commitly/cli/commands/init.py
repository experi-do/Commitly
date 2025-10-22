"""
init 명령어 구현
"""

from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

import yaml


def init_command(args: Any) -> None:
    """
    Commitly 프로젝트 초기화

    Args:
        args: CLI 인자
    """
    print("Commitly 프로젝트 초기화 중...")

    workspace_path = Path.cwd()

    # .commitly 디렉토리 생성
    commitly_dir = workspace_path / ".commitly"
    commitly_dir.mkdir(exist_ok=True)

    # 하위 디렉토리 생성
    (commitly_dir / "cache").mkdir(exist_ok=True)
    (commitly_dir / "logs").mkdir(exist_ok=True)
    (commitly_dir / "slack").mkdir(exist_ok=True)
    (commitly_dir / "reports").mkdir(exist_ok=True)

    print(f"✓ .commitly 디렉토리 생성 완료: {commitly_dir}")

    # .gitignore 업데이트
    _update_gitignore(workspace_path)

    config_path = workspace_path / args.config
    env_path = workspace_path / ".env"

    missing_items: list[str] = []

    main_command, main_candidates, main_info = _discover_main_command(workspace_path)
    venv_path, venv_candidates = _detect_virtualenv(workspace_path)

    if config_path.exists():
        print(f"✓ 기존 설정 파일을 사용합니다: {config_path}")
        if len(main_candidates) > 1:
            _print_multiple_main_warning(main_candidates)
        elif main_command:
            _maybe_update_execution_command(config_path, main_command)
        else:
            print(
                "⚠️ 실행할 main.py 파일을 찾지 못했습니다. config.yaml의 execution.command를 직접 확인하세요."
            )
    else:
        if main_command:
            _write_config_with_command(config_path, main_command)
            print(f"✓ 실행 커맨드를 자동 설정하여 config.yaml을 생성했습니다: {main_command}")
        elif len(main_candidates) > 1:
            missing_items.append("config.yaml")
            _print_multiple_main_warning(main_candidates)
        else:
            missing_items.append("config.yaml")
            print(
                "⚠️ config.yaml 파일이 존재하지 않으며, 실행할 main.py 파일을 찾지 못했습니다."
                " 프로젝트에 맞는 설정 파일을 직접 준비해주세요."
            )

    if env_path.exists():
        print(f"✓ 기존 .env 파일을 사용합니다: {env_path}")
    else:
        missing_items.append(".env")
        print("⚠️ .env 파일이 존재하지 않습니다. 필요한 환경 변수를 포함한 .env 파일을 준비해주세요.")

    if missing_items:
        print(
            "\n⚠️ 위 파일을 프로젝트 루트에 준비한 뒤 다시 'commitly init'을 실행하거나,"
            " 수동으로 설정을 마친 후 커맨드를 사용해주세요."
        )
        return

    script_command = None
    script_path = workspace_path / "commitly_exec.sh"

    if main_info is None and main_candidates:
        _print_multiple_main_warning(main_candidates)
    elif main_info is None:
        print("⚠️ 실행할 main.py 후보를 찾지 못했습니다. commitly_exec.sh는 생성되지 않았습니다.")

    if venv_path is None:
        if venv_candidates:
            _print_multiple_virtualenv_warning(venv_candidates)
        else:
            print("⚠️ 가상환경을 찾지 못했습니다. 필요 시 commitly_exec.sh를 직접 수정하세요.")

    if main_info and venv_path:
        script_command = _write_exec_script(script_path, workspace_path, venv_path, main_info)
        print(f"✓ commitly_exec.sh 생성 완료: {script_path}")
        print("  ↳ 버전 관리에 추가하여 원격 저장소에도 반영해주세요.")

    if script_command:
        _maybe_update_execution_command(
            config_path,
            script_command,
            allowed_existing=(None, "python main.py", main_command),
        )

    print("\n✓ Commitly 초기화가 완료되었습니다!")
    print("\n다음 단계:")
    print("1. config.yaml 내용을 확인하고 필요한 값이 정확한지 검증하세요")
    print("2. .env 파일에 필요한 API 키와 환경 변수가 설정되어 있는지 확인하세요")
    print("3. commitly commit 명령어로 파이프라인을 실행하세요")


def _update_gitignore(workspace_path: Path) -> None:
    """
    .gitignore에 Commitly 관련 항목 추가

    Args:
        workspace_path: 워크스페이스 경로
    """
    gitignore_path = workspace_path / ".gitignore"

    commitly_entries = [
        "",
        "# Commitly",
        ".commitly/cache/",
        ".commitly/logs/",
        ".commitly_hub_*/",
        ".env",
        "commitly_exec.sh",
    ]

    # 기존 .gitignore 읽기
    existing_lines = []
    if gitignore_path.exists():
        with open(gitignore_path, "r", encoding="utf-8") as f:
            existing_lines = f.read().splitlines()

    # Commitly 항목이 없으면 추가
    if "# Commitly" not in existing_lines:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write("\n".join(commitly_entries) + "\n")
        print(f"✓ .gitignore 업데이트 완료")
    else:
        print(".gitignore에 Commitly 항목이 이미 존재합니다")


def _discover_main_command(workspace_path: Path) -> Tuple[Optional[str], List[str], Optional[Tuple[str, bool]]]:
    """
    프로젝트 내 main.py 위치를 기반으로 실행 커맨드를 추론합니다.

    Args:
        workspace_path: 워크스페이스 경로
    """
    candidates: list[Path] = []
    for main_path in workspace_path.rglob("main.py"):
        if any(part.startswith(".") for part in main_path.relative_to(workspace_path).parts[:-1]):
            continue
        if main_path.is_file():
            candidates.append(main_path)

    if not candidates:
        return None, [], None

    candidates.sort(key=lambda path: (len(path.relative_to(workspace_path).parts), str(path)))
    candidate_info: List[Tuple[str, bool]] = []
    for candidate in candidates:
        relative_parts = candidate.relative_to(workspace_path).parts
        relative_path = "/".join(relative_parts)
        parent_dir = candidate.parent / "__init__.py"
        has_package_init = parent_dir.exists()
        candidate_info.append((relative_path, has_package_init))

    relative_paths = [info[0] for info in candidate_info]

    if len(relative_paths) > 1:
        return None, relative_paths, None

    relative_path, has_package_init = candidate_info[0]

    if has_package_init:
        module_path = relative_path.replace("/", ".").removesuffix(".py")
        return f"python -m {module_path}", relative_paths, (relative_path, True)

    return f"python {relative_path}", relative_paths, (relative_path, False)


def _print_multiple_main_warning(candidates: List[str]) -> None:
    """
    여러 개의 main.py가 발견되었을 때 안내 메시지를 출력합니다.

    Args:
        candidates: 발견된 main.py 상대 경로 목록
    """
    print("⚠️ 여러 개의 main.py 파일을 발견했습니다. 실행 커맨드를 직접 설정해주세요:")
    for path in candidates:
        print(f"   - {path}")
    print("config.yaml의 execution.command 값을 프로젝트에 맞게 수정한 뒤 다시 실행하세요.")


def _detect_virtualenv(workspace_path: Path) -> Tuple[Optional[Path], List[str]]:
    """
    워크스페이스에서 사용할 가상환경 경로를 탐색합니다.

    Args:
        workspace_path: 워크스페이스 경로
    """
    candidates: List[Path] = []
    for candidate in workspace_path.iterdir():
        if not candidate.is_dir():
            continue
        if candidate.name.startswith(".") and candidate.name not in (".venv",):
            continue

        activate_paths = [candidate / "bin" / "activate", candidate / "Scripts" / "activate"]
        if any(path.exists() for path in activate_paths):
            candidates.append(candidate)

    candidates.sort()

    if not candidates:
        return None, []

    if len(candidates) > 1:
        return None, [path.name for path in candidates]

    return candidates[0], [candidates[0].name]


def _print_multiple_virtualenv_warning(candidates: List[str]) -> None:
    """
    여러 개의 가상환경 디렉터리가 발견되었을 때 안내 메시지를 출력합니다.

    Args:
        candidates: 발견된 가상환경 디렉터리 목록
    """
    print("⚠️ 여러 개의 가상환경 후보를 발견했습니다. 사용하려는 환경을 선택한 뒤 commitly_exec.sh를 수정하세요:")
    for path in candidates:
        print(f"   - {path}")


def _write_exec_script(
    script_path: Path,
    workspace_path: Path,
    venv_path: Path,
    main_info: Tuple[str, bool],
) -> str:
    """commitly_exec.sh 스크립트를 생성하고 실행 커맨드를 반환합니다.

    Args:
        script_path: 스크립트 경로
        workspace_path: 워크스페이스 위치
        venv_path: 사용할 가상환경 디렉터리 경로 (워크스페이스 기준)
        main_info: (relative_path, is_module) 튜플

    Returns:
        config.yaml에서 사용할 실행 커맨드 (예: "./commitly_exec.sh")
    """
    relative_path, is_module = main_info

    venv_rel = venv_path.name
    workspace_venv = workspace_path / venv_path.name

    script_lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        "",
        f'VENV_DIR="${{SCRIPT_DIR}}/{venv_rel}"',
        'if [[ -f "${VENV_DIR}/bin/activate" ]]; then',
        '    # shellcheck disable=SC1090',
        '    source "${VENV_DIR}/bin/activate"',
        'elif [[ -f "${VENV_DIR}/Scripts/activate" ]]; then',
        '    # shellcheck disable=SC1090',
        '    source "${VENV_DIR}/Scripts/activate"',
        'else',
        '    if [[ -n "${COMMITLY_WORKSPACE_VENV:-}" ]]; then',
        '        ALT_VENV="${COMMITLY_WORKSPACE_VENV}"',
        '    else',
        f'        ALT_VENV="{workspace_venv}"',
        '    fi',
        '    if [[ -f "${ALT_VENV}/bin/activate" ]]; then',
        '        # shellcheck disable=SC1090',
        '        source "${ALT_VENV}/bin/activate"',
        '    elif [[ -f "${ALT_VENV}/Scripts/activate" ]]; then',
        '        # shellcheck disable=SC1090',
        '        source "${ALT_VENV}/Scripts/activate"',
        '    else',
        '        echo "[commitly] 경고: 가상환경을 찾지 못했습니다. ${VENV_DIR} 또는 ${ALT_VENV}" >&2',
        '    fi',
        'fi',
        "",
    ]

    if is_module:
        module_path = relative_path.replace("/", ".").removesuffix(".py")
        script_lines.append(f'python -m {module_path} "$@"')
    else:
        script_lines.append(f'python "${{SCRIPT_DIR}}/{relative_path}" "$@"')

    script_content = "\n".join(script_lines) + "\n"

    script_path.write_text(script_content, encoding="utf-8")
    script_path.chmod(0o755)

    return "./" + script_path.name

def _write_config_with_command(config_path: Path, command: str) -> None:
    """
    감지된 실행 커맨드를 사용해 config.yaml을 생성합니다.

    Args:
        config_path: 설정 파일 경로
        command: 실행 커맨드
    """
    default_config = f"""# Commitly 설정 파일

# Git 설정
git:
  remote: origin

# LLM 설정
llm:
  enabled: true
  provider: openai
  model: gpt-4o-mini
  api_key: ${{OPENAI_API_KEY}}

# 실행 프로필
execution:
  command: {command}
  timeout: 300

# 테스트 프로필
test:
  timeout: 300

# 데이터베이스 설정 (SQL 최적화용)
database:
  host: localhost
  port: 5432
  user: ${{DB_USER}}
  password: ${{DB_PASSWORD}}
  dbname: ${{DB_NAME}}

# 리팩토링 규칙
refactoring:
  rules: |
    Remove duplicate code
    Add exception handling for risky operations (I/O, network, DB)

# Slack 설정
slack:
  enabled: false
  time_range_days: 7
  require_tag: false
  keywords: []
  save_path: .commitly/slack/matches.json

# 보고서 설정
report:
  format: md
  output_path: .commitly/reports
  filter:
    labels: []
    authors: []
  privacy:
    anonymize_user: false
    redact_patterns: []
"""

    config_path.write_text(default_config, encoding="utf-8")


def _maybe_update_execution_command(
    config_path: Path,
    command: str,
    *,
    allowed_existing: Sequence[Optional[str]] = (None, "python main.py"),
) -> None:
    """
    기존 config.yaml의 실행 커맨드를 필요 시 자동 업데이트합니다.

    Args:
        config_path: 설정 파일 경로
        command: 감지된 실행 커맨드
        allowed_existing: 덮어쓸 수 있는 기존 command 값
    """
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            config_data = yaml.safe_load(config_file) or {}
    except (yaml.YAMLError, OSError) as exc:
        print(f"⚠️ config.yaml을 읽는 동안 오류가 발생했습니다: {exc}")
        return

    execution = config_data.get("execution", {})
    current_command = execution.get("command")

    if current_command not in allowed_existing:
        return

    execution["command"] = command
    config_data["execution"] = execution

    try:
        with open(config_path, "w", encoding="utf-8") as config_file:
            yaml.safe_dump(config_data, config_file, allow_unicode=True, sort_keys=False)
        print(f"✓ 실행 커맨드를 자동으로 {command} 값으로 업데이트했습니다.")
    except OSError as exc:
        print(f"⚠️ config.yaml을 업데이트하는 동안 오류가 발생했습니다: {exc}")
