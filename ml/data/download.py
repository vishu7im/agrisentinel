"""Fetch the PlantVillage images for the 14 classes in classes.py.

    .venv/bin/python ml/data/download.py

Source is the canonical GitHub mirror, not Kaggle: Kaggle needs an API token that a
teammate cloning this repo at 2am will not have, and the images there are the same images.

**Why not just clone the repo.** Three approaches were tried. A blobless sparse clone is the
tidy answer on paper and it stalled mid-pack with no progress and no error — one dead TCP
connection and the whole 500 MB is lost. The codeload tarball is a single stream at ~1.6
MB/s, and two thirds of it is the grayscale and segmented variants we do not want. So:
resolve the file list through the git trees API (17 requests, no pagination, no truncation),
then pull the blobs from the raw CDN across a thread pool.

That makes the download **resumable**, which is the property that actually matters here.
Files already on disk are skipped, so an interrupted run costs you the seconds since the
last file rather than starting over.

Set GITHUB_TOKEN in the environment to raise the API rate limit if you hit it. Not needed
for a normal run — the 17 tree requests are well inside the anonymous 60/hour.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

_HERE = Path(__file__).resolve().parent
# Drop this script's own directory from sys.path — inspect.py next door shadows the stdlib
# `inspect` module and breaks `import torch`. See ml/data/__init__.py.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _HERE]
sys.path.insert(0, str(_HERE.parent))
from data.classes import CLASSES  # noqa: E402

OWNER_REPO = "spMohanty/PlantVillage-Dataset"
BRANCH = "master"
SUBDIR = ("raw", "color")  # the repo also ships grayscale/ and segmented/
API = f"https://api.github.com/repos/{OWNER_REPO}"
RAW = f"https://raw.githubusercontent.com/{OWNER_REPO}/{BRANCH}"

DEFAULT_RAW = _HERE.parent / "data" / "raw"
MANIFEST_NAME = ".manifest.json"
USER_AGENT = "agrisentinel-download/1.0"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


def _get(url: str, timeout: int = 60) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith(API):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _tree(sha: str) -> list[dict]:
    return json.loads(_get(f"{API}/git/trees/{sha}"))["tree"]


def _child(entries: list[dict], name: str) -> dict:
    for entry in entries:
        if entry["path"] == name:
            return entry
    raise SystemExit(f"'{name}' not found in the upstream tree — has the repo moved?")


def build_manifest() -> dict[str, list[str]]:
    """{class folder: [filenames]} — walked one tree level at a time.

    Deliberately not `git/trees/master?recursive=1`: that call comes back truncated for
    this repo, and a truncated listing looks exactly like a smaller dataset rather than
    like an error.
    """
    print(f"resolving file list from {OWNER_REPO}@{BRANCH}")
    node = _tree(BRANCH)
    for name in SUBDIR:
        node = _tree(_child(node, name)["sha"])

    wanted = {c.folder for c in CLASSES}
    present = {e["path"] for e in node if e["type"] == "tree"}
    if missing := wanted - present:
        raise SystemExit(
            "these class folders are not in the upstream dataset:\n  "
            + "\n  ".join(sorted(missing))
            + "\nFix ml/data/classes.py."
        )

    manifest: dict[str, list[str]] = {}
    for entry in node:
        if entry["path"] not in wanted:
            continue
        files = [e["path"] for e in _tree(entry["sha"]) if e["type"] == "blob"]
        manifest[entry["path"]] = sorted(files)
        print(f"  {entry['path']:<52} {len(files):>6,} files")
    return manifest


def download_one(folder: str, filename: str, dest: Path, retries: int = 4) -> int:
    """Fetch one image unless it is already on disk. Returns bytes written (0 if skipped)."""
    target = dest / filename
    if target.exists() and target.stat().st_size > 0:
        return 0

    path = "/".join(urllib.parse.quote(part) for part in (*SUBDIR, folder, filename))
    for attempt in range(retries):
        try:
            data = _get(f"{RAW}/{path}", timeout=30)
            # Write via a temp name so an interrupted run never leaves a half file that
            # the next run would happily skip as "already downloaded".
            tmp = target.with_suffix(target.suffix + ".part")
            tmp.write_bytes(data)
            tmp.rename(target)
            return len(data)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"{folder}/{filename}: {exc}") from exc
            time.sleep(2**attempt)  # 1s, 2s, 4s — rides out CDN throttling
    return 0


def download_all(manifest: dict[str, list[str]], raw_dir: Path, workers: int) -> dict[str, int]:
    jobs = [(folder, name) for folder, names in manifest.items() for name in names]
    for folder in manifest:
        (raw_dir / folder).mkdir(parents=True, exist_ok=True)

    total = len(jobs)
    state = {"done": 0, "bytes": 0, "failed": 0}
    lock = Lock()
    started = time.time()

    def work(job: tuple[str, str]) -> None:
        folder, name = job
        written = download_one(folder, name, raw_dir / folder)
        with lock:
            state["done"] += 1
            state["bytes"] += written
            if state["done"] % 50 == 0 or state["done"] == total:
                elapsed = time.time() - started
                rate = state["done"] / elapsed if elapsed else 0
                eta = (total - state["done"]) / rate if rate else 0
                print(
                    f"\r  {state['done']:>6,}/{total:,}  "
                    f"{state['bytes'] / 1024**2:>6.0f} MB  "
                    f"{rate:5.1f} files/s  eta {eta / 60:4.1f} min",
                    end="",
                    flush=True,
                )

    print(f"\ndownloading {total:,} files with {workers} workers (already-present are skipped)")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work, job) for job in jobs]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001 — one bad file must not kill the run
                state["failed"] += 1
                print(f"\n  FAILED {exc}")
    print()
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--refresh-manifest", action="store_true")
    args = parser.parse_args()

    raw_dir: Path = args.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / MANIFEST_NAME

    if manifest_path.exists() and not args.refresh_manifest:
        manifest = json.loads(manifest_path.read_text())
        print(f"reusing {manifest_path} ({sum(len(v) for v in manifest.values()):,} files)")
    else:
        manifest = build_manifest()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    state = download_all(manifest, raw_dir, args.workers)

    # Count what is actually on disk rather than what we think we fetched. Case-insensitive
    # and multi-extension on purpose: this dataset is mostly .JPG with a scattering of .jpg
    # and exactly one .jpeg, and a narrower check reports a phantom missing file.
    counts = {
        folder: sum(1 for p in (raw_dir / folder).iterdir() if is_image(p))
        for folder in manifest
    }
    width = max(len(f) for f in counts)
    print(f"\n{'class folder':<{width}}  {'on disk':>8} {'expected':>9}")
    print(f"{'-' * width}  {'-' * 8} {'-' * 9}")
    incomplete = []
    for folder in sorted(counts):
        expected = len(manifest[folder])
        flag = "" if counts[folder] == expected else "  <-- INCOMPLETE"
        if flag:
            incomplete.append(folder)
        print(f"{folder:<{width}}  {counts[folder]:>8,} {expected:>9,}{flag}")
    print(f"{'-' * width}  {'-' * 8} {'-' * 9}")
    print(f"{'TOTAL':<{width}}  {sum(counts.values()):>8,} "
          f"{sum(len(v) for v in manifest.values()):>9,}")

    if incomplete or state["failed"]:
        print(f"\n{state['failed']} download(s) failed. Re-run this script — it resumes.")
        return 1

    print("\nnext: .venv/bin/python ml/data/prepare.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
