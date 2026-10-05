CREATE SCHEMA IF NOT EXISTS users;

CREATE TYPE users.user_role AS ENUM ('admin', 'user');
CREATE TYPE users.auth_provider AS ENUM ('local', 'google', 'microsoft');

CREATE TABLE users.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    password_hash VARCHAR(255),
    auth_provider users.auth_provider NOT NULL DEFAULT 'local',
    provider_sub VARCHAR(255),
    role users.user_role NOT NULL DEFAULT 'user',
    department VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users.users (email);
CREATE INDEX idx_users_role ON users.users (role);
CREATE INDEX idx_users_department ON users.users (department);
CREATE INDEX idx_users_provider ON users.users (auth_provider, provider_sub);

CREATE TYPE users.visibility AS ENUM ('public', 'department', 'restricted');

CREATE TABLE users.dataset_visibility (
    id SERIAL PRIMARY KEY,
    fqn VARCHAR(500) UNIQUE NOT NULL,
    service VARCHAR(200) NOT NULL,
    database_name VARCHAR(200) NOT NULL,
    schema_name VARCHAR(200) NOT NULL,
    table_name VARCHAR(200) NOT NULL,
    visibility users.visibility NOT NULL DEFAULT 'department',
    department VARCHAR(100),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_visibility_fqn ON users.dataset_visibility (fqn);
CREATE INDEX idx_visibility_service ON users.dataset_visibility (service);
CREATE INDEX idx_visibility_visibility ON users.dataset_visibility (visibility);

CREATE TABLE users.access_requests (
    id SERIAL PRIMARY KEY,
    fqn VARCHAR(500) NOT NULL,
    user_id INTEGER,
    requester_email VARCHAR(255),
    note VARCHAR(1000),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_access_requests_fqn ON users.access_requests (fqn);
CREATE INDEX idx_access_requests_user ON users.access_requests (user_id);
