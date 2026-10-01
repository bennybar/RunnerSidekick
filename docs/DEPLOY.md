# Deploying the API — runnersidekick.ibarak.org

Layout: code in `/var/www/RunnerSidekick`, data in `/var/lib/runnersidekick` (0700, created by systemd), secrets in
`/etc/runnersidekick.env`. The API listens on `127.0.0.1:8765`, and nginx terminates TLS for the public hostname.

```sh
# 1. Service user and code
sudo useradd --system --home /var/lib/runnersidekick --shell /usr/sbin/nologin runnersidekick
sudo git clone <repo> /var/www/RunnerSidekick        # or rsync the repo
cd /var/www/RunnerSidekick/backend
sudo python3.12 -m venv .venv && sudo .venv/bin/pip install -r requirements.txt

# 2. Secrets (optional: only needed for AI summaries)
sudo install -m 600 -o root -g root /dev/null /etc/runnersidekick.env
echo 'OPENAI_API_KEY=sk-...' | sudo tee -a /etc/runnersidekick.env >/dev/null

# 3. Units
sudo cp ../deploy/runnersidekick.service ../deploy/runnersidekick-sync.service ../deploy/runnersidekick-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now runnersidekick.service        # creates /var/lib/runnersidekick

# 4. Garmin session: either copy your existing tokens and history from the Mac (recommended: Garmin often
#    rate-limits logins from datacenter IPs) ...
rsync -a ~/.runner-sidekick/garmin_tokens ~/.runner-sidekick/garmin.db server:/tmp/rsk/     # on the Mac
sudo systemctl stop runnersidekick
sudo cp -r /tmp/rsk/* /var/lib/runnersidekick/ && sudo chown -R runnersidekick: /var/lib/runnersidekick && rm -rf /tmp/rsk
sudo systemctl start runnersidekick
#    ... or log in on the server (interactive):
sudo -u runnersidekick env RSK_SOURCE=garmin RSK_DATA_DIR=/var/lib/runnersidekick \
    /var/www/RunnerSidekick/backend/.venv/bin/python -m sidekick garmin-login

# 5. Device token for the phone (printed once)
sudo -u runnersidekick env RSK_DATA_DIR=/var/lib/runnersidekick \
    /var/www/RunnerSidekick/backend/.venv/bin/python -m sidekick create-token pixel

# 6. Hourly sync
sudo systemctl enable --now runnersidekick-sync.timer

# 7. TLS first (DNS for runnersidekick.ibarak.org must already point here), then the proxy config that uses it
sudo certbot certonly --nginx -d runnersidekick.ibarak.org
sudo cp ../deploy/nginx-runnersidekick.conf /etc/nginx/sites-available/runnersidekick.conf
sudo ln -s /etc/nginx/sites-available/runnersidekick.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Check it:

```sh
curl -s -o /dev/null -w '%{http_code}\n' https://runnersidekick.ibarak.org/v1/status                       # 401 without token
curl -s -H "Authorization: Bearer <token>" https://runnersidekick.ibarak.org/v1/status | head -c 200       # 200
journalctl -u runnersidekick -u runnersidekick-sync -n 50
```

In the app: Settings → Connection → URL `https://runnersidekick.ibarak.org` (the release-build default), then the token.

Updating: `git pull`, then `.venv/bin/pip install -r requirements.txt` and `sudo systemctl restart runnersidekick`.
Migrations apply automatically on start. Back up `/var/lib/runnersidekick` like any other private data. It contains
health data and the Garmin session.
