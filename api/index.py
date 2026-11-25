"""
Vercel Serverless & Local FastAPI Backend for DramaDownloader.
Stateless: resolves metadata, direct CDN video URLs, and subtitles without saving videos to the server.
"""

import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import struct
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urlparse
import zlib

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from drama_downloader import (  # noqa: E402
    AuthConfig,
    Episode,
    HttpClient,
    get_all_platforms,
    get_platform,
    get_video_url,
    load_series,
    vtt_to_srt,
)
from drama_downloader.downloader import sanitize_filename  # noqa: E402

app = FastAPI(title="DramaDownloader API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthPayload(BaseModel):
    cookies_text: Optional[str] = None
    cookie_header: Optional[str] = None
    cookies: Dict[str, str] = Field(default_factory=dict)
    headers: Dict[str, str] = Field(default_factory=dict)
    platform_headers: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    domain_headers: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    goodbos_token: Optional[str] = None


class InfoRequest(BaseModel):
    target: str
    platform: Optional[str] = None
    auth: Optional[AuthPayload] = None


class EpisodeUrlRequest(BaseModel):
    num: int = 1
    title: str = "Episode"
    url: str
    direct_url: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
    platform: Optional[str] = None
    auth: Optional[AuthPayload] = None


class CatalogRequest(BaseModel):
    platform: str
    page: int = 1
    query: Optional[str] = None
    category: Optional[str] = None
    auth: Optional[AuthPayload] = None


class SubtitleRequest(BaseModel):
    url: str
    lang: str = "en"
    filename: Optional[str] = None
    auth: Optional[AuthPayload] = None


class ZipEpisodeItem(BaseModel):
    num: int = 1
    title: str = "Episode"
    url: str
    direct_url: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
    subs: List[Dict[str, Any]] = Field(default_factory=list)


class ZipDownloadRequest(BaseModel):
    series_name: str = "Drama"
    platform: Optional[str] = None
    episodes: List[ZipEpisodeItem] = Field(default_factory=list)
    include_subs: bool = True
    auth: Optional[AuthPayload] = None


def _build_client(auth_payload: Optional[AuthPayload]) -> HttpClient:
    if not auth_payload:
        return HttpClient()
    # Intentionally ignore cookies_file from remote payloads so clients cannot probe server files.
    auth = AuthConfig(
        cookies_text=auth_payload.cookies_text,
        cookie_header=auth_payload.cookie_header,
        cookies=auth_payload.cookies,
        headers=auth_payload.headers,
        platform_headers=auth_payload.platform_headers,
        domain_headers=auth_payload.domain_headers,
        goodbos_token=auth_payload.goodbos_token,
    )
    return HttpClient(auth=None if auth.is_empty() else auth)


def _is_vercel_env() -> bool:
    return os.environ.get("VERCEL") == "1" or bool(os.environ.get("VERCEL_ENV"))


def _content_disposition(filename: str, default_ext: str) -> str:
    """Builds an RFC 5987 Content-Disposition header safe for Starlette's latin-1 header encoder."""
    safe_name = sanitize_filename(filename)
    if not safe_name.lower().endswith(default_ext):
        safe_name += default_ext
    stem = safe_name[: -len(default_ext)]
    ascii_stem = stem.encode("ascii", "ignore").decode("ascii")
    ascii_stem = re.sub(r"[\s\-_]+$", "", ascii_stem).strip() or "download"
    ascii_name = f"{ascii_stem}{default_ext}"
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(safe_name)}'


def _validate_public_http_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Invalid HTTP/HTTPS URL")
    host = parsed.hostname
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        raise HTTPException(status_code=400, detail=f"Could not resolve host: {e}")

    for info in infos:
        ip_str = info[4][0]
        ip_obj = ipaddress.ip_address(ip_str)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast:
            raise HTTPException(status_code=403, detail="Target host resolves to a restricted address")
    return raw_url


@app.get("/")
def serve_index():
    index_path = ROOT_DIR / "public" / "index.html"
    if not index_path.is_file():
        return {"status": "ok", "message": "DramaDownloader API is running"}
    return FileResponse(index_path)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "proxy_download": not _is_vercel_env(),
    }


