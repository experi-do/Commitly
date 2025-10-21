"""
설정 관리 모듈

.commitly/config.yaml 파일을 로드하고 관리합니다.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class Config:
    """
    Commitly 설정 관리 클래스

    .commitly/config.yaml 파일을 읽어서 설정을 제공합니다.
    환경 변수 ${VAR_NAME} 형식을 자동으로 치환합니다.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        """
        Args:
            config_path: 설정 파일 경로. None이면 현재 디렉토리의 .commitly/config.yaml 사용
        """
        if config_path is None:
            config_path = Path.cwd() / ".commitly" / "config.yaml"

        self.config_path = config_path
        self._config: Dict[str, Any] = {}

        if self.config_path.exists():
            self._load()
        else:
            raise FileNotFoundError(
                f"설정 파일을 찾을 수 없습니다: {self.config_path}\n"
                "'commitly init'을 먼저 실행해주세요."
            )

    def _load(self) -> None:
        """YAML 파일을 로드하고 환경 변수를 치환합니다."""
        with open(self.config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)

        # 환경 변수 치환
        self._config = self._substitute_env_vars(raw_config)

    def _substitute_env_vars(self, obj: Any) -> Any:
        """
        재귀적으로 환경 변수를 치환합니다.

        ${VAR_NAME} 형식을 찾아서 환경 변수 값으로 치환합니다.

        Args:
            obj: 치환할 객체 (dict, list, str 등)

        Returns:
            환경 변수가 치환된 객체
        """
        if isinstance(obj, dict):
            return {k: self._substitute_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._substitute_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            # ${VAR_NAME} 패턴 찾기
            if obj.startswith("${") and obj.endswith("}"):
                var_name = obj[2:-1]
                return os.getenv(var_name, obj)  # 환경 변수 없으면 원본 그대로
            return obj
        else:
            return obj

    def get(self, key: str, default: Any = None) -> Any:
        """
        설정 값을 가져옵니다.

        점 표기법(예: "llm.model")을 지원합니다.

        Args:
            key: 설정 키 (점 표기법 가능)
            default: 기본값

        Returns:
            설정 값

        Examples:
            >>> config.get("project_name")
            "MyProject"
            >>> config.get("llm.model")
            "gpt-4o-mini"
        """
        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def get_all(self) -> Dict[str, Any]:
        """전체 설정을 딕셔너리로 반환합니다."""
        return self._config.copy()

    def reload(self) -> None:
        """설정 파일을 다시 로드합니다."""
        self._load()
