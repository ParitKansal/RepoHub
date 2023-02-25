from fastapi.templating import Jinja2Templates
from .config import settings
from .database import SessionLocal

templates = Jinja2Templates(directory=settings.templates_dir)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
