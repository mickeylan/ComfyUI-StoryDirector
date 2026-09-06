"""Disposable Qwen3.8 vision worker used by StoryDirector."""

import base64
import io
import json
import re
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
        from llama_cpp import Llama
        from llama_cpp.llama_chat_format import Qwen35ChatHandler
    except ImportError as error:
        raise RuntimeError("Qwen3.8 requires llama-cpp-python 0.3.48+ with Qwen MTMD support") from error

    llm = Llama(
        model_path=request["model_path"], n_gpu_layers=-1,
        n_ctx=32768, n_batch=256, n_ubatch=256,
        flash_attn=True, type_k=8, type_v=8, swa_full=False, verbose=False,
    )
    handler = None
    try:
        template = (getattr(llm, "metadata", {}) or {}).get("tokenizer.chat_template")
        if not template:
            raise RuntimeError("Qwen3.8 GGUF is missing tokenizer.chat_template")
        handler = Qwen35ChatHandler(
            clip_model_path=request["mmproj_path"], enable_thinking=False, preserve_thinking=False,
            extra_template_arguments={"reasoning_effort": "xhigh"},
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
