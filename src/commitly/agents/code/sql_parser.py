"""
SQL 쿼리 파싱 모듈

Python 코드에서 SQL 쿼리를 추출합니다.
"""

import ast
import re
from pathlib import Path
from typing import List

from commitly.core.context import QueryInfo


def extract_sql_from_file(file_path: Path) -> List[QueryInfo]:
    """
    Python 파일에서 SQL 쿼리 추출

    Args:
        file_path: Python 파일 경로

    Returns:
        QueryInfo 리스트
    """
    if not file_path.suffix == ".py":
        return []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source_code = f.read()

        # AST로 파싱
        tree = ast.parse(source_code)

        queries: List[QueryInfo] = []

        # 문자열 노드 방문
        for node in ast.walk(tree):
            if isinstance(node, ast.Str):
                # 문자열이 SQL인지 확인
                if _is_sql_query(node.s):
                    # 함수 이름 찾기
                    function_name = _find_parent_function(node, tree)

                    query_info: QueryInfo = {
                        "file_path": str(file_path.resolve()),
                        "function_name": function_name or "unknown",
                        "line_start": node.lineno,
                        "line_end": node.end_lineno or node.lineno,
                        "query": node.s.strip(),
                    }
                    queries.append(query_info)

            # Python 3.8+ f-string
            elif isinstance(node, ast.JoinedStr):
                # f-string 내부의 상수 부분 확인
                query_parts = []
                for value in node.values:
                    if isinstance(value, ast.Constant):
                        query_parts.append(str(value.value))

                full_query = "".join(query_parts)
                if _is_sql_query(full_query):
                    function_name = _find_parent_function(node, tree)

                    query_info: QueryInfo = {
                        "file_path": str(file_path.resolve()),
                        "function_name": function_name or "unknown",
                        "line_start": node.lineno,
                        "line_end": node.end_lineno or node.lineno,
                        "query": full_query.strip(),
                    }
                    queries.append(query_info)

        return queries

    except Exception:
        # 파싱 실패 시 정규식으로 fallback
        return _extract_sql_with_regex(file_path)


def _is_sql_query(text: str) -> bool:
    """
    문자열이 SQL 쿼리인지 판단

    Args:
        text: 검사할 문자열

    Returns:
        SQL 쿼리 여부
    """
    text = text.strip().upper()

    # SQL 키워드 확인
    sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"]

    return any(text.startswith(keyword) for keyword in sql_keywords)


def _find_parent_function(node: ast.AST, tree: ast.AST) -> str:
    """
    노드가 속한 함수 이름 찾기

    Args:
        node: AST 노드
        tree: 전체 AST 트리

    Returns:
        함수 이름 (없으면 빈 문자열)
    """
    # 단순화: 모든 함수 정의를 순회하며 라인 번호로 판단
    for func_node in ast.walk(tree):
        if isinstance(func_node, ast.FunctionDef):
            if (
                func_node.lineno <= node.lineno
                and (func_node.end_lineno or 0) >= node.lineno
            ):
                return func_node.name

    return ""


def _extract_sql_with_regex(file_path: Path) -> List[QueryInfo]:
    """
    정규식으로 SQL 쿼리 추출 (fallback)

    Args:
        file_path: Python 파일 경로

    Returns:
        QueryInfo 리스트
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        queries: List[QueryInfo] = []

        # SQL 패턴
        pattern = r'["\']?\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\s+.*["\']?'

        for i, line in enumerate(lines):
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                query_info: QueryInfo = {
                    "file_path": str(file_path.resolve()),
                    "function_name": "unknown",
                    "line_start": i + 1,
                    "line_end": i + 1,
                    "query": match.group(0).strip(' "\'"'),
                }
                queries.append(query_info)

        return queries

    except Exception:
        return []


def parse_sql_from_files(file_paths: List[str]) -> tuple[bool, List[QueryInfo]]:
    """
    여러 파일에서 SQL 쿼리 추출

    Args:
        file_paths: 파일 경로 리스트

    Returns:
        (hasQuery, queryFileList)
    """
    all_queries: List[QueryInfo] = []

    for file_path_str in file_paths:
        file_path = Path(file_path_str)

        if file_path.suffix == ".py":
            queries = extract_sql_from_file(file_path)
            all_queries.extend(queries)

    has_query = len(all_queries) > 0

    return has_query, all_queries
