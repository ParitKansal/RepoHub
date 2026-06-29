import time
from unittest.mock import MagicMock

import pytest
from jose import jwt

import auth
import models


class TestVerifyPassword:
    def test_correct_password(self):
        hashed = auth.get_password_hash("secret")
        assert auth.verify_password("secret", hashed) is True

    def test_wrong_password(self):
        hashed = auth.get_password_hash("secret")
        assert auth.verify_password("wrong", hashed) is False

    def test_empty_password(self):
        hashed = auth.get_password_hash("")
        assert auth.verify_password("", hashed) is True
        assert auth.verify_password("notempty", hashed) is False


class TestGetPasswordHash:
    def test_returns_string(self):
        result = auth.get_password_hash("password")
        assert isinstance(result, str)

    def test_different_from_plaintext(self):
        result = auth.get_password_hash("password")
        assert result != "password"

    def test_different_hashes_for_same_input(self):
        h1 = auth.get_password_hash("password")
        h2 = auth.get_password_hash("password")
        assert h1 != h2  # bcrypt uses random salt


class TestCreateAccessToken:
    def test_returns_string(self):
        token = auth.create_access_token(data={"sub": "user1"})
        assert isinstance(token, str)

    def test_contains_subject(self):
        token = auth.create_access_token(data={"sub": "user1"})
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        assert payload["sub"] == "user1"

    def test_contains_expiry(self):
        token = auth.create_access_token(data={"sub": "user1"})
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        assert "exp" in payload

    def test_preserves_extra_data(self):
        token = auth.create_access_token(data={"sub": "user1", "role": "admin"})
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        assert payload["role"] == "admin"

    def test_does_not_mutate_input(self):
        data = {"sub": "user1"}
        auth.create_access_token(data=data)
        assert "exp" not in data


class TestGetCurrentUserFromCookie:
    def _make_request(self, cookie_value=None):
        request = MagicMock()
        if cookie_value is None:
            request.cookies = {}
        else:
            request.cookies = {"access_token": cookie_value}
        return request

    def test_no_cookie_returns_none(self, db_session):
        request = self._make_request(cookie_value=None)
        assert auth.get_current_user_from_cookie(request, db_session) is None

    def test_valid_bearer_token(self, db_session, sample_user):
        token = auth.create_access_token(data={"sub": sample_user.username})
        request = self._make_request(cookie_value=f"Bearer {token}")
        user = auth.get_current_user_from_cookie(request, db_session)
        assert user is not None
        assert user.username == sample_user.username

    def test_valid_token_without_bearer_prefix(self, db_session, sample_user):
        token = auth.create_access_token(data={"sub": sample_user.username})
        request = self._make_request(cookie_value=token)
        user = auth.get_current_user_from_cookie(request, db_session)
        assert user is not None
        assert user.username == sample_user.username

    def test_invalid_token_returns_none(self, db_session):
        request = self._make_request(cookie_value="Bearer invalid.token.here")
        assert auth.get_current_user_from_cookie(request, db_session) is None

    def test_token_with_no_sub_returns_none(self, db_session):
        token = auth.create_access_token(data={"role": "admin"})
        request = self._make_request(cookie_value=f"Bearer {token}")
        assert auth.get_current_user_from_cookie(request, db_session) is None

    def test_token_for_nonexistent_user_returns_none(self, db_session):
        token = auth.create_access_token(data={"sub": "nonexistent"})
        request = self._make_request(cookie_value=f"Bearer {token}")
        assert auth.get_current_user_from_cookie(request, db_session) is None
