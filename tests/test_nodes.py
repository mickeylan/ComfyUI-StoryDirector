import importlib.util
import json
import pathlib
import re
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
        self.assertEqual(catalog["videos"][0]["type"], "主体")

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
        valid = NODES.compile_fallback("门打开。", {"segment_count": "1"})
        with self.assertRaises(ValueError):
            NODES.validate_script(valid.replace("overall_soundscape:", "soundscape:"), 1)

    def test_uploaded_assets_get_semantic_defaults(self):
        assets = NODES.normalize_assets([
            {"path": "story_director/hero.png", "type": "image"},
            {"path": "story_director/move.mp4", "type": "video"},
            {"path": "story_director/voice.wav", "type": "audio"},
        ])
        self.assertEqual([asset["role"] for asset in assets], ["角色", "主体", "音色"])
        self.assertEqual([asset["name"] for asset in assets], ["hero", "move", "voice"])

    def test_material_intros_keep_media_groups(self):
        assets = NODES.normalize_assets([
            {"path": "story_director/hero.png", "type": "image", "role": "角色", "name": "女主", "description": "红衣"},
            {"path": "story_director/move.mp4", "type": "video", "name": "追逐运镜"},
            {"path": "story_director/voice.wav", "type": "audio", "name": "女主音色"},
        ])
        image, video, audio = NODES._material_intros(assets)
        self.assertIn("角色A = 女主", image)
        self.assertIn("视频A = 追逐运镜", video)
        self.assertIn("音频A = 女主音色", audio)

    def test_enhancer_replaces_only_detail(self):
        block = NODES.compile_fallback("门打开。", {"segment_count": "1"})
        changed = NODES._replace_detailed_description(block, "新的镜头描述")
        self.assertIn("detailed_description: 新的镜头描述", changed)
        self.assertIn("overall_soundscape: 环境声与动作声", changed)

    def test_last_processed_script_is_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / "last.json"
            with mock.patch.object(NODES, "_last_processed_file", return_value=str(target)):
                NODES._save_last_processed_script("script", {"assets": []})
                self.assertEqual(NODES.load_last_processed_script()["script"], "script")

    def test_full_story_style_catalog_is_exposed(self):
        expected = {"热血战斗", "悬疑推理", "温馨日常", "奇幻冒险", "科幻未来", "古风武侠", "都市情感", "恐怖惊悚", "末日废土", "黑色电影", "校园青春", "历史权谋", "修仙问道", "逆袭打脸", "歌神舞台", "穿越重生", "霸总甜宠", "乡村喜剧", "谍战风云"}
        styles = NODES.StoryDirector.INPUT_TYPES()["required"]["story_style"][0]
        self.assertEqual(set(styles), expected)
        self.assertEqual(len(styles), 19)

    def test_only_one_node_is_registered(self):
        self.assertEqual(list(NODES.NODE_CLASS_MAPPINGS), ["StoryDirector"])
        self.assertTrue(NODES.StoryDirector.OUTPUT_NODE)
        schema = NODES.StoryDirector.INPUT_TYPES()
        self.assertIn("director_state", schema["required"])
        self.assertNotIn("hidden", schema)

    def test_offline_node_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / "last.json"
            with mock.patch.object(NODES, "_last_processed_file", return_value=str(target)):
                script, catalog = NODES.StoryDirector().direct(
                    story="门打开。侦探走入。", prompt_override="", mode="离线预览",
                    story_style="悬疑推理", segment_count="4段", segment_duration=5,
                    prompt_lang="中文 [ZH]", preference="推镜", custom_rules="", enhance=False,
                    llm_model="未选择本地 GGUF", context_size=32768, gpu_layers=-1,
                    max_tokens=8192, temperature=0.6, top_k=40, top_p=0.9,
                    min_p=0.05, repeat_penalty=1.05, seed=0,
                    director_state='{"assets": []}')
        self.assertEqual(len(re.findall(r"\[SHOT_START\]", script)), 4)
        self.assertEqual(json.loads(catalog), {"images": [], "videos": [], "audios": []})


if __name__ == "__main__":
    unittest.main()
