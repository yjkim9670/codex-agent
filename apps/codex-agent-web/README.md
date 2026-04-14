# codex-agent-web

Separated frontend app for Codex Agent (`Vercel` target).

## Local Development

```bash
npm install
cp .env.example .env.local
npm run dev
```

## Environment Variables

- `VITE_CODEX_API_BASE_URL`
  - Example: `https://your-machine.your-tailnet.ts.net`
  - Browser API base URL for Codex backend.
- `VITE_APP_ENV_NAME`
  - Example: `private-tailnet`
  - Optional environment label shown in header/title.

## Build

```bash
npm run build
npm run preview
```

## Vercel

Configure the Vercel project root directory to `apps/codex-agent-web` and set:

- `VITE_CODEX_API_BASE_URL`
- `VITE_APP_ENV_NAME`

Automated setup/deploy scripts are available in:

- `deploy/vercel/setup_vercel_project.sh`
- `deploy/vercel/deploy_codex_agent_web.sh`
