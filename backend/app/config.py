from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg2://bda_user:change_me@localhost:5432/ecommerce_bda"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    upload_dir: str = "uploads"
    max_upload_mb: int = 100
    spark_master: str = "local[2]"
    spark_shuffle_partitions: int = Field(4, ge=1)
    spark_jdbc_package: str = "org.postgresql:postgresql:42.7.14"
    spark_jdbc_jar: str = ""  # optional local JAR for offline use
    spark_job_timeout_seconds: int = Field(1800, ge=30)


settings = Settings()
