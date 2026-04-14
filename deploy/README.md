# Codex Backend/Deploy Ops (Steps 4-6)

## 1) Environment file

```bash
cp deploy/codex-backend.env.example deploy/codex-backend.env
```

Fill at least these values:

- `CODEX_CHAT_SECRET_KEY`
- `CODEX_ALLOWED_ORIGINS`
- `CODEX_WORKSPACE_DIR`

`CODEX_ALLOWED_ORIGINS` accepts comma-separated exact origins and simple glob patterns such as `https://your-vercel-preview-*.vercel.app`.

## 2) Manual backend run

```bash
./deploy/scripts/run_codex_backend.sh
```

Keep the backend on `6000` for Vercel/API traffic. `8080` should stay reserved for `code-server`.

## 3) systemd --user (recommended)

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/codex-agent-backend.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now codex-agent-backend.service
systemctl --user status codex-agent-backend.service
```

Logs:

- `workspace/.agent_state/logs/codex-backend.log`
- `workspace/.agent_state/logs/codex-backend.error.log`

## 4) Tailscale HTTPS expose

```bash
./deploy/tailscale/expose_codex_backend.sh 6000
./deploy/tailscale/expose_code_server.sh 8080
```

If `serve config denied` appears, grant operator once on local PC:

```bash
sudo tailscale set --operator=$USER
```

Then verify from a tailnet client:

```bash
./deploy/tailscale/verify_tailscale_backend.sh https://<machine>.<tailnet>.ts.net
curl -I https://<machine>.<tailnet>.ts.net:8080/
```

When using `tailscale serve`, keep `VITE_CODEX_API_BASE_URL` as the HTTPS `ts.net` URL without `:6000`.
Use `https://<machine>.<tailnet>.ts.net:8080` for `code-server`.
Do not point Vercel or the backend launcher at `:8080`.

`verify_tailscale_backend.sh` runs smoke checks for:

- `/health`
- `/api/codex/runtime/info`
- session list/create/detail/delete
- stream list
- `files`/`git` disabled-policy checks (when runtime flags are `false`)

Optional CORS header check:

```bash
CHECK_ORIGIN_HEADER=https://codex-agent-web.vercel.app \
./deploy/tailscale/verify_tailscale_backend.sh https://<machine>.<tailnet>.ts.net
```

For `code-server`, a successful remote check typically returns `HTTP/2 302` with `location: ./login`.

## 5) ACL policy

Restrict access in Tailscale ACL so only the intended users/devices can reach the backend node.

## 6) Vercel project setup and deploy

Create Vercel env config:

```bash
cp deploy/vercel/codex-agent-web.vercel.env.example deploy/vercel/codex-agent-web.vercel.env
```

Edit `deploy/vercel/codex-agent-web.vercel.env`:

- `VERCEL_PROJECT_NAME`
- `VITE_CODEX_API_BASE_URL` (tailnet HTTPS backend URL)
- `VITE_APP_ENV_NAME` (optional)
- `VERCEL_SCOPE` (optional team scope)

Link/configure project + set env vars:

```bash
./deploy/vercel/setup_vercel_project.sh
```

`setup_vercel_project.sh` stores `development/production` env vars, attempts `preview` env sync when Vercel allows it, and the deploy script still passes `--build-env` so manual CLI preview deploys keep working even if preview env sync is skipped.

Preview deploy:

```bash
./deploy/vercel/deploy_codex_agent_web.sh preview
```

Production deploy:

```bash
./deploy/vercel/deploy_codex_agent_web.sh production
```
