from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str

    SECRET_KEY: str

    CHROMA_HOST: str
    CHROMA_PORT: int

    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_CHAT_MODEL: str = "cieloforge/qwen2.5-14B-instruct-spec"
    MAX_EMBED_CHARS: int = 8000
    MAX_ASK_CONTEXT_CHARS: int = 100_000

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
