"""
drama_downloader.cli
~~~~~~~~~~~~~~~~~~~~
Command-line interface for Drama Downloader.
"""

import argparse
import sys
from typing import List
from .auth import AuthConfig
from .client import http
from .models import Series, Episode
from .platforms import (
    load_series,
    detect_platform,
    get_all_platforms,
    get_platform,
)
from .downloader import DramaDownloader, DownloadProgress


def parse_range(range_str: str, max_ep: int) -> List[int]:
    """Parses episode range expressions like '1-10,12,15-20'."""
    res = set()
    parts = range_str.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            sub = part.split("-", 1)
            start = int(sub[0])
            end = int(sub[1]) if sub[1] else max_ep
            for i in range(start, end + 1):
                res.add(i)
        elif part.isdigit():
            res.add(int(part))
    return sorted(list(res))


def cmd_info(args):
    print(f"\n[*] Inspecting drama: {args.target}")
    try:
        series = load_series(args.target, platform_hint=args.platform)
        print("=" * 60)
        print(f"Title:       {series.name}")
        print(f"Platform:    {series.platform.upper()}")
        print(f"Series ID:   {series.series_id}")
        print(f"Episodes:    {series.episode_count} (Accessible: {series.accessible_count})")
        if series.cover:
            print(f"Cover:       {series.cover}")
        if series.description:
            desc = series.description.strip().replace("\n", " ")
            print(f"Description: {desc[:120]}..." if len(desc) > 120 else f"Description: {desc}")
        print("=" * 60)

        print("\nEpisode List:")
        for ep in series.episodes:
            status = "[FREE]" if not ep.locked else "[LOCKED]"
            direct = " [HAS STREAM]" if ep.direct_url else ""
            subs = f" ({len(ep.subs)} subs)" if ep.subs else ""
            print(f"  EP{ep.num:03d}: {ep.title} {status}{direct}{subs}")
        print(f"\nTotal: {len(series.episodes)} episodes found.\n")
    except Exception as e:
        print(f"[!] Error: {e}")
        sys.exit(1)


def cmd_download(args):
    print(f"\n[*] Loading drama: {args.target}")
    try:
        series = load_series(args.target, platform_hint=args.platform)
        print(f"[*] Found series: '{series.name}' ({len(series.episodes)} episodes)")

        selected_nums = None
        if args.episodes:
            selected_nums = parse_range(args.episodes, len(series.episodes))
            print(f"[*] Downloading selected episodes: {selected_nums}")
        else:
            print(f"[*] Downloading all unlocked episodes (1 to {len(series.episodes)})")

        dl = DramaDownloader(
            output_dir=args.output,
            concurrency=args.concurrency,
        )

        done_count = 0
        skipped_count = 0
        failed_count = 0

        def on_done(ep: Episode, path: str):
            nonlocal done_count
            done_count += 1
            print(f"[+] Downloaded: EP{ep.num:02d} -> {path}")

        def on_error(ep: Episode, err: Exception):
            nonlocal failed_count
            failed_count += 1
            print(f"[x] Failed EP{ep.num:02d}: {err}")

        def on_skipped(ep: Episode):
            nonlocal skipped_count
            skipped_count += 1
            print(f"[!] Skipped EP{ep.num:02d} (locked, no stream available): {ep.title}")

        print(f"[*] Output directory: {dl.output_dir}")
        print("[*] Starting download...")
        dl.download_series(
            series,
            episodes_range=selected_nums,
            skip_locked=not args.include_locked,
            on_episode_done=on_done,
            on_episode_error=on_error,
            on_episode_skipped=on_skipped,
        )
        print(
            f"\n[✔] Download batch finished! "
            f"Downloaded: {done_count}, Skipped (locked): {skipped_count}, Failed: {failed_count}"
        )
    except Exception as e:
        print(f"[!] Error: {e}")
        sys.exit(1)