@app.get("/api/proxy-download")
def proxy_download(
    url: str = Query(..., description="Direct CDN video URL"),
    filename: str = Query("video.mp4", description="Download filename"),
):
    """Streams an external CDN video with Content-Disposition: attachment (local/VPS only)."""
    if _is_vercel_env():
        raise HTTPException(
            status_code=501,
            detail="Proxy video download is disabled on Vercel due to serverless payload limits. Use direct CDN download or run locally/on a VPS.",
        )

    _validate_public_http_url(url)
    client = HttpClient(timeout=30)
    resp = client.get(url, stream=True)
    if resp.status_code >= 400:
        resp.close()
        raise HTTPException(status_code=resp.status_code, detail=f"Upstream CDN returned HTTP {resp.status_code}")

    headers = {
        "Content-Disposition": _content_disposition(filename, ".mp4"),
    }
    if resp.headers.get("Content-Length"):
        headers["Content-Length"] = resp.headers["Content-Length"]

    media_type = resp.headers.get("Content-Type") or "video/mp4"

    def _stream():
        try:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk
        finally:
            resp.close()

    return StreamingResponse(_stream(), media_type=media_type, headers=headers)


def _dos_datetime() -> Tuple[int, int]:
    t = time.localtime()
    year = max(1980, t.tm_year)
    dos_time = (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2)
    dos_date = ((year - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday
    return dos_time, dos_date


def iter_streaming_zip(entries: Iterable[Tuple[str, Iterable[bytes]]]):
    """Yields a valid PKZIP stream (ZIP_STORED + data descriptors) without buffering files."""
    dos_time, dos_date = _dos_datetime()
    flags = 0x0808  # Bit 3: data descriptor, Bit 11: UTF-8 filename
    offset = 0
    central_records: List[Tuple[bytes, int, int, int]] = []

    for arcname, chunk_iter in entries:
        name_bytes = arcname.encode("utf-8")
        local_header = struct.pack(
            "<IHHHHHIIIHH",
            0x04034B50,
            20,
            flags,
            0,
            dos_time,
            dos_date,
            0,
            0,
            0,
            len(name_bytes),
            0,
        )
        local_offset = offset
        yield local_header
        yield name_bytes
        offset += len(local_header) + len(name_bytes)

        crc = 0
        size = 0
        for chunk in chunk_iter:
            if not chunk:
                continue
            crc = zlib.crc32(chunk, crc) & 0xFFFFFFFF
            size += len(chunk)
            offset += len(chunk)
            yield chunk

        descriptor = struct.pack("<IIII", 0x08074B50, crc, size, size)
        yield descriptor
        offset += len(descriptor)
        central_records.append((name_bytes, crc, size, local_offset))

    cd_offset = offset
    cd_size = 0
    for name_bytes, crc, size, local_offset in central_records:
        cd_header = struct.pack(
            "<IHHHHHHIIIHHHHHII",
            0x02014B50,
            20,
            20,
            flags,
            0,
            dos_time,
            dos_date,
            crc,
            size,
            size,
            len(name_bytes),
            0,
            0,
            0,
            0,
            0,
            local_offset,
        )
        yield cd_header
        yield name_bytes
        cd_size += len(cd_header) + len(name_bytes)

    eocd = struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,
        0,
        len(central_records),
        len(central_records),
        cd_size,
        cd_offset,
        0,
    )
    yield eocd


def _fetch_subtitle_srt_bytes(client: HttpClient, url: str) -> Optional[bytes]:
    if url.startswith("data:"):
        raw_content = base64.b64decode(url.split(",", 1)[1])
    else:
        _validate_public_http_url(url)
        resp = client.get(url)
        if resp.status_code != 200:
            return None
        raw_content = resp.content
    text = raw_content.decode("utf-8", errors="ignore")
    if "WEBVTT" in text[:50] or url.lower().endswith(".vtt"):
        text = vtt_to_srt(text)
    return text.encode("utf-8")


@app.post("/api/download-zip")
async def download_zip(request: Request):
    """Streams selected episodes and .srt subtitles as a single ZIP straight to the browser."""
    if _is_vercel_env():
        raise HTTPException(
            status_code=501,
            detail="ZIP streaming is disabled on Vercel due to serverless payload limits. Run locally/on a VPS or use single-episode downloads.",
        )

    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        raw_data = await request.json()
    else:
        body = (await request.body()).decode("utf-8", errors="ignore")
        form_data = parse_qs(body)
        payload_vals = form_data.get("payload")
        if not payload_vals:
            raise HTTPException(status_code=400, detail="Missing payload")
        raw_data = json.loads(payload_vals[0])

    req = ZipDownloadRequest(**raw_data)
    if not req.episodes:
        raise HTTPException(status_code=400, detail="No episodes selected")

    client = _build_client(req.auth)
    zip_name = sanitize_filename(req.series_name or "Drama")

    def _build_entries():
        for item in req.episodes:
            ep = Episode(
                num=item.num,
                title=item.title,
                url=item.url,
                direct_url=item.direct_url,
                extra=item.extra,
            )
            stream_url = ep.direct_url or get_video_url(ep, platform_hint=req.platform or None, client=client)
            if not stream_url or ".m3u8" in stream_url.lower():
                continue
            try:
                _validate_public_http_url(stream_url)
            except HTTPException:
                continue

            ep_prefix = f"EP{ep.num:02d}"
            mp4_name = f"{ep_prefix} - {sanitize_filename(ep.title)}.mp4"

            def _iter_video(u=stream_url):
                resp = client.get(u, stream=True, timeout=30)
                if resp.status_code >= 400:
                    resp.close()
                    return
                try:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            yield chunk
                finally:
                    resp.close()

            yield mp4_name, _iter_video()

            if req.include_subs:
                subs = item.subs or [s.to_dict() for s in ep.subs]
                for sub in subs:
                    sub_url = sub.get("url")
                    if not sub_url:
                        continue
                    try:
                        srt_bytes = _fetch_subtitle_srt_bytes(client, sub_url)
                        if srt_bytes:
                            lang = sanitize_filename(str(sub.get("lang") or "en"))
                            yield f"{ep_prefix}_{lang}.srt", [srt_bytes]
                    except Exception:
                        continue

    headers = {
        "Content-Disposition": _content_disposition(zip_name, ".zip"),
    }
    return StreamingResponse(iter_streaming_zip(_build_entries()), media_type="application/zip", headers=headers)


@app.get("/api/platforms")
def list_platforms():
    return {
        "platforms": [
            {"id": p.platform_id, "name": p.display_name}
            for p in get_all_platforms()
        ]
    }


@app.post("/api/info")
def inspect_series(req: InfoRequest):
    target = req.target.strip()
    if not target:
        raise HTTPException(status_code=400, detail="Target URL or Series ID is required")
    try:
        client = _build_client(req.auth)
        series = load_series(target, platform_hint=req.platform or None, client=client)
        return series.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to load series: {e}")


@app.post("/api/episode-url")
def resolve_episode_url(req: EpisodeUrlRequest):
    try:
        client = _build_client(req.auth)
        ep = Episode(
            num=req.num,
            title=req.title,
            url=req.url,
            direct_url=req.direct_url,
            extra=req.extra,
        )
        resolved = get_video_url(ep, platform_hint=req.platform or None, client=client)
        if not resolved:
            raise HTTPException(status_code=404, detail="No stream URL available for this episode")
        return {
            "direct_url": resolved,
            "subs": [s.to_dict() for s in ep.subs],
            "locked": ep.locked,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to resolve stream URL: {e}")


@app.post("/api/catalog")
def browse_catalog(req: CatalogRequest):
    client = _build_client(req.auth)
    plat = get_platform(req.platform, client=client)
    if not plat:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {req.platform}")
    try:
        result = plat.get_catalog(page=req.page, query=req.query or None, category=req.category or None)
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch catalog: {e}")


@app.post("/api/subtitle")
def fetch_subtitle(req: SubtitleRequest):
    try:
        if req.url.startswith("data:"):
            data_part = req.url.split(",", 1)[1]
            raw_content = base64.b64decode(data_part)
        else:
            parsed = urlparse(req.url)
            if parsed.scheme not in ("http", "https"):
                raise HTTPException(status_code=400, detail="Unsupported subtitle URL scheme")
            client = _build_client(req.auth)
            resp = client.get(req.url)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Subtitle upstream returned HTTP {resp.status_code}")
            raw_content = resp.content

        text = raw_content.decode("utf-8", errors="ignore")
        if "WEBVTT" in text[:50] or req.url.lower().endswith(".vtt"):
            text = vtt_to_srt(text)

        return Response(
            content=text.encode("utf-8"),
            media_type="application/x-subrip; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(req.filename or f"subtitle_{req.lang}", ".srt")},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch subtitle: {e}")
