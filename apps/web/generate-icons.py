#!/usr/bin/env python3
"""Generate web favicon + PWA icons from a single master.

Usage:
    python apps/web/generate-icons.py [path-to-master.png]

Master should be a square PNG (icon-master.png by default). Requires Pillow,
a build-time tool only:  .venv/bin/pip install pillow  (do NOT add it to any
pyproject.toml — it is not a runtime dependency).
"""

import sys
from pathlib import Path

from PIL import Image

WEB = Path(__file__).resolve().parent
PUBLIC = WEB / "public"

PNG_TARGETS = [
    ("favicon-16x16.png", 16),
    ("favicon-32x32.png", 32),
    ("favicon-48x48.png", 48),
    ("apple-touch-icon.png", 180),
    ("pwa-192x192.png", 192),
    ("pwa-512x512.png", 512),
]
ICO_SIZES = [16, 32, 48]


def load_master(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    if img.width != img.height:
        raise SystemExit(f"Master must be square, got {img.width}x{img.height}")
    return img


def resize(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    master_path = Path(sys.argv[1]) if len(sys.argv) > 1 else WEB / "icon-master.png"
    if not master_path.exists():
        raise SystemExit(f"No master image at {master_path}")

    master = load_master(master_path)
    PUBLIC.mkdir(parents=True, exist_ok=True)

    for name, size in PNG_TARGETS:
        resize(master, size).save(PUBLIC / name)
        print(f"wrote public/{name}")

    resize(master, 512).save(
        PUBLIC / "favicon.ico",
        sizes=[(s, s) for s in ICO_SIZES],
    )
    print("wrote public/favicon.ico")


if __name__ == "__main__":
    main()
