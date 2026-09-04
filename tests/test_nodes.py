import importlib.util
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).parents[1]
PACKAGE = types.ModuleType("storydirector_test")
PACKAGE.__path__ = [str(ROOT)]
sys.modules.setdefault("storydirector_test", PACKAGE)
SPEC = importlib.util.spec_from_file_location("storydirector_test.nodes", ROOT / "nodes.py")
NODES = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = NODES
SPEC.loader.exec_module(NODES)


class StoryDirectorTests(unittest.TestCase):
    def test_filename_and_type(self):
        self.assertEqual(NODES.normalize_filename("../角色 图.png"), "asset.png")
        self.assertEqual(NODES.asset_type("clip.MP4"), "video")
        with self.assertRaises(ValueError):
            NODES.asset_type("payload.exe")

    def test_assets_are_confined_and_ordered(self):
        assets = NODES.normalize_assets([
            {"path": "story_director/a.png", "name": "角色A", "role": "角色"},
            {"path": "../secret.png", "name": "bad"},
            {"path": "story_director/b.wav", "enabled": False},
        ])
        self.assertEqual([asset["order"] for asset in assets], [0, 1])
        self.assertEqual([asset["type"] for asset in assets], ["image", "audio"])
        self.assertEqual(assets[0]["role"], "角色")

    def test_fallback_uses_native_shot_markers(self):
        state = {"assets": [], "segment_count": 3, "segment_duration": 2.5, "style": "电影感"}
        prompt = NODES.compile_fallback("角色进门。灯光熄灭。", state)
        self.assertTrue(prompt.startswith("[Shot 1] |"))
        self.assertIn("[Shot 2] At 00:02.500", prompt)
        self.assertIn("[Shot 3] At 00:05.000", prompt)
        self.assertEqual(NODES.validate_prompt(prompt, 3), prompt)

    def test_validation_rejects_bad_timing_and_fields(self):
        valid = NODES.compile_fallback("A。B。", {"assets": [], "segment_count": 2, "segment_duration": 3})
        with self.assertRaises(ValueError):
            NODES.validate_prompt(valid.replace("[Shot 2] At 00:03.000", "[Shot 2]"), 2)
        with self.assertRaises(ValueError):
            NODES.validate_prompt(valid.replace("Action:", "Movement:"), 2)
        with self.assertRaises(ValueError):
            NODES.validate_prompt(valid.replace("[Shot 1]", "[Shot 1] At 00:00.000"), 2)

    def test_llm_request_has_semantic_assets_not_paths(self):
        state = {
            "assets": [{"name": "女主", "type": "image", "role": "角色", "description": "金发蓝眼", "path": "story_director/a.png", "enabled": True}],
            "segment_count": 2,
            "segment_duration": 4,
        }
        system, user = NODES.compose_llm_request("她进入房间", state)
        self.assertIn("[Shot 1]", system)
        self.assertIn("女主", user)
        self.assertNotIn("story_director/a.png", user)

    def test_only_one_node_is_registered(self):
        self.assertEqual(list(NODES.NODE_CLASS_MAPPINGS), ["StoryDirector"])


if __name__ == "__main__":
    unittest.main()
