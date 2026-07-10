import secrets
import urllib.parse
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import httpx

from shared.database import get_db
from shared.models import UserIdentity, OAuthState, OAuthFlow
from ..config import settings
from ..auth import create_jwt

router = APIRouter(prefix="/auth", tags=["auth"])

_OSU_AUTH_URL  = "https://osu.ppy.sh/oauth/authorize"
_OSU_TOKEN_URL = "https://osu.ppy.sh/oauth/token"
_OSU_ME_URL    = "https://osu.ppy.sh/api/v2/me"

STATE_TTL_SECONDS = 600  # 10 minutes

# Increased timeouts for slower networks
HTTPX_TIMEOUT = httpx.Timeout(30.0, connect=10.0, read=20.0, write=10.0, pool=10.0)


def _callback_url() -> str:
    # MUST match the "Application Callback URL" registered in your osu! OAuth app.
    return f"{settings.base_url}/auth/osu-callback"


def _osu_redirect(state_value: str) -> RedirectResponse:
    params = urllib.parse.urlencode({
        "client_id":     settings.osu_client_id,
        "redirect_uri":  _callback_url(),
        "response_type": "code",
        "scope":         "identify",
        "state":         state_value,
    })
    return RedirectResponse(f"{_OSU_AUTH_URL}?{params}")


# ── Discord verify ─────────────────────────────────────────────────────────────

