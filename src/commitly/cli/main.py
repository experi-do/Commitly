"""
Commitly CLI 메인 모듈
"""

import argparse
import sys

from commitly.cli.commands.commit import commit_command
from commitly.cli.commands.init import init_command
from commitly.cli.commands.report import report_command
from commitly.cli.commands.status import status_command


def main() -> None:
    """CLI 메인 엔트리포인트"""
    parser = argparse.ArgumentParser(
        prog="commitly",
        description="Commitly - AI-powered commit automation tool",
    )

    subparsers = parser.add_subparsers(dest="command", help="사용 가능한 명령어")

    # init 명령어
    init_parser = subparsers.add_parser(
        "init",
        help="Commitly 프로젝트 초기화",
    )
    init_parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="설정 파일 경로 (기본: config.yaml)",
    )
    init_parser.set_defaults(handler=init_command)

    # git 하위 명령 그룹
    git_parser = subparsers.add_parser(
        "git",
        help="Git 워크플로우 보조 명령",
    )
    git_subparsers = git_parser.add_subparsers(
        dest="git_command",
        help="Git 명령",
    )

    git_commit_parser = git_subparsers.add_parser(
        "commit",
        help="git commit 후 Commitly 파이프라인 실행",
    )
    git_commit_parser.add_argument(
        "-m",
        "--message",
        type=str,
        help="git commit 메시지 (지정 시 commitly가 직접 commit 실행)",
    )
    git_commit_parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="설정 파일 경로 (기본: config.yaml)",
    )
    git_commit_parser.set_defaults(handler=commit_command)

    # 기존 commit 명령도 유지 (호환용)
    commit_parser = subparsers.add_parser(
        "commit",
        help="Commitly 파이프라인 실행",
    )
    commit_parser.add_argument(
        "-m",
        "--message",
        type=str,
        help="git commit 메시지 (지정 시 commitly가 직접 commit 실행)",
    )
    commit_parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="설정 파일 경로 (기본: config.yaml)",
    )
    commit_parser.set_defaults(handler=commit_command)

    # report 명령어
    report_parser = subparsers.add_parser(
        "report",
        help="작업 보고서 생성",
    )
    report_parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="설정 파일 경로 (기본: config.yaml)",
    )
    report_parser.add_argument(
        "--from",
        dest="from_date",
        type=str,
        help="시작일 (ISO 8601 형식)",
    )
    report_parser.add_argument(
        "--to",
        dest="to_date",
        type=str,
        help="종료일 (ISO 8601 형식)",
    )
    report_parser.set_defaults(handler=report_command)

    # status 명령어
    status_parser = subparsers.add_parser(
        "status",
        help="Commitly 상태 확인",
    )
    status_parser.set_defaults(handler=status_command)

    args = parser.parse_args()

    handler = getattr(args, "handler", None)

    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args)


if __name__ == "__main__":
    main()
