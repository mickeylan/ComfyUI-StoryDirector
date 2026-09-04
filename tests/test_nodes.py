import importlib.util
import pathlib
import sys
import types
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]
PACKAGE = types.ModuleType("storydirector_test")
PACKAGE.__path__ = [str(ROOT)]
sys.modules.setdefault("storydirector_test", PACKAGE)
SPEC = importlib.util.spec_from_file_location("storydirector_test.nodes", ROOT / "nodes.py")
NODES = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = NODES
SPEC.loader.exec_module(NODES)


class StoryDirectorTests(unittest.TestCase):
    def test_filename_and_asset_containment(self):
        self.assertEqual(NODES.normalize_filename("../bad name?.png"), "bad_name.png")
        assets = NODES.normalize_assets([{"path": "story_director/hero.png", "role": "角色"}])
        self.assertEqual(assets[0]["role"], "角色")
        self.assertEqual(NODES.normalize_assets([{"path": "../secret.png"}]), [])

    def test_mature_catalog_round_trip(self):
        catalog = NODES.mature_catalog({"images": [{"path": "story_director/hero.png", "type": "角色", "name": "hero"}],
                                        "videos": [{"path": "story_director/ref.mp4", "name": "ref"}]})
        self.assertEqual([a["name"] for a in catalog["images"]], ["hero"])
        self.assertEqual(catalog["videos"][0]["type"], "其他")

    def test_fallback_uses_h3_block_contract(self):
        state = {"segment_count": "2", "preference": "推镜"}
        prompt = NODES.compile_fallback("门打开。有人走入。", state)
        self.assertEqual(len(prompt.split("[SHOT_START]")) - 1, 2)
        self.assertIn("===H3_PROMPT===", prompt)
        self.assertIn("===AUDIO_INSTRUCTION===", prompt)
        self.assertEqual(NODES.validate_script(prompt, 2), prompt)

    def test_validation_rejects_incomplete_script(self):
        with self.assertRaises(ValueError):
            NODES.validate_script("[SHOT_START]\n===H3_PROMPT===\npartial", 1)

    def test_last_processed_script_is_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / "last.json"
            with mock.patch.object(NODES, "_last_processed_file", return_value=str(target)):
                NODES._save_last_processed_script("script", {"assets": []})
                self.assertEqual(NODES.load_last_processed_script()["script"], "script")

    def test_only_one_node_is_registered(self):
        self.assertEqual(list(NODES.NODE_CLASS_MAPPINGS), ["StoryDirector"])


if __name__ == "__main__":
    unittest.main()
