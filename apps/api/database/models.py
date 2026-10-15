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


class RegistryTable(Base):
    """A dataset table's processed schema, ingested from data_services'
    curated CSV snapshots (POST /registry/ingest).

    One row per ``table_id`` ("department.dataset.table"); the snapshot's
    column rows live in ``registry.columns``. OpenMetadata stays the
    catalogue of record -- these tables are the shared, queryable copy of
    our pipeline's output so the backend never needs the CSVs mailed over.
    """

    __tablename__ = "tables"
    __table_args__ = (
        Index("idx_registry_tables_dataset", "department", "dataset"),
        {"schema": "registry"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    dataset: Mapped[str] = mapped_column(String(200), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(200), nullable=False, default="public")
    table_name: Mapped[str] = mapped_column(String(200), nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # ingestion_timestamp copied from the snapshot itself (provenance)
    source_timestamp: Mapped[str | None] = mapped_column(String(40), nullable=True, default=None)
    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RegistryColumn(Base):
    """One column of an ingested table -- a curated snapshot row."""

    __tablename__ = "columns"
    __table_args__ = (
        Index("idx_registry_columns_table", "table_id", "position"),
        {"schema": "registry"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[str] = mapped_column(
        String(300), ForeignKey("registry.tables.table_id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    length: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    scale: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    nullable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_value: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    business_description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    tag: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    classification: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    glossary_term: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    validation_warning: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)


class TableInfo(Base):
    """Dataset information tags per OpenMetadata table (sidecar).

    Mirrors the OM Custom Properties panel: whether the dataset is exposed
    via an API, who owns it (free text), refresh frequency and covered
    timeline. Stored here (not in OM) so reads work without OM custom
    property definitions and stay under our access policy. Tables without
    a row render as "Not set".
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
