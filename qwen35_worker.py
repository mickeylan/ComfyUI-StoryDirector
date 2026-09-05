"""Disposable Qwen3.5 MTMD worker used by StoryDirector."""

import base64
import io
import json
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


def complete(request):
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import MTMDChatHandler

    handler = MTMDChatHandler(clip_model_path=request["mmproj_path"], verbose=False, use_gpu=False)
    llm = Llama(
        model_path=request["model_path"], chat_handler=handler, n_gpu_layers=-1,
        n_ctx=max(65536, int(request.get("n_ctx", 65536))), n_batch=64, n_ubatch=64,
        flash_attn=True, type_k=8, type_v=8, swa_full=False, verbose=False,
    )
    try:
        content = [{"type": "image_url", "image_url": {"url": image_data_url(path)}} for path in request.get("image_paths", ())]
        content.append({"type": "text", "text": request["user"]})
        response = llm.create_chat_completion(
            messages=[{"role": "system", "content": request["system"]}, {"role": "user", "content": content}],
            seed=int(request.get("seed", 0)), reasoning_budget=0, **request.get("params", {}),
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
    print(RESULT_PREFIX + json.dumps({"text": complete(request)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
