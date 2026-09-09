import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from skills import (SKILL_IDS, build_repair_prompt, build_skill_system_prompt, compile,
                    get_skill, output_issues, route_by_rules, select_skill)


class SkillIntegrationTests(unittest.TestCase):
    def test_all_skills_registered(self):
        self.assertEqual(len(SKILL_IDS), 9)
        for skill_id in SKILL_IDS:
            self.assertEqual(get_skill(skill_id).id, skill_id)
        self.assertEqual(get_skill("unknown").id, "h3-prompt-writing")

    def test_clear_routes_and_manual_override(self):
        self.assertEqual(route_by_rules("双人合作游戏菜单")[0], "co-op-game-intro-generator")
        self.assertEqual(route_by_rules("极简耳机产品广告")[0], "minimalist-product-ad-generator")
        self.assertEqual(route_by_rules("真人触碰发光手绘线条")[0], "handdrawn-live-video-generator")
        self.assertEqual(select_skill("品牌宣传视频", "普通街景")[0], "brand-promo-video-generator")
        self.assertEqual(route_by_rules("普通城市街景")[0], "h3-prompt-writing")

    def test_forbidden_assumptions_are_injected(self):
        self.assertIn("不得编造产品性能", build_skill_system_prompt("brand-promo-video-generator", "zh"))
        self.assertIn("不得编造、改写", build_skill_system_prompt("music-video-subtitle-generator", "zh"))

    def test_ref2va_compiler_and_contract(self):
        plan = {"global_prompt": "subject_definitions:\n<Subject 1> is the hero in <Picture 1>.\n\nretention_analysis:\n<Subject 1> remains consistent.",
                "overall_soundscape": "Wind and footsteps.", "non_diegetic_music": "N/A",
                "segments": [{"prompt": "The hero walks forward."}]}
        text = compile(plan, "ref2va", 8)
        self.assertEqual(output_issues(text, "ref2va", 8, {"image": 1}), [])
        self.assertIn("[Shot 1] The hero walks forward.", text)

    def test_skill_specific_quality_gates(self):
        from skills import skill_issues
        plan = {"global_prompt": "style", "overall_soundscape": "wind", "segments": [
            {"prompt": "Singer says: <d>[Chinese] 编造的歌词</d>"}]}
        self.assertTrue(skill_issues("music-video-subtitle-generator", plan, "用户没有提供歌词"))
        plan["segments"][0]["prompt"] = "产品续航 48小时，售价 999元"
        self.assertTrue(skill_issues("minimalist-product-ad-generator", plan, "展示耳机"))
        plan["segments"][0]["prompt"] = 'Menu shows “START GAME”'
        self.assertTrue(skill_issues("co-op-game-intro-generator", plan, "双人游戏菜单"))
        plan["segments"][0]["prompt"] = "smooth CG papercraft volcano"
        self.assertTrue(skill_issues("papercraft-stop-motion-explainer", plan, "纸艺火山"))

    def test_contract_reports_actionable_issues(self):
        issues = output_issues("```\noverall_soundscape: x", "ref2va", 8)
        self.assertTrue(any("必填字段" in issue for issue in issues))
        repair = build_repair_prompt(issues)
        self.assertIn("返回完整 Director JSON", repair)


if __name__ == "__main__":
    unittest.main()
