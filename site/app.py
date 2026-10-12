"""FastAPI-приложение каталога недвижимости MyReeltor."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


SITE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="MyReeltor")
app.mount("/static", StaticFiles(directory=SITE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=SITE_DIR / "templates")

from site.routes import router  # noqa: E402

app.include_router(router)
