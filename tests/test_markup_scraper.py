import pytest
from curl_cffi import requests

from chorba.lib.markup import scraper


class ErrorResponse:
    text = "<html></html>"

    def raise_for_status(self):
        raise requests.RequestsError("HTTP Error 404", response=self)


def test_scrape_from_url_raises_for_http_status(monkeypatch):
    monkeypatch.setattr(scraper.requests, "get", lambda *args, **kwargs: ErrorResponse())

    with pytest.raises(requests.RequestsError):
        scraper.RecipeScraper().scrape_from_url("https://example.com/missing")
