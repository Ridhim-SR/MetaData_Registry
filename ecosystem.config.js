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
      name: "registry-web",
      cwd: "/home/ubuntu/MetaData_Registry/apps/web",
      script: "npm",
      args: "run start -- -p 3100",       // Next.js style; adjust to your start script
      env: { NODE_ENV: "production", PORT: 3100,
             NEXT_PUBLIC_API_URL: "http://144.24.151.253:4100" },
      autorestart: true, max_restarts: 10, restart_delay: 5000,
    },
    {
      name: "registry-api",
      cwd: "/home/ubuntu/MetaData_Registry/apps/api",
      script: "npm",
      args: "run start",
      env: { NODE_ENV: "production", PORT: 4100 },
      autorestart: true, max_restarts: 10, restart_delay: 5000,
    },
    {
      name: "openmetadata",
      cwd: "/home/ubuntu/MetaData_Registry/data_services",   // adjust
      script: "npm",                                          // adjust
      args: "run start",
      env: { PORT: 8585 },
      autorestart: true, max_restarts: 10, restart_delay: 5000,
    },
  ],
};
