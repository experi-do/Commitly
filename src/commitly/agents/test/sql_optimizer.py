"""
SQL 최적화 모듈

EXPLAIN을 사용하여 SQL 쿼리 성능 비교
"""

import psycopg2
from typing import Dict, List, Tuple

from commitly.core.config import Config
from commitly.core.logger import CommitlyLogger


class SQLOptimizer:
    """SQL 최적화 클래스"""

    def __init__(self, config: Config, logger: CommitlyLogger) -> None:
        """
        Args:
            config: 설정
            logger: 로거
        """
        self.config = config
        self.logger = logger

        # DB 연결 정보
        self.db_config = {
            "host": config.get("database.host", "localhost"),
            "port": config.get("database.port", 5432),
            "user": config.get("database.user"),
            "password": config.get("database.password"),
            "dbname": config.get("database.dbname"),
        }

    def get_table_schema(self, table_name: str) -> str:
        """
        테이블 스키마 정보 가져오기

        Args:
            table_name: 테이블 이름

        Returns:
            CREATE TABLE 구문
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # PostgreSQL 스키마 정보 조회
            cursor.execute(
                """
                SELECT
                    'CREATE TABLE ' || table_name || ' (' ||
                    string_agg(column_name || ' ' || data_type, ', ') || ');'
                FROM information_schema.columns
                WHERE table_name = %s
                GROUP BY table_name
                """,
                (table_name,)
            )

            result = cursor.fetchone()
            cursor.close()
            conn.close()

            return result[0] if result else f"-- Schema for {table_name} not found"

        except Exception as e:
            self.logger.warning(f"스키마 조회 실패: {table_name} - {e}")
            return f"-- Schema for {table_name} not found"

    def extract_tables_from_query(self, query: str) -> List[str]:
        """
        쿼리에서 테이블 이름 추출 (간단한 방식)

        Args:
            query: SQL 쿼리

        Returns:
            테이블 이름 리스트
        """
        import re

        # FROM, JOIN 절에서 테이블 이름 추출
        pattern = r'(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        matches = re.findall(pattern, query, re.IGNORECASE)

        return list(set(matches))

    def explain_query(self, query: str) -> Dict[str, any]:
        """
        EXPLAIN ANALYZE로 쿼리 실행 계획 분석

        Args:
            query: SQL 쿼리

        Returns:
            {
                "total_cost": float,
                "execution_time": float,
                "plan": str,
            }
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # EXPLAIN ANALYZE 실행
            explain_query = f"EXPLAIN (ANALYZE, COSTS, VERBOSE, BUFFERS, FORMAT JSON) {query}"
            cursor.execute(explain_query)

            result = cursor.fetchone()[0]
            plan = result[0] if result else {}

            cursor.close()
            conn.close()

            # 비용 및 시간 추출
            total_cost = plan.get("Plan", {}).get("Total Cost", 0.0)
            execution_time = plan.get("Execution Time", 0.0)

            return {
                "total_cost": total_cost,
                "execution_time": execution_time,
                "plan": str(plan),
            }

        except Exception as e:
            self.logger.warning(f"EXPLAIN 실패: {e}")
            # 실패 시 높은 비용 반환 (선택되지 않도록)
            return {
                "total_cost": float("inf"),
                "execution_time": float("inf"),
                "plan": f"Error: {e}",
            }

    def find_best_query(
        self,
        candidates: List[str],
    ) -> Tuple[str, Dict[str, any]]:
        """
        후보 쿼리 중 가장 효율적인 쿼리 선택

        Args:
            candidates: 후보 쿼리 리스트 (원본 포함)

        Returns:
            (best_query, explain_result)
        """
        best_query = candidates[0]
        best_cost = float("inf")
        best_explain = {}

        for query in candidates:
            explain_result = self.explain_query(query)
            cost = explain_result.get("total_cost")

            if cost is None:
                self.logger.debug("쿼리 비용 정보를 가져올 수 없어 후보에서 제외합니다")
                continue

            self.logger.debug(f"쿼리 비용: {cost}")

            if cost < best_cost:
                best_cost = cost
                best_query = query
                best_explain = explain_result

        return best_query, best_explain
