# Mentorship Helper - Operator Checklist

## Pre-Deployment Checklist

### 1. Infrastructure Setup

- [ ] Docker host prepared (minimum 2GB RAM)
- [ ] Portainer installed and accessible
- [ ] Domain `mentorship.actiol.dev` resolves to Docker host
- [ ] Firewall allows ports 80, 443
- [ ] Storage space available (minimum 10GB for database + files)

### 2. SSL Certificates

- [ ] Obtained valid SSL certificate for `mentorship.actiol.dev`
- [ ] Certificate files copied to `nginx/certs/`:
  - [ ] `fullchain.pem` (certificate chain)
  - [ ] `privkey.pem` (private key)
  - [ ] `chain.pem` (optional, for OCSP stapling)
- [ ] Certificate permissions set correctly (644 or 755)
- [ ] Certificate expiration date noted

### 3. OAuth Applications

- [ ] osu! OAuth application registered:
  - [ ] Application ID recorded
  - [ ] Client secret recorded
  - [ ] Callback URL set to `https://mentorship.actiol.dev/auth/osu-callback`
  
- [ ] Discord application created:
  - [ ] Application ID recorded
  - [ ] Bot token generated and recorded
  - [ ] OAuth2 scopes configured (identify, email)
  - [ ] Redirect URIs set to `https://mentorship.actiol.dev/auth/discord-callback`
  - [ ] Bot permissions set (see Discord developer docs)

### 4. Secrets Generated

```bash
# Run these commands and record the output
JWT_SECRET=$(openssl rand -hex 32)
echo "JWT_SECRET=$JWT_SECRET" >> secrets.txt

POSTGRES_PASSWORD=$(openssl rand -hex 32)
echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" >> secrets.txt

API_BOT_SECRET=$(openssl rand -hex 32)
echo "API_BOT_SECRET=$API_BOT_SECRET" >> secrets.txt

# Store secrets.txt securely (NOT in version control!)
```

- [ ] JWT_SECRET generated and recorded
- [ ] POSTGRES_PASSWORD generated and recorded
- [ ] API_BOT_SECRET generated and recorded
- [ ] Secrets stored securely (e.g., password manager, vault)

---

## Deployment Checklist

### 1. Repository Setup

- [ ] Repository cloned to Docker host
- [ ] `docker-compose.yml` and `docker-compose.prod.yml` present
- [ ] `nginx/nginx.conf` present and updated for domain
- [ ] `.dockerignore` present

### 2. Environment Configuration

In Portainer, set these environment variables:

#### Required Variables

- [ ] `POSTGRES_PASSWORD` = (from generated secrets)
- [ ] `POSTGRES_USER` = `mentorship`
- [ ] `POSTGRES_DB` = `mentorship`
- [ ] `JWT_SECRET` = (from generated secrets)
- [ ] `OSU_CLIENT_ID` = (from osu! OAuth)
- [ ] `OSU_CLIENT_SECRET` = (from osu! OAuth)
- [ ] `DISCORD_BOT_TOKEN` = (from Discord bot)
- [ ] `DISCORD_TOKEN` = (same as DISCORD_BOT_TOKEN)
- [ ] `DISCORD_CLIENT_ID` = (from Discord application)
- [ ] `API_BOT_SECRET` = (from generated secrets)

#### Optional Variables (Defaults OK)

- [ ] `BASE_URL` = `https://mentorship.actiol.dev`
- [ ] `API_BASE_URL` = `https://mentorship.actiol.dev`
- [ ] `OSU_VERIFY_BASE_URL` = `https://mentorship.actiol.dev/auth/discord-verify`
- [ ] `ALLOWED_ORIGINS` = `https://osu.ppy.sh`
- [ ] `LOG_LEVEL` = `info`
- [ ] `HTTP_PORT` = `80`
- [ ] `HTTPS_PORT` = `443`
- [ ] `SERVER_NAME` = `mentorship.actiol.dev`

### 3. Portainer Stack Creation

- [ ] New stack created with name `mentorship`
- [ ] `docker-compose.prod.yml` content pasted or repository linked
- [ ] All environment variables entered
- [ ] Deployment options reviewed:
  - [ ] Auto-update enabled (optional)
  - [ ] Git auto-sync enabled (optional)

### 4. Deployment Execution

- [ ] Stack deployed successfully
- [ ] All services starting (check Stacks → mentorship → Services)
- [ ] No error messages in deployment logs

---

## Post-Deployment Verification

### 1. Service Health

```bash
# Run these commands from any machine with curl and network access
curl -k https://mentorship.actiol.dev/health
# Expected: 200 OK with "healthy"
```

- [ ] API service responds to health check
- [ ] HTTP → HTTPS redirect working (`curl -v http://mentorship.actiol.dev`)
- [ ] All services show "healthy" in Portainer

### 2. API Functionality

```bash
curl -k https://mentorship.actiol.dev/docs
# Expected: 200 OK with interactive API docs
```

