"""Disposable Qwen3.8 vision worker used by StoryDirector."""

import base64
import io
import json
import os
import re
import struct
import sys
from pathlib import Path

from PIL import Image

RESULT_PREFIX = "STORYDIRECTOR_RESULT="
_DLL_DIRECTORY_HANDLES = []


def prepare_windows_llama_dlls():
    if sys.platform != "win32":
        return
    for entry in sys.path:
        lib_dir = Path(entry) / "llama_cpp" / "lib"
        if not (lib_dir / "ggml-base.dll").is_file():
            continue
        _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(lib_dir)))
        print(f"[StoryDirector] registered llama.cpp DLL directory: {lib_dir}", flush=True)
        return
    print("[StoryDirector] WARNING: llama_cpp/lib with ggml-base.dll was not found on sys.path", flush=True)


def llama_system_info(llama_cpp_module):
    try:
        value = llama_cpp_module.llama_cpp.llama_print_system_info()
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value or "")
    except Exception as error:
        return f"unavailable: {error}"


def language_issue(value, output_language):
    cleaned = re.sub(r"<d>.*?</d>|<[^>]+>|\[Shot[^]]*]", "", str(value or ""), flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"\b(?:subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|non_diegetic_music)\s*:", "", cleaned, flags=re.IGNORECASE)
    han = len(re.findall(r"[\u4e00-\u9fff]", cleaned))
    latin = len(re.findall(r"\b[A-Za-z]{2,}\b", cleaned))
    if output_language == "zh" and (han < 4 or latin > han):
        return "必须使用简体中文"
    if output_language == "en" and han > max(4, latin):
        return "must be written in English"
    return ""


def extract_json(text):
    value = str(text or "")
    start = value.find("{")
    if start < 0:
        return None
    try:
        parsed, _end = json.JSONDecoder().raw_decode(value[start:])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def executable_plan(text, expected_count):
    value = extract_json(text)
    if value is None:
        return False
    segments = value.get("segments") if isinstance(value, dict) else None
    return (bool(str(value.get("global_prompt") or "").strip())
            and bool(str(value.get("overall_soundscape") or "").strip())
            and isinstance(segments, list) and len(segments) == int(expected_count)
            and all(isinstance(item, dict) and str(item.get("prompt") or "").strip() for item in segments))


def director_issues(text, expected_count, auto_skill=False, skill_id="", user_story="", output_language="en"):
    value = extract_json(text)
    if value is None:
        return ["返回内容不包含有效 JSON 对象"]
    issues = [f"缺少 {field}" for field in ("global_prompt", "overall_soundscape") if not str(value.get(field) or "").strip()]
    if auto_skill and not str(value.get("selected_skill") or "").strip():
        issues.append("缺少 selected_skill")
    segments = value.get("segments")
    if not isinstance(segments, list):
        issues.append("segments 必须是数组")
    elif len(segments) != int(expected_count):
        issues.append(f"segments 必须恰好包含 {int(expected_count)} 项，实际为 {len(segments)} 项")
    else:
        issues.extend(f"第 {index} 段缺少 prompt" for index, segment in enumerate(segments, 1)
                      if not isinstance(segment, dict) or not str(segment.get("prompt") or "").strip())
    selected = str(value.get("selected_skill") or skill_id)
    output = json.dumps(value, ensure_ascii=False)
    source = re.sub(r"\s+", " ", str(user_story or ""))
    if selected == "music-video-subtitle-generator":
        for block in re.findall(r"<d>\s*(?:\[[^]]+\]\s*)?(.*?)\s*</d>", output, re.DOTALL | re.IGNORECASE):
            if re.sub(r"\s+", " ", block).strip() not in source:
                issues.append("MV 中的歌词或对白必须逐字来自用户故事")
                break
    if selected in {"minimalist-product-ad-generator", "brand-promo-video-generator"}:
        pattern = r"\b\d+(?:\.\d+)?\s*(?:%|元|美元|万|亿|kg|g|mm|cm|mah|hz|小时|分钟)"
        if set(re.findall(pattern, output, re.IGNORECASE)) - set(re.findall(pattern, source, re.IGNORECASE)):
            issues.append("产品或品牌的数字参数、价格和业绩必须来自用户故事")
    if selected in {"papercraft-stop-motion-explainer", "handdrawn-live-video-generator"} and re.search(r"(?:smooth\s+(?:cg|3d)|polished\s+(?:cg|3d)|光滑\s*(?:cg|3d))", output, re.IGNORECASE):
        issues.append("禁止把目标风格描述为光滑 CG")
    return issues


