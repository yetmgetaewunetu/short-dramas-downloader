"""
drama_downloader.auth
~~~~~~~~~~~~~~~~~~~~~
Optional authentication configuration and session helpers (cookies, headers, tokens).
"""

from dataclasses import dataclass, field
import http.cookiejar
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse
import requests

PLATFORM_HOSTS: Dict[str, Tuple[str, ...]] = {
    "dramabox": ("dramaboxdb.com", "webfic.com", "dramabox.goodbos.online"),
    "goodshort": ("goodshort.com", "goodreels.com", "goodshort.goodbos.online"),
    "shortmax": ("shortmax.com", "shortmax.goodbos.online"),
    "netshort": ("netshort.com", "flickreels.com", "netshort.goodbos.online"),
    "freereels": ("freereels.app", "drakula.goodbos.online"),
    "kisskh": ("kisskh.co", "kisskh.do", "kisskh.id", "kisskh.is"),
    "hongguo": ("hongguoduanju.com", "fqnovel.com"),
    "dramawave": ("dramawave.com", "dramawave.goodbos.online"),
    "raptdrama": ("raptdrama.com", "raptdrama.goodbos.online"),
    "flextv": ("flextv.com", "flextv.goodbos.online"),
    "stardusttv": ("stardusttv.com", "stardusttv2.goodbos.online"),
}


def parse_header_string(header_str: str) -> Tuple[str, str]:
    """Parses a 'Header-Name: value' string into a (name, value) tuple."""
    if ":" not in header_str:
        raise ValueError(f"Invalid header format (expected 'Name: Value'): {header_str}")
    name, value = header_str.split(":", 1)
    name = name.strip()
    if not name:
        raise ValueError(f"Header name cannot be empty: {header_str}")
    return name, value.strip()


def parse_cookie_header(cookie_header: str) -> Dict[str, str]:
    """Parses a raw Cookie header string ('a=1; b=2') into a dict."""
    parsed: Dict[str, str] = {}
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        if k:
            parsed[k] = v.strip()
    return parsed


def _host_matches(host: str, pattern: str) -> bool:
    h = host.lower().strip(".")
    p = pattern.lower().strip(".")
    return h == p or h.endswith("." + p)


def _load_json_cookies(session: requests.Session, data: Any) -> None:
    if isinstance(data, dict):
        for k, v in data.items():
            session.cookies.set(str(k), str(v))
        return

    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            value = item.get("value")
            if not name or value is None:
                continue
            kwargs: Dict[str, Any] = {}
            if item.get("domain"):
                kwargs["domain"] = str(item["domain"])
            if item.get("path"):
                kwargs["path"] = str(item["path"])
            if item.get("secure") is not None:
                kwargs["secure"] = bool(item["secure"])
            session.cookies.set(str(name), str(value), **kwargs)
        return

    raise ValueError("Unsupported JSON cookie format: expected object or list of cookie objects")


def _load_netscape_cookies_text(session: requests.Session, text: str) -> None:
    """Parses Netscape cookies.txt text into a requests.Session."""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_") :]
        elif line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, path, secure, _expires, name, value = parts[:7]
        if not name:
            continue
        session.cookies.set(
            name,
            value,
            domain=domain or None,
            path=path or "/",
            secure=(secure.upper() == "TRUE"),
        )


def load_cookies_from_text(session: requests.Session, text: str) -> None:
    """Loads cookies from raw Netscape cookies.txt or JSON string into a Session."""
    stripped = text.lstrip()
    if not stripped:
        return
    if stripped.startswith("{") or stripped.startswith("["):
        _load_json_cookies(session, json.loads(stripped))
    else:
        _load_netscape_cookies_text(session, text)


def load_cookies_into_session(
    session: requests.Session,
    cookies_file: Optional[str] = None,
    cookies: Optional[Dict[str, str]] = None,
    cookie_header: Optional[str] = None,
    cookies_text: Optional[str] = None,
) -> None:
    """Loads optional cookies from file, raw text, dict, or Cookie header into a Session."""
    if cookies_file:
        if not os.path.isfile(cookies_file):
            raise FileNotFoundError(f"Cookies file not found: {cookies_file}")

        if cookies_file.lower().endswith(".json"):
            with open(cookies_file, "r", encoding="utf-8") as f:
                _load_json_cookies(session, json.load(f))
        else:
            with open(cookies_file, "r", encoding="utf-8", errors="ignore") as f:
                snippet = f.read(256).lstrip()
            if snippet.startswith("{") or snippet.startswith("["):
                with open(cookies_file, "r", encoding="utf-8") as f:
                    _load_json_cookies(session, json.load(f))
            else:
                jar = http.cookiejar.MozillaCookieJar(cookies_file)
                jar.load(ignore_discard=True, ignore_expires=True)
                for cookie in jar:
                    session.cookies.set_cookie(cookie)

    if cookies_text:
        load_cookies_from_text(session, cookies_text)

    if cookie_header:
        for k, v in parse_cookie_header(cookie_header).items():
            session.cookies.set(k, v)

    if cookies:
        for k, v in cookies.items():
            session.cookies.set(str(k), str(v))


