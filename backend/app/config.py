from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ExoDesk Agent"
    app_env: str = "development"
    demo_mode: bool = True
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'workorder.db'}"
    chroma_path: str = "./data/chroma"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    webhook_secret: str = ""
    webhook_tolerance_seconds: int = 300
    webhook_max_bytes: int = 1_000_000
    sse_poll_seconds: float = 0.2
    sse_heartbeat_seconds: float = 10.0

    ticket_provider: str = "mock"
    zendesk_subdomain: str = ""
    zendesk_email: str = ""
    zendesk_api_token: str = ""
    zendesk_serial_field_id: str = ""
    zendesk_timeout_seconds: float = 15.0

    llm_enabled: bool = False
    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-max"
    llm_timeout_seconds: float = 35.0

    agent_max_tool_calls: int = 5
    agent_timeout_seconds: float = 90.0
    tool_timeout_seconds: float = 15.0
    context_max_chars: int = 12000
    context_recent_messages: int = 8

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def chroma_dir(self) -> Path:
        path = Path(self.chroma_path)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path

    @property
    def sse_max_seconds(self) -> float:
        return max(self.agent_timeout_seconds + 30.0, 30.0)


settings = Settings()

