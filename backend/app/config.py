from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    robot_host: str = "192.168.1.80"
    robot_api_port: int = Field(default=8090, ge=1, le=65535)
    robot_stream_port: int = Field(default=8080, ge=1, le=65535)
    robot_request_timeout: float = Field(default=5, gt=0)

    @property
    def robot_api_url(self) -> str:
        return f"http://{self.robot_host}:{self.robot_api_port}"

    @property
    def robot_stream_url(self) -> str:
        return f"http://{self.robot_host}:{self.robot_stream_port}/"
