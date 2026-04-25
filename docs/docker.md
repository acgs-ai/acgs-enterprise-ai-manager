# Docker Deployment Guide

## Overview

This guide covers containerized deployment of ACGS Enterprise Manager using Docker and Docker Compose.

## Quick Start with Docker Compose

### 1. Create Docker Compose File

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:14-alpine
    container_name: acgs-postgres
    environment:
      POSTGRES_DB: acgs_manager
      POSTGRES_USER: acgs_user
      POSTGRES_PASSWORD: ${DB_PASSWORD:-secure_password}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U acgs_user -d acgs_manager"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - acgs-network

  backend:
    build:
      context: .
      dockerfile: docker/Dockerfile.backend
    container_name: acgs-backend
    environment:
      DATABASE_URL: postgresql+asyncpg://acgs_user:${DB_PASSWORD:-secure_password}@postgres:5432/acgs_manager
      SECRET_KEY: ${SECRET_KEY}
      GOVERNANCE_RULES_PATH: /app/config/governance_rules.yaml
      FAIL_CLOSED: "true"
      AUDIT_ENABLED: "true"
      HOST: 0.0.0.0
      PORT: 8000
      ENVIRONMENT: production
    volumes:
      - ./backend/governance/audit_logs:/app/backend/governance/audit_logs
      - ./config:/app/config:ro
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - acgs-network
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    container_name: acgs-nginx
    volumes:
      - ./docker/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./frontend/dist:/usr/share/nginx/html:ro
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - backend
    networks:
      - acgs-network
    restart: unless-stopped

volumes:
  postgres_data:
    driver: local

networks:
  acgs-network:
    driver: bridge
```

### 2. Create Backend Dockerfile

```dockerfile
# docker/Dockerfile.backend
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY config/ ./config/
COPY database/ ./database/

# Create audit log directory
RUN mkdir -p /app/backend/governance/audit_logs && \
    chmod 755 /app/backend/governance/audit_logs

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3. Create Nginx Configuration

```nginx
# docker/nginx.conf
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:8000;
    }

    server {
        listen 80;
        server_name _;

        client_max_body_size 50M;

        # API endpoints
        location /api/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Health check
        location /health {
            proxy_pass http://backend;
            access_log off;
        }

        # API documentation
        location /docs {
            proxy_pass http://backend;
        }

        # Frontend
        location / {
            root /usr/share/nginx/html;
            try_files $uri $uri/ /index.html;
        }
    }
}
```

### 4. Create Environment File

```bash
# .env.docker
DB_PASSWORD=your_secure_database_password
SECRET_KEY=your_secret_key_generate_with_openssl_rand_hex_32
```

### 5. Start Services

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps

# Stop services
docker-compose down
```

## Production Docker Setup

### Multi-Stage Build for Backend

```dockerfile
# docker/Dockerfile.backend.production
# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY backend/ ./backend/
COPY config/ ./config/
COPY database/ ./database/

# Create non-root user
RUN useradd -m -u 1000 acgs && \
    mkdir -p /app/backend/governance/audit_logs && \
    chown -R acgs:acgs /app

USER acgs

