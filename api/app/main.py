from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from shared.database import engine
from shared.models import Base
from .config import settings
from .routers.auth        import router as auth_router
from .routers.feedback    import router as feedback_router
from .routers.discussion  import router as discussion_router
from .routers.mentorship  import router as mentorship_router
from .routers.files       import router as files_router, BeatmapsetFile   # noqa: ensure model registered
from .routers.beatmapset  import router as beatmapset_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting: creating missing database tables")
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Startup complete")
    yield
    logger.info("🛑 Shutdown")


app = FastAPI(title="osu! Mentorship API", version="2.0.0", lifespan=lifespan)

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
app.include_router(beatmapset_router)


@app.get("/health")
def health():
    return {"ok": True}
