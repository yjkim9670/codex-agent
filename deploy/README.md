# Code Server Deploy Ops

## Tailscale HTTPS expose

```bash
./deploy/tailscale/expose_code_server.sh 8080
```

If `serve config denied` appears, grant operator once on the local PC:

```bash
sudo tailscale set --operator=$USER
```

Verify from a tailnet client:

```bash
curl -I https://<machine>.<tailnet>.ts.net:8080/
```

A healthy remote response usually returns `HTTP/2 302` with `location: ./login`.

## ACL policy

Restrict access in the Tailscale ACL so only the intended users and devices can reach the code-server node.
