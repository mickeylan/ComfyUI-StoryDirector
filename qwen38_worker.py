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
    try:
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
    llama_kwargs = {"model_path": request["model_path"], "n_gpu_layers": -1, "n_ctx": 32768,
                    "n_batch": 256, "n_ubatch": 256, "flash_attn": True, "type_k": 8,
                    "type_v": 8, "swa_full": False, "verbose": False}
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
        options["top_p"] = 0.8
        options["min_p"] = 0.0
        response = llm.create_chat_completion(
            messages=[{"role": "system", "content": request["system"]}, {"role": "user", "content": content}],
            seed=int(request.get("seed", 0)), reasoning_budget=0, **options,
        )
        message = response["choices"][0]["message"]
        return str(message.get("content") or message.get("reasoning_content") or "")
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
