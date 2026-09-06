"""Qwen3.5 local backend using a disposable llama-cpp-python worker."""

import json
import os
import subprocess
import sys
import threading
import time

RESULT_PREFIX = "STORYDIRECTOR_RESULT="


def _qwen_family(path):
    name = os.path.basename(path).casefold().replace("-", "").replace("_", "")
    return "qwen3.8" if "qwen38" in name or "qwen3.8" in name else "qwen3.5"


class LocalLlama:
    def _paths(self, config):
        try:
            import folder_paths
            model_path = folder_paths.get_full_path("LLM", config.get("model", ""))
            mmproj_path = folder_paths.get_full_path("LLM", config.get("mmproj", ""))
        except (ImportError, KeyError):
            model_path = None
            mmproj_path = None
        if not model_path or not os.path.isfile(model_path) or os.path.splitext(model_path)[1].lower() != ".gguf":
            raise ValueError("所选模型必须是 models/LLM 中列出的 Qwen3.5 GGUF 文件")
        if not mmproj_path or not os.path.isfile(mmproj_path) or os.path.splitext(mmproj_path)[1].lower() != ".gguf":
            raise ValueError("Qwen3.5 必须选择 models/LLM 中配套的 mmproj GGUF 文件")
        return model_path, mmproj_path

    def complete(self, config, system, user, seed=0, image_paths=(), **params):
        model_path, mmproj_path = self._paths(config)
        family = _qwen_family(model_path)
        if _qwen_family(mmproj_path) != family:
            raise ValueError(f"{family} 主模型与 mmproj 型号不匹配")
        allowed = {"max_tokens", "temperature", "top_k", "top_p", "min_p", "repeat_penalty"}
        options = {key: value for key, value in params.items() if key in allowed and value is not None}
        request = {
            "model_path": model_path,
            "mmproj_path": mmproj_path,
            "n_ctx": int(config.get("n_ctx", 65536)),
            "system": system,
            "user": user,
            "seed": int(seed),
            "image_paths": list(image_paths),
            "params": options,
        }
        print(f"[StoryDirector] 启动独立 {family.replace('qwen', 'Qwen')} 进程：{os.path.basename(model_path)}", flush=True)
        print(f"[StoryDirector] 提交 {len(image_paths)} 张参考图，最大输出 {options.get('max_tokens', '默认')} tokens", flush=True)
        worker = os.path.join(os.path.dirname(__file__), "qwen38_worker.py" if family == "qwen3.8" else "qwen35_worker.py")
        process = subprocess.Popen(
            [sys.executable, worker], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        started = time.perf_counter()
        done = threading.Event()

        def heartbeat():
            while not done.wait(15):
                print(f"[StoryDirector] {family.replace('qwen', 'Qwen')} 仍在生成，已耗时 {time.perf_counter() - started:.1f} 秒", flush=True)

        reporter = threading.Thread(target=heartbeat, daemon=True)
        reporter.start()
        try:
            stdout_bytes, stderr_bytes = process.communicate(json.dumps(request, ensure_ascii=True).encode("ascii"))
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
        finally:
            done.set()
            reporter.join()
        if stderr.strip():
            print(stderr.rstrip(), flush=True)
        if process.returncode != 0:
            raise RuntimeError(f"{family.replace('qwen', 'Qwen')} 独立进程失败（退出码 {process.returncode}）：{stderr.strip()[-2000:]}")
        result_line = next((line for line in reversed(stdout.splitlines()) if line.startswith(RESULT_PREFIX)), None)
        if result_line is None:
            raise RuntimeError(f"{family.replace('qwen', 'Qwen')} 独立进程没有返回结果")
        text = str(json.loads(result_line[len(RESULT_PREFIX):]).get("text") or "")
        print(f"[StoryDirector] 生成完成：{len(text)} 字符，总耗时 {time.perf_counter() - started:.1f} 秒", flush=True)
        if not text.strip():
            raise RuntimeError(f"{family.replace('qwen', 'Qwen')} 没有返回任何文本，请检查模型与 mmproj 是否匹配")
        return text

    def close(self):
        pass


LLAMA = LocalLlama()
