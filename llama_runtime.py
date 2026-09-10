"""Windows llama.cpp CUDA runtime preparation and diagnostics."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys


_WINDOWS_DLL_ORDER = (
    "cudart64_13.dll",
    "cublasLt64_13.dll",
    "cublas64_13.dll",
    "cudart64_12.dll",
    "cublasLt64_12.dll",
    "cublas64_12.dll",
    "ggml-base.dll",
    "ggml.dll",
    "ggml-cpu.dll",
    "ggml-cuda.dll",
)
_DLL_DIRECTORY_HANDLES = []


def prepare_windows_llama_dlls():
    """Load packaged CUDA/ggml DLLs in dependency order before importing llama_cpp."""
    if sys.platform != "win32":
        return None
    for entry in sys.path:
        lib_dir = Path(entry) / "llama_cpp" / "lib"
        if not (lib_dir / "ggml-base.dll").is_file():
            continue
        handle = os.add_dll_directory(str(lib_dir))
        _DLL_DIRECTORY_HANDLES.append(handle)
        loaded = []
        for name in _WINDOWS_DLL_ORDER:
            path = lib_dir / name
            if path.is_file():
                ctypes.WinDLL(str(path))
                loaded.append(name)
        print(f"[StoryDirector] llama.cpp DLL directory: {lib_dir}", flush=True)
        print(f"[StoryDirector] preloaded DLLs: {', '.join(loaded)}", flush=True)
        return lib_dir
    print("[StoryDirector] WARNING: llama_cpp/lib with ggml-base.dll was not found on sys.path", flush=True)
    return None


def llama_system_info(llama_cpp_module):
    """Return llama.cpp backend information without failing inference diagnostics."""
    try:
        value = llama_cpp_module.llama_cpp.llama_print_system_info()
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        return str(value or "").strip()
    except Exception as error:
        return f"unavailable: {error}"
