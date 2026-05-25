# Mentorship Helper

A full-stack mentorship application for the osu! community with FastAPI backend, Discord bot integration, and PostgreSQL database. Deployed on Portainer.

**Live Domain:** `mentorship.actiol.dev`

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Deployment](#deployment)
4. [Project Structure](#project-structure)
5. [Configuration](#configuration)
6. [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

This application provides a comprehensive mentorship platform for osu! players, featuring:

- **FastAPI Backend** - Modern async REST API for user management, mentorship matching, and file handling
- **Discord Bot** - Integration with Discord for user verification and community engagement
- **PostgreSQL Database** - Persistent data storage with SQLAlchemy ORM
- **Nginx Reverse Proxy** - SSL/TLS termination and request routing
- **Docker Stack** - Production-ready containerized deployment on Portainer
- **Loguru Logging** - Structured, colored logging throughout the application

### Services

| Service | Role | Tech Stack |
|---------|------|-----------|
| **API** | Backend server | FastAPI + Uvicorn |
| **Bot** | Discord integration | discord.py |
| **Database** | Data persistence | PostgreSQL 16 |
| **Nginx** | Reverse proxy | Nginx 1.27 Alpine |

---

## 📦 Prerequisites

- **Portainer instance** running on Docker
- **Docker host** with 2GB+ RAM minimum
- **DNS records** pointing `mentorship.actiol.dev` to your server
- **OAuth credentials:**
  - osu! OAuth: Register at https://osu.ppy.sh/home/account/edit#oauth
  - Discord Bot: Create at https://discord.com/developers/applications
- **SSL certificates** (Let's Encrypt recommended, or self-signed)

---

## 🐳 Deployment

### Step 1: Prepare Secrets

Generate secure random values for sensitive environment variables. Use an online generator or:

**For JWT_SECRET, API_BOT_SECRET, POSTGRES_PASSWORD:**
- Use a secure random string (64+ hex characters recommended)
- Example values (DO NOT USE THESE):
  ```
  JWT_SECRET: a1b2c3d4e5f6... (64 hex chars)
  POSTGRES_PASSWORD: x9y8z7w6v5u4... (64 hex chars)
  API_BOT_SECRET: m1n2o3p4q5r6... (64 hex chars)
  ```

### Step 2: Create Stack in Portainer

**Important:** Use **Git Repository** method only (not Web Editor):

1. Open **Portainer dashboard**
2. Navigate to **Stacks** → **Add Stack**
3. Select **Repository**
4. Fill in:
   - **Repository URL:** `https://github.com/Actiol/mentorship-helper.git`
   - **Repository Reference:** `main`
   - **Compose file:** `docker-compose.prod.yml`
   - **Auto-update:** Check if you want automatic redeploys on git push
5. Click **Next**

**Why Git Repository?** Portainer clones your repository and builds images from Dockerfiles. This is required—pasting compose files directly won't work.

### Step 3: Configure Environment Variables

In Portainer's **Environment** section, add these variables:

```env
POSTGRES_PASSWORD=<generate_secure_random>
POSTGRES_USER=mentorship
POSTGRES_DB=mentorship
JWT_SECRET=<generate_secure_random>
API_BOT_SECRET=<generate_secure_random>
OSU_CLIENT_ID=<from_osu_oauth_portal>
OSU_CLIENT_SECRET=<from_osu_oauth_portal>
DISCORD_BOT_TOKEN=<from_discord_developer_portal>
DISCORD_TOKEN=<same_as_discord_bot_token>
DISCORD_CLIENT_ID=<from_discord_developer_portal>
BASE_URL=https://mentorship.actiol.dev
API_BASE_URL=https://mentorship.actiol.dev
OSU_VERIFY_BASE_URL=https://mentorship.actiol.dev/auth/discord-verify
ALLOWED_ORIGINS=https://osu.ppy.sh
LOG_LEVEL=info
```

### Step 4: Deploy Stack

1. Click **Deploy the stack**
2. Monitor in **Stacks** → **mentorship** → **Services** tab
3. Wait for all services to show `healthy` or `running` status

### Step 5: Verify Deployment

Once deployed, verify everything is working:

1. **Check Services Status:**
   - Stacks → mentorship → Services
   - All services should show ✅ healthy or running

2. **Test API:**
   - Open browser: `https://mentorship.actiol.dev/docs`
   - Should show interactive API documentation

3. **Check Logs:**
   - Stacks → mentorship → Logs
   - Should show clean startup messages (no errors)

### Step 6: Cloudflare Tunnel Integration

If using Cloudflare tunnel, configure it to point to your internal mentorship service:

**In Cloudflare Tunnel Config:**
- **Service:** `http://mentorship-api:8000` or `http://nginx` (depends on your setup)
- **Network:** Stack name will be `mentorship` (Portainer auto-prefixes network names)

---

## ⚙️ Configuration

### Environment Variables Reference

| Variable | Purpose | Example |
|----------|---------|---------|
| `POSTGRES_PASSWORD` | Database password | Generate secure random |
| `POSTGRES_USER` | Database user | `mentorship` |
| `POSTGRES_DB` | Database name | `mentorship` |
| `JWT_SECRET` | JWT signing key | Generate secure random |
| `API_BOT_SECRET` | API-Bot communication secret | Generate secure random |
| `OSU_CLIENT_ID` | osu! OAuth client ID | From osu portal |
| `OSU_CLIENT_SECRET` | osu! OAuth client secret | From osu portal |
| `DISCORD_BOT_TOKEN` | Discord bot token | From Discord portal |
| `DISCORD_TOKEN` | Same as bot token | Same as above |
| `DISCORD_CLIENT_ID` | Discord app ID | From Discord portal |
| `BASE_URL` | Public base URL | `https://mentorship.actiol.dev` |
| `API_BASE_URL` | API endpoint URL | `https://mentorship.actiol.dev` |
| `OSU_VERIFY_BASE_URL` | OSU verification callback | `https://mentorship.actiol.dev/auth/discord-verify` |
| `ALLOWED_ORIGINS` | CORS origins | `https://osu.ppy.sh` |
| `LOG_LEVEL` | Logging level | `info` or `debug` |

### Discord Bot Setup (Critical)

Your Discord bot **must have intents enabled** in Discord Developer Portal:

1. Go to **https://discord.com/developers/applications**
2. Select your application
3. Click **Bot** section
4. Under **Privileged Gateway Intents**, enable:
   - ✅ **Server Members Intent**
   - ✅ **Message Content Intent**
   - ✅ **Guild Messages**
5. Click **Save Changes**
6. Restart the bot service in Portainer

---

## 📁 Project Structure

```
mentorship-helper/
├── docker-compose.yml              # Base configuration
├── docker-compose.prod.yml         # Production stack (used by Portainer)
├── docker-compose.override.yml     # Local dev overrides (ignored by Portainer)
├── .env.example                    # Environment template
├── .dockerignore                   # Build optimization
│
├── api/                            # FastAPI Backend
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py               # FastAPI entry point
│       ├── config.py             # Configuration
│       ├── routers/              # API endpoints
│       └── ...
│
├── bot/                            # Discord Bot
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py               # Bot entry point
│       ├── config.py
│       ├── cogs/                 # Discord commands
│       └── ...
│
├── shared/                         # Shared Code
│   ├── models.py                 # SQLAlchemy models
│   ├── database.py               # Database config
│   └── ...
│
├── nginx/                          # Reverse Proxy
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── certs/                    # SSL certificates
│   └── ...
│
├── userscript/                     # Tampermonkey Script
│   └── mentorship.user.js
│
└── README.md                       # This file
```

---

## 🐛 Troubleshooting

### Stack Shows "Created Outside of Portainer"

**Cause:** Stack was deployed outside Portainer UI (or using Web Editor instead of Git Repository)

**Fix (Portainer GUI only):**
1. **Stacks** → Select your stack → **Delete**
2. **Stacks** → **Add Stack** → **Repository** (not Web Editor)
3. Enter Git details and redeploy

### Discord Bot: PrivilegedIntentsRequired

**Error:** `discord.errors.PrivilegedIntentsRequired`

**Fix:**
1. Go to **https://discord.com/developers/applications**
2. Select your application → **Bot** → **Intents**
3. Enable: ✅ Server Members, ✅ Message Content, ✅ Guild Messages
4. Save and restart bot service (Stacks → mentorship → Services → Restart bot)

**Why?** Discord requires explicit intent declarations for privileged operations.

### API Not Responding / Service Crashes

**Debug in Portainer UI:**
1. **Stacks** → **mentorship** → **Services**
2. Click the failing service (e.g., `api`)
3. Click **Logs** tab
4. Review error messages
5. Check if all environment variables are set

**Common causes:**
- Missing environment variables
- Invalid database password
- Incorrect Discord/osu! credentials
- Network connectivity issues

### Database Connection Failed

**Check database health:**
1. **Stacks** → **mentorship** → **Services** → **db**
2. Verify status is ✅ healthy
3. Check Logs for PostgreSQL errors
4. Verify `POSTGRES_PASSWORD` is correctly set

### High Memory/CPU Usage

**Monitor in Portainer:**
1. **Stacks** → **mentorship**
2. Check **Stats** section (if available in your Portainer version)
3. If service is using excessive resources:
   - Check logs for memory leaks
   - Reduce `LOG_LEVEL` to `warning`
   - Consider redeploying stack

---

## 📝 Key Features

### Security
- ✅ TLS 1.2+ with modern ciphers
- ✅ CORS properly configured per OAuth requirements
- ✅ Environment variables for all secrets (not in code)
- ✅ Private Docker network (database isolated from internet)
- ✅ Health checks with auto-restart on failure
- ✅ SQL injection protection via SQLAlchemy ORM

### Performance
- ✅ HTTP/2 support via Nginx
- ✅ Connection pooling (API ↔ Database)
- ✅ Database indexes on frequently queried columns
- ✅ Nginx caching and compression
- ✅ Keepalive connections

### Observability
- ✅ Structured logging with **loguru**
- ✅ Color-coded, readable log output
- ✅ Health check endpoints
- ✅ Docker health checks with auto-restart
- ✅ Environment-controlled log levels

---

## 📚 Additional Resources

- **API Documentation:** `https://mentorship.actiol.dev/docs` (Swagger UI)
- **API Redoc:** `https://mentorship.actiol.dev/redoc` (Alternative docs)
- **osu! OAuth Setup:** https://osu.ppy.sh/home/account/edit#oauth
- **Discord Developer Portal:** https://discord.com/developers/applications
- **Portainer Docs:** https://docs.portainer.io/
- **FastAPI Docs:** https://fastapi.tiangolo.com/
- **PostgreSQL Docs:** https://www.postgresql.org/docs/

---

## ✅ Pre-Deployment Checklist

Before deploying to Portainer, ensure:

- [ ] Repository URL is correct: `https://github.com/Actiol/mentorship-helper.git`
- [ ] Compose file selected: `docker-compose.prod.yml`
- [ ] **All 10 required environment variables set** (see Configuration section)
- [ ] **Discord bot intents enabled** in Discord Developer Portal
- [ ] **osu! OAuth credentials registered** and added to env vars
- [ ] **DNS records** pointing `mentorship.actiol.dev` to your server
- [ ] **SSL certificates** configured (Let's Encrypt or self-signed)
- [ ] **Cloudflare tunnel** configured (if using): `http://mentorship:80`
- [ ] Stack deployed successfully and all services healthy
- [ ] API responds at `https://mentorship.actiol.dev/docs`
- [ ] Logs show no errors in Portainer UI

---

**Status:** Ready for Portainer Deployment ✅  
**Deployment Method:** Git Repository (Portainer UI only)  
**Last Updated:** 2026-05-25

