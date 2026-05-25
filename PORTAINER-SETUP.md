# Portainer Deployment Guide

## The Problem You Encountered

**"I pasted in the compose file but got a YAML error"**

When you just paste a docker-compose file into Portainer, two things happen:

1. **YAML Syntax Error** - Portainer's parser is stricter than Docker's (fixed ✓)
2. **Code Access Problem** - Portainer can't access the repository files (Dockerfiles, config, etc.)

---

## How Portainer Gets the Code

Portainer needs access to your repository in ONE of these ways:

### ✅ Option 1: Git Repository (RECOMMENDED)

Portainer clones your repository and uses files from it.

**Setup in Portainer:**

1. **Stacks** → **Add Stack**
2. Select **Repository**
3. Enter:
   - **Repository URL:** `https://github.com/Actiol/mentorship-helper.git`
   - **Repository Reference:** `main` (or your branch)
   - **Compose file:** `docker-compose.prod.yml`
   - **Auto-update:** Enabled (optional - auto-redeploy on git push)

4. **Environment** → Add all variables
5. **Deploy**

**Why this works:**
- ✅ Portainer clones the entire repo
- ✅ Can access `Dockerfile`, `nginx/nginx.conf`, `shared/`, etc.
- ✅ Can build images with proper context
- ✅ Perfect for your use case

---

### ✅ Option 2: Pre-Built Images (Without Building)

Build images locally and push to Docker Hub/private registry, then use pre-built images in Portainer.

```bash
# Build locally
docker-compose build api bot nginx

# Tag and push
docker tag mentorship-api:latest yourusername/mentorship-api:latest
docker push yourusername/mentorship-api:latest
# ... repeat for bot and nginx
```

Then modify `docker-compose.prod.yml`:
```yaml
api:
  image: yourusername/mentorship-api:latest  # Use pre-built instead of building
  # remove the 'build:' section
```

---

### ❌ Option 3: Just Pasting (Doesn't Work for This Project)

**Why it fails:**
- No access to `Dockerfile` files → Can't build images
- No access to `nginx/nginx.conf` → Nginx config missing
- No access to source code → Can't run the services

Only works if you use pre-built images (Option 2).

---

## Recommended Setup: Git Repository Method

**This is what you should use:**

### Step 1: In Portainer

```
Stacks → Add Stack → Repository

Repository URL: https://github.com/Actiol/mentorship-helper.git
Repository Reference: main
Compose file: docker-compose.prod.yml
Auto-update: ✓ (optional)
```

### Step 2: Add Environment Variables

```
POSTGRES_PASSWORD=<your_password>
POSTGRES_USER=mentorship
POSTGRES_DB=mentorship
JWT_SECRET=<your_jwt_secret>
OSU_CLIENT_ID=<from_osu>
OSU_CLIENT_SECRET=<from_osu>
DISCORD_BOT_TOKEN=<from_discord>
DISCORD_TOKEN=<from_discord>
DISCORD_CLIENT_ID=<from_discord>
API_BOT_SECRET=<your_api_secret>
BASE_URL=https://mentorship.actiol.dev
API_BASE_URL=http://mentorship:80
OSU_VERIFY_BASE_URL=https://mentorship.actiol.dev/auth/discord-verify
ALLOWED_ORIGINS=https://osu.ppy.sh
LOG_LEVEL=info
```

### Step 3: Deploy

Click **Deploy**. Portainer will:
1. Clone your repository
2. Read `docker-compose.prod.yml`
3. Build all images (api, bot, nginx) using Dockerfiles
4. Pull PostgreSQL from Docker Hub
5. Start all services
6. Create the `mentorship` network
7. Connect your Cloudflare tunnel to this network

---

## Your Cloudflare Tunnel Integration

Once deployed, your Portainer stack creates:
- `mentorship` bridge network
- `mentorship` DNS name (internal Docker DNS)

**Cloudflare Tunnel URL:**
```
http://mentorship:80
```

Make sure your Cloudflare tunnel container is on the `mentorship` network:

```bash
docker network connect mentorship cloudflare-tunnel-container
```

---

## What docker-compose.prod.yml Does

```yaml
build:
  context: .                 # Uses repository root (has Dockerfile, shared/, etc.)
  dockerfile: api/Dockerfile # Builds api service
```

This tells Portainer:
- Clone the repository
- Build images using Dockerfiles from the repo
- Copy source code, shared modules, nginx config into images
- Start everything

---

## Quick Checklist

- [ ] Create stack in Portainer with Git repository
- [ ] Enter: `https://github.com/Actiol/mentorship-helper.git`
- [ ] Compose file: `docker-compose.prod.yml`
- [ ] Add all environment variables
- [ ] Deploy
- [ ] Wait for all services to show "healthy"
- [ ] Connect Cloudflare tunnel to `mentorship` network
- [ ] Test: `http://mentorship:80` via Cloudflare tunnel

---

## Troubleshooting

**"Build is failing"**
- Check Docker host has internet access
- Check repository URL is correct
- View Portainer logs for details

**"Services won't start"**
- Check all environment variables are set
- View service logs in Portainer
- Verify volumes mount correctly

**"Can't reach via Cloudflare tunnel"**
- Verify tunnel container is on `mentorship` network
- Check tunnel config points to `http://mentorship:80`
- Test: `docker exec tunnel-container ping mentorship`

---

## Summary

| Method | How Code Gets In | Best For |
|--------|------------------|----------|
| Git Repository | Portainer clones repo | Production deployments |
| Pre-built Images | You build & push | CI/CD pipelines |
| Paste Compose | Doesn't work with this setup | Simple static stacks |

**Use Git Repository method for this project.**
