# Network

Where ComfyUI listens, and how the app reaches it.

## Same computer

This is the default. ComfyUI listens on `127.0.0.1`.

- Base URL: `http://127.0.0.1:8188/upai`.
- The port is 8188 for ComfyUI from source or the portable build. ComfyUI
  Desktop shows its port in Settings.
- Health check: `http://127.0.0.1:8188/upai/api/v1/health`.

## Another device on the LAN

1. Start ComfyUI on the local network: `python main.py --listen 0.0.0.0`.
2. Use the base URL `http://<lan-ip>:<port>/upai` in the app. Example:
   `http://192.168.1.20:8188/upai`.
3. Turn on LAN access in the pack settings. See below.

## Settings

Open ComfyUI Settings, category Unplatform AI, or edit
`<ComfyUI user dir>/default/upai/config.json`.

| Setting | Env | Default | What it does |
|---|---|---|---|
| `allow_lan` | `UPAI_ALLOW_LAN` | false | LAN peers may connect. Does not change the token rule. |
| `token` | `UPAI_TOKEN` | empty | Bearer token. Empty means auth off. |
| `allow_remote` | `UPAI_ALLOW_REMOTE` | false | Public peers, and LAN peers when a token is set. |
| `allowed_hosts` | `UPAI_ALLOWED_HOSTS` | empty | Extra `Host` names, comma separated. |

IP literals, `localhost` and names ending in `.local` always pass the Host check.

The settings panel also has **Maximum running jobs**. It maps to `max_running`
(`UPAI_MAX_RUNNING`), range 1 to 8.

## Token

- When a token is set, every pack route needs `Authorization: Bearer <token>`.
  The app sends it.
- LAN peers need the token too when one is set.
- The token is stored in plaintext in `config.json`.
- Plain HTTP sends the token unencrypted. Use a trusted network or a tunnel.

## allow_lan warning

**Warning:** with `allow_lan` on and no token, anyone who can reach the port can
upload files and run workflows. Use a trusted network or set a token.

## Ports and firewall

ComfyUI uses 8188 by default. A different port is possible, check ComfyUI
Settings or the startup log.

Linux example, restricted to the private network:

```bash
sudo ufw allow from 192.168.1.0/24 to any port 8188 proto tcp
```

Never open the port to the internet.

## Tailscale

Tailscale addresses are in `100.64.0.0/10` and count as LAN peers.

1. Install Tailscale on the ComfyUI machine and on the device with the app.
2. Start ComfyUI with `--listen 0.0.0.0`, or bind it to the Tailscale address.
3. Turn on `allow_lan` and set a token on a shared tailnet.
4. Use the Tailscale address of the ComfyUI machine in the base URL:
   `http://<tailscale-ip>:<port>/upai`.

## Remote access

Do not expose ComfyUI directly to the internet. Use Tailscale, an SSH tunnel or
another private tunnel. ComfyUI has no authentication beyond the pack token, and
the token protects only the `/upai` routes.
