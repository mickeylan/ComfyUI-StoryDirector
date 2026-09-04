"""故事导演：一个节点、节点内配置、本地素材副本。"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import PurePosixPath

from .nodes import (NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, asset_type,
                    normalize_filename, mature_catalog, load_last_processed_script)

WEB_DIRECTORY = "./js"
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def _input_root():
    import folder_paths
    root = os.path.realpath(folder_paths.get_input_directory())
    target = os.path.realpath(os.path.join(root, "story_director"))
    os.makedirs(target, exist_ok=True)
    return root, target


def _safe_target(target, filename):
    name = normalize_filename(filename)
    asset_type(name)
    path = os.path.realpath(os.path.join(target, name))
    if os.path.commonpath((os.path.realpath(target), path)) != os.path.realpath(target):
        raise ValueError("非法素材路径")
    return path, name


def _managed_path(relative):
    root, target = _input_root()
    value = str(relative or "").replace("\\", "/")
    parts = PurePosixPath(value).parts
    if parts[:1] != ("story_director",) or ".." in parts:
        raise ValueError("只允许访问托管素材")
    path = os.path.realpath(os.path.join(root, *parts))
    if os.path.commonpath((target, path)) != target or not os.path.isfile(path):
        raise ValueError("素材不存在")
    asset_type(path)
    return path


def _archive_root():
    _, target = _input_root()
    root = os.path.join(target, "archives")
    os.makedirs(root, exist_ok=True)
    return root


def _safe_archive_name(value):
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "archive")).strip("_-") or "archive"
    return name[:80] + ".json"


def _catalog_payload(value):
    """Accept exported mature catalogs and legacy flat-list payloads."""
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict) and "catalog" in value:
        value = value["catalog"]
    return mature_catalog(value or {})


def _register_routes():
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        return

    @PromptServer.instance.routes.get("/story-director/models")
    async def models(_request):
        import folder_paths
        return web.json_response({"models": folder_paths.get_filename_list("LLM")})

    @PromptServer.instance.routes.get("/story-director/last-processed")
    async def last_processed(_request):
        return web.json_response(load_last_processed_script() or {})

    @PromptServer.instance.routes.get("/story-director/archive")
    async def list_archives(_request):
        root = _archive_root()
        names = sorted(name for name in os.listdir(root) if name.endswith(".json"))
        return web.json_response({"archives": names})

    @PromptServer.instance.routes.post("/story-director/archive")
    async def archive(request):
        try:
            data = await request.json()
            catalog = _catalog_payload(data.get("catalog", data) if isinstance(data, dict) else data)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return web.json_response({"error": f"无效素材目录: {exc}"}, status=400)
        filename = _safe_archive_name(data.get("name", "archive") if isinstance(data, dict) else "archive")
        path = os.path.join(_archive_root(), filename)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(catalog, handle, ensure_ascii=False, indent=2)
        return web.json_response({"name": filename, "catalog": catalog})

    @PromptServer.instance.routes.post("/story-director/import")
    async def import_catalog(request):
        try:
            data = await request.json()
            catalog = _catalog_payload(data.get("catalog", data) if isinstance(data, dict) else data)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return web.json_response({"error": f"无效素材目录: {exc}"}, status=400)
        return web.json_response({"catalog": catalog})

    @PromptServer.instance.routes.get("/story-director/export")
    async def export_catalog(request):
        try:
            catalog = _catalog_payload(request.query.get("catalog", "{}"))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return web.json_response({"error": f"无效素材目录: {exc}"}, status=400)
        return web.json_response(catalog, headers={"Content-Disposition": "attachment; filename=story-director-catalog.json"})

    @PromptServer.instance.routes.post("/story-director/upload")
    async def upload(request):
        _, target = _input_root()
        reader = await request.multipart()
        uploaded = []
        async for field in reader:
            if field.name != "file":
                continue
            try:
                path, name = _safe_target(target, field.filename)
            except ValueError as exc:
                return web.json_response({"error": str(exc)}, status=400)
            stem, suffix = os.path.splitext(name)
            number = 1
            while os.path.exists(path):
                path, name = _safe_target(target, f"{stem}_{number}{suffix}")
                number += 1
            partial = f"{path}.{uuid.uuid4().hex}.partial"
            written = 0
            try:
                with open(partial, "wb") as output:
                    while True:
                        chunk = await field.read_chunk(CHUNK_SIZE)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > MAX_UPLOAD_BYTES:
                            raise ValueError("素材超过 512 MiB 限制")
                        output.write(chunk)
                os.replace(partial, path)
            except Exception as exc:
                try:
                    os.remove(partial)
                except OSError:
                    pass
                return web.json_response({"error": str(exc)}, status=413 if written > MAX_UPLOAD_BYTES else 400)
            uploaded.append({"type": asset_type(name), "role": "其他", "name": name,
                             "description": "", "path": f"story_director/{name}", "enabled": True})
        return web.json_response({"assets": uploaded})

    @PromptServer.instance.routes.get("/story-director/archive/{name}")
    async def get_archive(request):
        name = _safe_archive_name(request.match_info.get("name", ""))
        path = os.path.realpath(os.path.join(_archive_root(), name))
        if os.path.commonpath((_archive_root(), path)) != _archive_root() or not os.path.isfile(path):
            return web.json_response({"error": "存档不存在"}, status=404)
        with open(path, "r", encoding="utf-8-sig") as handle:
            return web.json_response(json.load(handle))

    async def preview(request):
        try:
            path = _managed_path(request.query.get("path", ""))
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=404)
        return web.FileResponse(path)

    PromptServer.instance.routes.get("/story-director/preview")(preview)
    PromptServer.instance.routes.get("/story-director/managed-preview")(preview)
    PromptServer.instance.routes.get("/story-director/previews")(preview)

    @PromptServer.instance.routes.post("/story-director/delete")
    async def delete(request):
        try:
            data = await request.json()
            path = _managed_path(data.get("path", ""))
        except (ValueError, TypeError):
            return web.json_response({"error": "非法素材路径"}, status=400)
        removed = False
        if bool(data.get("remove_file")):
            os.remove(path)
            removed = True
        return web.json_response({"ok": True, "managed_file_removed": removed})


_register_routes()
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
