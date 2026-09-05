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
from .presets.script import SEGMENT_COUNT_OPTIONS, build_shot_prompt, _resolve_segment_count
from .sheding.prompt_enhancer_rules import build_enhancer_prompt
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


def _replace_detailed_description(block, detail):
    pattern = r"(?ms)(^detailed_description:\s*).*?(?=^overall_soundscape:)"
    if not re.search(pattern, block):
        raise ValueError("H3 分段缺少 detailed_description/overall_soundscape 字段")
    return re.sub(pattern, lambda match: match.group(1) + detail.strip() + "\n", block, count=1)


def enhance_script(script, config, story_style, segment_duration, prompt_lang, preference, custom_rules, seed, image_paths=()):
    blocks = re.findall(r"\[SHOT_START\].*?\[SHOT_END\]", script, re.DOTALL)
    style_text = STORY_STYLES.get(story_style, story_style)
    system = build_enhancer_prompt("zh" if "ZH" in prompt_lang else "en", style_text, segment_duration, preference, custom_rules)
    output = []
    for index, block in enumerate(blocks):
        detail = re.search(r"(?ms)^detailed_description:\s*(.*?)(?=^overall_soundscape:)", block)
        if not detail:
            raise ValueError(f"第 {index + 1} 段缺少 detailed_description")
        request = f"分段 {index + 1}/{len(blocks)}\n\n{block}\n\n原 detailed_description：\n{detail.group(1).strip()}"
        polished = LLAMA.complete(config, system, request, seed=seed + index, image_paths=image_paths, max_tokens=4096, temperature=0.5)
        output.append(_replace_detailed_description(block, polished))
    return "\n\n".join(output)


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


def normalize_schedule_sections(script: str) -> str:
    """Add empty scheduling sections when the LLM returns a valid H3 body without them."""
    def normalize(match):
        shot = match.group(1).strip()
        marker_names = ("H3_PROMPT", "SCENE_INSTRUCTION", "VIDEO_INSTRUCTION", "AUDIO_INSTRUCTION")
        for name in marker_names:
            shot = re.sub(rf"(?im)^\s*(?:#+\s*)?=*[\s`*_]*{name}[\s`*_]*=*\s*$", f"==={name}===", shot)
        if "===H3_PROMPT===" not in shot:
            shot = f"===H3_PROMPT===\n{shot}"
        sections = []
        for marker in ("===SCENE_INSTRUCTION===", "===VIDEO_INSTRUCTION===", "===AUDIO_INSTRUCTION==="):
            if marker not in shot:
                sections.append(f"{marker}\n{{\"slots\": []}}")
        if sections:
            shot = f"{shot}\n" + "\n".join(sections)
        return f"[SHOT_START]\n{shot}\n[SHOT_END]"

    return re.sub(r"\[SHOT_START\](.*?)\[SHOT_END\]", normalize, str(script or ""), flags=re.DOTALL)


def validate_script(script: str, expected_count: int | None = None) -> str:
    text = str(script or "").strip()
    shots = re.findall(r"\[SHOT_START\](.*?)\[SHOT_END\]", text, re.DOTALL)
    if not text or not shots or "===H3_PROMPT===" not in text:
        raise ValueError("必须输出完整 H3 剧本块（[SHOT_START]...[SHOT_END]）")
    if expected_count is not None and len(shots) != int(expected_count):
        raise ValueError(f"分段数量应为 {expected_count}，实际为 {len(shots)}")
    required_sections = ("===H3_PROMPT===", "===SCENE_INSTRUCTION===", "===VIDEO_INSTRUCTION===", "===AUDIO_INSTRUCTION===")
    required_fields = ("subject_definitions:", "summary:", "retention_analysis:", "detailed_description:", "overall_soundscape:", "non_diegetic_music:")
    for index, shot in enumerate(shots, 1):
        if any(section not in shot for section in required_sections):
            raise ValueError(f"第 {index} 段缺少 H3 或调度区块")
        h3 = shot.split("===H3_PROMPT===", 1)[1].split("===SCENE_INSTRUCTION===", 1)[0]
        if any(field not in h3 for field in required_fields):
            raise ValueError(f"第 {index} 段缺少 H3 六段字段")
    return text


