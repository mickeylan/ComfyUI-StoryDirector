import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


QWEN35 = load("qwen35_worker")
QWEN38 = load("qwen38_worker")


class WorkerResponseTests(unittest.TestCase):
    def test_valid_director_plan_has_no_issues(self):
        text = json.dumps({"global_prompt": "style", "overall_soundscape": "wind",
                           "segments": [{"prompt": "one"}, {"prompt": "two"}]})
        self.assertEqual(QWEN35.director_issues(text, 2), [])
        self.assertEqual(QWEN38.director_issues(text, 2), [])

    def test_prompt_language_ignores_fixed_h3_labels(self):
        chinese = "subject_definitions: <Subject 1> 是 <Picture 1> 中的成年女性，暖色电影灯光笼罩房间。"
        for worker in (QWEN35, QWEN38):
            self.assertEqual(worker.language_issue(chinese, "zh"), "")

    def test_missing_fields_and_wrong_count_are_actionable(self):
        issues = QWEN38.director_issues('{"segments":[]}', 4)
        self.assertIn("缺少 global_prompt", issues)
        self.assertIn("缺少 overall_soundscape", issues)
        self.assertIn("segments 必须恰好包含 4 项，实际为 0 项", issues)

    def test_executable_plan_allows_language_fallback(self):
        valid = json.dumps({"global_prompt": "English style", "overall_soundscape": "wind",
                            "segments": [{"prompt": "English action"}]})
        for worker in (QWEN35, QWEN38):
            self.assertTrue(worker.executable_plan(valid, 1))
            self.assertFalse(worker.executable_plan("not json", 1))
            self.assertFalse(worker.executable_plan('{"global_prompt":"x","overall_soundscape":"x","segments":[]}', 1))

    def test_wrapped_json_is_executable(self):
        wrapped = '<think>done</think>\n```json\n{"global_prompt":"风格描述完整","overall_soundscape":"环境声音完整","segments":[{"prompt":"镜头动作描述完整"}]}\n```'
        for worker in (QWEN35, QWEN38):
            self.assertTrue(worker.executable_plan(wrapped, 1))
            self.assertIsInstance(worker.extract_json(wrapped), dict)

    def test_invalid_json_is_rejected(self):
        self.assertEqual(QWEN35.director_issues("not json", 1), ["返回内容不包含有效 JSON 对象"])


if __name__ == "__main__":
    unittest.main()
