# Mentorship Helper

A full-stack mentorship application for the osu! community with FastAPI backend, Discord bot integration, and PostgreSQL database. Ready for containerized deployment.

**Live Domain:** `mentorship.actiol.dev`

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Configuration](#configuration)
5. [Deployment](#deployment)
6. [Project Structure](#project-structure)
7. [Development](#development)
8. [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

This application provides a comprehensive mentorship platform for osu! players, featuring:

- **FastAPI Backend** - Modern async REST API for user management, mentorship matching, and file handling
- **Discord Bot** - Integration with Discord for user verification and community engagement
- **PostgreSQL Database** - Persistent data storage with SQLAlchemy ORM
- **Nginx Reverse Proxy** - SSL/TLS termination and request routing
- **Docker Stack** - Production-ready containerized deployment
- **Loguru Logging** - Structured, colored logging throughout the application

### Services

| Service | Role | Tech Stack |
|---------|------|-----------|
| **API** | Backend server | FastAPI + FastAPI + Uvicorn |
| **Bot** | Discord integration | discord.py |
| **Database** | Data persistence | PostgreSQL 16 |
| **Nginx** | Reverse proxy | Nginx 1.27 Alpine |

---

## 📦 Prerequisites

### For Local Development
- Docker & Docker Compose
- Python 3.12+ (optional, for IDE support)
- PostgreSQL client tools (psql) (optional)

### For Portainer Deployment
- Portainer instance (running on Docker)
- Docker host with 2GB+ RAM
- SSL certificates or Let's Encrypt setup
- OAuth credentials from osu! and Discord

---

## 🚀 Quick Start

### Option 1: Local Development (with Docker)

```bash
# Clone repository
git clone https://github.com/Actiol/mentorship-helper.git
cd mentorship-helper

# Copy and configure environment
cp .env.example .env
# Edit .env with your test credentials

# Start services with development overrides (hot reload, exposed ports)
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d

# View logs
docker-compose logs -f api

# Access
- API: http://localhost:8001/docs (interactive API documentation)
- Database: localhost:5432 (psql client)
```

### Option 2: Production on Portainer

See [Portainer Deployment](#portainer-deployment) section below.

---

## ⚙️ Configuration

### Environment Variables (Required)

Create a `.env` file with these variables:

```bash
# Database
POSTGRES_PASSWORD=<strong_random_password>
POSTGRES_USER=mentorship
POSTGRES_DB=mentorship

# Secrets (generate with: openssl rand -hex 32)
JWT_SECRET=<64_hex_characters>
API_BOT_SECRET=<64_hex_characters>

# osu! OAuth (register at https://osu.ppy.sh/home/account/edit#oauth)
OSU_CLIENT_ID=<your_osu_id>
OSU_CLIENT_SECRET=<your_osu_secret>

# Discord Bot (create at https://discord.com/developers/applications)
DISCORD_BOT_TOKEN=<your_bot_token>
DISCORD_TOKEN=<same_as_above>
DISCORD_CLIENT_ID=<your_app_id>

# URLs
BASE_URL=https://mentorship.actiol.dev
API_BASE_URL=https://mentorship.actiol.dev
OSU_VERIFY_BASE_URL=https://mentorship.actiol.dev/auth/discord-verify
ALLOWED_ORIGINS=https://osu.ppy.sh

# Logging
LOG_LEVEL=info
```

### How to Generate Secrets

```bash
# Generate JWT_SECRET
JWT_SECRET=$(openssl rand -hex 32)
echo "JWT_SECRET=$JWT_SECRET"

# Generate POSTGRES_PASSWORD
POSTGRES_PASSWORD=$(openssl rand -hex 32)
echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD"

# Generate API_BOT_SECRET
API_BOT_SECRET=$(openssl rand -hex 32)
echo "API_BOT_SECRET=$API_BOT_SECRET"
```

---

## 🐳 Deployment

### Portainer Deployment (Production)

#### 1. Prepare Infrastructure

```bash
# Set up SSL certificates (Let's Encrypt recommended)
docker run -it --rm -p 80:80 \
  -v /path/to/certs:/etc/letsencrypt \
  certbot/certbot certonly --standalone \
  -d mentorship.actiol.dev

# Copy certificates to repository
cp /etc/letsencrypt/live/mentorship.actiol.dev/fullchain.pem nginx/certs/
cp /etc/letsencrypt/live/mentorship.actiol.dev/privkey.pem nginx/certs/
chmod 644 nginx/certs/*
```

#### 2. Create Stack in Portainer

1. Open Portainer dashboard
2. Navigate to **Stacks** → **Add Stack**
3. Choose upload method:
   - **Web Editor**: Paste content of `docker-compose.prod.yml`
   - **Git**: `https://github.com/Actiol/mentorship-helper.git`

#### 3. Configure Environment Variables

In Portainer's **Environment** section, add:

```env
POSTGRES_PASSWORD=<your_password>
POSTGRES_USER=mentorship
POSTGRES_DB=mentorship
JWT_SECRET=<your_jwt_secret>
OSU_CLIENT_ID=<from_osu>
OSU_CLIENT_SECRET=<from_osu>
DISCORD_BOT_TOKEN=<from_discord>
DISCORD_TOKEN=<from_discord>
DISCORD_CLIENT_ID=<from_discord>
API_BOT_SECRET=<your_api_bot_secret>
BASE_URL=https://mentorship.actiol.dev
API_BASE_URL=https://mentorship.actiol.dev
OSU_VERIFY_BASE_URL=https://mentorship.actiol.dev/auth/discord-verify
ALLOWED_ORIGINS=https://osu.ppy.sh
LOG_LEVEL=info
```

#### 4. Deploy Stack

1. Click **Deploy the stack**
2. Monitor in **Stacks** → **mentorship** → **Services**
3. Wait for all services to show `healthy` or `running`

#### 5. Verify Deployment

```bash
# Health check
curl -k https://mentorship.actiol.dev/health
# Expected: {"ok": true}

# API documentation
curl -k https://mentorship.actiol.dev/docs
# Expected: Interactive API docs page
```

---

## 📁 Project Structure

```
mentorship-helper/
├── docker-compose.yml              # Main stack (base config)
├── docker-compose.prod.yml         # Production optimizations
├── docker-compose.override.yml     # Development overrides
├── .env.example                    # Environment template
├── .env.portainer                  # Portainer environment template
├── .dockerignore                   # Build optimization
│
├── api/                            # FastAPI Backend
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py               # FastAPI application
│       ├── config.py             # Configuration management
│       ├── routers/              # API endpoints
│       └── ...
│
├── bot/                            # Discord Bot
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py               # Bot entry point
│       ├── config.py
│       ├── cogs/                 # Discord command groups
│       └── ...
│
├── shared/                         # Shared Code
│   ├── models.py                 # SQLAlchemy models
│   ├── database.py               # Database configuration
│   └── ...
│
├── nginx/                          # Reverse Proxy
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── certs/                    # SSL certificates (gitignored)
│   └── ...
│
├── userscript/                     # Tampermonkey Script
│   └── mentorship.user.js
│
└── README.md                       # This file
```

---

## 💻 Development

### Local Setup with Hot Reload

```bash
# Start with development overrides
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d

# Changes to ./api and ./bot automatically reload
# Exposed ports:
#   - API direct: localhost:8001
#   - Nginx: localhost:80
#   - Database: localhost:5432
```

### Building Images

```bash
# Build all images
docker-compose build

# Build specific image
docker-compose build api

# Build without cache
docker-compose build --no-cache
```

### Database Access

```bash
# Connect to PostgreSQL
docker exec -it mentorship-db psql -U mentorship -d mentorship

# Run SQL query
docker exec mentorship-db psql -U mentorship -d mentorship -c "SELECT 1;"

# Backup database
docker exec mentorship-db pg_dump -U mentorship mentorship > backup.sql
```

### Logs

All services use **loguru** for structured logging:

```bash
# View logs
docker logs -f mentorship-api      # FastAPI logs
docker logs -f mentorship-bot      # Discord bot logs
docker logs -f mentorship-nginx    # Nginx logs
docker logs -f mentorship-db       # PostgreSQL logs
```

Logs are color-coded and structured for easy parsing:
- 🟦 **DEBUG** - Development debugging
- 🟩 **INFO** - Normal operation
- 🟨 **WARNING** - Potential issues
- 🟥 **ERROR** - Errors (check these!)

---

## 🐛 Troubleshooting

### Service Won't Start

```bash
# Check logs
docker logs mentorship-api

# Verify environment variables
docker inspect mentorship-api | grep -i env

# Common causes:
# - Missing POSTGRES_PASSWORD env var
# - Port already in use
# - Disk space full
```

### Database Connection Failed

```bash
# Test database directly
docker exec mentorship-db psql -U mentorship -c "SELECT 1;"

# If fails, check logs
docker logs mentorship-db

# Verify password matches in .env
grep POSTGRES_PASSWORD .env
```

### API Not Responding

```bash
# Check API health
curl http://localhost:8001/health

# Check logs for startup errors
docker logs -f mentorship-api

# Restart service
docker-compose restart api
```

### High Memory/CPU Usage

```bash
# Check container stats
docker stats mentorship-*

# Reduce log verbosity
# In .env: LOG_LEVEL=warning

# Check for memory leaks in logs
docker logs -f mentorship-api | grep -i "memory\|leak"
```

---

## 📝 Key Features

### Security
- ✅ TLS 1.2+ with modern ciphers
- ✅ CORS properly configured
- ✅ Environment variables for secrets (not in code)
- ✅ Private Docker network (database isolated)
- ✅ Health checks with auto-restart

### Performance
- ✅ HTTP/2 support
- ✅ Connection pooling
- ✅ Database indexes
- ✅ Caching strategies
- ✅ Keepalive connections

### Observability
- ✅ Structured JSON logging with **loguru**
- ✅ Health check endpoints
- ✅ Docker health checks
- ✅ Automatic log rotation
- ✅ Color-coded terminal output

---

## 📚 Additional Resources

- **API Documentation**: http://localhost:8001/docs (Swagger UI)
- **osu! OAuth Setup**: https://osu.ppy.sh/home/account/edit#oauth
- **Discord Developer Portal**: https://discord.com/developers/applications
- **Docker Docs**: https://docs.docker.com/
- **Portainer Docs**: https://docs.portainer.io/
- **FastAPI Docs**: https://fastapi.tiangolo.com/

---

## 🤝 Contributing

See the main repository for contribution guidelines.

---

## 📄 License

See LICENSE file in repository.

---

## ✅ Checklist for Production Deployment

- [ ] SSL certificates obtained and installed
- [ ] OAuth credentials from osu! and Discord registered
- [ ] All 7 required environment variables set
- [ ] Database backups configured
- [ ] Monitoring/alerting configured (optional)
- [ ] Logs reviewed and no errors present
- [ ] Health endpoints responding correctly
- [ ] Performance baselines established
- [ ] Disaster recovery plan documented
- [ ] Team trained on operational procedures

---

**Status:** Ready for Production Deployment ✅  
**Last Updated:** 2026-05-25  
**Maintainer:** [Your Team]
