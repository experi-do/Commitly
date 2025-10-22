"""
RunContext 타입 정의

LangGraph State로 사용되는 파이프라인 실행 컨텍스트
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict


class CommitInfo(TypedDict):
    """커밋 정보"""
    sha: str
    message: str
    author: str
    timestamp: datetime


class QueryInfo(TypedDict):
    """SQL 쿼리 정보"""
    file_path: str
    function_name: str
    line_start: int
    line_end: int
    query: str


class ExecutionProfile(TypedDict):
    """실행 프로필"""
    command: str
    timeout: int
    max_memory: int


class RunContext(TypedDict):
    """
    파이프라인 실행 컨텍스트

    LangGraph State로 사용되며, 모든 에이전트 간 공유되는 데이터 구조.
    """

    # 프로젝트 정보
    project_name: str
    workspace_path: str              # 로컬 프로젝트 루트
    hub_path: str                    # 허브 복제본 루트
    config_path: str                 # 설정 파일 경로

    # Git 정보
    git_remote: str                  # 기본 'origin'
    current_branch: str              # 사용자 작업 브랜치
    latest_local_commits: List[CommitInfo]  # 직전 실행 이후 새로 생성된 커밋 목록

    # 에이전트 브랜치 (허브에서만 존재)
    clone_agent_branch: Optional[str]
    code_agent_branch: Optional[str]
    test_agent_branch: Optional[str]
    refactoring_agent_branch: Optional[str]

    # 실행 상태
    pipeline_id: str                 # UUID
    started_at: datetime
    current_agent: str
    agent_status: Dict[str, str]     # {agent_name: 'pending'|'running'|'success'|'failed'}

    # 변경 사항
    commit_file_list: List[str]      # 커밋된 파일 절대 경로 (changed_files로도 참조됨)
    has_query: bool                  # SQL 쿼리 포함 여부
    query_file_list: Optional[List[QueryInfo]]  # SQL 정보

    # 환경 설정
    python_bin: str
    env_file: str
    execution_profile: ExecutionProfile
    llm_client: Any                  # LLM 클라이언트 핸들

    # 에러 처리
    error_log: Optional[str]
    rollback_point: Optional[str]    # 롤백 기준 커밋 SHA


class AgentOutput(TypedDict):
    """
    에이전트 출력 표준 구조

    모든 에이전트는 이 형식으로 결과를 반환합니다.
    """
    pipeline_id: str
    agent_name: str
    agent_branch: Optional[str]      # 에이전트가 생성한 브랜치명
    status: str                      # 'success' | 'failed'
    started_at: str                  # ISO 8601 형식
    ended_at: str                    # ISO 8601 형식
    error: Optional[Dict[str, str]]  # status='failed'일 때만 포함
    data: Dict[str, Any]             # 에이전트별 고유 데이터


class ErrorInfo(TypedDict):
    """에러 정보"""
    type: str                        # 에러 타입 (예: RuntimeError)
    message: str                     # 에러 메시지
    log_path: str                    # 에러 로그 파일 경로
