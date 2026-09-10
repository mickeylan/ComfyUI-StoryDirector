import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("storydirector_llama_runtime_test", ROOT / "llama_runtime.py")
RUNTIME = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNTIME)


class LlamaRuntimeTests(unittest.TestCase):
    def test_non_windows_does_not_load_dlls(self):
        with mock.patch.object(RUNTIME.sys, "platform", "linux"), \
             mock.patch.object(RUNTIME.ctypes, "WinDLL", create=True) as load:
            self.assertIsNone(RUNTIME.prepare_windows_llama_dlls())
        load.assert_not_called()

    def test_windows_loads_packaged_dlls_in_dependency_order(self):
        with tempfile.TemporaryDirectory() as directory:
            lib = pathlib.Path(directory) / "llama_cpp" / "lib"
            lib.mkdir(parents=True)
            for name in ("cudart64_13.dll", "cublas64_13.dll", "ggml-base.dll", "ggml-cuda.dll"):
                (lib / name).touch()
            handle = object()
            with mock.patch.object(RUNTIME.sys, "platform", "win32"), \
                 mock.patch.object(RUNTIME.sys, "path", [directory]), \
                 mock.patch.object(RUNTIME.os, "add_dll_directory", return_value=handle, create=True), \
                 mock.patch.object(RUNTIME.ctypes, "WinDLL", create=True) as load:
                self.assertEqual(RUNTIME.prepare_windows_llama_dlls(), lib)
        self.assertEqual([pathlib.Path(call.args[0]).name for call in load.call_args_list], [
            "cudart64_13.dll", "cublas64_13.dll", "ggml-base.dll", "ggml-cuda.dll",
        ])
        self.assertIn(handle, RUNTIME._DLL_DIRECTORY_HANDLES)

    def test_system_info_decodes_bytes(self):
        module = types.SimpleNamespace(
            llama_cpp=types.SimpleNamespace(llama_print_system_info=lambda: b"CUDA = 1")
        )
        self.assertEqual(RUNTIME.llama_system_info(module), "CUDA = 1")


if __name__ == "__main__":
    unittest.main()
