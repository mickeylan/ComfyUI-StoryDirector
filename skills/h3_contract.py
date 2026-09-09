import re


REF_FIELDS = (
    "subject_definitions:",
    "summary:",
    "retention_analysis:",
    "detailed_description:",
    "overall_soundscape:",
    "non_diegetic_music:",
)
BASE_FIELDS = ("integrated_multimodal_description:", "overall_soundscape:", "non_diegetic_music:")
TIMESTAMP_RE = re.compile(r"\bAt\s+(\d{2}):(\d{2})\.(\d{3})\b")
INTERACTIVE_PATTERNS = (
    re.compile(r"(?i)\bplease\s+(?:confirm|reply|provide|upload|choose|answer)\b"),
    re.compile(r"请(?:确认|回复|提供|上传|选择|回答)"),
    re.compile(r"等待(?:你|您|用户)?(?:确认|回复)"),
    re.compile(r"(?im)^\s*(?:#{1,6}\s*)?(?:questions?|next steps?|approval|confirmation)\b"),
)
REFERENCE_RE = re.compile(r"<(Picture|Video|Audio|Subject)\s+(\d+)>")


def output_issues(text, mode, duration, asset_counts=None):
    value = str(text or "").strip()
    if not value:
        return ["输出为空"]
    issues = []
    if "```" in value:
        issues.append("移除 Markdown 代码块")
    if any(pattern.search(value) for pattern in INTERACTIVE_PATTERNS):
        issues.append("移除提问、确认、审批和下一步请求")
    fields = REF_FIELDS if str(mode).casefold() == "ref2va" else BASE_FIELDS
    positions = [value.find(field) for field in fields]
    missing = [field for field, position in zip(fields, positions) if position < 0]
    if missing:
        issues.append("缺少必填字段：" + ", ".join(missing))
    elif positions != sorted(positions):
        issues.append("H3 字段顺序错误")
    previous = -1.0
    for match in TIMESTAMP_RE.finditer(value):
        timestamp = int(match.group(1)) * 60 + int(match.group(2)) + int(match.group(3)) / 1000
        if timestamp <= previous:
            issues.append("镜头时间戳必须严格递增")
            break
        if timestamp >= float(duration):
            issues.append(f"镜头时间戳 {timestamp:.3f}s 超出 {float(duration):.3f}s")
            break
        previous = timestamp
    if asset_counts:
        limits = {"Picture": int(asset_counts.get("image", 0)), "Video": int(asset_counts.get("video", 0)),
                  "Audio": int(asset_counts.get("audio", 0))}
        for kind, number in REFERENCE_RE.findall(value):
            if kind in limits and int(number) > limits[kind]:
                issues.append(f"引用不存在：<{kind} {number}>")
    return list(dict.fromkeys(issues))


def director_plan_issues(plan, expected_count=None):
    if not isinstance(plan, dict):
        return ["Director 结果必须是 JSON 对象"]
    issues = []
    for field in ("global_prompt", "overall_soundscape"):
        if not str(plan.get(field) or "").strip():
            issues.append(f"缺少 {field}")
    segments = plan.get("segments")
    if not isinstance(segments, list) or not segments:
        issues.append("缺少 segments")
        return issues
    if expected_count is not None and len(segments) != int(expected_count):
        issues.append(f"分镜数量应为 {int(expected_count)}，实际为 {len(segments)}")
    for index, segment in enumerate(segments, 1):
        if not isinstance(segment, dict) or not str(segment.get("prompt") or "").strip():
            issues.append(f"第 {index} 个分镜缺少 prompt")
    return issues


def skill_issues(skill_id, plan, user_story):
    text = "\n".join((str(plan.get("global_prompt") or ""), str(plan.get("overall_soundscape") or ""),
                      str(plan.get("non_diegetic_music") or ""),
                      *(str(item.get("prompt") or "") for item in plan.get("segments") or () if isinstance(item, dict))))
    source = str(user_story or "")
    issues = []
    if skill_id == "music-video-subtitle-generator":
        for block in re.findall(r"<d>\s*(?:\[[^]]+\]\s*)?(.*?)\s*</d>", text, re.DOTALL | re.IGNORECASE):
            lyric = re.sub(r"\s+", " ", block).strip()
            if lyric and lyric not in re.sub(r"\s+", " ", source):
                issues.append("MV 中的歌词或对白必须逐字来自用户故事")
                break
    if skill_id in {"minimalist-product-ad-generator", "brand-promo-video-generator"}:
        source_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\s*(?:%|元|美元|万|亿|kg|g|mm|cm|mah|hz|小时|分钟)?", source, re.IGNORECASE))
        output_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\s*(?:%|元|美元|万|亿|kg|g|mm|cm|mah|hz|小时|分钟)", text, re.IGNORECASE))
        if output_numbers - source_numbers:
            issues.append("产品或品牌的数字参数、价格和业绩必须来自用户故事")
    if skill_id == "co-op-game-intro-generator":
        quoted = re.findall(r'["“]([^"”]{2,80})["”]', text)
        if any(value not in source for value in quoted):
            issues.append("游戏 UI 文案必须来自用户故事")
    lowered = text.casefold()
    if skill_id == "paper-collage-explainer-generator":
        if not re.search(r"(?:旁白|字幕|bgm|background music|voiceover|subtitle)", source, re.IGNORECASE) and re.search(r"(?:旁白|字幕|voiceover|subtitle)", text, re.IGNORECASE):
            issues.append("纸张拼贴未获用户要求时不得增加旁白或字幕")
    if skill_id == "papercraft-stop-motion-explainer" and re.search(r"(?:smooth\s+(?:cg|3d)|光滑\s*(?:cg|3d))", lowered):
        issues.append("纸艺定格不得描述为光滑 CG")
    if skill_id == "handdrawn-live-video-generator" and re.search(r"(?:smooth\s+(?:cg|3d)|polished\s+(?:cg|3d)|光滑\s*(?:cg|3d))", lowered):
        issues.append("真人手绘融合不得描述为光滑 CG")
    return list(dict.fromkeys(issues))


def build_repair_prompt(issues):
    lines = "\n".join(f"{index}. {issue}" for index, issue in enumerate(issues, 1))
    return f"返回的 Director JSON 不合格，请只修复以下问题：\n{lines}\n返回完整 Director JSON，不要解释，不要理由。"
