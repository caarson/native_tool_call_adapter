from __future__ import annotations
import os
from pydantic import BaseModel, Field
from typing import Optional

class RuntimeConfig(BaseModel):
    target_base_url: str = Field(default_factory=lambda: os.getenv("TARGET_BASE_URL", "https://api.openai.com/v1"))
    message_dump_path: Optional[str] = Field(default_factory=lambda: os.getenv("MESSAGE_DUMP_PATH"))
    tool_dump_path: Optional[str] = Field(default_factory=lambda: os.getenv("TOOL_DUMP_PATH"))
    disable_strict_schemas: bool = Field(default_factory=lambda: bool(os.getenv("DISABLE_STRICT_SCHEMAS")))
    force_tool_calling: bool = Field(default_factory=lambda: bool(os.getenv("FORCE_TOOL_CALLING")))

_global_config: RuntimeConfig | None = None


def get_config() -> RuntimeConfig:
    global _global_config
    if _global_config is None:
        _global_config = RuntimeConfig()
    return _global_config


def update_config(data: dict) -> RuntimeConfig:
    global _global_config
    current = get_config()
    merged = current.model_copy(update=data)
    _global_config = merged
    return merged
