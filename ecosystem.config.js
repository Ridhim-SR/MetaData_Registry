// PM2 config: registry-web (3100), registry-api (4100), openmetadata (8585).
// Start: pm2 start ecosystem.config.js && pm2 save   (reboot persistence: pm2 startup)
const ROOT = "/home/bipp2/MetaData_Registry";
const WEB_PORT = 3100, API_PORT = 4100;

const common = { autorestart: true, max_restarts: 50, restart_delay: 5000, min_uptime: "20s" };

module.exports = {
  apps: [
    {
      // Outbound 5432 is blocked upstream; tunnel Postgres to Neon over wss:443.
      // registry-api's DATABASE_URL points at 127.0.0.1:5433 with sslmode=disable.
      name: "neon-bridge",
      cwd: `${ROOT}/infrastructure/neon-bridge`,
      script: `${ROOT}/apps/api/.venv/bin/python`,
      args: "bridge.py",
      interpreter: "none",
      env: { NEON_HOST: "ep-ancient-rice-b5kzj3vi-pooler.c-7.us-east-2.aws.neon.tech", BRIDGE_PORT: "5433" },
      ...common,
      min_uptime: "5s",
      restart_delay: 2000,
    },
    {
      // Static Vite build. Rebuild after changing the API URL:
      //   VITE_API_BASE_URL=http://10.0.96.105:4100 npm run build --workspace=web
      name: "registry-web",
      cwd: `${ROOT}/apps/web`,
      script: "npm",
      args: `run serve -- -l tcp://0.0.0.0:${WEB_PORT}`,
      interpreter: "none",
      ...common,
    },
    {
      name: "registry-api",
      cwd: `${ROOT}/apps/api`,
      script: `${ROOT}/apps/api/.venv/bin/uvicorn`,
      args: `src.main:app --host 0.0.0.0 --port ${API_PORT} --workers 2`,
      interpreter: "none",
      ...common,
    },
    {
      // OpenMetadata UI/API is published on 8585 by the compose file.
      name: "openmetadata",
      cwd: ROOT,
      script: "docker",
      args: "compose -f infrastructure/openmetadata/docker-compose.yml up",
      interpreter: "none",
      ...common,
      restart_delay: 15000,
    },
  ],
};
