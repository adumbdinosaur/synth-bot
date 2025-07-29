#!/usr/bin/env python3
"""
Simple test to start the server without client recovery to isolate the issue.
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

from app.database import init_db
from app.telegram_client import initialize_telegram_manager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def simple_lifespan(app: FastAPI):
    logger.info("Starting simple lifespan...")

    # Initialize Telegram manager
    logger.info("Initializing Telegram manager...")
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")

    if not api_id or not api_hash:
        logger.error(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH environment variables are required"
        )
        raise RuntimeError("Missing Telegram API credentials")

    initialize_telegram_manager(int(api_id), api_hash)
    logger.info("Telegram manager initialized successfully")

    # Initialize database
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully")

    logger.info("🚀 Simple app started - yielding control")

    yield

    logger.info("Simple app shutting down")


app = FastAPI(lifespan=simple_lifespan)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/test")
async def test():
    return {"message": "Server is working!"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
