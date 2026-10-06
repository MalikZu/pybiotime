import json

import httpx

from pybiotime._secret import Secret, secret_token


def test_value_is_sent_but_not_shown() -> None:
    secret = Secret("hunter2")
    assert secret == "hunter2"
    assert str(secret) == "hunter2"
    assert "hunter2" not in repr(secret)
    assert "hunter2" not in repr({"password": secret})
    assert "hunter2" not in repr([secret])
    assert json.dumps({"password": secret}) == '{"password": "hunter2"}'


def test_works_as_an_httpx_header() -> None:
    request = httpx.Request("GET", "http://x.test", headers={"Authorization": Secret("Token t")})
    assert request.headers["Authorization"] == "Token t"


def test_login_answer_token_is_wrapped() -> None:
    answer = secret_token({"token": "abc", "other": 1})
    assert answer["token"] == "abc"
    assert isinstance(answer["token"], Secret)
    assert answer["other"] == 1
    assert secret_token({"detail": "no"}) == {"detail": "no"}
