from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from loguru import logger
import sys

from .database import engine, Base
from .api import routes
from .workers.celery_tasks import start_daily_parsing

# Настройка логирования
logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>")
logger.add("logs/price_monitor.log", rotation="1 day", retention="30 days")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Price Monitor API...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")
    yield
    # Shutdown
    logger.info("Shutting down...")

app = FastAPI(
    title="Price Monitor API",
    description="API for monitoring competitor prices",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(routes.router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Price Monitor API", "status": "running"}

@app.post("/api/v1/parse/now")
async def parse_now(background_tasks: BackgroundTasks):
    """Запуск парсинга сейчас"""
    task = start_daily_parsing.delay()
    return {"task_id": task.id, "status": "started"}

@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy"}