def image_data_url(path):
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
        encoded = io.BytesIO()
        image.save(encoded, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(encoded.getvalue()).decode("ascii")


def gguf_mtp_layers(model_path):
    path = Path(model_path)
    fixed_types = {0: ("<B", 1), 1: ("<b", 1), 2: ("<H", 2), 3: ("<h", 2), 4: ("<I", 4),
                   5: ("<i", 4), 6: ("<f", 4), 7: ("<?", 1), 10: ("<Q", 8), 11: ("<q", 8), 12: ("<d", 8)}
    try:
        with path.open("rb") as gguf:
            def read_exact(size):
                value = gguf.read(size)
                if len(value) != size:
                    raise EOFError
                return value
            def read_string():
                size = struct.unpack("<Q", read_exact(8))[0]
                return read_exact(size).decode("utf-8", errors="replace")
            def read_value(value_type, capture=False):
                if value_type in fixed_types:
                    fmt, size = fixed_types[value_type]
                    value = struct.unpack(fmt, read_exact(size))[0]
                    return value if capture else None
                if value_type == 8:
                    value = read_string()
                    return value if capture else None
                if value_type == 9:
                    element_type = struct.unpack("<I", read_exact(4))[0]
                    count = struct.unpack("<Q", read_exact(8))[0]
                    if element_type in fixed_types:
                        gguf.seek(fixed_types[element_type][1] * count, os.SEEK_CUR)
                    else:
                        for _ in range(count):
                            read_value(element_type)
                    return None
                raise ValueError(value_type)
            if read_exact(4) != b"GGUF" or struct.unpack("<I", read_exact(4))[0] not in (2, 3):
                return None
            tensor_count, metadata_count = struct.unpack("<QQ", read_exact(16))
            layers = 0
            for _ in range(metadata_count):
                key = read_string()
                value_type = struct.unpack("<I", read_exact(4))[0]
                capture = key.casefold().endswith(".nextn_predict_layers")
                value = read_value(value_type, capture)
                if capture and isinstance(value, (int, float)):
                    layers = max(layers, int(value))
            if layers <= 0:
                for _ in range(tensor_count):
                    name = read_string().casefold()
                    dimensions = struct.unpack("<I", read_exact(4))[0]
                    gguf.seek(dimensions * 8 + 4 + 8, os.SEEK_CUR)
                    if ".nextn." in name or ".mtp." in name:
                        layers = 1
            return layers
    except (OSError, EOFError, ValueError, struct.error):
        return None


def install_mtmd_physical_token_ledger(llm):
    original_generate = getattr(llm, "generate", None)
    if not callable(original_generate):
        return
    def physical_generate(*args, **kwargs):
        n_tokens = int(getattr(llm, "n_tokens", 0))
        physical_tokens = llm.input_ids[:n_tokens].tolist() if n_tokens > 0 else []
        supplied_tokens = args[0] if args else kwargs.get("tokens")
        if supplied_tokens is not None and any(int(token) < 0 for token in supplied_tokens):
            final_text_token = next((int(token) for token in reversed(supplied_tokens) if int(token) >= 0), None)
            if final_text_token is None:
                raise RuntimeError("Qwen3.8 MTMD prompt has no final text token for MTP")
            supplied_tokens = [final_text_token]
            if args:
                args = (supplied_tokens, *args[1:])
            else:
                kwargs["tokens"] = supplied_tokens
            kwargs["reset"] = False
        elif supplied_tokens is not None and n_tokens > 0 and len(supplied_tokens) < n_tokens:
            supplied_tokens = physical_tokens
            if args:
                args = (supplied_tokens, *args[1:])
            else:
                kwargs["tokens"] = supplied_tokens
        if supplied_tokens is not None and list(supplied_tokens) == physical_tokens and n_tokens > 0:
            start = int(getattr(llm, "_last_eval_output_start", 0))
            count = int(getattr(llm, "_last_eval_output_count", 0))
            if not start <= n_tokens - 1 < start + count:
                llm._last_eval_output_start = n_tokens - 1
                llm._last_eval_output_count = 1
        return original_generate(*args, **kwargs)
    llm.generate = physical_generate


def adapt_mtmd_template(chat_template):
    if not chat_template or "<|image_pad|>" not in chat_template:
        return chat_template
    pattern = r"\{\{-?\s*(['\"])<\|vision_start\|><\|image_pad\|><\|vision_end\|>\1\s*-?\}\}"
    replacement = (
        "{{- '<|vision_start|>' }}"
        "{%- if item.image_url is string %}{{- item.image_url }}"
        "{%- else %}{{- item.image_url.url }}{%- endif %}"
        "{{- '<|vision_end|>' }}"
    )
    adapted, count = re.subn(pattern, replacement, chat_template)
    if count == 0:
        raise RuntimeError("Qwen3.8 chat template contains an unsupported image_pad expression")
    return adapted


def complete(request):
    prepare_windows_llama_dlls()
    try:
        import llama_cpp
        from llama_cpp import Llama, SpecConfig, SpeculativeType
        from llama_cpp.llama_chat_format import Qwen35ChatHandler
    except ImportError as error:
        raise RuntimeError("Qwen3.8 requires llama-cpp-python 0.3.48+ with Qwen MTMD support") from error

    draft_tokens = int(request.get("mtp_draft_tokens", 2))
    n_cpu_moe = int(request.get("n_cpu_moe", 0))
    reasoning_effort = str(request.get("reasoning_effort", "xhigh"))
    if not 1 <= draft_tokens <= 8:
        raise ValueError("Qwen3.8 MTP draft tokens must be between 1 and 8")
    if n_cpu_moe < 0:
        raise ValueError("Qwen3.8 n_cpu_moe cannot be negative")
    if reasoning_effort not in {"xhigh", "medium", "low"}:
        raise ValueError(f"Unknown Qwen3.8 reasoning effort: {reasoning_effort}")
    llama_kwargs = {"model_path": request["model_path"],
                    "n_gpu_layers": int(request.get("n_gpu_layers", -1)),
                    "n_ctx": int(request.get("n_ctx", 32768)),
                    "n_batch": 256, "n_ubatch": 256, "flash_attn": True, "type_k": 8,
                    "type_v": 8, "swa_full": False, "verbose": False}
    print(f"[StoryDirector] llama.cpp system info: {llama_system_info(llama_cpp)}", flush=True)
    print(
        f"[StoryDirector] Qwen3.8 runtime: n_gpu_layers={llama_kwargs['n_gpu_layers']} "
        f"n_ctx={llama_kwargs['n_ctx']} cpu_moe={bool(request.get('cpu_moe', False))} "
        f"n_cpu_moe={n_cpu_moe} mtp={bool(request.get('mtp', True))}",
        flush=True,
    )
    if request.get("cpu_moe", False):
        llama_kwargs["cpu_moe"] = True
    elif n_cpu_moe > 0:
        llama_kwargs["n_cpu_moe"] = n_cpu_moe
    mtp_layers = gguf_mtp_layers(request["model_path"]) if request.get("mtp", True) else 0
    if mtp_layers and mtp_layers > 0:
        llama_kwargs["speculative"] = SpecConfig(spec_type=SpeculativeType.DRAFT_MTP, draft_n_max=draft_tokens)
    llm = Llama(**llama_kwargs)
    if "speculative" in llama_kwargs:
        install_mtmd_physical_token_ledger(llm)
    handler = None
    try:
        template = (getattr(llm, "metadata", {}) or {}).get("tokenizer.chat_template")
        if not template:
            raise RuntimeError("Qwen3.8 GGUF is missing tokenizer.chat_template")
        handler = Qwen35ChatHandler(
            clip_model_path=request["mmproj_path"], enable_thinking=False, preserve_thinking=False,
            extra_template_arguments={"reasoning_effort": reasoning_effort},
            chat_template_override=adapt_mtmd_template(template), verbose=False, use_gpu=True,
        )
        llm.chat_handler = handler
        content = [{"type": "image_url", "image_url": {"url": image_data_url(path)}} for path in request.get("image_paths", ())]
        content.append({"type": "text", "text": request["user"]})
        options = dict(request.get("params", {}))
        messages = [{"role": "system", "content": request["system"]}, {"role": "user", "content": content}]
        response_format = {"type": "json_object", "schema": {
                "type": "object",
                "properties": {
                    "global_prompt": {"type": "string"},
                    "overall_soundscape": {"type": "string"},
                    "non_diegetic_music": {"type": "string"},
                    "selected_skill": {"type": "string"},
                    "skill_selection_reason": {"type": "string"},
                    "segments": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"prompt": {"type": "string"}},
                        "required": ["prompt"],
                        "additionalProperties": False,
                    }},
                },
                "required": (["global_prompt", "overall_soundscape", "non_diegetic_music", "segments",
                              "selected_skill", "skill_selection_reason"] if request.get("auto_skill") else
                             ["global_prompt", "overall_soundscape", "non_diegetic_music", "segments"]),
                "additionalProperties": False,
            }}
        response = llm.create_chat_completion(
            messages=messages, seed=int(request.get("seed", 0)), reasoning_budget=0,
            response_format=response_format, **options,
        )
        message = response["choices"][0]["message"]
        text = str(message.get("content") or message.get("reasoning_content") or "")
        issues = director_issues(text, request.get("expected_count", 1), request.get("auto_skill", False),
                                 request.get("selected_skill", ""), request.get("user_story", ""),
                                 request.get("output_language", "en"))
        if issues:
            original_text, original_issues = text, issues
            original_executable = executable_plan(text, request.get("expected_count", 1))
            repair = "只修复以下问题并返回完整 JSON，不要解释：\n" + "\n".join(f"- {issue}" for issue in issues)
            if request.get("enhance"):
                repair += "\n同时保持每段 prompt 的构图、主体位置、环境光线、连续动作、状态变化、运镜类型/幅度/速度及当前声音足够详细。"
            llm.reset()
            response = llm.create_chat_completion(
                messages=[{"role": "system", "content": request["system"]},
                          {"role": "user", "content": "请按以下要求修复这份 Director JSON。\n" + repair + "\n\n原 JSON：\n" + text}],
                seed=int(request.get("seed", 0)), reasoning_budget=0, response_format=response_format, **options,
            )
            message = response["choices"][0]["message"]
            text = str(message.get("content") or message.get("reasoning_content") or "")
            issues = director_issues(text, request.get("expected_count", 1), request.get("auto_skill", False),
                                     request.get("selected_skill", ""), request.get("user_story", ""),
                                     request.get("output_language", "en"))
            if not executable_plan(text, request.get("expected_count", 1)):
                if original_executable:
                    text, issues = original_text, original_issues
                    print("[StoryDirector] WARNING: Qwen3.8 纠正结果无效，保留首次结构完整的生成结果。", flush=True)
                else:
                    raise ValueError("Qwen3.8 首次及修复结果均缺少可执行 JSON 结构")
            elif issues:
                print("[StoryDirector] WARNING: Qwen3.8 纠正后仍有非结构问题，保留可执行生成结果。", flush=True)
        value = extract_json(text)
        return json.dumps(value, ensure_ascii=False) if value is not None else text
    finally:
        llm.close()
        close_handler = getattr(handler, "close", None)
        if callable(close_handler):
            close_handler()


def main():
    request = json.loads(sys.stdin.read())
    for key in ("model_path", "mmproj_path"):
        path = Path(request[key])
        if path.suffix.lower() != ".gguf" or not path.is_file():
            raise ValueError(f"Invalid {key}")
    sys.stdout.buffer.write((RESULT_PREFIX + json.dumps({"text": complete(request)}, ensure_ascii=True) + "\n").encode("ascii"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
