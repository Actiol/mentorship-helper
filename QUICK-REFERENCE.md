# Quick Reference Card - Mentorship Helper on Portainer

## 🚀 One-Line Deployment

```bash
# 1. Generate secrets
JWT_SECRET=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 32)
API_BOT_SECRET=$(openssl rand -hex 32)

# 2. In Portainer: Create Stack → docker-compose.prod.yml → Add env vars → Deploy
```

---

## 📋 Essential Environment Variables

```env
# Database (REQUIRED)
POSTGRES_PASSWORD=<strong_password>
POSTGRES_USER=mentorship
POSTGRES_DB=mentorship

# Secrets (REQUIRED - use generated values)
JWT_SECRET=<64_hex_chars>
API_BOT_SECRET=<64_hex_chars>

# OAuth (REQUIRED)
OSU_CLIENT_ID=<from_osu>
OSU_CLIENT_SECRET=<from_osu>

# Discord (REQUIRED)
DISCORD_BOT_TOKEN=<from_discord>
DISCORD_TOKEN=<from_discord>
DISCORD_CLIENT_ID=<from_discord>

# URLs (Defaults OK)
BASE_URL=https://mentorship.actiol.dev
API_BASE_URL=https://mentorship.actiol.dev
OSU_VERIFY_BASE_URL=https://mentorship.actiol.dev/auth/discord-verify
ALLOWED_ORIGINS=https://osu.ppy.sh

# Optional
LOG_LEVEL=info
HTTP_PORT=80
HTTPS_PORT=443
```

---

## 🔐 SSL Certificates

```bash
# Let's Encrypt (recommended)
docker run -it --rm -p 80:80 \
  -v /path/to/certs:/etc/letsencrypt \
  certbot/certbot certonly --standalone \
  -d mentorship.actiol.dev

# Copy to Portainer volume
cp /etc/letsencrypt/live/mentorship.actiol.dev/fullchain.pem nginx/certs/
cp /etc/letsencrypt/live/mentorship.actiol.dev/privkey.pem nginx/certs/
```

---

## ✅ Post-Deployment Checks

```bash
# 1. Health check
curl https://mentorship.actiol.dev/health
# Expected: 200 OK

# 2. API docs
curl https://mentorship.actiol.dev/docs
# Expected: 200 OK

# 3. All services healthy
# In Portainer: Stacks → mentorship → Services
# All should show "healthy" or "running"
```

---

## 📊 Monitoring

### In Portainer

1. **Dashboard**: Stacks → mentorship
2. **Service Status**: Services tab → [service name] → Status
3. **Logs**: Services tab → [service name] → Logs
4. **Resources**: Stats tab (if available)

### Command Line

```bash
# View all containers
docker ps -a

# View logs
docker logs -f mentorship-api
docker logs -f mentorship-bot
docker logs -f mentorship-nginx
docker logs -f mentorship-db

# Check health
docker inspect mentorship-api | grep -A 5 "State"
```

---

## 🔧 Common Operations

### Restart Service

```bash
# In Portainer: Services → [service] → Restart
# Or via CLI:
docker-compose restart api      # Just API
docker-compose restart          # All services
```

### View Configuration

```bash
# Environment variables
docker inspect mentorship-api | grep -i env

# Mounted volumes
docker inspect mentorship-api | grep -A 10 Mounts
```

### Database Access

```bash
# Connect to PostgreSQL
docker exec -it mentorship-db psql -U mentorship -d mentorship

# Run query
docker exec mentorship-db psql -U mentorship -d mentorship -c "SELECT 1;"
```

### Backup Database

```bash
docker exec mentorship-db pg_dump -U mentorship mentorship > backup-$(date +%Y%m%d-%H%M%S).sql
```

---

## 🚨 Troubleshooting

| Issue | Quick Fix |
|-------|-----------|
| Service won't start | Check logs: `docker logs <service>` |
| Connection refused | Verify env vars, check health checks |
| SSL certificate error | Verify cert files in nginx/certs/ |
| Database connection failed | Check POSTGRES_PASSWORD matches |
| High memory usage | Check container resource limits |
| Port already in use | Change HTTP_PORT or HTTPS_PORT env var |

---

## 📁 Important Files

```
docker-compose.yml          # Base configuration
docker-compose.prod.yml     # Production stack (use this!)
.env                        # Environment variables (gitignored)
.env.portainer             # Template for Portainer
nginx/nginx.conf           # Nginx configuration
nginx/certs/               # SSL certificates (gitignored)
README-PORTAINER.md        # Full documentation
PORTAINER-DEPLOYMENT.md    # Deployment guide
OPERATOR-CHECKLIST.md      # Operational procedures
```

---

## 🔗 Useful URLs

- **API Health**: https://mentorship.actiol.dev/health
- **API Docs**: https://mentorship.actiol.dev/docs
- **Portainer**: https://portainer.your-host
- **osu! OAuth Setup**: https://osu.ppy.sh/home/account/edit#oauth
- **Discord Dev Portal**: https://discord.com/developers/applications

---

## 📋 Deployment Checklist

- [ ] SSL certificates ready in nginx/certs/
- [ ] osu! OAuth credentials obtained
- [ ] Discord bot created and token obtained
- [ ] Secrets generated (JWT_SECRET, API_BOT_SECRET, POSTGRES_PASSWORD)
- [ ] docker-compose.prod.yml uploaded to Portainer
- [ ] All environment variables set in Portainer
- [ ] Stack deployed
- [ ] All services showing healthy/running
- [ ] Health check returning 200 OK
- [ ] API docs page loads
- [ ] Database connection verified

---

## 🆘 Emergency Contacts

| Role | Contact | Escalation |
|------|---------|-----------|
| Infrastructure | | |
| Operations | | |
| Security | | |

---

## 📞 Support

1. Check logs first: `docker logs <service>`
2. Read README-PORTAINER.md
3. Review OPERATOR-CHECKLIST.md
4. Check PORTAINER-DEPLOYMENT.md for your issue

---

**Last Updated:** 2026-05-25  
**Domain:** mentorship.actiol.dev  
**Status:** Ready for Production Deployment ✅
