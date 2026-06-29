import datetime

import pytest

import models


class TestUserModel:
    def test_create_user(self, db_session):
        user = models.User(username="alice", email="alice@example.com", hashed_password="hashed")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.id is not None
        assert user.username == "alice"
        assert user.email == "alice@example.com"

    def test_username_uniqueness(self, db_session):
        u1 = models.User(username="bob", email="bob1@example.com", hashed_password="h")
        db_session.add(u1)
        db_session.commit()

        u2 = models.User(username="bob", email="bob2@example.com", hashed_password="h")
        db_session.add(u2)
        with pytest.raises(Exception):
            db_session.commit()

    def test_email_uniqueness(self, db_session):
        u1 = models.User(username="charlie1", email="same@example.com", hashed_password="h")
        db_session.add(u1)
        db_session.commit()

        u2 = models.User(username="charlie2", email="same@example.com", hashed_password="h")
        db_session.add(u2)
        with pytest.raises(Exception):
            db_session.commit()

    def test_user_repositories_relationship(self, db_session, sample_user, sample_repo):
        assert len(sample_user.repositories) == 1
        assert sample_user.repositories[0].name == "test-repo"


class TestRepositoryModel:
    def test_create_repository(self, db_session, sample_user):
        repo = models.Repository(
            name="my-repo", description="desc", is_private=False, owner_id=sample_user.id
        )
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)

        assert repo.id is not None
        assert repo.name == "my-repo"
        assert repo.owner_id == sample_user.id
        assert repo.is_private is False

    def test_private_repository(self, db_session, sample_user):
        repo = models.Repository(
            name="secret", is_private=True, owner_id=sample_user.id
        )
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)
        assert repo.is_private is True

    def test_repository_owner_relationship(self, db_session, sample_repo):
        assert sample_repo.owner is not None
        assert sample_repo.owner.username == "testuser"

    def test_nullable_description(self, db_session, sample_user):
        repo = models.Repository(name="no-desc", owner_id=sample_user.id)
        db_session.add(repo)
        db_session.commit()
        db_session.refresh(repo)
        assert repo.description is None


class TestIssueModel:
    def test_create_issue(self, db_session, sample_user, sample_repo):
        issue = models.Issue(
            title="Bug report",
            description="Something is broken",
            repo_id=sample_repo.id,
            author_id=sample_user.id,
        )
        db_session.add(issue)
        db_session.commit()
        db_session.refresh(issue)

        assert issue.id is not None
        assert issue.title == "Bug report"
        assert issue.status == "Open"
        assert issue.repository.name == "test-repo"
        assert issue.author.username == "testuser"

    def test_issue_default_status(self, db_session, sample_user, sample_repo):
        issue = models.Issue(title="Test", repo_id=sample_repo.id, author_id=sample_user.id)
        db_session.add(issue)
        db_session.commit()
        db_session.refresh(issue)
        assert issue.status == "Open"

    def test_issue_repo_relationship(self, db_session, sample_user, sample_repo):
        issue = models.Issue(title="Test", repo_id=sample_repo.id, author_id=sample_user.id)
        db_session.add(issue)
        db_session.commit()
        db_session.refresh(sample_repo)
        assert len(sample_repo.issues) == 1


class TestCommentModel:
    def test_create_comment(self, db_session, sample_user, sample_repo):
        issue = models.Issue(title="Issue", repo_id=sample_repo.id, author_id=sample_user.id)
        db_session.add(issue)
        db_session.commit()
        db_session.refresh(issue)

        comment = models.Comment(
            content="This is a comment",
            issue_id=issue.id,
            author_id=sample_user.id,
        )
        db_session.add(comment)
        db_session.commit()
        db_session.refresh(comment)

        assert comment.id is not None
        assert comment.content == "This is a comment"
        assert comment.issue.title == "Issue"
        assert comment.author.username == "testuser"
        assert comment.created_at is not None

    def test_comment_issue_relationship(self, db_session, sample_user, sample_repo):
        issue = models.Issue(title="Issue", repo_id=sample_repo.id, author_id=sample_user.id)
        db_session.add(issue)
        db_session.commit()
        db_session.refresh(issue)

        c1 = models.Comment(content="c1", issue_id=issue.id, author_id=sample_user.id)
        c2 = models.Comment(content="c2", issue_id=issue.id, author_id=sample_user.id)
        db_session.add_all([c1, c2])
        db_session.commit()
        db_session.refresh(issue)
        assert len(issue.comments) == 2


class TestStarModel:
    def test_create_star(self, db_session, sample_user, sample_repo):
        star = models.Star(user_id=sample_user.id, repo_id=sample_repo.id)
        db_session.add(star)
        db_session.commit()
        db_session.refresh(star)

        assert star.id is not None
        assert star.user.username == "testuser"
        assert star.repository.name == "test-repo"
        assert star.created_at is not None

    def test_star_repo_relationship(self, db_session, sample_user, sample_repo):
        star = models.Star(user_id=sample_user.id, repo_id=sample_repo.id)
        db_session.add(star)
        db_session.commit()
        db_session.refresh(sample_repo)
        assert len(sample_repo.stars) == 1
