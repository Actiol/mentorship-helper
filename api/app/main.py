from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.database import engine
from shared.models import Base
from .config import settings
from .routers.auth        import router as auth_router
from .routers.feedback    import router as feedback_router
from .routers.discussion  import router as discussion_router
from .routers.mentorship  import router as mentorship_router
from .routers.files       import router as files_router, BeatmapsetFile


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Creates any missing tables. In production prefer: docker compose run api alembic upgrade head
    Base.metadata.create_all(bind=engine)
    # BeatmapsetFile is defined in the files router module, so we need to ensure
    # its table also gets created
    from .routers.files import BeatmapsetFile as _  # noqa: ensure model is registered
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="osu! Mentorship API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(feedback_router)
app.include_router(discussion_router)
app.include_router(mentorship_router)
app.include_router(files_router)


@app.get("/health")
def health():
    return {"ok": True}
