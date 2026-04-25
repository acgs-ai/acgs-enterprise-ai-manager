# Deployment Guide

## Overview

This guide covers production deployment of the ACGS Enterprise Manager platform for medium-scale deployments (50-500 concurrent users).

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Load Balancer (Nginx)                    │
│                    SSL/TLS Termination                       │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
┌────────▼────────┐            ┌────────▼────────┐
│  FastAPI App    │            │  FastAPI App    │
│  (Uvicorn)      │            │  (Uvicorn)      │
│  Instance 1     │            │  Instance 2     │
└────────┬────────┘            └────────┬────────┘
         │                               │
         └───────────────┬───────────────┘
                         │
                ┌────────▼────────┐
                │   PostgreSQL    │
                │   Primary DB    │
                └─────────────────┘
```

## Prerequisites

### Infrastructure Requirements
- **CPU**: 4+ cores per application instance
- **RAM**: 8GB+ per application instance
- **Storage**: 100GB+ SSD for database
- **Network**: 1Gbps+ network interface
- **OS**: Ubuntu 22.04 LTS or similar

### Software Requirements
- Python 3.8+
- PostgreSQL 14+
- Nginx or similar reverse proxy
- Systemd for process management
- SSL/TLS certificates

## Production Setup

### 1. Server Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y python3.11 python3.11-venv postgresql-14 nginx certbot python3-certbot-nginx

# Create application user
sudo useradd -m -s /bin/bash acgs
sudo usermod -aG sudo acgs
```

### 2. Application Deployment

```bash
# Switch to application user
sudo su - acgs

# Clone repository
cd /opt
sudo git clone <repository-url> acgs-manager
sudo chown -R acgs:acgs acgs-manager
cd acgs-manager

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install gunicorn  # Production WSGI server
```

### 3. Database Setup

```bash
# Create production database
sudo -u postgres psql << 'DBEOF'
CREATE DATABASE acgs_manager_prod;
CREATE USER acgs_prod WITH PASSWORD 'STRONG_PASSWORD_HERE';
ALTER USER acgs_prod WITH SUPERUSER;
GRANT ALL PRIVILEGES ON DATABASE acgs_manager_prod TO acgs_prod;
\c acgs_manager_prod
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
DBEOF

# Run migrations
psql -U acgs_prod -d acgs_manager_prod -f database/schema.sql
```

### 4. Production Configuration

Create production environment file:

```bash
sudo cat > /opt/acgs-manager/.env.production << 'ENVEOF'
# Database
DATABASE_URL=postgresql+asyncpg://acgs_prod:STRONG_PASSWORD_HERE@localhost:5432/acgs_manager_prod

# Security
SECRET_KEY=GENERATE_WITH_openssl_rand_hex_32
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# ACGS Governance
GOVERNANCE_RULES_PATH=/opt/acgs-manager/config/governance_rules.yaml
FAIL_CLOSED=true
AUDIT_ENABLED=true

# Server
HOST=127.0.0.1
PORT=8000
RELOAD=false
WORKERS=4

# Environment
ENVIRONMENT=production
LOG_LEVEL=INFO

# CORS (adjust for your frontend domain)
CORS_ORIGINS=https://yourdomain.com

# Session
SESSION_TIMEOUT=3600
MAX_CONNECTIONS=100
ENVEOF

# Secure the file
sudo chmod 600 /opt/acgs-manager/.env.production
sudo chown acgs:acgs /opt/acgs-manager/.env.production
```

### 5. Systemd Service Configuration

Create systemd service file:

