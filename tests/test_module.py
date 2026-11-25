"""
test_module.py
~~~~~~~~~~~~~~
Verification test suite for drama_downloader package.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import drama_downloader as dd


class TestDramaDownloader(unittest.TestCase):

    def test_rsa_signing(self):
        sig = dd.sign_dramabox("hello")
        self.assertTrue(len(sig) > 100)
        self.assertTrue(sig.startswith("e1Womj1QYXmFgI1NcC9bUFl5LIQLmUV9hjtFjwct"))
        print("[OK] RSA signing test passed (signature identical to Node.js)")

    def test_platform_detection(self):
        cases = [
            ("https://www.dramaboxdb.com/movie/42000001234/drama", "dramabox"),
            ("https://netshort.com/drama/test12345", "netshort"),
            ("https://kisskh.co/Drama/My-Title?id=1234", "kisskh"),
            ("https://www.shortmax.com/drama/sm12345", "shortmax"),
            ("https://freereels.app/drama/fr123456", "freereels"),
            ("https://hongguoduanju.com/detail?series_id=74123456789", "hongguo"),
            ("https://www.dramawave.com/drama/dw12345", "dramawave"),
            ("https://raptdrama.com/drama/12345", "raptdrama"),
            ("https://flextv.com/drama/fx12345", "flextv"),
            ("https://stardusttv.com/video/12345", "stardusttv"),
        ]
        for url, expected in cases:
            plat = dd.detect_platform(url)
            self.assertIsNotNone(plat, f"Failed to detect platform for {url}")
            self.assertEqual(plat.platform_id, expected)
        print(f"[OK] All {len(cases)} platform detection tests passed")

    def test_platforms_list(self):
        platforms = dd.get_all_platforms()
        self.assertGreaterEqual(len(platforms), 11)
        print(f"[OK] Total active platforms: {len(platforms)}")

    def test_vtt_to_srt(self):
        sample_vtt = """WEBVTT

00:00:01.000 --> 00:00:03.500
Hello World!

