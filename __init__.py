"""故事导演：一个节点、节点内配置、本地素材副本。"""
from __future__ import annotations

import os
import uuid
from pathlib import PurePosixPath

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, asset_type, normalize_filename

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

    @PromptServer.instance.routes.get("/story-director/preview")
    async def preview(request):
        try:
            path = _managed_path(request.query.get("path", ""))
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=404)
        return web.FileResponse(path)

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
