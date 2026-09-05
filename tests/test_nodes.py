import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

from PIL import Image

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
        self.assertEqual(NODES.normalize_assets([{"path": "../secret.png"}]), [])

    def test_mature_catalog_round_trip(self):
        catalog = NODES.mature_catalog({"images": [{"path": "story_director/hero.png", "type": "角色", "name": "hero"}],
                                        "videos": [{"path": "story_director/ref.mp4", "name": "ref"}]})
        self.assertEqual(catalog["images"][0]["name"], "hero")
        self.assertEqual(catalog["videos"][0]["type"], "主体")

    def test_director_plan_validation(self):
        value = {"global_prompt": "subject_definitions:\n<Subject 1> 是 <Picture 1> 中的女主。",
                 "overall_soundscape": "风声", "non_diegetic_music": "N/A",
                 "segments": [{"prompt": "女主向前走。"}, {"prompt": "镜头跟随她。"}]}
        self.assertEqual(NODES.validate_director_plan(value, 2), value)

    def test_director_plan_rejects_repeated_global_fields(self):
        value = {"global_prompt": "风格", "overall_soundscape": "风声",
                 "segments": [{"prompt": "subject_definitions: 重复"}]}
        with self.assertRaisesRegex(ValueError, "重复了全局字段"):
            NODES.validate_director_plan(value, 1)

    def test_extracts_json_from_model_wrappers(self):
        raw = '<think>ignore</think>\n```json\n{"global_prompt":"风格","overall_soundscape":"风声","segments":[{"prompt":"动作"}]}\n```'
        self.assertEqual(NODES.validate_director_plan(raw, 1)["segments"][0]["prompt"], "动作")

    def test_reference_contract_uses_enabled_image_order(self):
        plan = {"global_prompt": "古风", "overall_soundscape": "风声", "non_diegetic_music": "N/A", "segments": [{"prompt": "动作"}]}
        assets = NODES.normalize_assets([
            {"path": "story_director/a.png", "type": "image", "name": "女主"},
            {"path": "story_director/off.png", "type": "image", "name": "禁用", "enabled": False},
            {"path": "story_director/b.png", "type": "image", "name": "男主"},
        ])
        result = NODES.apply_reference_contract(plan, assets)["global_prompt"]
        self.assertIn("<Subject 1> is 女主 shown in <Picture 1>", result)
        self.assertIn("<Subject 2> is 男主 shown in <Picture 2>", result)
        self.assertNotIn("禁用", result)
        self.assertIn("retention_analysis:", result)

    def test_timeline_matches_minimax_director_schema(self):
        plan = {"global_prompt": "风格", "overall_soundscape": "风声", "non_diegetic_music": "N/A",
                "segments": [{"prompt": "第一镜"}, {"prompt": "第二镜"}]}
        timeline = NODES.build_timeline_data(plan, 5)
        self.assertEqual(timeline["reference_mode"], "REF2VA")
        self.assertEqual(timeline["prompt_format"], "minimax")
        self.assertEqual(timeline["global_prompt"], "风格")
        self.assertEqual((timeline["normalStartFrame"], timeline["normalDurationFrames"]), (0, 240))
        self.assertEqual([(x["start"], x["length"]) for x in timeline["segments"]], [(0, 120), (120, 120)])
        self.assertEqual([x["prompt"] for x in timeline["segments"]], ["第一镜", "第二镜"])

    def test_material_numbering_uses_enabled_media_order(self):
        assets = NODES.normalize_assets([
            {"path": "story_director/a.png", "type": "image", "name": "女主"},
            {"path": "story_director/off.png", "type": "image", "name": "禁用", "enabled": False},
            {"path": "story_director/b.png", "type": "image", "name": "男主"},
        ])
        prompt = NODES.build_director_prompt("相遇", "拆解模式 (Decompose)", "古风武侠", "4段", "zh", 5, assets)
        self.assertIn("<Picture 1>: 女主", prompt)
        self.assertIn("<Picture 2>: 男主", prompt)
        self.assertNotIn("禁用", prompt)

    def test_last_processed_director_data_is_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / "last.json"
            with mock.patch.object(NODES, "_last_processed_file", return_value=str(target)):
                NODES._save_last_processed_script("总提示词", '{"segments":[]}', {"assets": []})
                result = NODES.load_last_processed_script()
        self.assertEqual(result["global_prompt"], "总提示词")

    def test_reference_images_keep_enabled_order_and_common_canvas(self):
        with tempfile.TemporaryDirectory() as directory:
            Image.new("RGB", (200, 100), (255, 0, 0)).save(pathlib.Path(directory) / "a.png")
            Image.new("RGB", (100, 200), (0, 255, 0)).save(pathlib.Path(directory) / "b.png")
            folder_paths = types.ModuleType("folder_paths")
            folder_paths.get_input_directory = lambda: directory
            assets = NODES.normalize_assets([
                {"path": "story_director/a.png", "type": "image", "name": "A"},
                {"path": "story_director/off.png", "type": "image", "name": "off", "enabled": False},
                {"path": "story_director/b.png", "type": "image", "name": "B"},
            ])
            managed = pathlib.Path(directory) / "story_director"
            managed.mkdir()
            (pathlib.Path(directory) / "a.png").replace(managed / "a.png")
            (pathlib.Path(directory) / "b.png").replace(managed / "b.png")
            with mock.patch.dict(sys.modules, {"folder_paths": folder_paths}):
                images = NODES.load_reference_images(assets)
        self.assertEqual(tuple(images.shape), (2, 100, 200, 3))
        self.assertGreater(float(images[0, 50, 100, 0]), 0.99)
        self.assertGreater(float(images[1, 50, 100, 1]), 0.99)

    def test_node_contract_preserves_input_order(self):
        schema = NODES.StoryDirector.INPUT_TYPES()
        self.assertEqual(list(schema["required"])[-2:], ["director_state", "llm_mmproj"])
        self.assertEqual(NODES.StoryDirector.RETURN_NAMES,
                         ("总提示词", "MiniMaxH3 Director 时间线 JSON", "素材目录 JSON", "参考图片"))
        self.assertEqual(list(NODES.NODE_CLASS_MAPPINGS), ["StoryDirector"])

    def test_offline_node_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / "last.json"
            with mock.patch.object(NODES, "_last_processed_file", return_value=str(target)):
                with mock.patch.object(NODES, "load_reference_images", return_value="images"):
                    global_prompt, timeline_json, catalog, images = NODES.StoryDirector().direct(
                    story="门打开。侦探走入。", prompt_override="", mode="离线预览",
                    story_style="悬疑推理", segment_count="4段", segment_duration=5,
                    prompt_lang="中文 [ZH]", preference="推镜", custom_rules="", enhance=False,
                    llm_model="未选择 Qwen3.5 GGUF", llm_mmproj="未选择 Qwen3.5 mmproj",
                    context_size=32768, gpu_layers=-1, max_tokens=8192, temperature=0.6,
                    top_k=40, top_p=0.9, min_p=0.05, repeat_penalty=1.05, seed=0,
                        director_state='{"assets": []}')
        self.assertTrue(global_prompt)
        self.assertEqual(images, "images")
        self.assertEqual(len(json.loads(timeline_json)["segments"]), 4)
        self.assertEqual(json.loads(catalog), {"images": [], "videos": [], "audios": []})


if __name__ == "__main__":
    unittest.main()