00:00:04.000 --> 00:00:06.000
<b>Welcome to Drama Downloader</b>
"""
        srt = dd.vtt_to_srt(sample_vtt)
        self.assertIn("00:00:01,000 --> 00:00:03,500", srt)
        self.assertIn("1\n", srt)
        self.assertIn("Hello World!", srt)
        self.assertIn("Welcome to Drama Downloader", srt)
        print("[OK] VTT to SRT subtitle conversion test passed")

    def test_auth_netscape_cookies_and_json_cookies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            netscape_path = os.path.join(tmpdir, "cookies.txt")
            with open(netscape_path, "w", encoding="utf-8") as f:
                f.write(
                    "# Netscape HTTP Cookie File\n"
                    ".dramaboxdb.com\tTRUE\t/\tTRUE\t0\tsid\tabc123\n"
                )

            client1 = dd.HttpClient(auth=dd.AuthConfig(cookies_file=netscape_path))
            cookies_dict = client1.session.cookies.get_dict(domain=".dramaboxdb.com")
            self.assertEqual(cookies_dict.get("sid"), "abc123")

            json_path = os.path.join(tmpdir, "cookies.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(
                    [{"name": "token", "value": "xyz789", "domain": ".hongguoduanju.com", "path": "/"}],
                    f,
                )

            client2 = dd.HttpClient(auth=dd.AuthConfig(cookies_file=json_path))
            self.assertEqual(
                client2.session.cookies.get_dict(domain=".hongguoduanju.com").get("token"),
                "xyz789",
            )

    def test_auth_scoped_headers_and_cli_merge(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "auth.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "headers": {"X-Global": "1"},
                        "platform_headers": {
                            "dramabox": {"Authorization": "Bearer db-secret"},
                        },
                        "domain_headers": {
                            "hongguoduanju.com": {"X-HG": "hg-val"},
                        },
                        "goodbos_token": "CUSTOM_TOKEN_123",
                    },
                    f,
                )

            with patch.dict(os.environ, {"DRAMA_DL_COOKIE": "env_k=env_v"}, clear=False):
                auth = dd.AuthConfig.from_cli(
                    cookie_header="cli_k=cli_v",
                    header_list=["X-CLI: yes"],
                    auth_config_file=cfg_path,
                )

            db_headers = auth.headers_for_url("https://www.dramaboxdb.com/movie/123/drama")
            self.assertEqual(db_headers.get("Authorization"), "Bearer db-secret")
            self.assertEqual(db_headers.get("X-Global"), "1")
            self.assertEqual(db_headers.get("X-CLI"), "yes")

            hg_headers = auth.headers_for_url("https://hongguoduanju.com/detail?series_id=1")
            self.assertIsNone(hg_headers.get("Authorization"))
            self.assertEqual(hg_headers.get("X-HG"), "hg-val")

            client = dd.HttpClient(auth=auth)
            self.assertEqual(client.session.cookies.get("cli_k"), "cli_v")
            plat = dd.get_platform("goodshort", client=client)
            self.assertEqual(plat.goodbos_token, "CUSTOM_TOKEN_123")

    def test_auth_cookies_text_and_fastapi_endpoints(self):
        import asyncio
        import base64
        import httpx
        from api.index import app

        netscape_text = (
            "# Netscape HTTP Cookie File\n"
            "#HttpOnly_.dramaboxdb.com\tTRUE\t/\tTRUE\t0\tsess\tval42\n"
        )
        client_http = dd.HttpClient(auth=dd.AuthConfig(cookies_text=netscape_text))
        self.assertEqual(client_http.session.cookies.get_dict(domain=".dramaboxdb.com").get("sess"), "val42")

        async def run_api_checks():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as api_client:
                resp_index = await api_client.get("/")
                self.assertEqual(resp_index.status_code, 200)
                self.assertIn("DramaDownloader", resp_index.text)

                resp_health = await api_client.get("/api/health")
                self.assertEqual(resp_health.status_code, 200)
                self.assertEqual(resp_health.json(), {"status": "ok", "proxy_download": True})

                resp_ssrf = await api_client.get("/api/proxy-download", params={"url": "http://127.0.0.1:8000/test.mp4"})
                self.assertEqual(resp_ssrf.status_code, 403)

                resp_plats = await api_client.get("/api/platforms")
                self.assertEqual(resp_plats.status_code, 200)
                self.assertGreaterEqual(len(resp_plats.json()["platforms"]), 11)

                vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi there!\n"
                data_uri = "data:text/vtt;base64," + base64.b64encode(vtt.encode("utf-8")).decode("ascii")
                resp_sub = await api_client.post(
                    "/api/subtitle",
                    json={"url": data_uri, "lang": "en", "filename": "EP01 - 第一集_en"},
                )
                self.assertEqual(resp_sub.status_code, 200)
                self.assertIn("00:00:01,000 --> 00:00:02,000", resp_sub.text)
                cd = resp_sub.headers.get("content-disposition", "")
                self.assertIn("EP01", cd)
                self.assertIn("filename*=UTF-8''", cd)

        from api.index import _content_disposition, iter_streaming_zip
        cd_mp4 = _content_disposition("EP01 - 第一集.mp4", ".mp4")
        cd_mp4.encode("latin-1")
        self.assertIn('filename="EP01.mp4"', cd_mp4)
        self.assertIn("filename*=UTF-8''", cd_mp4)

        import io
        import zipfile
        zip_bytes = b"".join(
            iter_streaming_zip(
                [
                    ("EP01 - 第一集.mp4", [b"abc", b"123"]),
                    ("EP01_en.srt", [b"1\n00:00:01,000 --> 00:00:02,000\nHi\n"]),
                ]
            )
        )
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            self.assertIsNone(zf.testzip())
            self.assertEqual(zf.read("EP01 - 第一集.mp4"), b"abc123")
            self.assertIn(b"Hi", zf.read("EP01_en.srt"))

        asyncio.run(run_api_checks())

    def test_dramabox_expired_url_check(self):
        from drama_downloader.platforms.dramabox import _is_signed_url_expired

        self.assertTrue(_is_signed_url_expired("https://hwvideoseo.dramaboxdb.com/a.mp4?Expires=1700000000&Signature=x"))
        self.assertFalse(_is_signed_url_expired("https://hwvideoseo.dramaboxdb.com/a.mp4?Expires=4102444800&Signature=x"))
        self.assertFalse(_is_signed_url_expired("https://example.com/video.mp4"))


if __name__ == "__main__":
    unittest.main()
