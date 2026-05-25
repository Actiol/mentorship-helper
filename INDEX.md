# Mentorship Helper - Documentation Index

**Domain:** `mentorship.actiol.dev`  
**Deployment Target:** Portainer Docker Stack  
**Optimization Date:** 2026-05-25

---

## 📚 Documentation Files

### For First-Time Setup

Start here if you're new to this project:

1. **[README-PORTAINER.md](README-PORTAINER.md)** ⭐ START HERE
   - Complete overview of the system
   - Architecture explanation with diagrams
   - Quick start guide
   - Environment variable reference
   - SSL/TLS setup instructions
   - Troubleshooting guide

2. **[QUICK-REFERENCE.md](QUICK-REFERENCE.md)** 
   - One-page cheat sheet
   - Essential commands
   - Common operations
   - Emergency procedures
   - Print this for quick access!

### For Deployment

Follow these in order:

1. **[PORTAINER-DEPLOYMENT.md](PORTAINER-DEPLOYMENT.md)**
   - Prerequisites checklist
   - Step-by-step deployment
   - Environment variable setup
   - SSL certificate configuration
   - Post-deployment verification

2. **[OPERATOR-CHECKLIST.md](OPERATOR-CHECKLIST.md)**
   - Pre-deployment verification
   - Deployment execution checklist
   - Post-deployment verification
   - Daily/weekly/monthly tasks
   - Incident response procedures
   - Team sign-off sheet

### For Day-to-Day Operations

Keep these handy:

