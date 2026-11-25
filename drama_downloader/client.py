"""
drama_downloader.client
~~~~~~~~~~~~~~~~~~~~~~~
HTTP client session wrapper with retry logic, pooling, and helper utilities.
"""

import logging
from typing import Any, Dict, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .auth import AuthConfig

logger = logging.getLogger("drama_downloader.client")

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class HttpClient:
    """Wrapper around requests.Session with connection pooling and retries."""

    def __init__(
        self,
        default_headers: Optional[Dict[str, str]] = None,
        timeout: int = 15,
        max_retries: int = 3,
        verify_ssl: bool = True,
        auth: Optional[AuthConfig] = None,
    ):
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.auth: Optional[AuthConfig] = None

        headers = {
            "User-Agent": DEFAULT_UA,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        }
        if default_headers:
            headers.update(default_headers)
        self.session.headers.update(headers)

        retries = Retry(
            total=max_retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        if auth is not None:
            self.configure_auth(auth)

    def configure_auth(self, auth: Optional[AuthConfig]) -> None:
        """Applies (or clears) optional AuthConfig on this client's session."""
        self.auth = auth
        if auth is not None and not auth.is_empty():
            auth.apply_to_session(self.session)

    def _merge_headers(self, url: str, headers: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        if not self.auth or self.auth.is_empty():
            return headers
        merged = self.auth.headers_for_url(url)
        if headers:
            merged.update(headers)
        return merged or None

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        stream: bool = False,
    ) -> requests.Response:
        t = timeout or self.timeout
        return self.session.get(
            url,
            params=params,
            headers=self._merge_headers(url, headers),
            timeout=t,
            verify=self.verify_ssl,
            stream=stream,
        )

    def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Any:
        resp = self.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def post(
        self,
        url: str,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> requests.Response:
        t = timeout or self.timeout
        return self.session.post(
            url,
            data=data,
            json=json,
            headers=self._merge_headers(url, headers),
            timeout=t,
            verify=self.verify_ssl,
        )

    def post_json(
        self,
        url: str,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Any:
        resp = self.post(url, data=data, json=json, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()


http = HttpClient()
