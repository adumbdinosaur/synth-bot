"""Main application entry point for the Telegram UserBot web interface."""

from fastapi.responses import FileResponse
from app.config import create_app
from app.routes import (
    auth,
    dashboard,
    telegram,
    settings,
    public,
    public_api,
    admin,
    api,
)

# Create the FastAPI application
app = create_app()


# Add favicon route
@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/favicon.ico")


# Add robots.txt route
@app.get("/robots.txt")
async def robots():
    return FileResponse("static/robots.txt")


# Include all route modules
app.include_router(auth.router, tags=["Authentication"])
app.include_router(dashboard.router, tags=["Dashboard"])
app.include_router(telegram.router, tags=["Telegram"])
app.include_router(settings.router, tags=["Settings"])
app.include_router(public.router, tags=["Public"])
app.include_router(public_api.router, tags=["Public API"])
app.include_router(admin.router, tags=["Admin"])
app.include_router(api.router, tags=["API"])

if __name__ == "__main__":
    import uvicorn
    import logging
    import os

    # Get log level from environment variable, default to INFO
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level_value = getattr(logging, log_level, logging.INFO)

    logging.basicConfig(level=log_level_value)
    logger = logging.getLogger(__name__)

    logger.info("Starting application with uvicorn...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
