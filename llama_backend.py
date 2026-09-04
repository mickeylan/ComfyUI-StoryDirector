"""llama-cpp-python 本地模型适配器。"""

import os


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
        except (ImportError, KeyError):
            path = None
        if not path or not os.path.isfile(path) or os.path.splitext(path)[1].lower() != ".gguf":
            raise ValueError("所选模型必须是 models/LLM 中列出的 GGUF 文件")
        self.close()
        kwargs = {
            "model_path": path,
            "n_ctx": int(config.get("n_ctx", 8192)),
            "n_gpu_layers": int(config.get("n_gpu_layers", -1)),
            "verbose": False,
        }
        self._llm = Llama(**kwargs)
        self._config = config
        return self._llm

    def complete(self, config, system, user, seed=0, **params):
        llm = self.load(config)
        allowed = {"max_tokens", "temperature", "top_k", "top_p", "min_p", "repeat_penalty"}
        options = {k: v for k, v in params.items() if k in allowed and v is not None}
        result = llm.create_chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            seed=int(seed), **options,
        )
        return result["choices"][0]["message"]["content"]

    def close(self):
        if self._llm is not None:
            close = getattr(self._llm, "close", None)
            if close:
                close()
        self._llm = None
        self._config = None


LLAMA = LocalLlama()
