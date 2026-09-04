"""StoryDirector: extracted H3 story planning console.

This node deliberately stops at the planning boundary.  It preserves the H3
script contract (SHOT_START blocks, six-part H3 prompts and schedule sections)
and returns the complete script plus a portable asset catalog.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import PurePosixPath

from .llama_backend import LLAMA
from .presets.script import STORY_STYLES, SEGMENT_COUNT_OPTIONS, build_shot_prompt, _resolve_segment_count

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".webm", ".mkv", ".avi"})
AUDIO_EXTENSIONS = frozenset({".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac", ".wma", ".opus"})
ASSET_ROLES = ("角色", "场景", "道具", "分镜", "音效", "音乐", "其他")


def _last_processed_file():
    try:
        import folder_paths
        root = folder_paths.get_output_directory()
    except Exception:
        root = os.path.join(os.path.dirname(__file__), "output")
    root = os.path.join(root, "story_director")
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, "last_processed.json")


def _save_last_processed_script(script, state):
    try:
        with open(_last_processed_file(), "w", encoding="utf-8") as handle:
            json.dump({"script": script, "catalog": mature_catalog(state.get("assets", []))},
                      handle, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_last_processed_script():
    try:
        with open(_last_processed_file(), "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) and isinstance(data.get("script"), str) else None
    except (OSError, ValueError):
        return None


def normalize_filename(value: str) -> str:
    name = os.path.basename(str(value or "")).replace("\x00", "")
    stem, suffix = os.path.splitext(name)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_-") or "asset"
    suffix = re.sub(r"[^A-Za-z0-9.]", "", suffix).lower()
    return f"{stem[:160]}{suffix[:20]}"


def asset_type(filename: str) -> str:
    suffix = os.path.splitext(normalize_filename(filename))[1].lower()
    for kind, extensions in (("image", IMAGE_EXTENSIONS), ("video", VIDEO_EXTENSIONS), ("audio", AUDIO_EXTENSIONS)):
        if suffix in extensions:
            return kind
    raise ValueError(f"不支持的素材扩展名：{suffix or '无'}")


def _safe_relative(path: str) -> str:
    parts = PurePosixPath(str(path or "").replace("\\", "/").lstrip("/")).parts
    if not parts or parts[0] != "story_director" or ".." in parts or any(p in ("", ".") for p in parts):
        raise ValueError("素材路径必须位于 input/story_director")
    return "/".join(parts)


def normalize_assets(value) -> list[dict]:
    """Normalize the mature catalog shape and the node's legacy flat-list shape.

    The original asset manager stores ``images``, ``videos`` and ``audios``;
    older StoryDirector workflows stored one ``assets`` list.  Keep both on
    input, but use one validated internal representation for prompt building.
    """
    data = json.loads(value) if isinstance(value, str) and value.strip() else value
    if isinstance(data, dict):
        if isinstance(data.get("assets"), list):
            data = data["assets"]
        else:
            source = data
            data = []
            for kind, key in (("image", "images"), ("video", "videos"), ("audio", "audios")):
                for item in (source.get(key) or []):
                    if isinstance(item, dict):
                        copied = dict(item)
                        copied.setdefault("role", copied.get("type", "其他"))
                        copied["type"] = kind
                        data.append(copied)
    if not isinstance(data, list):
        return []
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            path = _safe_relative(item.get("path", ""))
            kind = str(item.get("type") or asset_type(path))
            if kind not in {"image", "video", "audio"}:
                continue
        except (TypeError, ValueError):
            continue
        entry = dict(item)
        entry.update({"type": kind, "role": item.get("role") if item.get("role") in ASSET_ROLES else "其他",
                      "name": str(item.get("name") or os.path.basename(path))[:180],
                      "description": str(item.get("description", ""))[:2000], "path": path,
                      "enabled": bool(item.get("enabled", True)), "order": len(result)})
        result.append(entry)
    return result


def mature_catalog(assets) -> dict:
    """Return the source asset-manager schema without tensor/media payloads."""
    catalog = {"images": [], "videos": [], "audios": []}
    for item in normalize_assets(assets):
        kind = item["type"]
        key = {"image": "images", "video": "videos", "audio": "audios"}[kind]
        clean = dict(item)
        clean.pop("order", None)
        # In the source manager ``type`` is the semantic dropdown for each
        # bucket (the bucket itself carries image/video/audio kind).
        clean["type"] = clean.get("role", "其他")
        clean.setdefault("letter", "")
        catalog[key].append(clean)
    return catalog


def _state(value) -> dict:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError) as exc:
        raise ValueError("节点设置必须是 JSON 对象") from exc
    if not isinstance(parsed, dict):
        raise ValueError("节点设置必须是 JSON 对象")
    parsed = dict(parsed)
    parsed["assets"] = normalize_assets(parsed.get("assets", []))
    return parsed


def _material_intro(assets):
    lines = []
    counters = {"image": 0, "video": 0, "audio": 0}
    labels = {"image": "图片", "video": "视频", "audio": "音频"}
    for asset in assets:
        if not asset.get("enabled", True):
            continue
        kind = asset["type"]
        counters[kind] += 1
        slot = f"{labels[kind]}{counters[kind]}"
        lines.append(f"{asset.get('role', '其他')}{slot[-1]} = {asset['name']}（{asset['description']}）")
    return "\n".join(lines)


def compile_fallback(story: str, state: dict) -> str:
    """Offline preview retaining the real H3 six-part/block contract."""
    count = _resolve_segment_count(state.get("segment_count", 4))
    parts = [p.strip() for p in re.split(r"\n+|(?<=[。.!！？?])\s*", story or "") if p.strip()]
    parts = (parts or ["故事中的关键情节"]) + [parts[-1] if parts else "故事中的关键情节"] * count
    preference = state.get("preference", "")
    blocks = []
    for index, part in enumerate(parts[:count], 1):
        h3 = (f"subject_definitions: {part}\nsummary: {part}\nretention_analysis: 保持主体与空间连续\n"
              f"detailed_description: {part}，动作连续可拍摄。\noverall_soundscape: 环境声与动作声\n"
              f"non_diegetic_music: N/A\n{preference}").strip()
        blocks.append(f"[SHOT_START]\n===H3_PROMPT===\n{h3}\n===SCENE_INSTRUCTION===\n{{\"slots\": []}}\n"
                      f"===VIDEO_INSTRUCTION===\n{{\"slots\": []}}\n===AUDIO_INSTRUCTION===\n{{\"slots\": []}}\n[SHOT_END]")
    return "\n\n".join(blocks)


def validate_script(script: str, expected_count: int | None = None) -> str:
    text = str(script or "").strip()
    shots = re.findall(r"\[SHOT_START\](.*?)\[SHOT_END\]", text, re.DOTALL)
    if not text or not shots or "===H3_PROMPT===" not in text:
        raise ValueError("必须输出完整 H3 剧本块（[SHOT_START]...[SHOT_END]）")
    if expected_count is not None and len(shots) != int(expected_count):
        raise ValueError(f"分段数量应为 {expected_count}，实际为 {len(shots)}")
    if any("===H3_PROMPT===" not in shot for shot in shots):
        raise ValueError("每个分段都必须包含 ===H3_PROMPT===")
    return text


class StoryDirector:
    @classmethod
    def INPUT_TYPES(cls):
        try:
            import folder_paths
            models = folder_paths.get_filename_list("LLM")
            models = [name for name in models if name.lower().endswith(".gguf")] or ["未选择本地 GGUF"]
        except (ImportError, KeyError):
            models = ["未选择本地 GGUF"]
        return {"required": {
            "story": ("STRING", {"default": "", "multiline": True}),
            "prompt_override": ("STRING", {"default": "", "multiline": True}),
            "mode": (["拆解模式 (Decompose)", "生成模式 (Generate)", "离线预览"],),
            "story_style": (list(STORY_STYLES),),
            "segment_count": (list(SEGMENT_COUNT_OPTIONS),),
            "segment_duration": ("INT", {"default": 8, "min": 4, "max": 15}),
            "prompt_lang": (["中文 [ZH]", "英文 [EN]"],),
            "preference": ("STRING", {"default": "", "multiline": True}),
            "llm_model": (models,),
            "context_size": ("INT", {"default": 32768, "min": 1024, "max": 262144, "step": 128}),
            "gpu_layers": ("INT", {"default": -1, "min": -1, "max": 999}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 9223372036854775807}),
        }, "hidden": {"director_state": ("STRING", {"default": '{"assets": []}', "multiline": True})}}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("H3完整剧本", "素材目录 JSON")
    FUNCTION = "direct"
    CATEGORY = "StoryDirector"

    def direct(self, story, prompt_override, mode, story_style, segment_count, segment_duration, prompt_lang,
               preference, llm_model, context_size, gpu_layers, seed, director_state):
        state = _state(director_state)
        state.update({"segment_count": segment_count, "segment_duration": segment_duration, "preference": preference})
        count = _resolve_segment_count(segment_count)
        catalog = json.dumps(mature_catalog(state["assets"]), ensure_ascii=False, indent=2)
        if str(prompt_override or "").strip():
            script = validate_script(prompt_override, count)
            _save_last_processed_script(script, state)
            return script, catalog
        if mode == "离线预览":
            script = validate_script(compile_fallback(story, state), count)
            _save_last_processed_script(script, state)
            return script, catalog
        if not llm_model or llm_model.startswith("未选择"):
            raise ValueError("拆解/生成模式必须选择 models/LLM 中的 GGUF")
        system = build_shot_prompt(story, mode=mode, story_style=story_style, segment_count_label=segment_count,
                                   lang="zh" if "ZH" in prompt_lang else "en", segment_duration=segment_duration,
                                   ref_image_intro=_material_intro(state["assets"]), preference=preference)
        user = f"请严格输出恰好 {count} 个 [SHOT_START]...[SHOT_END] 完整 H3 分段，不要解释。"
        result = LLAMA.complete({"model": llm_model, "n_ctx": context_size, "n_gpu_layers": gpu_layers},
                                system, user, seed=seed, max_tokens=8192, temperature=0.6)
        script = validate_script(result, count)
        _save_last_processed_script(script, state)
        return script, catalog


NODE_CLASS_MAPPINGS = {"StoryDirector": StoryDirector}
NODE_DISPLAY_NAME_MAPPINGS = {"StoryDirector": "StoryDirector 故事导演"}