class StoryDirector:
    @classmethod
    def INPUT_TYPES(cls):
        try:
            import folder_paths
            files = [name for name in folder_paths.get_filename_list("LLM") if name.lower().endswith(".gguf")]
            qwen35 = [name for name in files if "qwen3.5" in name.lower() or "qwen35" in name.lower()]
            models = [name for name in qwen35 if "mmproj" not in os.path.basename(name).lower()] or ["未选择 Qwen3.5 GGUF"]
            mmproj_models = [name for name in qwen35 if "mmproj" in os.path.basename(name).lower()] or ["未选择 Qwen3.5 mmproj"]
        except (ImportError, KeyError):
            models = ["未选择 Qwen3.5 GGUF"]
            mmproj_models = ["未选择 Qwen3.5 mmproj"]
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

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("H3完整剧本", "素材目录 JSON")
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
        if str(prompt_override or "").strip():
            script = validate_script(prompt_override, count)
            _save_last_processed_script(script, state)
            return script, catalog
        if mode == "离线预览":
            script = validate_script(compile_fallback(story, state), count)
            _save_last_processed_script(script, state)
            return script, catalog
        if not llm_model or llm_model.startswith("未选择"):
            raise ValueError("拆解/生成模式必须选择 Qwen3.5 GGUF")
        if not llm_mmproj or llm_mmproj.startswith("未选择"):
            raise ValueError("拆解/生成模式必须选择 Qwen3.5 mmproj GGUF")
        image_intro, video_intro, audio_intro = _material_intros(state["assets"])
        system = build_shot_prompt(story, mode=mode, story_style=story_style, segment_count_label=segment_count,
                                   lang="zh" if "ZH" in prompt_lang else "en", segment_duration=segment_duration,
                                   ref_image_intro=image_intro, ref_video_intro=video_intro, ref_audio_intro=audio_intro,
                                   preference=preference, custom_rules=custom_rules)
        user = f"请严格输出恰好 {count} 个 [SHOT_START]...[SHOT_END] 完整 H3 分段，不要解释。"
        config = {"model": llm_model, "mmproj": llm_mmproj, "n_ctx": context_size, "n_gpu_layers": gpu_layers}
        params = {"max_tokens": max_tokens, "temperature": temperature, "top_k": top_k, "top_p": top_p,
                  "min_p": min_p, "repeat_penalty": repeat_penalty}
        print(f"[StoryDirector] 准备生成 {count} 个 H3 分段，模式={mode}，风格={story_style}，启用素材={len([a for a in state['assets'] if a.get('enabled', True)])}", flush=True)
        try:
            import folder_paths
            input_root = folder_paths.get_input_directory()
            image_paths = [os.path.join(input_root, _safe_relative(asset["path"]).replace("/", os.sep))
                           for asset in state["assets"] if asset.get("enabled", True) and asset["type"] == "image"]
        except (ImportError, KeyError):
            image_paths = []
        result = LLAMA.complete(config, system, user, seed=seed, image_paths=image_paths, **params)
        _save_last_processed_script(result, state)
        print(f"[StoryDirector] 原始模型输出已保存：{_last_processed_file()}", flush=True)
        print("[StoryDirector] 正在校验 H3 分段结构", flush=True)
        normalized = normalize_schedule_sections(result)
        if normalized != result:
            print("[StoryDirector] 模型遗漏了部分调度区块，已补为空 slots 并保留 H3 内容", flush=True)
        script = validate_script(normalized)
        actual_count = len(re.findall(r"\[SHOT_START\]", script))
        if actual_count != count:
            print(f"[StoryDirector] 警告：要求 {count} 个分段，模型实际返回 {actual_count} 个；保留完整结果，避免丢失剧情", flush=True)
        if enhance:
            print(f"[StoryDirector] 开始二次增强 {actual_count} 个分段", flush=True)
            script = validate_script(enhance_script(script, config, story_style, segment_duration,
                                                    prompt_lang, preference, custom_rules, seed, image_paths))
        _save_last_processed_script(script, state)
        return script, catalog


NODE_CLASS_MAPPINGS = {"StoryDirector": StoryDirector}
NODE_DISPLAY_NAME_MAPPINGS = {"StoryDirector": "StoryDirector 故事导演"}
