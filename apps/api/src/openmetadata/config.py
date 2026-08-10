from pydantic import Field
from pydantic_settings import BaseSettings


class OpenMetadataSettings(BaseSettings):
    host: str = Field(default="http://localhost:8585", alias="OPENMETADATA_HOST")
    api_version: str = Field(default="v1", alias="OPENMETADATA_API_VERSION")
    username: str = Field(default="admin@open-metadata.org", alias="OPENMETADATA_USERNAME")
    password: str = Field(default="admin", alias="OPENMETADATA_PASSWORD")
    jwt_token: str | None = Field(default=None, alias="OPENMETADATA_JWT_TOKEN")
    request_timeout: int = Field(default=30, alias="OPENMETADATA_TIMEOUT")

    class Config:
        env_prefix = "OM_"
        extra = "ignore"

    @property
    def base_url(self) -> str:
        return f"{self.host}/api/{self.api_version}"

    @property
    def auth_endpoint(self) -> str:
        return f"{self.base_url}/users/login"

    @property
    def entities_endpoint(self) -> str:
        return f"{self.base_url}/entities"


settings = OpenMetadataSettings()