@dataclass
class AuthConfig:
    """Optional authentication settings for DramaDownloader HTTP requests."""

    cookies_file: Optional[str] = None
    cookies_text: Optional[str] = None
    cookies: Dict[str, str] = field(default_factory=dict)
    cookie_header: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    platform_headers: Dict[str, Dict[str, str]] = field(default_factory=dict)
    domain_headers: Dict[str, Dict[str, str]] = field(default_factory=dict)
    goodbos_token: Optional[str] = None

    def is_empty(self) -> bool:
        return not (
            self.cookies_file
            or self.cookies_text
            or self.cookies
            or self.cookie_header
            or self.headers
            or self.platform_headers
            or self.domain_headers
            or self.goodbos_token
        )

    def headers_for_url(self, url: str) -> Dict[str, str]:
        """Returns combined global, platform-scoped, and domain-scoped headers for a URL."""
        merged: Dict[str, str] = dict(self.headers)
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return merged

        for pid, p_headers in self.platform_headers.items():
            hosts = PLATFORM_HOSTS.get(pid.lower(), ())
            if any(_host_matches(host, pattern) for pattern in hosts):
                merged.update(p_headers)

        for domain, d_headers in self.domain_headers.items():
            if _host_matches(host, domain):
                merged.update(d_headers)

        return merged

    def apply_to_session(self, session: requests.Session) -> None:
        """Applies configured cookies and global headers onto a requests.Session."""
        load_cookies_into_session(
            session,
            cookies_file=self.cookies_file,
            cookies_text=self.cookies_text,
            cookies=self.cookies,
            cookie_header=self.cookie_header,
        )
        if self.headers:
            session.headers.update(self.headers)

    def merge(self, other: "AuthConfig") -> "AuthConfig":
        """Returns a new AuthConfig combining self with overrides from other."""
        merged_platform = {k: dict(v) for k, v in self.platform_headers.items()}
        for pid, hdrs in other.platform_headers.items():
            merged_platform.setdefault(pid, {}).update(hdrs)

        merged_domain = {k: dict(v) for k, v in self.domain_headers.items()}
        for dom, hdrs in other.domain_headers.items():
            merged_domain.setdefault(dom, {}).update(hdrs)

        return AuthConfig(
            cookies_file=other.cookies_file or self.cookies_file,
            cookies_text=other.cookies_text or self.cookies_text,
            cookies={**self.cookies, **other.cookies},
            cookie_header=other.cookie_header or self.cookie_header,
            headers={**self.headers, **other.headers},
            platform_headers=merged_platform,
            domain_headers=merged_domain,
            goodbos_token=other.goodbos_token or self.goodbos_token,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cookies_file": self.cookies_file,
            "cookies_text": self.cookies_text,
            "cookies": dict(self.cookies),
            "cookie_header": self.cookie_header,
            "headers": dict(self.headers),
            "platform_headers": {k: dict(v) for k, v in self.platform_headers.items()},
            "domain_headers": {k: dict(v) for k, v in self.domain_headers.items()},
            "goodbos_token": self.goodbos_token,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuthConfig":
        if not isinstance(data, dict):
            raise ValueError("Auth config must be a JSON object")
        return cls(
            cookies_file=data.get("cookies_file"),
            cookies_text=data.get("cookies_text"),
            cookies=dict(data.get("cookies") or {}),
            cookie_header=data.get("cookie_header"),
            headers=dict(data.get("headers") or {}),
            platform_headers={k: dict(v) for k, v in (data.get("platform_headers") or {}).items()},
            domain_headers={k: dict(v) for k, v in (data.get("domain_headers") or {}).items()},
            goodbos_token=data.get("goodbos_token"),
        )

    @classmethod
    def from_json_file(cls, path: str) -> "AuthConfig":
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Auth config file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    @classmethod
    def from_env(cls) -> "AuthConfig":
        """Loads optional auth settings from environment variables if set."""
        cfg = cls()
        config_path = os.environ.get("DRAMA_DL_AUTH_CONFIG")
        if config_path:
            cfg = cfg.merge(cls.from_json_file(config_path))

        headers: Dict[str, str] = {}
        auth_header = os.environ.get("DRAMA_DL_AUTH_HEADER")
        if auth_header:
            k, v = parse_header_string(auth_header) if ":" in auth_header else ("Authorization", auth_header)
            headers[k] = v

        env_cfg = cls(
            cookies_file=os.environ.get("DRAMA_DL_COOKIES") or None,
            cookie_header=os.environ.get("DRAMA_DL_COOKIE") or None,
            headers=headers,
            goodbos_token=os.environ.get("DRAMA_DL_GOODBOS_TOKEN") or None,
        )
        return cfg.merge(env_cfg)

    @classmethod
    def from_cli(
        cls,
        cookies_file: Optional[str] = None,
        cookie_header: Optional[str] = None,
        header_list: Optional[Iterable[str]] = None,
        auth_config_file: Optional[str] = None,
        goodbos_token: Optional[str] = None,
    ) -> "AuthConfig":
        """Builds an AuthConfig combining env, optional JSON config file, and explicit CLI args."""
        cfg = cls.from_env()
        if auth_config_file:
            cfg = cfg.merge(cls.from_json_file(auth_config_file))

        headers: Dict[str, str] = {}
        for raw_h in header_list or ():
            name, value = parse_header_string(raw_h)
            headers[name] = value

        cli_cfg = cls(
            cookies_file=cookies_file,
            cookie_header=cookie_header,
            headers=headers,
            goodbos_token=goodbos_token,
        )
        return cfg.merge(cli_cfg)
