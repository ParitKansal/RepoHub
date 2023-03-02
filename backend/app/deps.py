from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from .config import settings
from .database import SessionLocal

limiter = Limiter(key_func=get_remote_address)

templates = Jinja2Templates(directory=settings.templates_dir)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
