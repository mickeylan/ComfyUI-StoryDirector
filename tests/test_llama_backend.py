import importlib.util
import json
import pathlib
import sys
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("storydirector_llama_backend_test", ROOT / "llama_backend.py")
BACKEND = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKEND)


class BackendDispatchTests(unittest.TestCase):
    def test_family_detection(self):
        self.assertEqual(BACKEND._qwen_family("Huihui-Qwen3.8-27B.gguf"), "qwen3.8")
        self.assertEqual(BACKEND._qwen_family("Huihui_Qwen3_8-27B.gguf"), "qwen3.8")
        self.assertEqual(BACKEND._qwen_family("Huihui-Qwen3.5-9B.gguf"), "qwen3.5")

    def test_qwen35_dispatch_is_unchanged(self):
        backend = BACKEND.LocalLlama()
        process = mock.Mock(returncode=0)
        process.communicate.return_value = (b'STORYDIRECTOR_RESULT={"text":"ok"}\n', b"")
        with mock.patch.object(backend, "_paths", return_value=("Qwen3.5.gguf", "mmproj-Qwen3.5.gguf")), \
             mock.patch.object(BACKEND.subprocess, "Popen", return_value=process) as popen:
            self.assertEqual(backend.complete({}, "system", "user"), "ok")
        self.assertTrue(popen.call_args.args[0][1].endswith("qwen35_worker.py"))
        request = json.loads(process.communicate.call_args.args[0].decode("ascii"))
        self.assertNotIn("mtp", request)
        self.assertNotIn("cpu_moe", request)

    def test_qwen38_uses_separate_worker(self):
        backend = BACKEND.LocalLlama()
        process = mock.Mock(returncode=0)
        process.communicate.return_value = (b'STORYDIRECTOR_RESULT={"text":"ok"}\n', b"")
        with mock.patch.object(backend, "_paths", return_value=("Qwen3.8.gguf", "mmproj-Qwen3.8.gguf")), \
             mock.patch.object(BACKEND.subprocess, "Popen", return_value=process) as popen:
            self.assertEqual(backend.complete({"qwen38": {"mtp": True, "mtp_draft_tokens": 4,
                                                            "reasoning_effort": "medium", "n_cpu_moe": 6}},
                                              "system", "user"), "ok")
        self.assertTrue(popen.call_args.args[0][1].endswith("qwen38_worker.py"))
        request = json.loads(process.communicate.call_args.args[0].decode("ascii"))
        self.assertEqual((request["mtp"], request["mtp_draft_tokens"], request["reasoning_effort"],
                          request["cpu_moe"], request["n_cpu_moe"]), (True, 4, "medium", False, 6))

    def test_mixed_model_and_projector_are_rejected(self):
        backend = BACKEND.LocalLlama()
        with mock.patch.object(backend, "_paths", return_value=("Qwen3.8.gguf", "mmproj-Qwen3.5.gguf")):
            with self.assertRaisesRegex(ValueError, "型号不匹配"):
                backend.complete({}, "system", "user")


if __name__ == "__main__":
    unittest.main()
