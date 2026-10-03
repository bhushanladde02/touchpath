# Deploying touchpath

A complete walkthrough for putting touchpath on a free Oracle Cloud instance
with a real hostname and HTTPS. Takes about twenty minutes, costs nothing, and
the result stays up permanently - no cold starts, no sleeping container.

The app needs roughly 170 MB of memory with all five sample datasets cached, so
the smallest free shape is enough.

---

## 1. Create the instance

In the Oracle Cloud console: **Compute → Instances → Create instance**.

| Setting | Value |
|---|---|
| Image | Canonical Ubuntu 22.04 |
| Shape | `VM.Standard.E2.1.Micro` (AMD, 1/8 OCPU, 1 GB) |
| Networking | Assign a public IPv4 address |
| SSH keys | Upload your public key |

`VM.Standard.E2.1.Micro` is chosen deliberately over the Ampere A1 shapes.
Always Free includes two of them and they are almost always available, whereas
A1 capacity in popular regions can take hundreds of attempts to obtain. It also
leaves the A1 allowance (4 OCPU / 24 GB total) free for other work.

Note the public IP once the instance is running.

---

## 2. Connect

```bash
ssh -i ~/.ssh/your_key ubuntu@<public-ip>
```

Everything from here runs on the instance, not on your laptop. The prompt should
read `ubuntu@...` before you continue.

---

## 3. Install and run

```bash
sudo apt update
sudo apt install -y python3-venv git

git clone https://github.com/bhushanladde02/touchpath.git
cd touchpath
python3 -m venv .venv
.venv/bin/pip install -e ".[web]"
```

Check it starts before making it permanent:

```bash
.venv/bin/uvicorn touchpath.web.app:app --host 127.0.0.1 --port 8000 &
sleep 3
curl -s localhost:8000/healthz
```

A healthy response means the app works. Stop it again:

```bash
kill %1
```

Binding to `127.0.0.1` rather than `0.0.0.0` is intentional: the app is never
exposed directly, only through the reverse proxy in step 7.

---

## 4. Run it as a service

`/etc/systemd/system/touchpath.service`:

```ini
[Unit]
Description=touchpath
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/touchpath
ExecStart=/home/ubuntu/touchpath/.venv/bin/uvicorn touchpath.web.app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
MemoryMax=700M

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now touchpath
systemctl status touchpath --no-pager
```

`Restart=always` brings it back after a crash; `enable` brings it back after a
reboot. `MemoryMax` means a runaway request gets the service killed and
restarted rather than taking the whole box down on a 1 GB machine.

---

## 5. Open the firewall - both layers

This is the step that catches people. Oracle filters traffic in two independent
places and opening one does nothing on its own.

**Console:** Networking → Virtual Cloud Networks → your VCN → Security Lists →
default → Add Ingress Rules. Source `0.0.0.0/0`, protocol TCP, destination ports
`80` and `443`.

**On the instance** - Ubuntu images ship with restrictive iptables:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

---

## 6. Point a hostname at it

Create a subdomain at [duckdns.org](https://www.duckdns.org) and set its IP to
the instance's public address.

Oracle public IPs are static once reserved, so nothing further is needed. If
yours is ephemeral, keep it current:

```bash
cat > ~/duck.sh <<'EOF'
curl -ks "https://www.duckdns.org/update?domains=YOURNAME&token=YOURTOKEN&ip=" -o ~/duck.log
EOF
chmod 700 ~/duck.sh
(crontab -l 2>/dev/null; echo "*/5 * * * * ~/duck.sh >/dev/null 2>&1") | crontab -
```

Confirm DNS has propagated before the next step, or certificate issuance will
fail:

```bash
dig +short YOURNAME.duckdns.org
```

---

## 7. HTTPS

Caddy obtains and renews the certificate itself. No certbot, no renewal cron, no
expiry surprises.

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

Replace `/etc/caddy/Caddyfile` with:

```
YOURNAME.duckdns.org {
    reverse_proxy localhost:8000
    encode gzip
}
```

```bash
sudo systemctl reload caddy
```

Certificate issuance takes a few seconds. If it fails, port 80 is almost always
the cause - re-check both firewall layers from step 5.

---

## 8. Verify

```bash
curl -sI https://YOURNAME.duckdns.org | head -1
curl -s https://YOURNAME.duckdns.org/healthz
```

Then open it in a browser and walk the whole thing yourself before sharing the
link: run a sample from `/datasets`, confirm the chart renders, upload a file,
and use the incrementality calculator. The dashboard has no external
dependencies, so if the page loads the chart will draw - but check rather than
assume.

---

## 9. Keep it alive

Oracle reclaims Always Free compute that sits genuinely idle. A cheap heartbeat
avoids losing the instance:

```bash
(crontab -l 2>/dev/null; echo "*/10 * * * * curl -s localhost:8000/healthz >/dev/null") | crontab -
```

---

## 10. Updating later

```bash
cd ~/touchpath
git pull
.venv/bin/pip install -e ".[web]"
sudo systemctl restart touchpath
```

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `curl localhost:8000/healthz` fails | App not running - `journalctl -u touchpath -n 50` |
| Site unreachable from outside, fine locally | Firewall. Both layers, step 5. |
| Caddy cannot get a certificate | Port 80 blocked, or DNS not propagated |
| Service keeps restarting | Check `MemoryMax` - raise it, or reduce cached samples |
| Instance disappeared | Idle reclamation. Step 9. |

---

## Notes on cost and alternatives

Everything above is free and stays free. Two caveats worth knowing.

A `duckdns.org` hostname reads as a hobby deployment. For anything you want
taken seriously as a product, a `.dev` or `.io` domain is about $12 a year and
points at the same box - change one line in the Caddyfile.

If you would rather not run a server at all, `render.yaml`, a `Procfile` and a
`Dockerfile` are included for Render, Railway and Fly. Those are quicker to set
up, but the free tiers sleep after inactivity and the first request takes
roughly a minute to wake.
