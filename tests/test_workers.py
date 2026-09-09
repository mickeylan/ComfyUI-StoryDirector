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

    def test_missing_fields_and_wrong_count_are_actionable(self):
        issues = QWEN38.director_issues('{"segments":[]}', 4)
        self.assertIn("缺少 global_prompt", issues)
        self.assertIn("缺少 overall_soundscape", issues)
        self.assertIn("segments 必须恰好包含 4 项，实际为 0 项", issues)

    def test_invalid_json_is_rejected(self):
        self.assertEqual(QWEN35.director_issues("not json", 1), ["返回内容不是有效 JSON 对象"])


if __name__ == "__main__":
    unittest.main()
