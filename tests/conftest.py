import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure the project root is on sys.path so imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import models


@pytest.fixture()
def db_session():
    """Create an in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def sample_user(db_session):
    """Create a sample user in the test database."""
    import auth

    user = models.User(
        username="testuser",
        email="test@example.com",
        hashed_password=auth.get_password_hash("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def sample_repo(db_session, sample_user):
    """Create a sample repository in the test database."""
    repo = models.Repository(
        name="test-repo",
        description="A test repository",
        is_private=False,
        owner_id=sample_user.id,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo
