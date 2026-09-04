"""本地故事分镜规划器：只输出文字提示词与资产目录。"""
from __future__ import annotations

import json
import os
import re
from pathlib import PurePosixPath

from .llama_backend import LLAMA

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".webm", ".mkv", ".avi"})
AUDIO_EXTENSIONS = frozenset({".wav", ".mp3", ".flac", ".m4a", ".ogg"})
ASSET_ROLES = ("角色", "场景", "道具", "分镜", "音效", "音乐", "其他")


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
    value = str(path or "").replace("\\", "/").lstrip("/")
    parts = PurePosixPath(value).parts
    if not parts or parts[0] != "story_director" or ".." in parts or any(p in ("", ".") for p in parts):
        raise ValueError("素材路径必须位于 input/story_director")
    return "/".join(parts)


def normalize_assets(value) -> list[dict]:
    data = json.loads(value) if isinstance(value, str) and value.strip() else value
    if isinstance(data, dict):
        data = data.get("assets", [])
    if not isinstance(data, list):
        return []
    result = []
    for order, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", ""))
        try:
            path = _safe_relative(path)
            kind = str(item.get("type") or asset_type(path))
        except (ValueError, TypeError):
            continue
        if kind not in {"image", "video", "audio"}:
            continue
        role = str(item.get("role", "其他"))
        result.append({
            "type": kind, "role": role if role in ASSET_ROLES else "其他",
            "name": (str(item.get("name") or os.path.basename(path))[:180]),
            "description": str(item.get("description", ""))[:2000],
            "path": path, "enabled": bool(item.get("enabled", True)), "order": len(result),
        })
    return result


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


def _stamp(seconds: float) -> str:
    minutes, remainder = divmod(max(0.0, float(seconds)), 60)
    return f"{int(minutes):02d}:{remainder:06.3f}"


