"""Download product images for a bounded country/shop scope."""

import argparse
import csv
import hashlib
import json
import mimetypes
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", required=True)
    parser.add_argument("--shop-id", required=True)
    parser.add_argument("--input", default="Dataset/DataProcessed/products_clean.csv")
    parser.add_argument("--output-dir", default="Dataset/ImageCache")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=0.1)
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Allow downloading with certificate verification disabled when the environment blocks the image host certificate.",
    )
    return parser.parse_args()


def extract_urls(row):
    values = []
    for column in ("image_url", "images"):
        raw = (row.get(column) or "").strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                values.extend(str(item).strip() for item in parsed)
            elif isinstance(parsed, str):
                values.append(parsed.strip())
        except json.JSONDecodeError:
            values.append(raw)
    return [url for url in dict.fromkeys(values) if url.startswith(("http://", "https://"))]


def extension(content_type, url):
    guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip())
    if guessed in {".jpe", ".jpeg"}:
        return ".jpg"
    if guessed:
        return guessed
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".bin"


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    files_dir = output_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.csv"

    rows = []
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("country_code") == args.country and row.get("shop_id") == args.shop_id:
                rows.append(row)

    image_refs = {}
    for row in rows:
        for url in extract_urls(row):
            image_refs.setdefault(url, []).append(row.get("item_id", ""))

    existing = {}
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                existing[row["image_url"]] = row

    now = datetime.now(timezone.utc).isoformat()
    ssl_context = ssl._create_unverified_context() if args.insecure else None
    for url, item_ids in image_refs.items():
        if url in existing and existing[url].get("status") == "downloaded":
            continue
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        cached_files = list(files_dir.glob(f"{digest}.*"))
        if cached_files:
            existing[url] = {
                "country_code": args.country,
                "shop_id": args.shop_id,
                "item_ids": ";".join(sorted(set(item_ids))),
                "image_url": url,
                "local_path": str(cached_files[0]),
                "status": "downloaded",
                "http_status": "cached",
                "content_type": "",
                "sha256": hashlib.sha256(cached_files[0].read_bytes()).hexdigest(),
                "downloaded_at": now,
                "error": "",
            }
            continue
        record = {
            "country_code": args.country,
            "shop_id": args.shop_id,
            "item_ids": ";".join(sorted(set(item_ids))),
            "image_url": url,
            "local_path": "",
            "status": "error",
            "http_status": "",
            "content_type": "",
            "sha256": "",
            "downloaded_at": now,
            "error": "",
        }
        try:
            request = Request(url, headers={"User-Agent": "ProductKnowledgeDataset/1.0"})
            with urlopen(request, timeout=args.timeout, context=ssl_context) as response:
                data = response.read()
                content_type = response.headers.get("Content-Type", "")
                file_path = files_dir / f"{digest}{extension(content_type, url)}"
                file_path.write_bytes(data)
                record.update({
                    "local_path": str(file_path),
                    "status": "downloaded",
                    "http_status": str(response.status),
                    "content_type": content_type,
                    "sha256": hashlib.sha256(data).hexdigest(),
                })
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            record["error"] = str(exc)
        existing[url] = record
        time.sleep(args.sleep)

    fieldnames = [
        "country_code", "shop_id", "item_ids", "image_url", "local_path",
        "status", "http_status", "content_type", "sha256", "downloaded_at", "error",
    ]
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted(existing.values(), key=lambda row: row["image_url"]))

    downloaded = sum(row.get("status") == "downloaded" for row in existing.values())
    errors = sum(row.get("status") == "error" for row in existing.values())
    print(f"scope={args.country}/{args.shop_id} urls={len(image_refs)} downloaded={downloaded} errors={errors}")
    print(f"manifest={manifest_path}")


if __name__ == "__main__":
    main()
