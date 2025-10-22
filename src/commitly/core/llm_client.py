"""
LLM 클라이언트 모듈

OpenAI API를 사용하여 LLM과 상호작용합니다.
"""

from typing import List, Optional

from openai import OpenAI

from commitly.core.config import Config
from commitly.core.logger import CommitlyLogger


class LLMClient:
    """
    LLM 클라이언트

    OpenAI API를 사용하여 텍스트 생성, 요약 등을 수행합니다.
    """

    def __init__(self, config: Config, logger: CommitlyLogger) -> None:
        """
        Args:
            config: 설정 인스턴스
            logger: 로거 인스턴스
        """
        self.config = config
        self.logger = logger

        # OpenAI 클라이언트 초기화
        api_key = config.get("llm.api_key")
        if not api_key:
            raise ValueError("LLM API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")

        self.client = OpenAI(api_key=api_key)

        # 모델 설정
        self.model = config.get("llm.model", "gpt-4o-mini")
        self.temperature = config.get("llm.temperature", 0.2)
        self.max_tokens = config.get("llm.max_tokens", 2048)

    def complete(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        텍스트 완성 (Chat Completion)

        Args:
            prompt: 사용자 프롬프트
            system_message: 시스템 메시지 (선택적)
            temperature: 온도 (None이면 기본값 사용)
            max_tokens: 최대 토큰 수 (None이면 기본값 사용)

        Returns:
            생성된 텍스트
        """
        messages = []

        if system_message:
            messages.append({"role": "system", "content": system_message})

        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
            )

            result = response.choices[0].message.content or ""
            self.logger.debug(f"LLM 응답 ({len(result)} chars)")
            return result

        except Exception as e:
            self.logger.error(f"LLM API 호출 실패: {e}")
            raise RuntimeError(f"LLM API 호출 실패: {e}") from e

    def summarize_error_log(self, error_log: str) -> str:
        """
        에러 로그 요약

        Args:
            error_log: 원본 에러 로그

        Returns:
            요약된 에러 로그
        """
        system_message = (
            "당신은 Python 에러 로그를 분석하는 전문가입니다. "
            "사용자에게 에러의 원인과 해결 방법을 간결하게 설명해주세요."
        )

        prompt = f"""다음 에러 로그를 분석하고 요약해주세요:

```
{error_log}
```

다음 형식으로 답변해주세요:
1. 에러 종류:
2. 발생 위치:
3. 원인:
4. 해결 방법:
"""

        return self.complete(prompt, system_message=system_message)

    def generate_sql_candidates(
        self,
        original_query: str,
        schema_info: str,
        db_type: str = "postgresql",
    ) -> List[str]:
        """
        SQL 쿼리 최적화 후보 생성

        Args:
            original_query: 원본 SQL 쿼리
            schema_info: 테이블 스키마 정보
            db_type: 데이터베이스 종류

        Returns:
            최적화된 SQL 쿼리 후보 3개
        """
        system_message = (
            f"당신은 {db_type} 데이터베이스 성능 최적화 전문가입니다. "
            "주어진 SQL 쿼리를 기능적으로 동일하면서도 더 효율적인 쿼리로 재작성합니다."
        )

        prompt = f"""# SCHEMA
다음은 관련 테이블의 스키마입니다:
{schema_info}

# ORIGINAL QUERY
```sql
{original_query}
```

# INSTRUCTION
위 스키마와 쿼리를 기반으로, 기능적으로 동일하지만 성능이 더 좋을 가능성이 있는
SQL 쿼리 3개를 생성해주세요.

제약사항:
- 인덱스 추가/삭제는 제안하지 마세요
- 출력 컬럼과 타입은 원본과 동일해야 합니다
- JSON 배열 형식으로만 응답해주세요: ["query1", "query2", "query3"]
"""

        response = self.complete(prompt, system_message=system_message)

        # JSON 파싱
        import json
        try:
            # 코드 블록 제거
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]

            candidates = json.loads(response)

            if not isinstance(candidates, list) or len(candidates) != 3:
                raise ValueError("응답 형식이 올바르지 않습니다.")

            return candidates

        except Exception as e:
            self.logger.error(f"SQL 후보 생성 실패: {e}")
            # 기본값: 원본 쿼리 3개 반환
            return [original_query, original_query, original_query]

    def suggest_refactoring(
        self,
        code: str,
        file_path: str,
        refactoring_rules: str,
    ) -> str:
        """
        코드 리팩토링 제안

        Args:
            code: 원본 코드
            file_path: 파일 경로
            refactoring_rules: 리팩토링 규칙

        Returns:
            리팩토링된 코드
        """
        system_message = (
            "당신은 Python 코드 리팩토링 전문가입니다. "
            "주어진 규칙에 따라 코드를 개선합니다."
        )

        prompt = f"""# FILE: {file_path}

# REFACTORING RULES
{refactoring_rules}

# ORIGINAL CODE
```python
{code}
```

# INSTRUCTION
위 리팩토링 규칙에 따라 코드를 개선해주세요.
반환 형식 지침:
- 변경된 코드만 출력하고 추가 설명, 머리말/꼬리말, 리스트, 마크다운 코드 블록(예: ```python) 등을 포함하지 마세요.
- 변경 이유가 필요하다면 Python 주석(# ...)으로 코드 내부에만 작성하세요.
- 변경할 필요가 없다면 원본 코드를 그대로 반환하세요.
"""

        return self.complete(prompt, system_message=system_message)

    def match_slack_feedback(
        self,
        commit_info: str,
        slack_messages: List[str],
    ) -> List[int]:
        """
        Slack 메시지와 커밋 매칭

        Args:
            commit_info: 커밋 정보 (메시지, 파일 목록 등)
            slack_messages: Slack 메시지 리스트

        Returns:
            매칭된 메시지 인덱스 리스트
        """
        system_message = (
            "당신은 커밋과 Slack 피드백을 매칭하는 전문가입니다. "
            "커밋 내용과 관련된 Slack 메시지를 찾아주세요."
        )

        messages_text = "\n\n".join(
            f"[{i}] {msg}" for i, msg in enumerate(slack_messages)
        )

        prompt = f"""# COMMIT INFO
{commit_info}

# SLACK MESSAGES
{messages_text}

# INSTRUCTION
위 커밋과 관련된 Slack 메시지의 인덱스를 JSON 배열로 반환해주세요.
예: [0, 2, 5]

관련이 없다면 빈 배열을 반환하세요: []
"""

        response = self.complete(prompt, system_message=system_message)

        # JSON 파싱
        import json
        try:
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]

            indices = json.loads(response)
            return indices if isinstance(indices, list) else []

        except Exception as e:
            self.logger.warning(f"Slack 메시지 매칭 실패: {e}")
            return []
