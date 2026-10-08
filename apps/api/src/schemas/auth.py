from pydantic import BaseModel, EmailStr, Field

from database.models import AuthProvider, UserRole


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)
    department: str | None = None


class LoginRequest(BaseModel):
    # Email preferred; a legacy username still works.
    email: str = Field(min_length=1)
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    username: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: UserRole
    department: str | None = None
    auth_provider: AuthProvider = AuthProvider.local


class OAuthCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


class OAuthURLResponse(BaseModel):
    authorization_url: str