```bash
sudo cat > /etc/systemd/system/acgs-manager.service << 'SERVICEEOF'
[Unit]
Description=ACGS Enterprise Manager API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=notify
User=acgs
Group=acgs
WorkingDirectory=/opt/acgs-manager
Environment="PATH=/opt/acgs-manager/venv/bin"
EnvironmentFile=/opt/acgs-manager/.env.production
ExecStart=/opt/acgs-manager/venv/bin/gunicorn \
    --bind 127.0.0.1:8000 \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --timeout 120 \
    --access-logfile /var/log/acgs-manager/access.log \
    --error-logfile /var/log/acgs-manager/error.log \
    backend.main:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF

# Create log directory
sudo mkdir -p /var/log/acgs-manager
sudo chown acgs:acgs /var/log/acgs-manager

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable acgs-manager
sudo systemctl start acgs-manager
sudo systemctl status acgs-manager
```

### 6. Nginx Configuration

```bash
sudo cat > /etc/nginx/sites-available/acgs-manager << 'NGINXEOF'
upstream acgs_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL Configuration (managed by certbot)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Logging
    access_log /var/log/nginx/acgs-manager-access.log;
    error_log /var/log/nginx/acgs-manager-error.log;

    # Max upload size
    client_max_body_size 50M;

    # API endpoints
    location /api/ {
        proxy_pass http://acgs_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://acgs_backend;
        access_log off;
    }

    # API documentation
    location /docs {
        proxy_pass http://acgs_backend;
    }

    # Frontend (to be added when frontend is deployed)
    location / {
        root /opt/acgs-manager/frontend/dist;
        try_files $uri $uri/ /index.html;
    }
}
NGINXEOF

# Enable site
sudo ln -s /etc/nginx/sites-available/acgs-manager /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 7. SSL Certificate Setup

```bash
# Install SSL certificate with Let's Encrypt
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal is configured by default
# Test renewal
sudo certbot renew --dry-run
```

## Database Backup and Recovery

### Automated Backups

```bash
# Create backup script
sudo cat > /opt/acgs-manager/scripts/backup.sh << 'BACKUPEOF'
#!/bin/bash
BACKUP_DIR="/var/backups/acgs-manager"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/acgs_manager_$DATE.sql.gz"

mkdir -p $BACKUP_DIR

# Backup database
pg_dump -U acgs_prod acgs_manager_prod | gzip > $BACKUP_FILE

# Backup governance audit logs
tar -czf "$BACKUP_DIR/audit_logs_$DATE.tar.gz" /opt/acgs-manager/backend/governance/audit_logs/

# Keep only last 30 days of backups
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_FILE"
BACKUPEOF

sudo chmod +x /opt/acgs-manager/scripts/backup.sh

# Schedule daily backups
sudo crontab -e
# Add: 0 2 * * * /opt/acgs-manager/scripts/backup.sh
```

### Recovery

```bash
# Restore from backup
gunzip -c /var/backups/acgs-manager/acgs_manager_YYYYMMDD_HHMMSS.sql.gz | \
    psql -U acgs_prod acgs_manager_prod

# Restore audit logs
tar -xzf /var/backups/acgs-manager/audit_logs_YYYYMMDD_HHMMSS.tar.gz -C /
```

## Monitoring and Logging

### Application Logs

```bash
# View application logs
sudo journalctl -u acgs-manager -f

# View Nginx logs
sudo tail -f /var/log/nginx/acgs-manager-access.log
sudo tail -f /var/log/nginx/acgs-manager-error.log

# View governance audit logs
tail -f /opt/acgs-manager/backend/governance/audit_logs/audit_*.jsonl
```

### Health Monitoring

```bash
# Create health check script
cat > /opt/acgs-manager/scripts/health_check.sh << 'HEALTHEOF'
#!/bin/bash
HEALTH_URL="http://localhost:8000/health"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $HEALTH_URL)

if [ $RESPONSE -eq 200 ]; then
    echo "OK: Service is healthy"
    exit 0
else
    echo "ERROR: Service returned $RESPONSE"
    exit 1
fi
HEALTHEOF

chmod +x /opt/acgs-manager/scripts/health_check.sh

# Schedule health checks
# Add to crontab: */5 * * * * /opt/acgs-manager/scripts/health_check.sh
```

## Performance Tuning

### PostgreSQL Optimization

```bash
# Edit PostgreSQL configuration
sudo nano /etc/postgresql/14/main/postgresql.conf

