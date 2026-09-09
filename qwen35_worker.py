"""Disposable Qwen3.5 MTMD worker used by StoryDirector."""

import base64
import io
import json
import re
import sys
from pathlib import Path

from PIL import Image

RESULT_PREFIX = "STORYDIRECTOR_RESULT="


def director_issues(text, expected_count, auto_skill=False, skill_id="", user_story=""):
    try:
        value = json.loads(str(text or "").strip())
    except (TypeError, json.JSONDecodeError):
        return ["返回内容不是有效 JSON 对象"]
    if not isinstance(value, dict):
        return ["返回内容不是 JSON 对象"]
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


def complete(request):
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import MTMDChatHandler

    handler = MTMDChatHandler(clip_model_path=request["mmproj_path"], verbose=False, use_gpu=True)
    llm = Llama(
        model_path=request["model_path"], chat_handler=handler,
        n_gpu_layers=int(request.get("n_gpu_layers", -1)),
        n_ctx=int(request.get("n_ctx", 65536)), n_batch=64, n_ubatch=64,
        flash_attn=True, type_k=8, type_v=8, swa_full=False, verbose=False,
    )
    try:
        content = [{"type": "image_url", "image_url": {"url": image_data_url(path)}} for path in request.get("image_paths", ())]
        content.append({"type": "text", "text": request["user"]})
        messages = [{"role": "system", "content": request["system"]}, {"role": "user", "content": content}]
        response = llm.create_chat_completion(
            messages=messages, seed=int(request.get("seed", 0)), reasoning_budget=0,
            **request.get("params", {}),
        )
        message = response["choices"][0]["message"]
        text = str(message.get("content") or message.get("reasoning_content") or "")
        issues = director_issues(text, request.get("expected_count", 1), request.get("auto_skill", False),
                                 request.get("selected_skill", ""), request.get("user_story", ""))
        if issues:
            repair = "只修复以下问题并返回完整 JSON，不要解释：\n" + "\n".join(f"- {issue}" for issue in issues)
            response = llm.create_chat_completion(
                messages=messages + [{"role": "assistant", "content": text}, {"role": "user", "content": repair}],
                seed=int(request.get("seed", 0)), reasoning_budget=0, **request.get("params", {}),
            )
            message = response["choices"][0]["message"]
            text = str(message.get("content") or message.get("reasoning_content") or "")
        if request.get("enhance"):
            enhance_prompt = ("保持所有 JSON 字段、分镜数量、事实、素材标签、对白和歌词不变，只增强每段 prompt 的构图、主体位置、"
                              "环境光线、连续动作、状态变化、运镜类型/幅度/速度及当前声音。返回完整 JSON，不要解释。")
            response = llm.create_chat_completion(
                messages=messages + [{"role": "assistant", "content": text}, {"role": "user", "content": enhance_prompt}],
                seed=int(request.get("seed", 0)), reasoning_budget=0, **request.get("params", {}),
            )
            message = response["choices"][0]["message"]
            text = str(message.get("content") or message.get("reasoning_content") or "")
        return text
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
