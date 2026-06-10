# Docker Deployment Guide

## Quick Start with Docker

### Prerequisites
- Docker Desktop installed
- `.env` file configured in project root
- Oracle wallet files in `./wallet/`
- OCI credentials in `C:\Users\asadc\.oci\` (host machine)

### Build and Run

#### 1. Build the Docker Image

```bash
docker build -t iads-sql-agent:latest .
```

#### 2. Run with Docker Compose (Recommended)

```bash
docker-compose up
```

This starts:
- **API**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs
- **Health check**: http://localhost:8000/health

#### 3. Run Individual Container

```bash
docker run -p 8000:8000 \
  --env-file .env \
  -v ./wallet:/app/wallet:ro \
  -v ./data:/app/data \
  iads-sql-agent:latest
```

## Docker Compose Services

### API Service

```yaml
api:
  build: .
  ports:
    - "8000:8000"
  env_file:
    - .env
  volumes:
    - ./wallet:/app/wallet:ro
  healthcheck:
    test: ["CMD", "curl", "-fsS", "http://localhost:8000/health"]
    interval: 30s
    timeout: 5s
    retries: 3
```

### UI Service (Streamlit)

```yaml
ui:
  build: .
  ports:
    - "8501:8501"
  env_file:
    - .env
  command: streamlit run frontend/streamlit_app.py --server.port=8501
```

## Environment Variables in Container

These are loaded from `.env` file:

```env
OCI_CONFIG_PATH=/app/.oci/config
ADB_WALLET_LOCATION=/app/wallet
PYTHONPATH=/app:/app/src
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8000
```

## Mounting OCI Credentials

### Option 1: Mount From Host (Development)

```bash
docker run -p 8000:8000 \
  -v ~/.oci:/home/appuser/.oci:ro \
  -v ./wallet:/app/wallet:ro \
  --env-file .env \
  iads-sql-agent:latest
```

Update `OCI_CONFIG_PATH` in `.env`:
```env
OCI_CONFIG_PATH=/home/appuser/.oci/config
```

### Option 2: Copy Into Image (Production)

```dockerfile
# Add to Dockerfile
COPY .oci /home/appuser/.oci
RUN chown -R appuser /home/appuser/.oci
```

⚠️ **Security Warning**: Never commit `.oci` credentials to git!

## Health Checks

The container includes automated health checks:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1
```

Check status:
```bash
docker ps
# STATUS column shows "healthy" or "unhealthy"
```

## Logs and Debugging

### View Logs

```bash
# All logs
docker-compose logs -f

# API logs only
docker-compose logs -f api

# Last 100 lines
docker-compose logs --tail=100 api
```

### Shell Access

```bash
docker-compose exec api bash
```

### Run Python REPL

```bash
docker-compose exec api python
```

## Multi-Stage Build (Production Optimization)

```dockerfile
# Build stage
FROM python:3.11-slim as builder
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --user --no-cache-dir -e .

# Runtime stage
FROM python:3.11-slim
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY app ./app
COPY src ./src
# ... rest of runtime setup
```

## Kubernetes Deployment

### Create ConfigMap for environment

```bash
kubectl create configmap sql-agent-config --from-file=.env
```

### Create Secret for wallet

```bash
kubectl create secret generic sql-agent-wallet \
  --from-file=wallet/
```

### Deployment manifest

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sql-agent-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: sql-agent
  template:
    metadata:
      labels:
        app: sql-agent
    spec:
      containers:
      - name: api
        image: iads-sql-agent:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: sql-agent-config
        volumeMounts:
        - name: wallet
          mountPath: /app/wallet
          readOnly: true
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 20
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
      volumes:
      - name: wallet
        secret:
          secretName: sql-agent-wallet
---
apiVersion: v1
kind: Service
metadata:
  name: sql-agent-api
spec:
  type: LoadBalancer
  ports:
  - port: 8000
    targetPort: 8000
  selector:
    app: sql-agent
```

Deploy:
```bash
kubectl apply -f deployment.yaml
kubectl get service sql-agent-api
```

## OCI Container Registry

### Push to OCI Registry

```bash
# Tag image
docker tag iads-sql-agent:latest \
  <region>.ocir.io/<tenancy>/<repo>/iads-sql-agent:latest

# Push
docker push <region>.ocir.io/<tenancy>/<repo>/iads-sql-agent:latest
```

### Deploy to OCI Container Instances

```bash
oci compute container-instances create \
  --compartment-id <COMPARTMENT_ID> \
  --display-name sql-agent-prod \
  --containers '[{
    "imageUrl": "<region>.ocir.io/<tenancy>/<repo>/iads-sql-agent:latest",
    "displayName": "sql-agent"
  }]'
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs api

# Common issues:
# - Missing .env file
# - Missing wallet directory
# - Port 8000 already in use
```

### Health check failing

```bash
# Test manually inside container
docker-compose exec api curl http://localhost:8000/health

# Check DB connection
docker-compose exec api python -c "from app.sql.oracle_connection import connect_adb; print('Connected!')"
```

### Out of memory

```yaml
# Add memory limits to docker-compose.yml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
```

## Performance Tips

1. **Use multi-stage builds** to reduce image size
2. **Pin Python version** (3.11-slim is good)
3. **Use volume mounts** for hot reloading in dev
4. **Enable BuildKit** for faster builds: `DOCKER_BUILDKIT=1`
5. **Cache layers properly**: install deps before copying code

## Security Best Practices

- ✅ Run as non-root user (`appuser`)
- ✅ Mount wallet read-only (`:ro`)
- ✅ Don't commit secrets to git
- ✅ Use .dockerignore to exclude unnecessary files
- ✅ Scan images for vulnerabilities: `docker scout cves iads-sql-agent:latest`

