import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"


class Visibility(str, enum.Enum):
    """Dataset/table access level for the metadata registry.

    public: anyone, no login. department: authenticated users of the owning
    department (or admins); guests see a teaser. restricted: discoverable as
    a teaser, details require authorization / access request. confidential:
    invisible to everyone except admins (absent from lists, search, counts
    and stats; direct access is 404).
    """

    public = "public"
    department = "department"
    restricted = "restricted"
    confidential = "confidential"


class AuthProvider(str, enum.Enum):
    local = "local"
    google = "google"
    microsoft = "microsoft"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role"),
        Index("idx_users_department", "department"),
        Index("idx_users_provider", "auth_provider", "provider_sub"),
        {"schema": "users"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    auth_provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, name="auth_provider", schema="users", create_constraint=True),
        default=AuthProvider.local,
        nullable=False,
    )
    provider_sub: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role", schema="users", create_constraint=True), default=UserRole.user, nullable=False)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DatasetVisibility(Base):
    """Sidecar access metadata for an OpenMetadata table.

    OpenMetadata remains the metadata store; FastAPI remains the policy
    enforcement point. Tables without a row default to ``department``.
    """

    __tablename__ = "dataset_visibility"
    __table_args__ = (
        Index("idx_visibility_fqn", "fqn", unique=True),
        Index("idx_visibility_service", "service"),
        Index("idx_visibility_visibility", "visibility"),
        {"schema": "users"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fqn: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    service: Mapped[str] = mapped_column(String(200), nullable=False)
    database_name: Mapped[str] = mapped_column(String(200), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(200), nullable=False)
    table_name: Mapped[str] = mapped_column(String(200), nullable=False)
    visibility: Mapped[Visibility] = mapped_column(
        Enum(Visibility, name="visibility", schema="users", create_constraint=True),
        default=Visibility.department,
        nullable=False,
    )
    department: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AccessRequest(Base):
    """Minimal access-request record for restricted metadata (demo flow)."""
    __tablename__ = "access_requests"
    __table_args__ = (
        Index("idx_access_requests_fqn", "fqn"),
        Index("idx_access_requests_user", "user_id"),
        {"schema": "users"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fqn: Mapped[str] = mapped_column(String(500), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    requester_email: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DatasetInfo(Base):
    """Dataset-level information per OpenMetadata database (sidecar).

    Keyed by the dataset FQN (service.database). These are the defaults
    every member table inherits: accountable owner, data steward, refresh
    frequency and covered timeline. A table's own TableInfo value, when
    set, overrides the dataset value. API availability and classification
    are table-level only and are summarized on the dataset, never stored.
    """

    __tablename__ = "dataset_info"
    __table_args__ = (
        Index("idx_dataset_info_fqn", "fqn", unique=True),
        {"schema": "users"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fqn: Mapped[str] = mapped_column(String(500), nullable=False)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    steward: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    frequency: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    timeline: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TableInfo(Base):
    """Table-level information per OpenMetadata table (sidecar).

    Whether the table is exposed via an API, plus optional per-table
    overrides of the dataset defaults in DatasetInfo (owner as free text,
    refresh frequency, covered timeline). Stored here (not in OM) so reads
    work without OM custom property definitions and stay under our access
    policy. Tables without a row inherit everything from their dataset.
    """

    __tablename__ = "table_info"
    __table_args__ = (
        Index("idx_table_info_fqn", "fqn", unique=True),
        {"schema": "users"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fqn: Mapped[str] = mapped_column(String(500), nullable=False)
    api_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    dataset_owner: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    frequency: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    timeline: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
