# 🚀 Production Deployment Guide

**IADS Agentic SQL Agent** - Complete guide to deploying to production

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [Docker Deployment](#docker-deployment)
4. [Configuration](#configuration)
5. [Security](#security)
6. [Monitoring](#monitoring)
7. [Troubleshooting](#troubleshooting)
8. [Scaling](#scaling)

---

## Prerequisites

### System Requirements

- **Docker** 20.10+
- **Docker Compose** 2.0+
- **Python** 3.11+ (for non-containerized deployments)
- **4GB RAM** minimum
- **2GB disk space** for logs/metrics
- **Stable internet connection** (for OCI APIs)

### Credentials Required

1. **Oracle Autonomous Database (OCI)**
   - Admin username & password
   - Database wallet (.zip file)
   - Wallet password
   - DSN connection string

2. **OCI Generative AI Access**
   - OCI API credentials (.oci directory)
   - Compartment ID with GenAI permissions
   - Region specification

3. **Network Access**
   - Outbound access to Oracle Cloud
   - Outbound access to OCI Generative AI endpoints
   - Database port access (usually 1522 for Autonomous DB)

---

## Pre-Deployment Checklist

Before deploying to production, verify:

### 1. Code Quality
```bash
# Run tests
python -m pytest tests/ -v

# Check code style
python -m pylint app/ --disable=C0114,C0115,C0116

# Type checking
python -m mypy app/
```

### 2. Dependencies
```bash
# Verify all requirements are pinned
cat requirements.txt

# Test requirements
python -m pip install -r requirements.txt --dry-run
```

### 3. Database Connectivity
```bash
# Test connection
python test_connection.py
```

### 4. Configuration Files
- [ ] `.oci/config` configured with correct credentials
- [ ] `wallet/` directory contains wallet files
- [ ] `.env.production` file created and populated
- [ ] All sensitive values are correct

### 5. Security Review
- [ ] CORS origins whitelisted correctly
- [ ] Rate limiting configured (100 req/min default)
- [ ] Database passwords rotated
- [ ] API keys secured
- [ ] Logs don't contain sensitive data

### 6. Monitoring Setup
- [ ] Logging directory exists and is writable
- [ ] Metrics collection enabled
- [ ] Health checks configured
- [ ] Error alerts ready

---

## Docker Deployment

### Step 1: Prepare Environment

```bash
# Create production .env
cp .env.prod.example .env.prod

# Edit with your values
nano .env.prod
```

**Critical variables to set:**
```bash
ADB_USER=ADMIN
ADB_PASSWORD=your-password          # 🔐 KEEP SECURE
ADB_DSN=hackatondb_high
ADB_WALLET_PASSWORD=wallet-pwd      # 🔐 KEEP SECURE
OCI_CONFIG_PATH=/app/.oci
OCI_REGION=us-ashburn-1
OCI_COMPARTMENT_ID=your-compartment-id
```

### Step 2: Prepare Credentials

```bash
# Copy OCI credentials
mkdir -p .oci
cp ~/.oci/config .oci/          # Linux/Mac
# or
copy %USERPROFILE%\.oci\config .oci\  # Windows

# Copy Oracle wallet
mkdir -p wallet
# Extract wallet files into wallet/ directory
```

### Step 3: Build & Start

**Option A: Using deployment script (Recommended)**

```bash
# Linux/Mac
./deploy.sh production up

# Windows
deploy.bat production up
```

**Option B: Manual Docker Compose**

```bash
# Build images
docker-compose -f docker-compose.prod.yml build

# Start services
docker-compose -f docker-compose.prod.yml up -d

# View status
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f
```

### Step 4: Verify Services

```bash
# Check API health
curl http://localhost:8000/health

# Expected response:
# {"status": "healthy", "database": "connected"}

# Check Frontend
curl -I http://localhost:8501

# Check Monitoring
curl -I http://localhost:8502
```

---

## Configuration

### Environment Variables

All configuration is done via `.env.production` file:

```bash
# API
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO

# Database
ADB_USER=ADMIN
ADB_PASSWORD=<your-password>
ADB_DSN=hackatondb_high
ADB_WALLET_LOCATION=/app/wallet
ADB_WALLET_PASSWORD=<wallet-password>

# OCI
OCI_CONFIG_PATH=/app/.oci
OCI_REGION=us-ashburn-1
OCI_COMPARTMENT_ID=<compartment-id>
OCI_GENAI_MODEL_ID=meta.llama-3.3-70b-instruct
OCI_EMBED_MODEL_ID=cohere.embed-english-v3.0

# Agent
AGENT_MAX_RETRIES=3
AGENT_QUERY_TIMEOUT_SECONDS=15
AGENT_MAX_ROWS_RETURNED=500

# Security
ALLOWED_ORIGINS=http://localhost:8501,https://yourdomain.com
RATE_LIMIT_MAX_REQUESTS=100
```

### Volumes & Mounts

```yaml
# docker-compose.prod.yml volumes:

volumes:
  - ./.oci:/app/.oci:ro              # OCI credentials (read-only)
  - ./wallet:/app/wallet:ro          # Oracle wallet (read-only)
  - ./logs:/app/logs                 # Logs and metrics (writable)
```

Ensure these directories exist and have correct permissions:

```bash
mkdir -p logs
mkdir -p .oci
mkdir -p wallet

# Check permissions
ls -la logs
ls -la .oci
ls -la wallet
```

---

## Security

### 1. Secret Management

**Never commit secrets to version control:**

```bash
# Good: .env.prod is in .gitignore
echo ".env.prod" >> .gitignore
echo ".oci/" >> .gitignore
echo "wallet/" >> .gitignore

# Verify
git check-ignore .env.prod
```

**Use environment variables or secret managers:**

```bash
# Docker Secrets (Swarm)
docker secret create db_password -

# Kubernetes Secrets
kubectl create secret generic db-credentials \
  --from-literal=password=<password>

# HashiCorp Vault
vault kv put secret/iads/db password=<password>
```

### 2. Rate Limiting

The API includes built-in rate limiting:

```python
# Default: 100 requests per 60 seconds per client IP

# Configure in .env
RATE_LIMIT_MAX_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60

# Example response when limit exceeded:
# HTTP 429 Too Many Requests
# {"error": "Rate limit exceeded. Max 100 requests per minute."}
```

### 3. CORS Configuration

Whitelist allowed origins:

```bash
# Allow specific domains
ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Check in logs:
grep "CORS" logs/agent.log
```

### 4. API Security Best Practices

- ✅ Use HTTPS in production (add reverse proxy like Nginx)
- ✅ Implement API key authentication
- ✅ Use request signing with OCI signatures
- ✅ Limit request payload size
- ✅ Implement request timeout

### 5. Database Security

- ✅ Use Autonomous Database encryption at rest
- ✅ Enable database audit logging
- ✅ Rotate credentials regularly
- ✅ Restrict network access to database
- ✅ Use wallet-based authentication

---

## Monitoring

### Health Checks

The system has built-in health checks:

```bash
# API health
curl http://localhost:8000/health
# {"status": "healthy", "database": "connected"}

# Performance metrics (24 hours)
curl http://localhost:8000/metrics?hours=24

# Recent errors
curl http://localhost:8000/metrics/errors?limit=10
```

### Accessing Monitoring Dashboard

Visit: **http://localhost:8502**

Features:
- 📈 Real-time performance metrics
- ⚠️ Error tracking and alerts
- 📊 Latency percentiles (P50, P95, P99)
- 📋 System logs viewer
- 🟢 Service health status

### Log Files

```bash
# Logs directory
logs/
├── agent.log           # Application logs
└── metrics.jsonl       # Performance metrics (JSON Lines)

# View logs
docker-compose -f docker-compose.prod.yml logs -f api

# Tail specific file
docker exec iads-agent-api tail -f /app/logs/agent.log

# Extract metrics
docker exec iads-agent-api cat /app/logs/metrics.jsonl | jq .
```

### Setting Up Alerts

**Example: Alert on high error rate**

```bash
# Check error rate
curl http://localhost:8000/metrics | jq '.error_rate'

# Setup webhook alert (example with PagerDuty)
if [ $(curl -s http://localhost:8000/metrics | jq '.error_rate') -gt 5 ]; then
  curl -X POST https://events.pagerduty.com/v2/enqueue \
    -H 'Content-Type: application/json' \
    -d '{
      "routing_key": "YOUR_ROUTING_KEY",
      "event_action": "trigger",
      "dedup_key": "IADS-High-Error-Rate",
      "payload": {
        "summary": "IADS Agent error rate > 5%",
        "severity": "critical"
      }
    }'
fi
```

---

## Troubleshooting

### Common Issues

#### 1. "Database: disconnected"

**Symptoms:** Health check shows `"database": "disconnected"`

**Solutions:**
```bash
# Check database connectivity
docker exec iads-agent-api python test_connection.py

# Verify wallet files
docker exec iads-agent-api ls -la /app/wallet/

# Check environment variables
docker exec iads-agent-api env | grep ADB

# View logs for details
docker-compose -f docker-compose.prod.yml logs api | tail -50
```

#### 2. "Rate limit exceeded"

**Symptoms:** Getting HTTP 429 errors

**Solutions:**
```bash
# Increase rate limit in .env.prod
RATE_LIMIT_MAX_REQUESTS=200  # Increase from 100

# Restart service
docker-compose -f docker-compose.prod.yml restart api
```

#### 3. "OCI authentication failed"

**Symptoms:** GenAI calls fail, logs show auth errors

**Solutions:**
```bash
# Verify OCI credentials
docker exec iads-agent-api ls -la /app/.oci/config

# Check OCI profile
docker exec iads-agent-api cat /app/.oci/config | grep "\[DEFAULT\]"

# Test OCI connection
docker exec iads-agent-api python -c "from oci import auth; print(auth.from_file())"
```

#### 4. "Out of memory"

**Symptoms:** Container crashes with OOMKilled

**Solutions:**
```yaml
# Increase memory limit in docker-compose.prod.yml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 2G  # Increase from default
```

#### 5. "Port already in use"

**Symptoms:** Error binding to port 8000/8501/8502

**Solutions:**
```bash
# Find process using port
lsof -i :8000          # Linux/Mac
netstat -ano | findstr :8000  # Windows

# Use different ports
docker-compose -f docker-compose.prod.yml down
# Edit .env.prod or use environment variables:
export API_PORT=8080
docker-compose -f docker-compose.prod.yml up -d
```

---

## Scaling

### Horizontal Scaling (Multiple API Instances)

**Using Docker Compose with load balancer:**

```yaml
services:
  nginx:
    image: nginx:latest
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - api-1
      - api-2

  api-1:
    build: .
    environment:
      - API_PORT=8000

  api-2:
    build: .
    environment:
      - API_PORT=8001
```

### Vertical Scaling (Increase Resources)

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: iads-agent-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: iads-agent
  template:
    metadata:
      labels:
        app: iads-agent
    spec:
      containers:
      - name: api
        image: iads-agent:latest
        ports:
        - containerPort: 8000
        env:
        - name: ADB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: password
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
```

---

## Production Checklist

Before going live:

- [ ] All tests passing (pytest, linting, type checking)
- [ ] .env.production configured and secured
- [ ] Database connectivity verified
- [ ] OCI credentials working
- [ ] Health checks responding
- [ ] Monitoring dashboard accessible
- [ ] Logs being written to disk
- [ ] HTTPS configured (if public-facing)
- [ ] Rate limiting configured
- [ ] CORS origins whitelisted
- [ ] Backup strategy in place
- [ ] Disaster recovery plan documented
- [ ] Performance baselines established
- [ ] Alert rules configured
- [ ] Team trained on operations

---

## Support & Resources

- **Issues?** Check logs: `docker-compose logs -f api`
- **Metrics?** Visit: http://localhost:8502
- **API Docs?** Visit: http://localhost:8000/docs
- **Questions?** Review SETUP_GUIDE.md in docs/

---

**Last Updated:** June 3, 2026  
**Version:** 1.0.0
