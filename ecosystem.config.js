// PM2 config: registry-web (3100), registry-api (4100), registry-db (5434), openmetadata (8585).
// Start: pm2 start ecosystem.config.js && pm2 save   (reboot persistence: pm2 startup)
const ROOT = "/home/bipp2/MetaData_Registry";
const WEB_PORT = 3100, API_PORT = 4100;

const common = { autorestart: true, max_restarts: 50, restart_delay: 5000, min_uptime: "20s" };

module.exports = {
  apps: [
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
      max_memory_restart: "800M",
      ...common,
    },
    {
      // Postgres for registry-api (infrastructure/postgres, 127.0.0.1:5434);
      // replaced Neon and the old neon-bridge tunnel. Same pattern as the
      // openmetadata entry below: bring the container up detached, then tail
      // its logs so it shows in `pm2 ls`. The container is owned by Docker
      // (restart: unless-stopped), so `pm2 stop/restart registry-db` only
      // stops/re-attaches the log tail and never stops the database. If the
      // container dies the tail exits, and PM2's restart brings it back up.
      name: "registry-db",
      cwd: ROOT,
      script: "bash",
      args: `-c "docker compose -f infrastructure/postgres/docker-compose.yml up -d; exec docker logs -f --tail=20 registry_postgres"`,
      interpreter: "none",
      ...common,
      restart_delay: 10000,
    },
    {
      // OpenMetadata UI/API is published on 8585 by the compose file.
      // NOTE: never run foreground `compose up` under PM2 — every PM2
      // restart SIGTERMs the compose process, which then stops all
      // containers ("Gracefully stopping...") and loops forever.
      // This entry brings the stack up detached (idempotent) and then
      // tails logs so PM2 has a stable foreground process that owns
      // no containers; restarts only re-attach the log tail.
      // No `--wait` and `;` not `&&`: --wait fails when a one-shot service
      // (e.g. the migration container) exits, which skipped the log tail
      // and made PM2 crash-loop this entry.
      // Services are named so `up -d` never starts the Airflow `ingestion`
      // container, which BIPP2 does not run (execute-migrate-all comes in as
      // a dependency of the server). Needs infrastructure/openmetadata/.env
      // (MYSQL_ROOT_PASSWORD), or compose refuses to start and this loops.
      name: "openmetadata",
      cwd: ROOT,
      script: "bash",
      args: `-c "docker compose -f infrastructure/openmetadata/docker-compose.yml up -d mysql elasticsearch openmetadata-server; exec docker compose -f infrastructure/openmetadata/docker-compose.yml logs -f --tail=50 mysql elasticsearch openmetadata-server"`,
      interpreter: "none",
      ...common,
      restart_delay: 15000,
      kill_timeout: 10000,
    },
  ],
};
