from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
import datetime
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    repositories = relationship("Repository", back_populates="owner")

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    
    owner = relationship("User", back_populates="repositories")
    issues = relationship("Issue", back_populates="repository")

class Issue(Base):
    __tablename__ = "issues"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text, nullable=True)
    status = Column(String, default="Open")
    repo_id = Column(Integer, ForeignKey("repositories.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    
    repository = relationship("Repository", back_populates="issues")
    author = relationship("User")
    comments = relationship("Comment", back_populates="issue")

class Comment(Base):
    __tablename__ = "comments"
    
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    issue_id = Column(Integer, ForeignKey("issues.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    
    issue = relationship("Issue", back_populates="comments")
    author = relationship("User")