# Set Python path
ENV PYTHONPATH=/app
ENV PATH=/root/.local/bin:$PATH

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use gunicorn for production
CMD ["gunicorn", "backend.main:app", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
```

### Production Docker Compose

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  postgres:
    image: postgres:14-alpine
    container_name: acgs-postgres
    environment:
      POSTGRES_DB: acgs_manager
      POSTGRES_USER: acgs_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql
      - ./backups:/backups
    networks:
      - acgs-network
    restart: always
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

  backend:
    build:
      context: .
      dockerfile: docker/Dockerfile.backend.production
    container_name: acgs-backend
    environment:
      DATABASE_URL: postgresql+asyncpg://acgs_user:${DB_PASSWORD}@postgres:5432/acgs_manager
      SECRET_KEY: ${SECRET_KEY}
      GOVERNANCE_RULES_PATH: /app/config/governance_rules.yaml
      FAIL_CLOSED: "true"
      AUDIT_ENABLED: "true"
      HOST: 0.0.0.0
      PORT: 8000
      ENVIRONMENT: production
      WORKERS: 4
    volumes:
      - audit_logs:/app/backend/governance/audit_logs
      - ./config:/app/config:ro
    depends_on:
      - postgres
    networks:
      - acgs-network
    restart: always
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
      replicas: 2

  nginx:
    image: nginx:alpine
    container_name: acgs-nginx
    volumes:
      - ./docker/nginx.prod.conf:/etc/nginx/nginx.conf:ro
      - ./frontend/dist:/usr/share/nginx/html:ro
      - ./ssl:/etc/nginx/ssl:ro
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - backend
    networks:
      - acgs-network
    restart: always

volumes:
  postgres_data:
    driver: local
  audit_logs:
    driver: local

networks:
  acgs-network:
    driver: bridge
```

## Docker Commands

### Build and Deploy

```bash
# Build images
docker-compose build

# Build without cache
docker-compose build --no-cache

# Start services
docker-compose up -d

# Scale backend instances
docker-compose up -d --scale backend=3

# View logs
docker-compose logs -f backend
docker-compose logs -f postgres

# Execute commands in container
docker-compose exec backend bash
docker-compose exec postgres psql -U acgs_user -d acgs_manager
```

### Database Operations

```bash
# Run migrations
docker-compose exec backend alembic upgrade head

# Create database backup
docker-compose exec postgres pg_dump -U acgs_user acgs_manager > backup.sql

# Restore database
cat backup.sql | docker-compose exec -T postgres psql -U acgs_user acgs_manager

# Access database shell
docker-compose exec postgres psql -U acgs_user -d acgs_manager
```

### Monitoring and Debugging

```bash
# Check container status
docker-compose ps

# View resource usage
docker stats

# Inspect container
docker inspect acgs-backend

# View container logs
docker logs acgs-backend --tail 100 -f

# Execute shell in container
docker-compose exec backend /bin/bash
```

## Docker Swarm Deployment

For high-availability production deployments:

```yaml
# docker-stack.yml
version: '3.8'

services:
  postgres:
    image: postgres:14-alpine
    environment:
      POSTGRES_DB: acgs_manager
      POSTGRES_USER: acgs_user
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - acgs-network
    deploy:
      replicas: 1
      placement:
        constraints:
          - node.role == manager

  backend:
    image: acgs-manager-backend:latest
    environment:
      DATABASE_URL: postgresql+asyncpg://acgs_user:${DB_PASSWORD}@postgres:5432/acgs_manager
      SECRET_KEY_FILE: /run/secrets/secret_key
    secrets:
      - secret_key
    networks:
      - acgs-network
    deploy:
      replicas: 3
      update_config:
        parallelism: 1
        delay: 10s
      restart_policy:
        condition: on-failure

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    networks:
      - acgs-network
    deploy:
      replicas: 2

secrets:
  db_password:
    external: true
  secret_key:
    external: true

volumes:
  postgres_data:

networks:
  acgs-network:
    driver: overlay
```

Deploy to swarm:

```bash
# Initialize swarm
docker swarm init

# Create secrets
echo "your_db_password" | docker secret create db_password -
echo "your_secret_key" | docker secret create secret_key -

# Deploy stack
docker stack deploy -c docker-stack.yml acgs

# List services
docker stack services acgs

# Scale service
docker service scale acgs_backend=5

# Remove stack
docker stack rm acgs
```

## Kubernetes Deployment

### Deployment YAML

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: acgs-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: acgs-backend
  template:
    metadata:
      labels:
        app: acgs-backend
    spec:
      containers:
      - name: backend
        image: acgs-manager-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: acgs-secrets
              key: database-url
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: acgs-secrets
              key: secret-key
        volumeMounts:
        - name: audit-logs
          mountPath: /app/backend/governance/audit_logs
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: audit-logs
        persistentVolumeClaim:
          claimName: audit-logs-pvc
```

## Backup and Recovery

### Automated Backup Script

```bash
#!/bin/bash
# docker/backup.sh

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup database
docker-compose exec -T postgres pg_dump -U acgs_user acgs_manager | \
    gzip > "$BACKUP_DIR/db_backup_$DATE.sql.gz"

# Backup audit logs
docker-compose exec -T backend tar -czf - /app/backend/governance/audit_logs > \
    "$BACKUP_DIR/audit_logs_$DATE.tar.gz"

# Keep only last 30 days
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
```

### Restore from Backup

```bash
# Restore database
gunzip -c /backups/db_backup_YYYYMMDD_HHMMSS.sql.gz | \
    docker-compose exec -T postgres psql -U acgs_user acgs_manager

# Restore audit logs
docker-compose exec -T backend tar -xzf - -C / < \
    /backups/audit_logs_YYYYMMDD_HHMMSS.tar.gz
```

## Performance Tuning

### PostgreSQL Configuration

```yaml
# docker-compose.yml
services:
  postgres:
    command:
      - "postgres"
      - "-c"
      - "shared_buffers=2GB"
      - "-c"
      - "effective_cache_size=6GB"
      - "-c"
      - "max_connections=200"
```

### Backend Scaling

```bash
# Scale backend instances
docker-compose up -d --scale backend=4

# Or in docker-compose.yml:
services:
  backend:
    deploy:
      replicas: 4
```

## Security Best Practices

1. **Use Secrets**: Never hardcode passwords in docker-compose.yml
2. **Non-Root User**: Run containers as non-root user
3. **Read-Only Filesystem**: Mount config as read-only
4. **Network Isolation**: Use custom networks
5. **Resource Limits**: Set CPU and memory limits
6. **Health Checks**: Implement proper health checks
7. **Image Scanning**: Scan images for vulnerabilities

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs backend

# Check container status
docker-compose ps

# Inspect container
docker inspect acgs-backend
```

### Database Connection Issues

```bash
# Test database connection
docker-compose exec backend python -c "
from backend.database import engine
print('Database connected')
"

# Check PostgreSQL logs
docker-compose logs postgres
```

### High Memory Usage

```bash
# Check resource usage
docker stats

# Reduce worker count
# Edit docker-compose.yml:
environment:
  WORKERS: 2
```

## References

- [Deployment Guide](deployment.md) - Production deployment
- [Installation Guide](installation.md) - Local installation
- [Architecture](architecture.md) - System architecture
