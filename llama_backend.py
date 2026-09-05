"""llama-cpp-python 本地模型适配器。"""

import base64
import io
import os
import threading
import time

from PIL import Image


class LocalLlama:
    """延迟加载的 llama-cpp-python 封装。"""

    def __init__(self):
        self._llm = None
        self._config = None

    def load(self, config):
        config = dict(config or {})
        model = config.get("model", "")
        if not model:
            raise ValueError("请在 models/LLM 中选择 GGUF 模型")
        if self._llm is not None and self._config == config:
            return self._llm
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError("故事导演需要 llama-cpp-python") from exc
        try:
            import folder_paths
            path = folder_paths.get_full_path("LLM", model)
            mmproj_name = config.get("mmproj", "None")
            mmproj_path = folder_paths.get_full_path("LLM", mmproj_name) if mmproj_name != "None" else None
        except (ImportError, KeyError):
            path = None
            mmproj_path = None
        if not path or not os.path.isfile(path) or os.path.splitext(path)[1].lower() != ".gguf":
            raise ValueError("所选模型必须是 models/LLM 中列出的 GGUF 文件")
        if not mmproj_path or not os.path.isfile(mmproj_path) or os.path.splitext(mmproj_path)[1].lower() != ".gguf":
            raise ValueError("Qwen3.5 必须选择 models/LLM 中的 mmproj GGUF 文件")
        try:
            from llama_cpp.llama_chat_format import MTMDChatHandler
        except ImportError as exc:
            raise RuntimeError("Qwen3.5 需要带 MTMD 支持的 llama-cpp-python") from exc
        self.close()
        print(f"[StoryDirector] 正在加载 Qwen3.5：{os.path.basename(path)}", flush=True)
        print(f"[StoryDirector] 正在加载 mmproj：{os.path.basename(mmproj_path)}", flush=True)
        started = time.perf_counter()
        kwargs = {
            "model_path": path,
            "n_ctx": int(config.get("n_ctx", 65536)),
            "n_batch": 256,
            "n_ubatch": 256,
            "n_gpu_layers": int(config.get("n_gpu_layers", -1)),
            "flash_attn": True,
            "type_k": 8,
            "type_v": 8,
            "swa_full": False,
            "verbose": False,
        }
        kwargs["chat_handler"] = MTMDChatHandler(clip_model_path=mmproj_path, verbose=False, use_gpu=False)
        self._llm = Llama(**kwargs)
        self._config = config
        print(f"[StoryDirector] 模型加载完成，耗时 {time.perf_counter() - started:.1f} 秒", flush=True)
        return self._llm

    def complete(self, config, system, user, seed=0, image_paths=(), **params):
        llm = self.load(config)
        allowed = {"max_tokens", "temperature", "top_k", "top_p", "min_p", "repeat_penalty"}
        options = {k: v for k, v in params.items() if k in allowed and v is not None}
        print(f"[StoryDirector] 开始生成：输入 {len(system) + len(user)} 字符，最大输出 {options.get('max_tokens', '默认')} tokens", flush=True)
        started = time.perf_counter()
        content = []
        print(f"[StoryDirector] 正在读取 {len(image_paths)} 张参考图", flush=True)
        for path in image_paths:
            with Image.open(path) as image:
                image = image.convert("RGB")
                image.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
                encoded_image = io.BytesIO()
                image.save(encoded_image, format="JPEG", quality=88)
                encoded = base64.b64encode(encoded_image.getvalue()).decode("ascii")
                print(f"[StoryDirector] 参考图已适配：{os.path.basename(path)} -> {image.width}x{image.height}", flush=True)
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}})
        content.append({"type": "text", "text": user})
        print(f"[StoryDirector] 已向 Qwen3.5 提交 {len(image_paths)} 张参考图", flush=True)
        done = threading.Event()
        def log_progress():
            while not done.wait(15):
                print(f"[StoryDirector] Qwen3.5 仍在生成，已耗时 {time.perf_counter() - started:.1f} 秒", flush=True)
        reporter = threading.Thread(target=log_progress, daemon=True)
        reporter.start()
        try:
            response = llm.create_chat_completion(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
                seed=int(seed), reasoning_budget=0, **options,
            )
        finally:
            done.set()
            reporter.join()
        message = response["choices"][0]["message"]
        text = str(message.get("content") or message.get("reasoning_content") or "")
        elapsed = time.perf_counter() - started
        print(f"[StoryDirector] 生成完成：{len(text)} 字符，总耗时 {elapsed:.1f} 秒", flush=True)
        if not text.strip():
            raise RuntimeError("Qwen3.5 没有返回任何文本，请检查模型与 mmproj 是否匹配")
        return text

    def close(self):
        if self._llm is not None:
            close = getattr(self._llm, "close", None)
            if close:
                close()
        self._llm = None
        self._config = None


LLAMA = LocalLlama()
