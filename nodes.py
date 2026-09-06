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

import numpy as np
import torch
from PIL import Image, ImageOps

from .llama_backend import LLAMA
from .presets.script import SEGMENT_COUNT_OPTIONS, build_director_prompt, _resolve_segment_count
from .sheding.story_styles import STORY_STYLES

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".webm", ".mkv", ".avi"})
AUDIO_EXTENSIONS = frozenset({".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac", ".wma", ".opus"})
ASSET_ROLES = ("角色", "场景", "道具", "分镜", "主体", "运镜", "特效", "音色", "音效", "配乐", "念白", "音乐", "其他")


def _last_processed_file():
    try:
        import folder_paths
        root = folder_paths.get_output_directory()
    except Exception:
        root = os.path.join(os.path.dirname(__file__), "output")
    root = os.path.join(root, "story_director")
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, "last_processed.json")


def _save_last_processed_script(global_prompt, timeline_data, state):
    try:
        with open(_last_processed_file(), "w", encoding="utf-8") as handle:
            json.dump({"global_prompt": global_prompt, "timeline_data": timeline_data,
                       "catalog": mature_catalog(state.get("assets", []))},
                      handle, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_last_processed_script():
    try:
        with open(_last_processed_file(), "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) and isinstance(data.get("global_prompt"), str) and isinstance(data.get("timeline_data"), str) else None
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
                        if copied.get("type"):
                            copied.setdefault("role", copied["type"])
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
        default_role = "角色" if kind == "image" else "主体" if kind == "video" else "音色"
        reference_name = str(item.get("reference_name") or item.get("name") or os.path.splitext(os.path.basename(path))[0])[:180].strip()
        entry.update({"type": kind, "role": item.get("role") if item.get("role") in ASSET_ROLES else default_role,
                      "reference_name": reference_name, "name": reference_name,
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


def load_reference_images(assets):
    import folder_paths

    input_root = folder_paths.get_input_directory()
    paths = [os.path.join(input_root, _safe_relative(asset["path"]).replace("/", os.sep))
             for asset in assets if asset.get("enabled", True) and asset["type"] == "image"]
    if not paths:
        return torch.empty((0, 1, 1, 3), dtype=torch.float32)

    with Image.open(paths[0]) as first:
        first = ImageOps.exif_transpose(first)
        width, height = first.size
    scale = min(1.0, 1920 / width, 1080 / height)
    target = (max(1, round(width * scale)), max(1, round(height * scale)))
    images = []
    for path in paths:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            if image.size != target:
                image = ImageOps.pad(image, target, method=Image.Resampling.LANCZOS, color=(0, 0, 0))
            images.append(torch.from_numpy(np.asarray(image, dtype=np.float32).copy()).div_(255.0))
    return torch.stack(images)


def _material_intros(assets):
    intros = {"image": [], "video": [], "audio": []}
    counters = {"image": 0, "video": 0, "audio": 0}
    slot_types = {"image": {"角色", "场景", "道具", "分镜"}, "video": {"视频"}, "audio": {"音频"}}
    for asset in assets:
        if not asset.get("enabled", True):
            continue
        kind = asset["type"]
        counters[kind] += 1
        role = asset.get("role", "其他")
        slot_type = role if role in slot_types[kind] else ("视频" if kind == "video" else "音频" if kind == "audio" else "其他")
        slot = f"{slot_type}{chr(64 + counters[kind])}"
        description = asset.get("description", "").strip()
        name = asset.get("reference_name") or asset["name"]
        intros[kind].append(f"{slot} = {name}{f'（{description}）' if description else ''}")
    return tuple("\n".join(intros[kind]) for kind in ("image", "video", "audio"))


def _extract_json_object(value):
    text = re.sub(r"(?is)<think>.*?</think>", "", str(value or "")).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Qwen3.5 没有返回 Director JSON")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Qwen3.5 返回的 Director JSON 无效：{exc}") from exc


def validate_director_plan(value, expected_count=None):
    data = _extract_json_object(value) if isinstance(value, str) else value
    if not isinstance(data, dict):
        raise ValueError("Director 结果必须是 JSON 对象")
    global_prompt = str(data.get("global_prompt") or "").strip()
    soundscape = str(data.get("overall_soundscape") or "").strip()
    music = str(data.get("non_diegetic_music") or "N/A").strip() or "N/A"
    segments = data.get("segments")
    if not global_prompt:
        raise ValueError("Director 结果缺少 global_prompt")
    if not soundscape:
        raise ValueError("Director 结果缺少 overall_soundscape")
    if not isinstance(segments, list) or not segments:
        raise ValueError("Director 结果缺少 segments")
    prompts = []
    for index, segment in enumerate(segments, 1):
        prompt = str(segment.get("prompt") if isinstance(segment, dict) else "").strip()
        if not prompt:
            raise ValueError(f"第 {index} 个分镜缺少 prompt")
        if re.search(r"(?im)^\s*(?:subject_definitions|retention_analysis|overall_soundscape|non_diegetic_music|detailed_description)\s*:", prompt):
            raise ValueError(f"第 {index} 个分镜重复了全局字段")
        prompts.append(prompt)
    if expected_count is not None and len(prompts) != int(expected_count):
        raise ValueError(f"分镜数量应为 {expected_count}，实际为 {len(prompts)}")
    return {"global_prompt": global_prompt, "overall_soundscape": soundscape,
            "non_diegetic_music": music, "segments": [{"prompt": prompt} for prompt in prompts]}


def apply_reference_contract(plan, assets):
    images = [asset for asset in assets if asset.get("enabled", True) and asset["type"] == "image"]
    definitions, retention = [], []
    for index, asset in enumerate(images, 1):
        name = asset.get("reference_name") or asset.get("name") or f"Picture {index}"
        description = str(asset.get("description") or "").strip()
        definitions.append(f"<Subject {index}> is {name} shown in <Picture {index}>" + (f" ({description})." if description else "."))
        retention.append(f"<Picture {index}> must preserve <Subject {index}>'s identity and visible appearance across every shot.")
    global_prompt = plan["global_prompt"].strip()
    if definitions and not re.search(r"(?im)^\s*subject_definitions\s*:", global_prompt):
        global_prompt = "subject_definitions:\n" + "\n".join(definitions) + "\n\n" + global_prompt
    if retention and not re.search(r"(?im)^\s*retention_analysis\s*:", global_prompt):
        global_prompt += "\n\nretention_analysis:\n" + "\n".join(retention)
    return {**plan, "global_prompt": global_prompt}


def build_timeline_data(plan, segment_duration, fps=24):
    length = max(1, int(round(float(segment_duration) * fps)))
    segments = [{"id": f"story-director-{index + 1}", "start": index * length,
                 "length": length, "prompt": item["prompt"], "type": "text", "isEndFrame": False}
                for index, item in enumerate(plan["segments"])]
    total_frames = len(segments) * length
    return {"mainTrackEnabled": True, "audioTrackEnabled": True, "motionTrackEnabled": True,
            "reference_mode": "REF2VA", "prompt_format": "minimax", "frame_rate": fps,
            "normalStartFrame": 0, "normalDurationFrames": total_frames,
            "global_prompt": plan["global_prompt"], "overall_soundscape": plan["overall_soundscape"],
            "non_diegetic_music": plan["non_diegetic_music"], "segments": segments,
            "motionSegments": [], "audioSegments": []}


def compile_fallback(story, state):
    count = _resolve_segment_count(state.get("segment_count", 4))
    parts = [part.strip() for part in re.split(r"\n+|(?<=[。.!！？?])\s*", story or "") if part.strip()]
    parts = (parts or ["故事中的关键情节"]) + [parts[-1] if parts else "故事中的关键情节"] * count
    return {"global_prompt": "保持整体视觉风格、角色身份、服饰与场景连续一致。",
            "overall_soundscape": "环境声与动作声随画面连续变化。", "non_diegetic_music": "N/A",
            "segments": [{"prompt": part} for part in parts[:count]]}


class StoryDirector:
    @classmethod
    def INPUT_TYPES(cls):
        try:
            import folder_paths
            files = [name for name in folder_paths.get_filename_list("LLM") if name.lower().endswith(".gguf")]
            supported = [name for name in files if any(marker in name.lower() for marker in ("qwen3.5", "qwen35", "qwen3.8", "qwen38"))]
            models = [name for name in supported if "mmproj" not in os.path.basename(name).lower()] or ["未选择 Qwen GGUF"]
            mmproj_models = [name for name in supported if "mmproj" in os.path.basename(name).lower()] or ["未选择 Qwen mmproj"]
        except (ImportError, KeyError):
            models = ["未选择 Qwen GGUF"]
            mmproj_models = ["未选择 Qwen mmproj"]
        return {"required": {
            "story": ("STRING", {"default": "", "multiline": True}),
            "prompt_override": ("STRING", {"default": "", "multiline": True}),
            "mode": (["拆解模式 (Decompose)", "生成模式 (Generate)", "离线预览"],),
            "story_style": (list(STORY_STYLES),),
            "segment_count": (list(SEGMENT_COUNT_OPTIONS),),
            "segment_duration": ("INT", {"default": 8, "min": 4, "max": 15}),
            "prompt_lang": (["中文 [ZH]", "英文 [EN]"],),
            "preference": ("STRING", {"default": "", "multiline": True}),
            "custom_rules": ("STRING", {"default": "", "multiline": True}),
            "enhance": ("BOOLEAN", {"default": False}),
            "llm_model": (models,),
            "context_size": ("INT", {"default": 32768, "min": 1024, "max": 262144, "step": 128}),
            "gpu_layers": ("INT", {"default": -1, "min": -1, "max": 999}),
            "max_tokens": ("INT", {"default": 8192, "min": 256, "max": 262144, "step": 256}),
            "temperature": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 2.0, "step": 0.01}),
            "top_k": ("INT", {"default": 40, "min": 0, "max": 1000}),
            "top_p": ("FLOAT", {"default": 0.9, "min": 0.0, "max": 1.0, "step": 0.01}),
            "min_p": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.01}),
            "repeat_penalty": ("FLOAT", {"default": 1.05, "min": 0.0, "max": 10.0, "step": 0.01}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 9223372036854775807}),
            "director_state": ("STRING", {"default": '{"assets": []}', "multiline": True}),
            "llm_mmproj": (mmproj_models,),
        }}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "IMAGE")
    RETURN_NAMES = ("总提示词", "MiniMaxH3 Director 时间线 JSON", "素材目录 JSON", "参考图片")
    FUNCTION = "direct"
    CATEGORY = "StoryDirector"
    OUTPUT_NODE = True

    def direct(self, story, prompt_override, mode, story_style, segment_count, segment_duration, prompt_lang,
               preference, custom_rules, enhance, llm_model, llm_mmproj, context_size, gpu_layers, max_tokens,
               temperature, top_k, top_p, min_p, repeat_penalty, seed, director_state):
        state = _state(director_state)
        state.update({"segment_count": segment_count, "segment_duration": segment_duration, "preference": preference})
        count = _resolve_segment_count(segment_count)
        catalog = json.dumps(mature_catalog(state["assets"]), ensure_ascii=False, indent=2)
        reference_images = load_reference_images(state["assets"])
        if str(prompt_override or "").strip():
            plan = apply_reference_contract(validate_director_plan(prompt_override, count), state["assets"])
            timeline_data = json.dumps(build_timeline_data(plan, segment_duration), ensure_ascii=False, indent=2)
            _save_last_processed_script(plan["global_prompt"], timeline_data, state)
            return plan["global_prompt"], timeline_data, catalog, reference_images
        if mode == "离线预览":
            plan = apply_reference_contract(validate_director_plan(compile_fallback(story, state), count), state["assets"])
            timeline_data = json.dumps(build_timeline_data(plan, segment_duration), ensure_ascii=False, indent=2)
            _save_last_processed_script(plan["global_prompt"], timeline_data, state)
            return plan["global_prompt"], timeline_data, catalog, reference_images
        if not llm_model or llm_model.startswith("未选择"):
            raise ValueError("拆解/生成模式必须选择 Qwen3.5 或 Qwen3.8 GGUF")
        if not llm_mmproj or llm_mmproj.startswith("未选择"):
            raise ValueError("拆解/生成模式必须选择配套的 Qwen mmproj GGUF")
        system = build_director_prompt(story, mode, story_style, segment_count,
                                       "zh" if "ZH" in prompt_lang else "en", segment_duration,
                                       state["assets"], preference, custom_rules)
        user = f"输出恰好 {count} 个分镜的 Director JSON。" + ("镜头细节必须充分。" if enhance else "")
        config = {"model": llm_model, "mmproj": llm_mmproj, "n_ctx": context_size, "n_gpu_layers": gpu_layers}
        params = {"max_tokens": max_tokens, "temperature": temperature, "top_k": top_k, "top_p": top_p,
                  "min_p": min_p, "repeat_penalty": repeat_penalty}
        print(f"[StoryDirector] 准备生成 Director 总提示词和 {count} 个分镜，模式={mode}，风格={story_style}，启用素材={len([a for a in state['assets'] if a.get('enabled', True)])}", flush=True)
        try:
            import folder_paths
            input_root = folder_paths.get_input_directory()
            image_paths = [os.path.join(input_root, _safe_relative(asset["path"]).replace("/", os.sep))
                           for asset in state["assets"] if asset.get("enabled", True) and asset["type"] == "image"]
        except (ImportError, KeyError):
            image_paths = []
        result = LLAMA.complete(config, system, user, seed=seed, image_paths=image_paths, **params)
        plan = apply_reference_contract(validate_director_plan(result, count), state["assets"])
        timeline_data = json.dumps(build_timeline_data(plan, segment_duration), ensure_ascii=False, indent=2)
        _save_last_processed_script(plan["global_prompt"], timeline_data, state)
        print(f"[StoryDirector] Director 结果已保存：{_last_processed_file()}", flush=True)
        return plan["global_prompt"], timeline_data, catalog, reference_images


NODE_CLASS_MAPPINGS = {"StoryDirector": StoryDirector}
NODE_DISPLAY_NAME_MAPPINGS = {"StoryDirector": "StoryDirector 故事导演"}
