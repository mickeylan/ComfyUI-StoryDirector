from dataclasses import dataclass


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    display_name_zh: str
    description_zh: str
    positive_signals: tuple[str, ...]
    negative_signals: tuple[str, ...]
    director_rules_zh: str
    director_rules_en: str
    forbidden_assumptions: tuple[str, ...] = ()


_SKILL_DATA = (
    ("h3-prompt-writing", "通用 H3 提示词", "标准 H3 多模态提示词", (), (), "遵循 H3 模式、素材标签、字段顺序、时间戳、动作、运镜与声音规范。", "Follow H3 mode, reference-label, field-order, timestamp, action, camera, and audio rules.", ()),
    ("3d-animation-short-generator", "3D 动画短片", "角色驱动的连续动画叙事", ("3d动画", "3d 动画", "动画短片", "角色故事"), ("真人实拍",), "锁定角色造型、环境地标和空间关系；动作保持因果连续，表情、表演、镜头与声音共同推进叙事。", "Lock character design, environment landmarks, and spatial relations; preserve causal action, performance, camera, and audio continuity.", ("不得在无授权时使用真实 IP 角色",)),
    ("brand-promo-video-generator", "品牌宣传视频", "基于已知事实的品牌推广", ("品牌", "app", "网站", "发布", "推广", "cta"), (), "区分已验证事实与创意表现，按痛点、能力、使用场景、证据和行动号召组织镜头，并保持品牌视觉一致。", "Separate verified facts from creative treatment; structure shots around problem, capability, use case, proof, and CTA while preserving brand identity.", ("不得编造产品性能、价格、认证、销量或卖点", "无授权素材时不得使用真实品牌标识")),
    ("co-op-game-intro-generator", "双人游戏开场", "双人角色选择与菜单动画", ("双人合作", "player 1", "player 2", "游戏菜单", "角色选择"), (), "锁定两名玩家的身份、左右位置、角色卡、菜单层级和选择反馈，按事件顺序设计 UI 动画。", "Lock both player identities, left/right positions, cards, menu hierarchy, selection feedback, and event timing.", ("不得编造 UI 文案", "无授权时不得使用真实游戏品牌")),
    ("handdrawn-live-video-generator", "真人手绘融合", "真人空间与粗糙发光手绘动画融合", ("真人加手绘", "手绘线条", "发光线条", "追逐", "连续变形"), ("光滑cg", "恐怖跳跃"), "保持真人空间真实；手绘线条粗糙有机，接触与变形连续可追踪，手持镜头对事件略有延迟并自然追随。", "Keep the live-action space real; use rough organic drawn strokes, traceable contact and morphing, and slightly delayed handheld pursuit.", ("不得描述恐怖跳跃", "不得描述光滑 CG 或毛绒角色")),
    ("minimalist-product-ad-generator", "极简产品广告", "高级产品静物和电商展示", ("商品图", "电商", "极简广告", "产品广告", "产品特写", "静物广告"), (), "锁定产品外形、材质、颜色与结构，以干净背景、几何构图、受控反射和克制的微距、环绕、推近、英雄镜头展示产品。", "Lock product form, material, color, and structure; use clean backgrounds, geometric composition, controlled reflections, and restrained macro, orbit, push-in, and hero shots.", ("不得编造产品参数、性能或价格",)),
    ("music-video-subtitle-generator", "MV 与歌词字幕", "歌词、字幕与节拍驱动的音乐影像", ("歌词", "mv", "字幕", "节拍", "演唱"), (), "只使用用户提供的歌词，逐字保持；让镜头、表演、字幕层级和空间排布与节拍及演唱时间对应。", "Use only user-supplied lyrics verbatim; align shots, performance, typography hierarchy, and placement to beat and vocal timing.", ("不得编造、改写、翻译或扩写歌词",)),
    ("paper-collage-explainer-generator", "纸张拼贴解说", "二维纸张拼贴和视觉隐喻", ("拼贴", "半色调", "撕纸", "观点解释", "视觉隐喻"), (), "把抽象概念转为清晰视觉隐喻，使用撕纸边缘、半色调、纸张阴影、拼贴层级及触感定格运动。", "Translate abstract ideas into clear visual metaphors using torn edges, halftone texture, paper shadows, collage layers, and tactile stop-motion.", ("不得主动增加旁白、字幕或 BGM",)),
    ("papercraft-stop-motion-explainer", "纸艺定格科普", "立体纸艺、翻页机构和教学步骤", ("纸艺", "立体书", "纸板", "定格科普", "火山科普"), ("光滑cg",), "按学习目标分步骤展开，使用有厚度和纤维的纸材、折痕接缝、前中后景以及弹出、折叠、翻页、滑轨和转盘机构。", "Sequence the learning goal with tactile paper thickness, fibers, folds, seams, layered depth, and pop-up, fold, page-turn, slider, and rotating mechanisms.", ("不得描述光滑 CG 效果", "不得编造用户未提供的科学数据",)),
)

SKILL_IDS = tuple(item[0] for item in _SKILL_DATA)
SKILLS = {item[0]: SkillDefinition(*item) for item in _SKILL_DATA}
SKILL_OPTIONS_ZH = ("自动选择",) + tuple(item.display_name_zh for item in SKILLS.values())
DISPLAY_TO_ID = {item.display_name_zh: item.id for item in SKILLS.values()}


def skill_options():
    return [(skill_id, SKILLS[skill_id].display_name_zh) for skill_id in SKILL_IDS]


def get_skill(skill_id):
    return SKILLS.get(skill_id, SKILLS["h3-prompt-writing"])


def resolve_skill_option(value):
    text = str(value or "").strip()
    if text in SKILLS:
        return text
    return DISPLAY_TO_ID.get(text)


def build_auto_skill_prompt(lang):
    lines = []
    for skill in SKILLS.values():
        rules = skill.director_rules_zh if lang == "zh" else skill.director_rules_en
        forbidden = "; ".join(skill.forbidden_assumptions)
        lines.append(f"- {skill.id}: {skill.description_zh}; {rules}" + (f"; {forbidden}" if forbidden else ""))
    return ("根据故事和素材选择一个最合适的 Skill，并立即应用其规则生成 Director JSON。"
            "输出必须额外包含 selected_skill 和 skill_selection_reason；selected_skill 只能取以下 ID：\n" + "\n".join(lines))


def build_skill_system_prompt(skill_id, lang):
    skill = get_skill(skill_id)
    rules = skill.director_rules_zh if lang == "zh" else skill.director_rules_en
    forbidden = "\n".join(f"- {item}" for item in skill.forbidden_assumptions)
    heading = "禁止假设" if lang == "zh" else "Forbidden assumptions"
    return f"Skill ID: {skill.id}\n{rules}" + (f"\n\n## {heading}\n{forbidden}" if forbidden else "")