1. **[OPERATOR-CHECKLIST.md](OPERATOR-CHECKLIST.md)** - Operational procedures
2. **[QUICK-REFERENCE.md](QUICK-REFERENCE.md)** - Quick commands and troubleshooting
3. **[README-PORTAINER.md](README-PORTAINER.md#troubleshooting)** - Detailed troubleshooting

### For Understanding Changes

1. **[OPTIMIZATION-SUMMARY.md](OPTIMIZATION-SUMMARY.md)**
   - What was optimized
   - Performance improvements
   - Security enhancements
   - Configuration changes
   - Technical stack details

---

## 🔧 Configuration Files

### Environment Configuration

| File | Purpose | Usage |
|------|---------|-------|
| `.env.example` | Basic template | Development, reference |
| `.env.portainer` | Production template | Portainer deployments |
| `.env` | Actual configuration | Created from template (gitignored) |

### Docker Configuration

| File | Purpose | Usage |
|------|---------|-------|
| `docker-compose.yml` | Base stack definition | All environments |
| `docker-compose.prod.yml` | Production optimizations | Use with Portainer ⭐ |
| `docker-compose.override.yml` | Development overrides | Local development |
| `.dockerignore` | Build optimization | All builds |

### Nginx Configuration

| File | Purpose |
|------|---------|
| `nginx/nginx.conf` | Nginx configuration with mentorship.actiol.dev domain |
| `nginx/Dockerfile` | Nginx container with health checks |
| `nginx/certs/` | SSL certificates (gitignored) |

### Application Dockerfiles

| File | Purpose |
|------|---------|
| `api/Dockerfile` | FastAPI backend with health checks |
| `bot/Dockerfile` | Discord bot service |

---

## 🚀 Quick Navigation by Role

### Infrastructure Engineer

1. Read: [README-PORTAINER.md - Architecture](README-PORTAINER.md#-architecture)
2. Review: [PORTAINER-DEPLOYMENT.md - Prerequisites](PORTAINER-DEPLOYMENT.md)
3. Deploy: Follow [PORTAINER-DEPLOYMENT.md](PORTAINER-DEPLOYMENT.md)
4. Reference: [QUICK-REFERENCE.md](QUICK-REFERENCE.md)

### Operations/DevOps

1. Study: [OPERATOR-CHECKLIST.md](OPERATOR-CHECKLIST.md)
2. Keep handy: [QUICK-REFERENCE.md](QUICK-REFERENCE.md)
3. Reference: [README-PORTAINER.md - Monitoring](README-PORTAINER.md#-monitoring--logs)
4. Escalate: See [OPERATOR-CHECKLIST.md - Incident Response](OPERATOR-CHECKLIST.md#incident-response)

### Security/Compliance

1. Review: [README-PORTAINER.md - SSL/TLS Setup](README-PORTAINER.md#-ssltls-setup)
2. Check: [OPERATOR-CHECKLIST.md - Security Hardening](OPERATOR-CHECKLIST.md#security-hardening)
3. Audit: [PORTAINER-DEPLOYMENT.md - Service Configuration](PORTAINER-DEPLOYMENT.md#service-configuration-details)

### Product/Manager

1. Understand: [OPTIMIZATION-SUMMARY.md](OPTIMIZATION-SUMMARY.md)
2. Track: [OPERATOR-CHECKLIST.md - Pre-Deployment Checklist](OPERATOR-CHECKLIST.md#pre-deployment-checklist)
3. Sign off: [OPERATOR-CHECKLIST.md - Sign-Off](OPERATOR-CHECKLIST.md#sign-off)

---

## 📋 Environment Variables at a Glance

### Must Set (7 Required)

```env
POSTGRES_PASSWORD=<generate>           # Database password
JWT_SECRET=<generate>                  # JWT key (64 hex)
OSU_CLIENT_ID=<get_from_osu>          # osu! OAuth
OSU_CLIENT_SECRET=<get_from_osu>      # osu! OAuth
DISCORD_BOT_TOKEN=<get_from_discord>  # Discord bot
DISCORD_CLIENT_ID=<get_from_discord>  # Discord app
API_BOT_SECRET=<generate>              # Shared secret (64 hex)
```

### Nice to Have (Defaults OK)

```env
POSTGRES_USER=mentorship               # DB user
POSTGRES_DB=mentorship                 # DB name
BASE_URL=https://mentorship.actiol.dev
API_BASE_URL=https://mentorship.actiol.dev
ALLOWED_ORIGINS=https://osu.ppy.sh
LOG_LEVEL=info
```

**See [README-PORTAINER.md - Environment Variables](README-PORTAINER.md#-environment-variables) for full reference.**

---

## 🔑 Key Files by Task

### Deploying to Portainer
- [`docker-compose.prod.yml`](docker-compose.prod.yml) - Use this stack file
- [`.env.portainer`](.env.portainer) - Copy env vars from this
- [`PORTAINER-DEPLOYMENT.md`](PORTAINER-DEPLOYMENT.md) - Follow steps here

### Setting Up SSL
- [`nginx/nginx.conf`](nginx/nginx.conf) - Nginx config (domain already set)
- [`nginx/certs/`](nginx/) - Put certificates here
- [README-PORTAINER.md - SSL/TLS Setup](README-PORTAINER.md#-ssltls-setup) - Detailed instructions

### Understanding the System
- [README-PORTAINER.md - Architecture](README-PORTAINER.md#-architecture) - System overview
- [OPTIMIZATION-SUMMARY.md](OPTIMIZATION-SUMMARY.md) - What was optimized

### Troubleshooting Issues
- [QUICK-REFERENCE.md - Troubleshooting](QUICK-REFERENCE.md#-troubleshooting) - Quick fixes
- [README-PORTAINER.md - Troubleshooting](README-PORTAINER.md#-troubleshooting) - Detailed guide
- [OPERATOR-CHECKLIST.md - Incident Response](OPERATOR-CHECKLIST.md#incident-response) - Procedures

### Daily Operations
- [OPERATOR-CHECKLIST.md - Operational Checklist](OPERATOR-CHECKLIST.md#operational-checklist) - Daily tasks
- [QUICK-REFERENCE.md](QUICK-REFERENCE.md) - Common commands
- [README-PORTAINER.md - Monitoring](README-PORTAINER.md#-monitoring--logs) - How to monitor

---

## 🎯 Common Tasks

### Deploy New Stack

1. Open [PORTAINER-DEPLOYMENT.md](PORTAINER-DEPLOYMENT.md)
2. Follow "Quick Deployment" section
3. Use [`docker-compose.prod.yml`](docker-compose.prod.yml)
4. Set environment variables from [`.env.portainer`](.env.portainer)

### Check Service Health

1. Quick check: 
   ```bash
   curl https://mentorship.actiol.dev/health
   ```
2. Full check: See [OPERATOR-CHECKLIST.md - Verification](OPERATOR-CHECKLIST.md#post-deployment-verification)

### Restart a Service

1. In Portainer: Stacks → mentorship → Services → [service] → Restart
2. Or: `docker-compose restart <service>`
3. See [QUICK-REFERENCE.md - Common Operations](QUICK-REFERENCE.md#-common-operations)

### Debug Issues

1. Check logs: `docker logs <service>`
2. Search [README-PORTAINER.md - Troubleshooting](README-PORTAINER.md#-troubleshooting)
3. Check [QUICK-REFERENCE.md - Troubleshooting](QUICK-REFERENCE.md#-troubleshooting)

### Backup Database

```bash
docker exec mentorship-db pg_dump -U mentorship mentorship > backup.sql
```

See [OPERATOR-CHECKLIST.md - Backup/Restore](OPERATOR-CHECKLIST.md#backuprestore-procedure)

---

## 📊 File Structure

```
mentorship-helper/
├── 📄 docker-compose.yml             ← Base stack
├── 📄 docker-compose.prod.yml        ← Use this for Portainer ⭐
├── 📄 docker-compose.override.yml    ← Dev overrides
├── 📄 .env.example                   ← Env template
├── 📄 .env.portainer                 ← Portainer template ⭐
├── 📄 .dockerignore                  ← Build optimization
│
├── 📚 README-PORTAINER.md            ← Complete guide ⭐ START HERE
├── 📚 PORTAINER-DEPLOYMENT.md        ← Deployment steps
├── 📚 OPERATOR-CHECKLIST.md          ← Operations procedures
├── 📚 QUICK-REFERENCE.md             ← Cheat sheet
├── 📚 OPTIMIZATION-SUMMARY.md        ← What changed
├── 📚 THIS FILE (INDEX.md)           ← You are here
│
├── nginx/
│   ├── nginx.conf                    ← Updated for mentorship.actiol.dev
│   ├── Dockerfile                    ← With health checks
│   └── certs/                        ← SSL certificates (gitignored)
├── api/
│   ├── Dockerfile                    ← With health checks
│   └── requirements.txt
├── bot/
│   ├── Dockerfile
│   └── requirements.txt
├── shared/
│   └── [shared Python packages]
└── userscript/
    └── [Tampermonkey script]
```

---

## 🔐 Security Notes

✅ **Implemented:**
- TLS 1.2+ enforced
- Modern cipher suites
- Security headers (HSTS, X-Frame-Options, etc.)
- Private Docker network (database not exposed)
- Environment variables not in git

⚠️ **To Implement:**
- Keep secrets out of version control
- Rotate secrets quarterly
- Monitor logs for suspicious activity
- Implement rate limiting (if not already done)
- Regular security audits

See [OPERATOR-CHECKLIST.md - Security Hardening](OPERATOR-CHECKLIST.md#security-hardening)

---

## 📞 Getting Help

| Need | File/Location |
|------|---------------|
| System overview | [README-PORTAINER.md](README-PORTAINER.md) |
| Deploy to Portainer | [PORTAINER-DEPLOYMENT.md](PORTAINER-DEPLOYMENT.md) |
| Operational tasks | [OPERATOR-CHECKLIST.md](OPERATOR-CHECKLIST.md) |
| Quick commands | [QUICK-REFERENCE.md](QUICK-REFERENCE.md) |
| What changed | [OPTIMIZATION-SUMMARY.md](OPTIMIZATION-SUMMARY.md) |
| Troubleshooting | [README-PORTAINER.md#troubleshooting](README-PORTAINER.md#-troubleshooting) |

---

## 📈 Deployment Status

- [x] Configuration files optimized
- [x] Documentation created
- [x] Domain updated to mentorship.actiol.dev
- [x] Health checks configured
- [x] Security hardened
- [x] Logging optimized
- [ ] Ready for your deployment!

**Next Step:** Follow [PORTAINER-DEPLOYMENT.md](PORTAINER-DEPLOYMENT.md) to deploy.

---

**Last Updated:** 2026-05-25  
**Version:** 1.0  
**Status:** Ready for Portainer Deployment ✅
