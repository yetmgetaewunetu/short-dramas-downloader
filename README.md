# Drama Downloader (Python Core)

<p align="center">
  <img src="banner.png" alt="Drama Downloader Banner" width="100%" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg?style=for-the-badge&logo=python" alt="Python 3.8+" />
  <img src="https://img.shields.io/badge/Platforms-11+-orange.svg?style=for-the-badge" alt="Supported Platforms" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge" alt="License MIT" />
  <img src="https://img.shields.io/badge/Subtitles-SRT%20%2F%20VTT-cyan.svg?style=for-the-badge" alt="Subtitles SRT / VTT" />
  <img src="https://img.shields.io/badge/CLI-Ready-purple.svg?style=for-the-badge" alt="CLI Ready" />
</p>

A standalone, powerful, high-speed Python toolkit for extracting metadata, episode lists, subtitles, and downloading videos directly from **11+ popular OTT short-drama platforms**.

The project has been fully redesigned and ported to Python from the core architecture of the `Drama Downloader` application, with built-in ByteDance Spade URL decryption algorithms and standardized DramaBox RSA signing.

---

## 📑 Table of Contents

- [Key Features](#-key-features)
- [Supported Platforms](#-supported-platforms)
- [Installation](#-installation)
- [Command Line Usage (CLI)](#-command-line-usage-cli)
- [Usage in Python Code (API)](#-usage-in-python-code-api)
- [Subtitle Processing Engine (SRT / VTT Engine)](#-subtitle-processing-engine-srt--vtt-engine)
- [Technical Architecture & Cryptography](#-technical-architecture--cryptography)
- [Testing](#-testing)
- [Directory Structure](#-directory-structure)
- [Links & Useful Tools](#-links--useful-tools)
- [Disclaimer](#-disclaimer)

---

## ✨ Key Features

- ⚡ **Auto-Detection Router:** Automatically detects the platform from just a movie link (URL) or Series ID.
- 🔓 **Bypass DRM & Payload Obfuscation:** Built-in Spade URL decryptor (ByteDance AES-128-CBC) and standardized RSA-SHA256 signing for DramaBox.
- 🚀 **Parallel multi-threaded video downloads:** Download multiple episodes concurrently with chunk streaming and automatic safe file renaming.
- 🎯 **Automatic subtitle extraction & conversion:** Automatically downloads subtitles bundled with episodes and converts WebVTT to SubRip (.srt), compatible with all devices.
- 💻 **Intuitive command-line interface (CLI):** Preview episode lists, classify locked/unlocked episodes (`[FREE] [HAS STREAM]`), download by episode range (e.g. `1-10,15,20`).
- 📦 **Modular architecture:** Easily integrate into a Telegram bot, FastAPI web service, or automated crawler.

---

## 🌐 Supported Platforms

| Platform ID | Display Name | Extraction Mechanism | Subtitles |
| :--- | :--- | :--- | :---: |
| `dramabox` | **DramaBox** | Next.js Scrape + RSA Signing + Goodbos Fallback | Yes |
| `goodshort`| **GoodShort / GoodReels** | Goodbos Mobile API + Chapter CDN Resolver | Yes |
| `shortmax` | **ShortMax** | ShortMax API v1 Multi-Quality (1080p/720p/540p) | Yes |
| `netshort` | **NetShort / FlickReels** | NetShort Core API + PlayVoucher Watch Token | Yes |
| `freereels`| **FreeReels** | Drakula API + Subtitle Parser | Yes |
| `kisskh`   | **KissKH** | KissKH Multi-Mirrors + Stream PNG Decryptor | Yes |
| `hongguo`  | **Hongguo / Fanqie** | Modern.js Loader + ByteDance Spade URL Decryption | Yes |
| `dramawave`| **DramaWave** | Goodbos DramaWave API | Yes |
| `raptdrama`| **RaptDrama** | Goodbos RaptDrama API | Yes |
| `flextv`   | **FlexTV** | Goodbos FlexTV API | Yes |
| `stardusttv`| **StardustTV** | Goodbos StardustTV2 API | Yes |

---

## 📦 Installation

### Requirements
- Python `>= 3.8`
- `requests >= 2.28.0`
- `cryptography >= 41.0.0`

### Quick Install

```bash
# Clone the project
git clone https://github.com/yetmgetaewunetu/short-dramas-downloader.git
cd short-dramas-downloader

# Install dependencies and the module
pip install -e .
```

---

## 💻 Command Line Usage (CLI)

After installation, you can use the `dramadl` command or `python -m drama_downloader`.

### 1. List supported platforms
```bash
python -m drama_downloader platforms
```

### 2. Check movie info and episode list (`info`)
```bash
python -m drama_downloader info "https://www.dramaboxdb.com/movie/42000001234/drama"
```

*Sample output:*
```
[*] Inspecting drama: https://www.dramaboxdb.com/movie/42000001234/drama
============================================================
Title:       Glory Returns
Platform:    DRAMABOX
Series ID:   dramabox:42000001234
Episodes:    60 (Accessible: 60)
Cover:       https://thwztchapter.dramaboxdb.com/...
============================================================

Episode List:
  EP001: Episode 1 [FREE] [HAS STREAM]
  EP002: Episode 2 [FREE] [HAS STREAM]
  ...
  EP060: Episode 60 [FREE] [HAS STREAM]

Total: 60 episodes found.
```

### 3. Download a movie (`download`)

```bash
# Download episode 1
python -m drama_downloader download "https://www.dramaboxdb.com/movie/42000001234/drama" -e 1

# Download by episode range (e.g. episodes 1 to 5 and episode 10) with 3 threads
python -m drama_downloader download "https://www.dramaboxdb.com/movie/42000001234/drama" -e 1-5,10 -c 3 -o ./downloads

# Download the entire series
python -m drama_downloader download "https://netshort.com/drama/12345678" -c 4 -o ./downloads
```

### 4. Browse the short-drama catalog (`catalog`)
```bash
python -m drama_downloader catalog dramabox --page 1 -q "Love"
```

---

## 🐍 Usage in Python Code (API)

### Extracting Series & Stream URL info

```python
import drama_downloader as dd

url = "https://www.dramaboxdb.com/movie/42000001234/drama"

# Automatically detect the platform and parse all episodes
series = dd.load_series(url)

print(f"Title: {series.name}")
print(f"Platform: {series.platform}")
print(f"Total episodes: {series.episode_count} (Accessible: {series.accessible_count})")

# Iterate over the episode list
for ep in series.episodes:
    print(f"EP{ep.num:02d}: {ep.title} -> {ep.direct_url}")
```

### Downloading video with automatic subtitles

```python
from drama_downloader import DramaDownloader, load_series

series = load_series("https://netshort.com/drama/12345678")

downloader = DramaDownloader(
    output_dir="./downloads",
    concurrency=2,
    save_vtt=True  # Set True to also save the original .vtt file alongside the .srt
)

downloader.download_series(
    series,
    episodes_range=[1, 2, 3],
    on_episode_start=lambda ep: print(f"[*] Starting download for episode {ep.num}..."),
    on_episode_done=lambda ep, path: print(f"[✔] Done: {path}"),
    on_episode_error=lambda ep, err: print(f"[x] Error on episode {ep.num}: {err}")
)
```

---

## 🎯 Subtitle Processing Engine (SRT / VTT Engine)

The module includes a built-in smart subtitle processor:
1. **Automatic multi-language subtitle extraction:** Platforms like NetShort, FreeReels, and KissKH automatically extract subtitle paths (`episode.subs`).
2. **WebVTT $\to$ SRT normalization ([`vtt_to_srt()`](drama_downloader/downloader.py)):**
   - Automatically detects the WebVTT format.
   - Converts dot-style timestamps (`00:00:01.000`) to standard SubRip comma format (`00:00:01,000`).
   - Automatically numbers dialogue lines (`1, 2, 3...`) and strips HTML/WebVTT cue tags (`<c>`, `<b>`, `NOTE`).
   - The `.srt` file is saved with the same name as the video, so players (VLC, Media Player, TV) display subtitles immediately.

```python
import drama_downloader as dd

vtt_content = """WEBVTT

00:00:01.000 --> 00:00:03.500
<b>Hello!</b> This is a Drama Downloader short clip.
"""

srt_content = dd.vtt_to_srt(vtt_content)
print(srt_content)
```

---

## 🔐 Technical Architecture & Cryptography

### 1. RSA CRT normalization for DramaBox
DramaBox's embedded RSA private key has a non-standard ASN.1 structure containing CRT parameters ($dP, dQ$), which causes the OpenSSL 3+ library in Python to reject initialization. The module fully resolves this by parsing the ASN.1 structure and recalculating:
$$dP = d \pmod{p-1}, \quad dQ = d \pmod{q-1}$$
This produces a PKCS#1 v1.5 SHA-256 signature that matches $100\%$ with the Node.js runtime.

### 2. Spade Decryption Algorithm (ByteDance / Fanqie / Hongguo)
Decrypting video URLs encrypted via the Spade mechanism:
1. Base64-decode the `spade_a` string and extract the `payload`.
2. Recover the 32-character hex content key via XOR transformation and bit parity.
3. Derive the key and IV via `SHA-512(SHA-512(key) + SPADE_CONSTANTS)`.
4. Decrypt with `AES-128-CBC` and remove PKCS#7 padding to obtain the original stream URL.

---

## 🧪 Testing

The project ships with a complete unit test suite covering RSA signing, the Spade URL cipher, the 11-platform router, and the subtitle converter:

```bash
python tests/test_module.py
```

Result:
```text
Ran 4 tests in 0.056s
OK
[OK] All 10 platform detection tests passed
[OK] Total active platforms: 11
[OK] RSA signing test passed (signature identical to Node.js)
[OK] VTT to SRT subtitle conversion test passed
```

---

## 📂 Directory Structure

```
drama_downloader/
├── __init__.py           # Public exports: load_series, DramaDownloader, vtt_to_srt
├── __main__.py          # CLI execution entrypoint
├── cli.py               # argparse command-line argument handling
├── models.py            # Dataclasses: Series, Episode, Subtitle
├── client.py            # Session pooling & auto-retry
├── downloader.py        # Multi-threaded parallel download management & Subtitle Engine
├── crypto/
│   ├── dramabox_rsa.py  # RSA-SHA256 signature (CRT normalized)
│   └── spade.py         # ByteDance Spade cipher
└── platforms/
    ├── base.py          # BasePlatform abstract class
    ├── dramabox.py      # DramaBox extractor
    ├── goodshort.py     # GoodShort extractor
    ├── shortmax.py      # ShortMax extractor
    ├── netshort.py      # NetShort extractor
    ├── freereels.py     # FreeReels extractor
    ├── kisskh.py        # KissKH extractor
    ├── hongguo.py       # Hongguo / Fanqie extractor
    └── goodbos_aggregators.py # DramaWave, RaptDrama, FlexTV, StardustTV
```

---

## 🔗 Links & Useful Tools

- 🌐 **Official Website:** [https://www.tnkre.dev/](https://www.tnkre.dev/)
- 🛠️ **Online Decompiler Tool:** [https://decompile.tnkre.dev/](https://decompile.tnkre.dev/)

---

## ⚖️ Disclaimer

This project was created for the purpose of **academic research, education, and clean-room compatibility**. Users are solely responsible for the legality of using this tool against the respective streaming services, in accordance with local laws and each platform's terms of service.