def _story_parts(story: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n+|(?<=[。.!！？?])\s*", str(story or "").strip()) if p.strip()]


def compile_fallback(story: str, state: dict) -> str:
    count = max(1, min(64, int(state.get("segment_count", state.get("shots", 4)))))
    duration = max(0.001, float(state.get("segment_duration", state.get("shot_duration", 3.0))))
    parts = _story_parts(story) or ["一个具有明确动作的电影感瞬间"]
    parts = (parts + [parts[-1]] * count)[:count]
    style = str(state.get("style", "电影感"))
    language = str(state.get("language", "中文"))
    camera = str(state.get("camera_preferences", "中景，平稳推进"))
    lines = []
    for i, part in enumerate(parts, 1):
        marker = "[Shot 1]" if i == 1 else f"[Shot {i}] At {_stamp((i - 1) * duration)}"
        lines.append(f"{marker} | Visual: {part}（{style}） | Action: 连续且可见的物理动作 | Camera: {camera} | Lighting: {style}光线 | Audio: 环境声与动作声（{language}）")
    return "\n".join(lines)


def compose_llm_request(story: str, state: dict) -> tuple[str, str]:
    """构造稳定的 H3 分镜请求；素材只以语义目录进入请求。"""
    count = max(1, min(64, int(state.get("segment_count", state.get("shots", 4)))))
    duration = max(0.001, float(state.get("segment_duration", state.get("shot_duration", 3.0))))
    system = ("你是专业影视分镜规划师。将故事拆成准确的镜头节奏，保持角色、场景、道具在镜头间连续。"
              "每个镜头必须写可观察的 Visual、连续的 Action、具体的 Camera、Lighting、Audio；"
              "先写主体和动作，再写镜头运动、景别、光线与声音，避免抽象形容词、不可拍摄的意图和矛盾动作。"
              "只引用素材目录中真实存在且适合当前镜头的素材名称，不得编造素材。"
              f"严格输出恰好 {count} 个纯文本镜头，不要 Markdown、解释或代码围栏。"
              "首段以 [Shot 1] 开始且不写时间；后续每段以 [Shot N] At MM:SS.mmm 开始，时间严格递增。")
    catalog = [{"name": a["name"], "type": a["type"], "role": a["role"], "description": a["description"]}
               for a in state.get("assets", []) if a.get("enabled", True)]
    user = json.dumps({"故事": str(story or "").strip(), "镜头数": count, "单镜头秒数": duration,
                       "风格": state.get("style", "电影感"), "语言": state.get("language", "中文"),
                       "镜头偏好": state.get("camera_preferences", ""), "素材目录": catalog}, ensure_ascii=False, indent=2)
    return system, user


def validate_prompt(text: str, expected_count: int | None = None) -> str:
    prompt = str(text or "").strip()
    if not prompt or "```" in prompt or re.search(r"\[StoryDirector error\]", prompt, re.I):
        raise ValueError("提示词为空或含有非法错误标记")
    matches = list(re.finditer(r"^\[Shot (\d+)\](?: At ([0-9]{2,}):([0-5][0-9])\.([0-9]{3}))?(?:[ \t]*\||[ \t]+)", prompt, re.M))
    numbers = [int(m.group(1)) for m in matches]
    if numbers != list(range(1, len(matches) + 1)) or not matches:
        raise ValueError("必须包含连续的 [Shot 1]、[Shot N] 标记")
    if expected_count is not None and len(matches) != int(expected_count):
        raise ValueError(f"镜头数量应为 {expected_count}，实际为 {len(matches)}")
    if matches[0].group(2) is not None:
        raise ValueError("Shot 1 不应包含时间码")
    if any(match.group(2) is None for match in matches[1:]):
        raise ValueError("Shot 2 及后续镜头必须包含时间码")
    times = [int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000 for m in matches[1:]]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("后续镜头时间必须严格递增")
    required = ("Visual:", "Action:", "Camera:", "Lighting:", "Audio:")
    for i, match in enumerate(matches):
        block = prompt[match.start():matches[i + 1].start() if i + 1 < len(matches) else len(prompt)]
        if any(field not in block for field in required):
            raise ValueError("每个镜头都必须包含 Visual、Action、Camera、Lighting、Audio")
    return prompt


class StoryDirector:
    @classmethod
    def INPUT_TYPES(cls):
        try:
            import folder_paths
            models = folder_paths.get_filename_list("LLM")
        except (ImportError, KeyError):
            models = []
        return {"required": {
            "story": ("STRING", {"default": "", "multiline": True}),
            "prompt_override": ("STRING", {"default": "", "multiline": True}),
            "mode": (["确定性编排", "本地 LLM"],),
            "llm_model": (models or ["未选择本地 GGUF"],),
            "segment_count": ("INT", {"default": 4, "min": 1, "max": 64}),
            "segment_duration": ("FLOAT", {"default": 3.0, "min": 0.001, "max": 3600.0, "step": 0.001}),
            "style": ("STRING", {"default": "电影感"}),
            "language": (["中文", "English", "中英双语"],),
            "camera_preferences": ("STRING", {"default": "中景，平稳推进"}),
            "context_size": ("INT", {"default": 32768, "min": 1024, "max": 262144, "step": 128}),
            "gpu_layers": ("INT", {"default": -1, "min": -1, "max": 999, "step": 1}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 9223372036854775807}),
        }, "hidden": {"director_state": ("STRING", {"default": '{"assets": []}', "multiline": True})}}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("H3 分镜提示词", "素材目录 JSON")
    FUNCTION = "direct"
    CATEGORY = "故事导演"

    def direct(self, story, prompt_override, mode, llm_model, segment_count, segment_duration, style, language, camera_preferences, context_size, gpu_layers, seed, director_state):
        state = _state(director_state)
        state.update({"segment_count": segment_count, "segment_duration": segment_duration, "style": style,
                      "language": language, "camera_preferences": camera_preferences,
                      "context_size": context_size, "gpu_layers": gpu_layers})
        catalog = json.dumps({"assets": state["assets"]}, ensure_ascii=False, indent=2)
        if str(prompt_override or "").strip():
            return (validate_prompt(prompt_override, segment_count), catalog)
        if mode == "本地 LLM":
            if not llm_model or llm_model.startswith("未选择"):
                raise ValueError("本地 LLM 模式必须选择 GGUF 模型")
            system, request = compose_llm_request(story, state)
            prompt = LLAMA.complete({"model": llm_model, "n_ctx": context_size, "n_gpu_layers": gpu_layers}, system, request, seed=seed, max_tokens=8192, temperature=0.2)
            return (validate_prompt(prompt, segment_count), catalog)
        return (validate_prompt(compile_fallback(story, state), segment_count), catalog)


NODE_CLASS_MAPPINGS = {"StoryDirector": StoryDirector}
NODE_DISPLAY_NAME_MAPPINGS = {"StoryDirector": "故事导演"}