- [ ] API documentation page loads
- [ ] Database connection established (check API logs)
- [ ] No errors in API logs

### 3. Database

```bash
docker exec mentorship-db psql -U mentorship -d mentorship -c "SELECT 1;"
# Expected: output of 1
```

- [ ] Database accepts connections
- [ ] Database initialized
- [ ] No connection errors in API/Bot logs

### 4. SSL Certificate

```bash
echo | openssl s_client -servername mentorship.actiol.dev -connect mentorship.actiol.dev:443 2>/dev/null | openssl x509 -noout -dates
```

- [ ] Certificate is valid
- [ ] Certificate has not expired
- [ ] Certificate matches domain

### 5. Logs Review

In Portainer, check logs for each service:

- [ ] **DB logs**: No connection errors
- [ ] **API logs**: Started successfully, awaiting connections
- [ ] **Bot logs**: Connected to Discord
- [ ] **Nginx logs**: Receiving requests, proxying to API

---

## Operational Checklist

### Daily

- [ ] Services remain healthy (check Portainer dashboard)
- [ ] No unusual error rates in logs
- [ ] API response times are acceptable

### Weekly

- [ ] Review container resource usage
- [ ] Check for any pending updates
- [ ] Verify SSL certificate expiration date approaching
- [ ] Database backup verification

### Monthly

- [ ] Update Docker images to latest versions
- [ ] Review and rotate secrets if needed
- [ ] Perform disaster recovery test
- [ ] Performance optimization review

### Quarterly

- [ ] Security audit (log review, access control)
- [ ] Capacity planning (storage, memory)
- [ ] Documentation update
- [ ] Team knowledge transfer session

---

## Incident Response

### Service is Down

1. Check Portainer dashboard for service status
2. Review service logs: `Stacks → mentorship → Services → [service] → Logs`
3. Check resource limits: CPU, memory, disk space
4. Restart service if needed: `Stacks → mentorship → Services → [service] → Restart`
5. If issue persists, check Docker host logs

### High Error Rate

1. Review API logs for error patterns
2. Check database connectivity
3. Verify all environment variables are set correctly
4. Check for resource exhaustion (CPU, memory)
5. Increase log level temporarily: Change `LOG_LEVEL=debug`

### SSL Certificate Expired

1. Immediately restart Nginx with new certificate
2. Update certificate files in `nginx/certs/`
3. Restart Nginx service
4. Set calendar reminder for next renewal

### Database Issues

1. Check database logs: `docker logs mentorship-db`
2. Verify disk space: `docker exec mentorship-db df -h`
3. Check database size: `docker exec mentorship-db psql -U mentorship -d mentorship -c "SELECT pg_size_pretty(pg_database_size('mentorship'));"`
4. Consider backing up before attempting repairs

### Backup/Restore Procedure

```bash
# Backup database
docker exec mentorship-db pg_dump -U mentorship mentorship > backup-$(date +%Y%m%d-%H%M%S).sql

# Restore database
cat backup-YYYYMMDD-HHMMSS.sql | docker exec -i mentorship-db psql -U mentorship mentorship
```

---

## Security Hardening

- [ ] SSH keys configured for Portainer access
- [ ] All credentials stored in secure vault (NOT in git)
- [ ] Firewall configured to only allow necessary ports
- [ ] Regular security updates applied
- [ ] Log aggregation enabled (optional)
- [ ] Rate limiting configured for API
- [ ] CORS settings reviewed
- [ ] Database access restricted to internal network only

---

## Documentation

- [ ] README-PORTAINER.md reviewed and understood
- [ ] PORTAINER-DEPLOYMENT.md reviewed and understood
- [ ] Database schema documented
- [ ] API endpoints documented
- [ ] Disaster recovery procedure documented
- [ ] Team contacts and escalation path documented

---

## Sign-Off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Infrastructure | | | |
| Operations | | | |
| Security | | | |
| Product | | | |

---

## Quick Reference

### Essential Commands

```bash
# View all services
docker-compose ps

# View logs
docker-compose logs -f api    # API logs
docker-compose logs -f bot    # Bot logs
docker-compose logs -f nginx  # Nginx logs
docker-compose logs -f db     # Database logs

# Restart service
docker-compose restart api

# Rebuild images
docker-compose build

# Access database
docker exec -it mentorship-db psql -U mentorship

# Check health
curl https://mentorship.actiol.dev/health
```

### Environment Variables to Verify

```bash
grep "^[A-Z_]*=" .env | sort
```

### File Locations

```
./docker-compose.yml              # Main stack definition
./docker-compose.prod.yml         # Production optimizations
./nginx/nginx.conf                # Nginx configuration
./nginx/certs/fullchain.pem       # SSL certificate
./nginx/certs/privkey.pem         # SSL private key
./.env                            # Environment variables (DO NOT COMMIT)
```

---

**Last Updated:** [Today's Date]  
**Maintained By:** [Team Name]  
**Next Review Date:** [3 Months From Today]
