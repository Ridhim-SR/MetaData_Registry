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
