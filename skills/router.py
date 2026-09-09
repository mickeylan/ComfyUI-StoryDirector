from .registry import SKILL_IDS, get_skill, resolve_skill_option


_PRIORITY = (
    "co-op-game-intro-generator",
    "minimalist-product-ad-generator",
    "brand-promo-video-generator",
    "music-video-subtitle-generator",
    "handdrawn-live-video-generator",
    "paper-collage-explainer-generator",
    "papercraft-stop-motion-explainer",
    "3d-animation-short-generator",
)


def route_by_rules(story, assets=()):
    text = " ".join((str(story or ""), *(str(item.get("description") or "") for item in assets))).casefold()
    for skill_id in _PRIORITY:
        skill = get_skill(skill_id)
        if any(signal.casefold() in text for signal in skill.negative_signals):
            continue
        matches = [signal for signal in skill.positive_signals if signal.casefold() in text]
        if matches:
            return skill_id, f"匹配制作特征：{matches[0]}"
    return "h3-prompt-writing", "未发现明确的专用制作类型"


def parse_skill_selection(value):
    text = str(value or "").strip().casefold()
    if text in SKILL_IDS:
        return text
    matches = [skill_id for skill_id in SKILL_IDS if skill_id in text]
    return matches[0] if len(matches) == 1 else "h3-prompt-writing"


def select_skill(option, story, assets=()):
    selected = resolve_skill_option(option)
    if selected:
        return selected, "用户手动选择"
    selected, reason = route_by_rules(story, assets)
    if selected == "h3-prompt-writing":
        return "auto", "未发现明确特征，交由本地 Qwen 判断"
    return selected, reason