# Recommended settings for medium-scale deployment:
# shared_buffers = 2GB
# effective_cache_size = 6GB
# maintenance_work_mem = 512MB
# checkpoint_completion_target = 0.9
# wal_buffers = 16MB
# default_statistics_target = 100
# random_page_cost = 1.1
# effective_io_concurrency = 200
# work_mem = 10MB
# min_wal_size = 1GB
# max_wal_size = 4GB
# max_connections = 200

# Restart PostgreSQL
sudo systemctl restart postgresql
```

### Application Tuning

```bash
# Adjust worker count based on CPU cores
# Rule of thumb: (2 x CPU cores) + 1
# Edit /etc/systemd/system/acgs-manager.service
# --workers 9  # For 4-core system
```

## Security Hardening

### Firewall Configuration

```bash
# Configure UFW firewall
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### Database Security

```bash
# Edit PostgreSQL access control
sudo nano /etc/postgresql/14/main/pg_hba.conf

# Restrict to local connections only
# local   all             all                                     peer
# host    all             all             127.0.0.1/32            scram-sha-256
```

### Application Security

```bash
# Ensure proper file permissions
sudo chown -R acgs:acgs /opt/acgs-manager
sudo chmod 600 /opt/acgs-manager/.env.production
sudo chmod 755 /opt/acgs-manager/backend/governance/audit_logs
```

## Scaling Considerations

### Horizontal Scaling

For deployments exceeding 500 users:

1. **Multiple Application Instances**
   - Deploy additional FastAPI instances
   - Use load balancer (Nginx, HAProxy, or cloud LB)
   - Share session state via Redis

2. **Database Replication**
   - Set up PostgreSQL primary-replica replication
   - Route read queries to replicas
   - Use connection pooling (PgBouncer)

3. **Caching Layer**
   - Add Redis for session and query caching
   - Cache governance rule evaluations
   - Cache frequently accessed entities

### Vertical Scaling

- Increase CPU cores and RAM
- Upgrade to faster SSD storage
- Optimize database indexes
- Tune PostgreSQL configuration

## Troubleshooting

### Service Won't Start

```bash
# Check service status
sudo systemctl status acgs-manager

# Check logs
sudo journalctl -u acgs-manager -n 100

# Verify configuration
source /opt/acgs-manager/venv/bin/activate
python -m backend.main --check-config
```

### Database Connection Issues

```bash
# Test database connection
psql -U acgs_prod -d acgs_manager_prod -c "SELECT 1;"

# Check PostgreSQL is running
sudo systemctl status postgresql

# Verify DATABASE_URL in .env.production
```

### High Memory Usage

```bash
# Check memory usage
free -h
ps aux --sort=-%mem | head

# Reduce worker count if needed
# Edit /etc/systemd/system/acgs-manager.service
```

## Rollback Procedure

```bash
# Stop service
sudo systemctl stop acgs-manager

# Restore database backup
gunzip -c /var/backups/acgs-manager/acgs_manager_BACKUP.sql.gz | \
    psql -U acgs_prod acgs_manager_prod

# Checkout previous version
cd /opt/acgs-manager
git checkout <previous-commit>

# Restart service
sudo systemctl start acgs-manager
```

## Maintenance Windows

Schedule regular maintenance:

1. **Weekly**: Review logs and audit trails
2. **Monthly**: Update dependencies and security patches
3. **Quarterly**: Performance review and optimization
4. **Annually**: Disaster recovery drill

## Support and Monitoring

- Monitor application logs: `/var/log/acgs-manager/`
- Monitor governance audit: `/opt/acgs-manager/backend/governance/audit_logs/`
- Monitor system resources: `htop`, `iotop`, `nethogs`
- Set up alerting for critical errors

## Next Steps

- [Monitoring Guide](monitoring.md) - Set up comprehensive monitoring
- [API Documentation](api-reference.md) - API reference
- [Governance Framework](governance.md) - Governance configuration
