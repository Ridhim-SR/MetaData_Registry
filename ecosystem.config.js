// PM2 process config for cloud deployment: frontend + backend + OpenMetadata.
// Target: a Linux host with Docker, Node 20+, Python 3.11+.
//
// One-time host setup (run on the server, NOT via PM2):
//   1. npm install -g pm2 && pm2 install pm2-logrotate
//   2. cd apps/api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
//   3. VITE_API_BASE_URL=https://<your-backend-host>:8000 npm run build --workspace=web
//      (Vite bakes the API URL into the bundle at BUILD time — rebuild if it changes.)
//   4. Export required secrets (see env blocks below), then: npm run pm2:start
//   5. Persist across reboots: pm2 startup  &&  pm2 save
//
// Operate: npm run pm2:logs | pm2:restart | pm2:stop  (see root package.json)

const API_PORT = Number(process.env.API_PORT || 8000);
const WEB_PORT = Number(process.env.WEB_PORT || 4173);
const API_WORKERS = Number(process.env.API_WORKERS || 2);

module.exports = {
  apps: [
    {
      // OpenMetadata stack (MySQL + Elasticsearch + server + Airflow) via Compose.
      // Runs ATTACHED (no -d) so PM2 owns the lifecycle and aggregates logs.
      // Containers already carry `restart: always`; PM2 restarts this wrapper
      // if the compose process itself exits.
      name: "openmetadata",
      script: "docker",
      args: "compose -f infrastructure/openmetadata/docker-compose.yml up",
      autorestart: true,
      max_restarts: 15,
      min_uptime: "60s", // first boot pulls images + migrates; allow slow starts
      max_memory_restart: "256M", // wrapper only (containers are managed by Docker)
      env: {
        // Airflow DB overrides (compose defaults apply when unset):
        // AIRFLOW_DB_PASSWORD: "change-me",
      },
    },
    {
      // FastAPI backend (Linux venv). Create it first:
      //   python3 -m venv apps/api/.venv && apps/api/.venv/bin/pip install -r apps/api/requirements.txt
      name: "registry-api",
      cwd: "./apps/api",
      script: ".venv/bin/uvicorn",
      interpreter: "none", // script is already an executable binary
      args: `src.main:app --host 0.0.0.0 --port ${API_PORT} --workers ${API_WORKERS}`,
      autorestart: true,
      max_restarts: 15,
      min_uptime: "10s",
      max_memory_restart: "768M",
      env: {
        PORT: API_PORT,
        DATABASE_URL: process.env.DATABASE_URL || "postgresql+asyncpg://postgres:postgres@localhost:5432/appdb",
        SECRET_KEY: process.env.SECRET_KEY || "CHANGE-ME-generate-with-openssl-rand-hex-32",
        JWT_ALGORITHM: "HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES: "60",
        CORS_ALLOW_ORIGINS:
          process.env.CORS_ALLOW_ORIGINS || `http://localhost:${WEB_PORT}`,
        OPENMETADATA_HOST: process.env.OPENMETADATA_HOST || "http://localhost:8585",
        OPENMETADATA_API_VERSION: "v1",
        OPENMETADATA_USERNAME: process.env.OPENMETADATA_USERNAME || "admin@open-metadata.org",
        OPENMETADATA_PASSWORD: process.env.OPENMETADATA_PASSWORD || "admin",
        // Long-lived ingestion-bot JWT from the OM UI (required for metadata writes):
        OPENMETADATA_JWT_TOKEN: process.env.OPENMETADATA_JWT_TOKEN || "",
      },
    },
    {
      // Frontend: pure-JS static server over apps/web/dist (vite preview needs
      // a Rollup native binary that old glibc hosts can't load — serve has none).
      // Build dist on a machine where `vite build` works, then copy dist/ over:
      //   VITE_API_BASE_URL=https://<backend-host>:8000 npm run build --workspace=web
      //   scp -r apps/web/dist <user>@<host>:~/MetaData_Registry/apps/web/dist
      name: "registry-web",
      cwd: "./apps/web",
      script: "npm",
      args: `run serve -- -l tcp://0.0.0.0:${WEB_PORT}`,
      autorestart: true,
      max_restarts: 15,
      min_uptime: "10s",
      max_memory_restart: "512M",
      env: {
        PORT: WEB_PORT,
      },
    },
  ],
};
