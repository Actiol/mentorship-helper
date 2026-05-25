from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url:        str
    osu_client_id:       str
    osu_client_secret:   str
    jwt_secret:          str
    base_url:            str   # e.g. https://mentorship.yourdomain.com (no trailing slash)
    allowed_origins:     str = "https://osu.ppy.sh"
    discord_bot_token:   str  # used by the API to DM users after OAuth verification

    class Config:
        env_file = ".env"


settings = Settings()
