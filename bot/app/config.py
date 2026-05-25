from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url:        str
    discord_token:       str
    discord_client_id:   str
    osu_verify_base_url: str  # e.g. https://mentorship.yourdomain.com/auth/discord-verify
    api_base_url:        str  # e.g. https://mentorship.yourdomain.com  (for bot→API file uploads)
    api_bot_secret:      str  # shared secret so the API trusts uploads from the bot

    class Config:
        env_file = ".env"


settings = Settings()
