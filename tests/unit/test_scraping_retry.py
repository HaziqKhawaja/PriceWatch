import pytest
import requests
import responses

from app.services import scraping
from app.services.scraping import FetchError, fetch_html

URL = "http://shopalpha.mock:8080/items/1"


@pytest.fixture
def sleeps(monkeypatch):
    calls: list[float] = []
    monkeypatch.setattr(scraping, "_sleep", calls.append)
    return calls


@responses.activate
def test_success_first_try(sleeps):
    responses.get(URL, body="ok")
    assert fetch_html(URL) == "ok"
    assert len(responses.calls) == 1
    assert sleeps == []


@responses.activate
def test_retries_5xx_then_succeeds(sleeps):
    responses.get(URL, status=503)
    responses.get(URL, status=503)
    responses.get(URL, body="ok")
    assert fetch_html(URL) == "ok"
    assert len(responses.calls) == 3
    assert sleeps == [1, 2]


@responses.activate
def test_retries_connection_error(sleeps):
    responses.get(URL, body=requests.ConnectionError("boom"))
    responses.get(URL, body=requests.Timeout("slow"))
    responses.get(URL, body="ok")
    assert fetch_html(URL) == "ok"
    assert sleeps == [1, 2]


@responses.activate
def test_gives_up_after_max_retries(sleeps):
    responses.get(URL, status=500)
    with pytest.raises(FetchError, match="HTTP 500"):
        fetch_html(URL)
    assert len(responses.calls) == 4
    assert sleeps == [1, 2, 4]


@responses.activate
def test_4xx_not_retried(sleeps):
    responses.get(URL, status=404)
    with pytest.raises(FetchError, match="HTTP 404"):
        fetch_html(URL)
    assert len(responses.calls) == 1
    assert sleeps == []


@responses.activate
def test_non_connection_request_exception_not_retried(sleeps):
    responses.add(responses.GET, URL, body=requests.exceptions.InvalidURL("bad url"))
    with pytest.raises(FetchError, match="Network error"):
        fetch_html(URL)
    assert sleeps == []
    assert len(responses.calls) == 1
