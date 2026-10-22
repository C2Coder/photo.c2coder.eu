#!/usr/bin/env bash
# Setup of the photo admin (photo-admin.c2cdn.eu) on the hetzner VPS, safe to re-run:
#     sudo bash deploy/deploy.sh
# Code arrives via Syncthing; re-run after admin code, requirements or nginx.conf changes.
# Needs ~/.config/photo-admin/env (R2 keys, Access AUD) - see README.
set -euo pipefail

APP_DIR=/home/c2coder/Codes/Projects/C2Coder/photo.c2coder.eu
DATA_DIR=/home/c2coder/.local/share/photo-admin
ENV_FILE=/home/c2coder/.config/photo-admin/env
KEY=/home/c2coder/.ssh/photo-admin
DOMAIN=photo-admin.c2cdn.eu
as_me() { sudo -u c2coder "$@"; }

[[ $EUID -eq 0 ]] || { echo "Run this with sudo." >&2; exit 1; }
[[ -f $APP_DIR/admin.py ]] || { echo "$APP_DIR not synced yet." >&2; exit 1; }
[[ -f $ENV_FILE ]] || { echo "$ENV_FILE is missing." >&2; exit 1; }
chmod 600 "$ENV_FILE"

echo "==> deploy key + content clone"
if [[ ! -f $KEY ]]; then
  as_me ssh-keygen -q -t ed25519 -N "" -C photo-admin@hetzner -f "$KEY"
  as_me bash -c 'ssh-keyscan -q github.com >> ~/.ssh/known_hosts 2>/dev/null'
fi
if [[ ! -d $DATA_DIR/repo/.git ]]; then
  as_me mkdir -p "$DATA_DIR"
  if ! as_me env GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes" \
      git clone -q git@github.com:C2Coder/photo.c2coder.eu.git "$DATA_DIR/repo"; then
    echo
    echo "Add this deploy key with write access, then re-run:"
    echo "  gh repo deploy-key add - -R C2Coder/photo.c2coder.eu --allow-write -t 'photo-admin hetzner' <<< '$(cat $KEY.pub)'"
    exit 1
  fi
  as_me git -C "$DATA_DIR/repo" config user.name C2Coder
  as_me git -C "$DATA_DIR/repo" config user.email jansky.stepan08@gmail.com
fi

echo "==> venv"
[[ -d $APP_DIR/.venv ]] || as_me python3 -m venv "$APP_DIR/.venv"
as_me "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

if [[ ! -d /etc/letsencrypt/live/$DOMAIN ]]; then
  echo "==> temporary HTTP site for the certbot challenge"
  cat > /etc/nginx/sites-available/$DOMAIN <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/html; }
}
NGINX
  ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/$DOMAIN
  nginx -t && systemctl reload nginx
  echo "==> certificate"
  certbot certonly --webroot -w /var/www/html -d $DOMAIN \
      --non-interactive --agree-tos -m me@c2coder.eu
fi

echo "==> service"
cp "$APP_DIR/deploy/photo-admin.service" /etc/systemd/system/photo-admin.service
systemctl daemon-reload
systemctl enable photo-admin
systemctl restart photo-admin

echo "==> nginx site"
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/$DOMAIN
ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/$DOMAIN
nginx -t && systemctl reload nginx

sleep 2
code=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: $DOMAIN" http://127.0.0.1:8327/)
echo "Admin answers $code on loopback (403 = running, wants a Cloudflare Access login)"
echo "Open https://$DOMAIN"