def cmd_catalog(args):
    platform = get_platform(args.platform)
    if not platform:
        print(f"[!] Unknown platform: {args.platform}")
        sys.exit(1)

    print(f"\n[*] Fetching catalog from {platform.display_name} (Page {args.page})...")
    res = platform.get_catalog(page=args.page, query=args.query, category=args.category)
    print("=" * 60)
    print(f"Catalog: {platform.display_name} | Total: {res.total}")
    print("=" * 60)
    for idx, it in enumerate(res.items):
        print(f"[{idx + 1:02d}] {it.name} ({it.episodes} eps) - ID: {it.id}")
        if it.link:
            print(f"     URL: {it.link}")
    print()


def cmd_platforms(args):
    print("\nSupported OTT & Short Drama Platforms:")
    print("=" * 50)
    for p in get_all_platforms():
        print(f" - {p.platform_id:<14} : {p.display_name}")
    print("=" * 50 + "\n")


def _apply_cli_auth(args) -> None:
    auth = AuthConfig.from_cli(
        cookies_file=getattr(args, "cookies", None),
        cookie_header=getattr(args, "cookie", None),
        header_list=getattr(args, "header", None),
        auth_config_file=getattr(args, "auth_config", None),
        goodbos_token=getattr(args, "goodbos_token", None),
    )
    if not auth.is_empty():
        http.configure_auth(auth)


def main():
    auth_parent = argparse.ArgumentParser(add_help=False)
    auth_parent.add_argument(
        "--cookies",
        help="Optional path to Netscape cookies.txt or JSON cookies file",
    )
    auth_parent.add_argument(
        "--cookie",
        help="Optional raw Cookie header string (e.g. 'session=abc; uid=123')",
    )
    auth_parent.add_argument(
        "-H",
        "--header",
        action="append",
        help="Optional custom HTTP header (repeatable, e.g. 'Authorization: Bearer ...')",
    )
    auth_parent.add_argument(
        "--auth-config",
        help="Optional path to JSON auth config file (cookies, headers, per-platform headers)",
    )
    auth_parent.add_argument(
        "--goodbos-token",
        help="Optional custom Goodbos token override",
    )

    parser = argparse.ArgumentParser(
        prog="drama_downloader",
        description="Multi-Platform Short Drama Extractor and Downloader Module",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_info = subparsers.add_parser("info", parents=[auth_parent], help="Inspect series metadata and episode list")
    p_info.add_argument("target", help="URL or Series ID")
    p_info.add_argument("-p", "--platform", help="Explicit platform name/ID")
    p_info.set_defaults(func=cmd_info)

    p_dl = subparsers.add_parser("download", parents=[auth_parent], help="Download series or episodes")
    p_dl.add_argument("target", help="URL or Series ID")
    p_dl.add_argument("-p", "--platform", help="Explicit platform name/ID")
    p_dl.add_argument("-e", "--episodes", help="Episode range (e.g. 1-10,12,15)")
    p_dl.add_argument("-o", "--output", default="./downloads", help="Output directory (default: ./downloads)")
    p_dl.add_argument("-c", "--concurrency", type=int, default=2, help="Concurrency workers (default: 2)")
    p_dl.add_argument(
        "--include-locked",
        action="store_true",
        help="Attempt locked episodes too instead of skipping them (will fail unless a stream URL was resolved)",
    )
    p_dl.set_defaults(func=cmd_download)

    p_cat = subparsers.add_parser("catalog", parents=[auth_parent], help="Browse catalog of short dramas")
    p_cat.add_argument("platform", help="Platform ID (e.g. dramabox, shortmax, kisskh)")
    p_cat.add_argument("--page", type=int, default=1, help="Page number")
    p_cat.add_argument("-q", "--query", help="Search keyword")
    p_cat.add_argument("--category", help="Category filter")
    p_cat.set_defaults(func=cmd_catalog)

    p_plat = subparsers.add_parser("platforms", help="List all supported platforms")
    p_plat.set_defaults(func=cmd_platforms)

    args = parser.parse_args()
    try:
        _apply_cli_auth(args)
    except Exception as e:
        print(f"[!] Auth configuration error: {e}")
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
