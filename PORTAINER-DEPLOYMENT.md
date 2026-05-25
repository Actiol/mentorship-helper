# Portainer Stack Deployment Guide

## Prerequisites

- Portainer up and running
- Docker host with at least 2GB RAM
- SSL certificates ready (or Let's Encrypt)
- OAuth credentials from osu! and Discord

## Quick Deployment

### 1. Prepare Environment Variables

Generate secure secrets:

```bash
JWT_SECRET=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 32)
API_BOT_SECRET=$(openssl rand -hex 32)

echo "JWT_SECRET=$JWT_SECRET"
echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD"
echo "API_BOT_SECRET=$API_BOT_SECRET"
```

### 2. Access Portainer

- Navigate to `https://portainer.yourdomain.com` (or localhost)
- Go to **Environments** → Select your Docker host
- Click **Stacks** → **+ Add Stack**

### 3. Choose Deployment Method

#### Option A: Web Editor (Recommended)

1. Select **Web editor**
2. Copy the entire content of `docker-compose.prod.yml`
3. Paste into the editor
4. Click **Environment** tab

#### Option B: Git Repository

1. Select **Repository**
2. Enter: `https://github.com/Actiol/mentorship-helper.git`
3. Select **docker-compose.prod.yml** as compose file
4. Configure as needed

### 4. Configure Environment Variables

In Portainer's **Environment** section, add these variables:

```
# Database
POSTGRES_USER=mentorship
POSTGRES_PASSWORD=<your_generated_password>
POSTGRES_DB=mentorship

# API
JWT_SECRET=<your_generated_jwt_secret>
OSU_CLIENT_ID=<from_osu_oauth>
OSU_CLIENT_SECRET=<from_osu_oauth>
BASE_URL=https://mentorship.actiol.dev
ALLOWED_ORIGINS=https://osu.ppy.sh
DISCORD_BOT_TOKEN=<from_discord>

# Bot
DISCORD_TOKEN=<from_discord>
DISCORD_CLIENT_ID=<from_discord>
OSU_VERIFY_BASE_URL=https://mentorship.actiol.dev/auth/discord-verify
API_BASE_URL=https://mentorship.actiol.dev
API_BOT_SECRET=<your_generated_api_bot_secret>

# Logging
LOG_LEVEL=info

# Portainer
HTTP_PORT=80
HTTPS_PORT=443
SERVER_NAME=mentorship.actiol.dev
```

### 5. Configure SSL Certificates

Before deploying, ensure certificates are ready:

```bash
# Create certs directory on host
mkdir -p /path/to/docker/volumes/mentorship-certs

# Copy certificates (assuming Let's Encrypt)
sudo cp /etc/letsencrypt/live/mentorship.actiol.dev/fullchain.pem \
        /path/to/docker/volumes/mentorship-certs/

sudo cp /etc/letsencrypt/live/mentorship.actiol.dev/privkey.pem \
        /path/to/docker/volumes/mentorship-certs/

# Set permissions
sudo chmod 644 /path/to/docker/volumes/mentorship-certs/*
```

In Portainer, the nginx service will mount `/etc/nginx/certs` to this host path.

### 6. Deploy Stack

1. Click **Deploy the stack**
2. Wait for confirmation message
3. Monitor in **Stacks** → **mentorship** → **Services**

### 7. Verify Deployment

```bash
# Check all services are healthy
curl -k https://mentorship.actiol.dev/health

# Check API documentation
curl -k https://mentorship.actiol.dev/docs

# Check logs
# In Portainer: Stacks → mentorship → Services → api → Logs
```

---

## Service Configuration Details

### Database Service (PostgreSQL)

- **Image:** `postgres:16-alpine`
- **Network:** Private (mentorship bridge)
- **Volumes:** `pgdata:/var/lib/postgresql/data`
- **Health Check:** SQL connectivity check every 10 seconds
- **Restart Policy:** Always (unless manually stopped)
- **Logging:** JSON format, 10MB per file, 3 file rotation

### API Service (FastAPI)

- **Image:** Built from `./api/Dockerfile`
- **Network:** Private (mentorship bridge)
- **Depends On:** Database (healthy state)
- **Port:** 8000 (internal, exposed via nginx)
- **Volumes:** `oszdata:/data/osz` (map storage path)
- **Health Check:** HTTP GET /health every 30 seconds
- **Restart Policy:** Always
- **Logging:** JSON format, 20MB per file, 5 file rotation

### Bot Service (Discord)

- **Image:** Built from `./bot/Dockerfile`
- **Network:** Private (mentorship bridge)
- **Depends On:** Database (healthy state)
- **No external ports** (internal only)
- **Restart Policy:** Always
- **Logging:** JSON format, 10MB per file, 3 file rotation

### Nginx Service (Reverse Proxy)

- **Image:** `nginx:1.27-alpine`
- **Network:** Private + expose public ports
- **Ports:** 80 (HTTP) and 443 (HTTPS)
- **Volumes:**
  - `./nginx/nginx.conf:/etc/nginx/nginx.conf` (config)
  - `./nginx/certs:/etc/nginx/certs` (SSL certificates)
  - `oszdata:/data/osz` (read-only map sharing)
- **Health Check:** HTTP GET http://localhost/health
- **Restart Policy:** Always
- **Logging:** JSON format, 50MB per file, 5 file rotation

---

## Networking

All services communicate on the private `mentorship` bridge network:

- Database is only accessible from API and Bot
- API is only accessible from Nginx
- Bot calls API via HTTP (internal URL)
- External users access Nginx on ports 80/443

---

## Volume Management

### pgdata

Stores PostgreSQL database files. DO NOT delete unless you want to reset the database.

```bash
# Backup database
docker exec mentorship-db pg_dump -U mentorship mentorship > backup.sql

# Restore database
cat backup.sql | docker exec -i mentorship-db psql -U mentorship mentorship
```

### oszdata

Stores .osz files uploaded by users. These are mapped as read-only to Nginx.

---

## Troubleshooting

### Stack won't deploy

Check logs in Portainer:

```
Stacks → mentorship → Logs
```

Common issues:
- Environment variables not set → Add them before deploying
- Ports in use → Change HTTP_PORT/HTTPS_PORT
- Volume mount failed → Check Docker host path permissions

### Service shows "unhealthy"

```bash
# View detailed logs
docker logs mentorship-api    # or bot, nginx, db
docker ps                     # check status

# Restart service
docker-compose restart api
```

### SSL certificate not loading

```bash
# Verify certificate files exist
ls -la /path/to/docker/volumes/mentorship-certs/

# Check certificate validity
openssl x509 -in /path/to/docker/volumes/mentorship-certs/fullchain.pem -text -noout
```

### Database connection failed

```bash
# Test database
docker exec mentorship-db psql -U mentorship -d mentorship -c "SELECT 1;"

# Reset if corrupted
docker-compose down -v
docker-compose up -d db
```

---

## Monitoring & Maintenance

### Daily Checks

```bash
# Check all services are healthy
curl https://mentorship.actiol.dev/health
curl https://mentorship.actiol.dev/docs

# Monitor logs
docker logs -f mentorship-api
```

### Weekly Tasks

- Check SSL certificate expiration
- Review API error logs
- Verify bot is connected to Discord
- Ensure database backups are working

### Monthly Tasks

- Update Docker images: `docker pull image:tag`
- Review and rotate secrets if needed
- Test disaster recovery (restore from backup)

---

## Scaling & Optimization

### Multiple API Replicas

To run multiple API instances behind Nginx:

```yaml
services:
  api:
    deploy:
      replicas: 3
```

### Database Backups

```bash
# Automated daily backup
0 2 * * * docker exec mentorship-db pg_dump -U mentorship mentorship > /backups/mentorship-$(date +\%Y\%m\%d).sql
```

### Cache Configuration

Nginx is configured with:
- Compression enabled
- Keep-alive connections
- Session caching
- Buffer optimization

---

## Support

For issues:

1. Check logs: `docker logs <service-name>`
2. Review `.env` variables match expected values
3. Verify SSL certificates are valid
4. Consult README-PORTAINER.md for detailed troubleshooting
