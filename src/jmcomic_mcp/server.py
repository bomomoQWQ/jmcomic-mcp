"""
jmcomic-mcp — MCP server for JM Comic
=======================================
Async-first, clean architecture. Powered by jmcomic's native async client.

Usage:
    uv run jmcomic-mcp              # stdio mode (default)
    uv run jmcomic-mcp --http 8003  # HTTP mode
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from typing import Optional

from mcp.server import FastMCP

# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_DOWNLOAD_DIR = os.path.expanduser("~/downloads")
FILE_SERVER_BASE = os.environ.get("FILE_SERVER_URL", "")
CATEGORY_MAP: dict[str, str] = {}  # populated after jmcomic import

# ── Globals (lazy init) ────────────────────────────────────────────────────

_option: "JmOption | None" = None
_client: "AsyncJmApiClient | None" = None
_downloads: dict[str, dict] = {}  # album_id → {status, progress, path, ...}

# ── Helpers ────────────────────────────────────────────────────────────────

_setup_done = False

async def _ensure_client() -> "AsyncJmApiClient":
    """Lazy-init the async API client. Safe to call multiple times."""
    global _option, _client, _setup_done

    if _client is not None and _setup_done:
        return _client

    import jmcomic
    from jmcomic import JmModuleConfig, JmOption

    JmModuleConfig.FLAG_API_CLIENT_AUTO_UPDATE_DOMAIN = True
    JmModuleConfig.FLAG_DECODE_URL_WHEN_LOGGING = False

    # Load option from op.yml, or create default
    config_path = os.environ.get("JM_OPTION_PATH", "op.yml")
    if os.path.exists(config_path):
        _option = jmcomic.create_option_by_file(config_path)
    else:
        _option = JmOption.default()
        _option.dir_rule.base_dir = DEFAULT_DOWNLOAD_DIR

    # Inject proxy from env
    proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    if proxy:
        _option.client.postman.meta_data.src_dict["proxies"] = {
            "http": proxy, "https": proxy,
        }

    _client = _option.new_jm_async_client()
    await _client.setup()
    _setup_done = True
    return _client

def _get_file_url(path: str) -> str:
    """Convert a local file path to a file-server URL."""
    if not FILE_SERVER_BASE:
        return f"file://{path}"
    rel = os.path.relpath(path, DEFAULT_DOWNLOAD_DIR)
    return f"{FILE_SERVER_BASE.rstrip('/')}/{rel}"

def _j(obj) -> str:
    """JSON dump with ensure_ascii=False."""
    return json.dumps(obj, ensure_ascii=False, default=str)


def _title_of(album) -> str:
    """Extract title string from an album object or dict."""
    if isinstance(album, str):
        return album
    if isinstance(album, dict):
        return album.get("name") or album.get("title") or str(album)
    # JmAlbumDetail or similar — try .title then .name
    for attr in ("title", "name"):
        val = getattr(album, attr, None)
        if val and isinstance(val, str):
            return val
    return str(album)

# ── App ────────────────────────────────────────────────────────────────────

def _build_app() -> FastMCP:
    parser = argparse.ArgumentParser(description="jmcomic-mcp")
    parser.add_argument("--http", type=int, default=0, help="Run in HTTP mode on given port")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--storage", type=str, default="", help="Override download directory")
    args, _ = parser.parse_known_args()

    if args.storage:
        global DEFAULT_DOWNLOAD_DIR
        DEFAULT_DOWNLOAD_DIR = args.storage
        os.environ["JM_DOWNLOAD_DIR"] = args.storage

    extra = {}
    if args.http:
        extra["host"] = args.host
        extra["port"] = args.http

    return FastMCP("jmcomic-mcp", **extra)


app = _build_app()

# ═══════════════════════════════════════════════════════════════════════════
#  TOOLS — Browse & Discover
# ═══════════════════════════════════════════════════════════════════════════

@app.tool()
async def search(
    query: str,
    page: int = 1,
    category: str = "all",
    time: str = "all",
    sort: str = "view",
) -> str:
    """
    Search for comics by keyword.

    Args:
        query: Search keyword.
        page: Page number (1-based).
        category: Category filter. Options: all, doujin, single, short, another,
                  hanman, meiman, doujin_cosplay, 3d, english_site.
        time: Time range. Options: all, today, week, month.
        sort: Sort order. Options: latest, view, picture, like.
    """
    from jmcomic import JmMagicConstants

    cat_map = {
        "all": JmMagicConstants.CATEGORY_ALL,
        "doujin": JmMagicConstants.CATEGORY_DOUJIN,
        "single": JmMagicConstants.CATEGORY_SINGLE,
        "short": JmMagicConstants.CATEGORY_SHORT,
        "another": JmMagicConstants.CATEGORY_ANOTHER,
        "hanman": JmMagicConstants.CATEGORY_HANMAN,
        "meiman": JmMagicConstants.CATEGORY_MEIMAN,
        "doujin_cosplay": JmMagicConstants.CATEGORY_DOUJIN_COSPLAY,
        "3d": JmMagicConstants.CATEGORY_3D,
        "english_site": JmMagicConstants.CATEGORY_ENGLISH_SITE,
    }
    time_map = {
        "all": JmMagicConstants.TIME_ALL, "today": JmMagicConstants.TIME_TODAY,
        "week": JmMagicConstants.TIME_WEEK, "month": JmMagicConstants.TIME_MONTH,
    }
    sort_map = {
        "latest": JmMagicConstants.ORDER_BY_LATEST, "view": JmMagicConstants.ORDER_BY_VIEW,
        "picture": JmMagicConstants.ORDER_BY_PICTURE, "like": JmMagicConstants.ORDER_BY_LIKE,
    }

    try:
        c = await _ensure_client()
        page_data = await c.search(
            search_query=query, page=page, main_tag=0,
            order_by=sort_map.get(sort, JmMagicConstants.ORDER_BY_VIEW),
            time=time_map.get(time, JmMagicConstants.TIME_ALL),
            category=cat_map.get(category, JmMagicConstants.CATEGORY_ALL),
            sub_category=None,
        )
        items = [{"id": aid, "title": _title_of(title)} for aid, title in page_data[:20]]
        return _j({"query": query, "page": page, "total": len(items), "results": items})
    except Exception as e:
        return _j({"error": str(e)})


@app.tool()
async def album_detail(album_id: str) -> str:
    """Get detailed info for an album: title, author, tags, page count, chapters."""
    try:
        c = await _ensure_client()
        album = await c.get_album_detail(album_id)
        chapters = []
        try:
            for p in album:
                if len(chapters) >= 50:
                    break
                chapters.append({"id": p.photo_id, "title": p.title, "index": p.index})
        except Exception:
            pass  # some albums have iteration quirks
        return _j({
            "id": album.album_id,
            "title": album.title,
            "author": getattr(album, "author", ""),
            "tags": getattr(album, "tags", []),
            "page_count": getattr(album, "page_count", 0),
            "chapters": chapters,
        })
    except Exception as e:
        return _j({"error": str(e)})



@app.tool()
async def ranking(period: str = "week") -> str:
    """Get comic ranking. period: week, month, or total."""
    from jmcomic import JmMagicConstants

    try:
        c = await _ensure_client()
        if period == "week":
            page = await c.categories_filter(
                page=1, time=JmMagicConstants.TIME_WEEK,
                category=JmMagicConstants.CATEGORY_ALL,
                order_by=JmMagicConstants.ORDER_BY_VIEW,
            )
        elif period == "month":
            page = await c.categories_filter(
                page=1, time=JmMagicConstants.TIME_MONTH,
                category=JmMagicConstants.CATEGORY_ALL,
                order_by=JmMagicConstants.ORDER_BY_VIEW,
            )
        else:
            page = await c.categories_filter(
                page=1, time=JmMagicConstants.TIME_ALL,
                category=JmMagicConstants.CATEGORY_ALL,
                order_by=JmMagicConstants.ORDER_BY_VIEW,
            )
        items = [{"id": aid, "title": _title_of(title)} for aid, title in page[:20]]
        return _j({"period": period, "results": items})
    except Exception as e:
        return _j({"error": str(e)})


@app.tool()
async def browse(
    category: str = "all",
    time: str = "all",
    sort: str = "view",
    page: int = 1,
) -> str:
    """Browse comics by category without a search keyword. Like search but without query."""
    from jmcomic import JmMagicConstants

    cat_map = {
        "all": JmMagicConstants.CATEGORY_ALL,
        "doujin": JmMagicConstants.CATEGORY_DOUJIN,
        "single": JmMagicConstants.CATEGORY_SINGLE,
        "short": JmMagicConstants.CATEGORY_SHORT,
        "3d": JmMagicConstants.CATEGORY_3D,
    }
    time_map = {
        "all": JmMagicConstants.TIME_ALL, "today": JmMagicConstants.TIME_TODAY,
        "week": JmMagicConstants.TIME_WEEK, "month": JmMagicConstants.TIME_MONTH,
    }
    sort_map = {
        "latest": JmMagicConstants.ORDER_BY_LATEST, "view": JmMagicConstants.ORDER_BY_VIEW,
        "picture": JmMagicConstants.ORDER_BY_PICTURE, "like": JmMagicConstants.ORDER_BY_LIKE,
    }

    try:
        c = await _ensure_client()
        page_data = await c.categories_filter(
            page=page,
            time=time_map.get(time, JmMagicConstants.TIME_ALL),
            category=cat_map.get(category, JmMagicConstants.CATEGORY_ALL),
            order_by=sort_map.get(sort, JmMagicConstants.ORDER_BY_VIEW),
        )
        items = [{"id": aid, "title": _title_of(title)} for aid, title in page_data[:20]]
        return _j({"category": category, "time": time, "sort": sort, "results": items})
    except Exception as e:
        return _j({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
#  TOOLS — Download & Manage
# ═══════════════════════════════════════════════════════════════════════════

_download_sem = asyncio.Semaphore(1)

@app.tool()
async def download(album_id: str) -> str:
    """
    Download an entire album. Runs in background, returns immediately.
    Only 1 download at a time (others queue). Use download_status() to check progress.
    """
    if album_id in _downloads and _downloads[album_id].get("status") in ("downloading", "queued"):
        return _j({"status": "already_queued", "album_id": album_id})

    _downloads[album_id] = {"status": "queued", "progress": 0, "path": "", "error": ""}

    async def _do():
        async with _download_sem:
            try:
                _downloads[album_id]["status"] = "downloading"
                import jmcomic
                opt = _option
                if opt is None:
                    from jmcomic import JmOption
                    opt = JmOption.default()
                    opt.dir_rule.base_dir = DEFAULT_DOWNLOAD_DIR

                # Limit download threads for weak CPU
                opt.download.threading.image = 2
                opt.download.threading.photo = 1

                _downloads[album_id]["progress"] = 10

                # Get album info
                c = await _ensure_client()
                album = await c.get_album_detail(album_id)
                title = album.title
                total_pages = getattr(album, 'page_count', 0) or 0

                _downloads[album_id].update({
                    "progress": 15, "title": title,
                    "total_pages": total_pages, "downloaded_pages": 0,
                })

                start_time = time.time()
                base = opt.dir_rule.base_dir or DEFAULT_DOWNLOAD_DIR
                # Find the download directory — use the newest one matching any part of the title or album_id
                def _find_dir():
                    best = None
                    best_time = 0
                    for d in os.listdir(base):
                        dp = os.path.join(base, d)
                        if os.path.isdir(dp):
                            # Match by album_id first, then by title substring
                            if album_id in d or (title and any(t in d for t in title[:20].split(' '))):
                                mt = os.path.getmtime(dp)
                                if mt > best_time:
                                    best = dp
                                    best_time = mt
                    # Fallback: just the newest directory
                    if not best:
                        for d in os.listdir(base):
                            dp = os.path.join(base, d)
                            if os.path.isdir(dp):
                                mt = os.path.getmtime(dp)
                                if mt > best_time:
                                    best = dp
                                    best_time = mt
                    return best

                polling = True

                async def _track():
                    while polling:
                        await asyncio.sleep(1)
                        if not polling:
                            break
                        elapsed = time.time() - start_time
                        dp = _find_dir()
                        count = 0
                        if dp:
                            count = sum(1 for r, _, fs in os.walk(dp) for f in fs if os.path.isfile(os.path.join(r, f)))
                        if count > 0:
                            pct = 15 + int(70 * count / total_pages) if total_pages > 0 else 15 + min(count, 50)
                            eta = (elapsed / count * (total_pages - count)) if total_pages > 0 and count > 0 else 0
                            _downloads[album_id].update({
                                "progress": min(pct, 90),
                                "downloaded_pages": count,
                                "elapsed_sec": round(elapsed, 1),
                                "eta_sec": round(eta, 1),
                            })

                track_task = asyncio.create_task(_track())

                # Download using sync API in thread
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda: jmcomic.download_album(album_id, opt))

                polling = False
                try: await track_task
                except: pass

                elapsed = time.time() - start_time
                _downloads[album_id].update({
                    "progress": 90, "elapsed_sec": round(elapsed, 1),
                    "downloaded_pages": total_pages,
                })

                # Convert to PDF using PIL (img2pdf can't handle webp)
                try:
                    from PIL import Image
                    base = opt.dir_rule.base_dir or DEFAULT_DOWNLOAD_DIR
                    dp = _find_dir()
                    if dp and os.path.isdir(dp):
                        pdf_path = os.path.join(base, os.path.basename(dp) + '.pdf')
                        pdf_ok = os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0
                        if not pdf_ok:
                            images = []
                            for r, _, fs in os.walk(dp):
                                for f in fs:
                                    if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp')):
                                        images.append(os.path.join(r, f))
                            images.sort(key=lambda x: int(''.join(c for c in os.path.splitext(os.path.basename(x))[0] if c.isdigit()) or 0))
                            if images:
                                imgs = [Image.open(p).convert('RGB') for p in images]
                                imgs[0].save(pdf_path, save_all=True, append_images=imgs[1:])
                                for img in imgs: img.close()
                                _downloads[album_id]["pdf"] = pdf_path
                except ImportError:
                    pass
                except Exception as e:
                    _downloads[album_id]["pdf_error"] = str(e)

                _downloads[album_id]["progress"] = 95

                base = opt.dir_rule.base_dir or DEFAULT_DOWNLOAD_DIR
                dp = _find_dir()
                pdf_path = os.path.join(base, os.path.basename(dp) + '.pdf') if dp else ""

                if pdf_path and os.path.exists(pdf_path):
                    _downloads[album_id].update({
                        "status": "done", "progress": 100,
                        "path": pdf_path, "size_mb": round(os.path.getsize(pdf_path) / 1048576, 1),
                    })
                elif dp and os.path.isdir(dp):
                    count = sum(1 for r, _, fs in os.walk(dp) for f in fs if os.path.isfile(os.path.join(r, f)))
                    _downloads[album_id].update({
                        "status": "done", "progress": 100,
                        "path": dp, "file_count": count,
                    })
                else:
                    _downloads[album_id]["status"] = "done"
                    _downloads[album_id]["progress"] = 100

            except Exception as e:
                _downloads[album_id].update({"status": "failed", "error": str(e)})

    asyncio.create_task(_do())
    return _j({"status": "queued", "album_id": album_id, "message": "Download started in background"})


@app.tool()
async def download_status(album_id: str) -> str:
    """Check download progress for an album."""
    info = _downloads.get(album_id)
    if not info:
        return _j({"error": f"No download record for {album_id}"})
    return _j(info)


@app.tool()
async def download_list() -> str:
    """List all downloads (active + completed + failed)."""
    return _j({"downloads": _downloads})


@app.tool()
async def cleanup(album_id: str, keep_pdf: bool = True) -> str:
    """
    Clean up downloaded files for an album.
    Args:
        album_id: The album ID.
        keep_pdf: If True, delete raw images but keep the PDF. If False, delete everything.
    """
    info = _downloads.get(album_id)
    path = info.get("path", "") if info else ""

    if not path:
        base = _option.dir_rule.base_dir if _option else DEFAULT_DOWNLOAD_DIR
        # Search by album_id, then by filename substring
        for entry in os.listdir(base):
            if album_id in entry or album_id in os.path.splitext(entry)[0]:
                path = os.path.join(base, entry)
                break
        # If still not found, try searching by filename from files_list
        if not os.path.exists(path) if path else True:
            path = ""

    if not path or not os.path.exists(path):
        return _j({"error": f"No files found for {album_id}", "searched": str(base) if path else "?"})

    freed = 0
    if os.path.isdir(path):
        # It's an image folder
        size = sum(
            os.path.getsize(os.path.join(dirpath, f))
            for dirpath, _, files in os.walk(path) for f in files
        )
        freed += size
        if keep_pdf:
            shutil.rmtree(path)
            msg = f"Deleted image folder ({size / 1048576:.1f} MB freed), PDF kept"
        else:
            shutil.rmtree(path)
            msg = f"Deleted folder ({size / 1048576:.1f} MB freed)"
    elif os.path.isfile(path) and path.endswith(".pdf"):
        size = os.path.getsize(path)
        freed += size
        # Also check for matching image folder
        folder = os.path.splitext(path)[0]
        if os.path.isdir(folder):
            fsize = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(folder) for f in fs)
            freed += fsize
            shutil.rmtree(folder)
        if not keep_pdf:
            os.remove(path)
            msg = f"Deleted PDF + images ({freed / 1048576:.1f} MB freed)"
        else:
            msg = f"Deleted images ({freed / 1048576:.1f} MB freed), PDF kept"

    if info:
        info["status"] = "cleaned"
    return _j({"status": "ok", "message": msg, "freed_mb": round(freed / 1048576, 1)})


# ═══════════════════════════════════════════════════════════════════════════
#  TOOLS — File Delivery
# ═══════════════════════════════════════════════════════════════════════════

@app.tool()
async def files_list() -> str:
    """List all downloaded PDFs with short-name download URLs."""
    base = _option.dir_rule.base_dir if _option else DEFAULT_DOWNLOAD_DIR
    if not os.path.exists(base):
        return _j({"base_dir": base, "files": []})

    fs_url = os.environ.get("FILE_SERVER_URL", "http://192.168.1.10:8888")
    files = []
    entries = sorted(
        [e for e in os.listdir(base) if os.path.isfile(os.path.join(base, e)) and e.lower().endswith(('.pdf','.zip','.cbz'))],
        key=lambda x: os.path.getmtime(os.path.join(base, x)), reverse=True
    )
    for i, entry in enumerate(entries, 1):
        full = os.path.join(base, entry)
        ext = os.path.splitext(entry)[1].lower()
        files.append({
            "name": entry,
            "short": f"f_{i:03d}{ext}",
            "size_mb": round(os.path.getsize(full) / 1048576, 1),
            "url": f"{fs_url.rstrip('/')}/f_{i:03d}{ext}",
        })
    return _j({"base_dir": base, "files": files})


@app.tool()
async def file_url(album_id: str) -> str:
    """Get the short-name download URL for a completed album by its ID."""
    fs_url = os.environ.get("FILE_SERVER_URL", "http://192.168.1.10:8888")
    base = _option.dir_rule.base_dir if _option else DEFAULT_DOWNLOAD_DIR
    entries = sorted(
        [e for e in os.listdir(base) if os.path.isfile(os.path.join(base, e)) and e.lower().endswith(('.pdf','.zip','.cbz'))],
        key=lambda x: os.path.getmtime(os.path.join(base, x)), reverse=True
    )
    for i, entry in enumerate(entries, 1):
        if album_id in entry or album_id in os.path.splitext(entry)[0]:
            ext = os.path.splitext(entry)[1].lower()
            full = os.path.join(base, entry)
            return _j({
                "album_id": album_id, "name": entry,
                "short": f"f_{i:03d}{ext}",
                "url": f"{fs_url.rstrip('/')}/f_{i:03d}{ext}",
                "size_mb": round(os.path.getsize(full) / 1048576, 1),
            })
    return _j({"error": f"No file found for {album_id}"})


# ═══════════════════════════════════════════════════════════════════════════
#  Entry Point
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """CLI entry point."""
    import sys
    if "--http" in sys.argv:
        app.run(transport="streamable-http")
    else:
        app.run(transport="stdio")


if __name__ == "__main__":
    main()
