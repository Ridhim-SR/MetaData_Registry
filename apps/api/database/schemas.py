from datetime import datetime

from pydantic import BaseModel, EmailStr

from database.models import AuthProvider, UserRole


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: UserRole
    department: str | None = None
    auth_provider: AuthProvider = AuthProvider.local
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    first_name: str | None = None
    last_name: str | None = None
    role: UserRole = UserRole.user
    department: str | None = None