@router.get("/discord-verify")
async def discord_verify_start(
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """Entry point linked in the Discord bot DM."""
    row = (
        db.query(OAuthState)
        .filter(OAuthState.state == state, OAuthState.flow == OAuthFlow.discord)
        .first()
    )
    if not row:
        return HTMLResponse(_error_page("This link is invalid or has already been used."), status_code=400)

    age = (datetime.utcnow() - row.created_at).total_seconds()
    if age > STATE_TTL_SECONDS:
        db.delete(row)
        db.commit()
        return HTMLResponse(_error_page("This link has expired. Run /verify again in Discord."), status_code=400)

    return _osu_redirect(f"discord:{state}")


# ── Userscript login ───────────────────────────────────────────────────────────

@router.get("/userscript-login")
async def userscript_login_start(db: Session = Depends(get_db)):
    """Opened in a popup by the userscript."""
    state = secrets.token_urlsafe(32)
    db.add(OAuthState(state=state, flow=OAuthFlow.userscript, discord_id=None))
    db.commit()
    return _osu_redirect(f"userscript:{state}")


# ── Shared callback ────────────────────────────────────────────────────────────

@router.get("/osu-callback")
async def oauth_callback(
    code:  str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """osu! redirects here for both flows. The state prefix tells us which path to take."""
    if ":" not in state:
        return HTMLResponse(_error_page("Malformed state parameter."), status_code=400)

    flow, token = state.split(":", 1)

    # Exchange code for osu! access token
    try:
        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            token_resp = await client.post(_OSU_TOKEN_URL, json={
                "client_id":     settings.osu_client_id,
                "client_secret": settings.osu_client_secret,
                "code":          code,
                "grant_type":    "authorization_code",
                "redirect_uri":  _callback_url(),
            })
            if token_resp.status_code != 200:
                return HTMLResponse(_error_page("Failed to exchange osu! token. Try again."), status_code=502)

            access_token = token_resp.json()["access_token"]

            me_resp = await client.get(_OSU_ME_URL, headers={"Authorization": f"Bearer {access_token}"})
            if me_resp.status_code != 200:
                return HTMLResponse(_error_page("Failed to fetch your osu! profile. Try again."), status_code=502)

            me = me_resp.json()
    except httpx.ConnectError as e:
        return HTMLResponse(
            _error_page(
                "Could not reach osu! servers. This usually means:<br/>"
                "• Your server has no internet access<br/>"
                "• osu! servers are temporarily unavailable<br/>"
                "• There's a firewall blocking outbound connections<br/><br/>"
                f"<small>Error: {type(e).__name__}</small>"
            ),
            status_code=503
        )
    except httpx.TimeoutException as e:
        return HTMLResponse(
            _error_page(
                "Request to osu! timed out (took >30s). Possible causes:<br/>"
                "• Slow network connection<br/>"
                "• osu! servers are slow<br/>"
                "• Docker container has no internet access<br/><br/>"
                "<small>Try refreshing this page to retry.</small>"
            ),
            status_code=504
        )
    except httpx.HTTPError as e:
        return HTMLResponse(
            _error_page(
                f"Network error contacting osu!: {e.__class__.__name__}<br/>"
                "Please try again or contact support if the issue persists."
            ),
            status_code=502
        )

    osu_user_id: int  = me["id"]
    osu_username: str = me["username"]

    # ── Discord flow ──────────────────────────────────────────────────────────
    if flow == "discord":
        row = db.query(OAuthState).filter(OAuthState.state == token).first()
        if not row:
            return HTMLResponse(_error_page("State not found or already used."), status_code=400)

        # Prevent one osu! account being linked to multiple Discord users
        conflict = (
            db.query(UserIdentity)
            .filter(
                UserIdentity.osu_user_id != None,
                UserIdentity.osu_user_id == osu_user_id,
                UserIdentity.discord_id  != row.discord_id,
            )
            .first()
        )
        if conflict:
            db.delete(row)
            db.commit()
            return HTMLResponse(
                _error_page(f"That osu! account is already linked to a different Discord user."),
                status_code=409,
            )

        now = datetime.utcnow()
        identity = db.query(UserIdentity).filter(UserIdentity.discord_id == row.discord_id).first()
        if not identity:
            identity = UserIdentity(
                discord_id=row.discord_id,
                osu_user_id=osu_user_id,
                osu_username=osu_username,
                verified_at=now,
            )
            db.add(identity)
        else:
            identity.osu_user_id  = osu_user_id
            identity.osu_username = osu_username
            identity.verified_at  = now

        discord_id = row.discord_id
        db.delete(row)
        db.commit()

        await _discord_dm(discord_id, f"✅ Verified as **{osu_username}**! You can now be assigned to mentorships.")
        return HTMLResponse(_success_page(osu_username))

    # ── Userscript flow ───────────────────────────────────────────────────────
    if flow == "userscript":
        row = db.query(OAuthState).filter(OAuthState.state == token).first()
        if not row:
            return HTMLResponse(_error_page("State not found or already used."), status_code=400)

        db.delete(row)
        db.commit()

        # Must have verified via Discord first
        identity = db.query(UserIdentity).filter(UserIdentity.osu_user_id == osu_user_id).first()
        if not identity:
            return HTMLResponse(_error_page(
                "Your osu! account isn't linked yet. "
                "Run <strong>/verify</strong> in the mentorship Discord server first."
            ))

        jwt_token = create_jwt(osu_user_id, osu_username)
        return HTMLResponse(_postmessage_page(jwt_token))

    return HTMLResponse(_error_page("Unknown OAuth flow."), status_code=400)


# ── Discord DM helper ──────────────────────────────────────────────────────────

async def _discord_dm(discord_id: str, message: str) -> None:
    """Send a DM to a Discord user directly via the bot token (no discord.py needed)."""
    try:
        headers = {"Authorization": f"Bot {settings.discord_bot_token}"}
        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            dm = await client.post(
                "https://discord.com/api/v10/users/@me/channels",
                json={"recipient_id": discord_id},
                headers=headers,
            )
            if dm.status_code not in (200, 201):
                return
            channel_id = dm.json()["id"]
            await client.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                json={"content": message},
                headers=headers,
            )
    except Exception:
        pass  # DM failure is non-fatal


# ── HTML page helpers ──────────────────────────────────────────────────────────

_BASE_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>osu! Mentorship</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:#1a1a2e;display:flex;align-items:center;justify-content:center;min-height:100vh}}
  .card{{background:#16213e;color:#e0e0e0;padding:2.5rem 3rem;border-radius:14px;
         text-align:center;max-width:420px;box-shadow:0 8px 32px rgba(0,0,0,.4)}}
  h2{{font-size:1.4rem;margin-bottom:1rem}}
  p{{line-height:1.6;color:rgba(255,255,255,.7)}}
  code{{background:rgba(255,255,255,.08);padding:2px 6px;border-radius:4px;font-size:.9em}}
  small{{color:rgba(255,255,255,.4);font-size:.85em}}
  .ok{{color:#4bd28f}} .err{{color:#e94560}}
</style></head><body><div class="card">{body}</div></body></html>"""


def _error_page(msg: str) -> str:
    return _BASE_HTML.format(body=f'<h2 class="err">❌ Error</h2><p>{msg}</p>')


def _success_page(username: str) -> str:
    return _BASE_HTML.format(body=(
        f'<h2 class="ok">✅ Verified!</h2>'
        f'<p>Linked as <strong>{username}</strong>.<br>You can close this tab.</p>'
    ))


def _postmessage_page(token: str) -> str:
    # JWT contains only base64url chars + dots — safe to embed in a JS string literal
    return _BASE_HTML.format(body=(
        "<h2>Logged in!</h2><p>Closing…</p>"
        f"<script>"
        f"window.opener&&window.opener.postMessage("
        f"{{type:'osu-mentorship-auth',token:'{token}'}},'https://osu.ppy.sh');"
        f"setTimeout(()=>window.close(),400);"
        f"</script>"
    ))
