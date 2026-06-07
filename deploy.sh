#!/bin/bash
# deploy.sh
# Usage: sudo bash deploy.sh [your-domain.com]

set -e

DOMAIN=$1
APP_DIR=$(pwd)
APP_USER=$SUDO_USER
if [ -z "$APP_USER" ]; then
    APP_USER=$(whoami)
fi

echo "Deploying Anki Generator SaaS..."
echo "App directory: $APP_DIR"
echo "Running as user: $APP_USER"

# 1. Update and install dependencies
echo "Installing system dependencies..."
yum update -y
yum install -y python3 python3-pip nginx git
# Try to install certbot via yum, if it fails, we will skip it for now
yum install -y certbot python3-certbot-nginx || echo "Skipping yum certbot install"

# 2. Setup Python Virtual Environment
echo "Setting up Python environment..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

# 3. Setup Systemd Service for Gunicorn
echo "Configuring systemd service..."
cat > /etc/systemd/system/anki-generator.service << EOF
[Unit]
Description=Gunicorn instance to serve Anki Generator
After=network.target

[Service]
User=$APP_USER
Group=nginx
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 3 --bind unix:anki-generator.sock -m 007 app:app

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl start anki-generator
systemctl enable anki-generator

# 4. Setup Nginx
echo "Configuring Nginx..."
if [ -z "$DOMAIN" ]; then
    SERVER_NAME="_"
    echo "No domain provided. Configuring Nginx for HTTP only on all interfaces."
else
    SERVER_NAME="$DOMAIN"
    echo "Domain provided. Configuring Nginx for $DOMAIN."
fi

cat > /etc/nginx/conf.d/anki-generator.conf << EOF
server {
    listen 80;
    server_name $SERVER_NAME;

    location / {
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_pass http://unix:$APP_DIR/anki-generator.sock;
    }
}
EOF

# Restart Nginx
systemctl enable nginx
systemctl restart nginx

# 5. SSL / HTTPS (If domain provided)
if [ ! -z "$DOMAIN" ]; then
    echo "Setting up SSL certificate for $DOMAIN via Let's Encrypt..."
    certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN || echo "Warning: Certbot failed. Please ensure your domain points to this EC2 instance's IP and run: sudo certbot --nginx -d $DOMAIN"
fi

echo "=========================================="
echo "Deployment Complete! 🚀"
if [ ! -z "$DOMAIN" ]; then
    echo "Your app should now be live at: https://$DOMAIN"
else
    echo "Your app should now be live on this server's public IP address (HTTP)."
    echo "Note: HTTPS is required for the API keys feature and AnkiConnect to work securely in modern browsers."
fi
echo "=========================================="
