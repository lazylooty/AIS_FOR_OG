from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, SessionLocal, engine, ensure_schema_upgrades
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.crm import router as crm_router
from app.routers.deals import router as deals_router
from app.routers.documents import router as documents_router
from app.routers.profile import router as profile_router
from app.routers.properties import router as properties_router
from app.routers.public import router as public_router
from app.routers.reviews import router as reviews_router
from app.seed import seed_initial_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.templates_dir
    settings.contracts_dir
    settings.photos_dir
    Base.metadata.create_all(bind=engine)
    ensure_schema_upgrades()
    db = SessionLocal()
    try:
        seed_initial_data(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="ИП Голубина Ольга Геннадьевна — АИС Риэлторского Агентства",
    version="1.0.0",
    lifespan=lifespan,
)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
app.mount("/media/photos", StaticFiles(directory=str(settings.photos_dir)), name="media_photos")

app.include_router(public_router)
app.include_router(auth_router)
app.include_router(properties_router)
app.include_router(crm_router)
app.include_router(deals_router)
app.include_router(documents_router)
app.include_router(reviews_router)
app.include_router(profile_router)
app.include_router(admin_router)
