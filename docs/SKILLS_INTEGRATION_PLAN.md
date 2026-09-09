# StoryDirector 融合 MiniMax H3 Skills 详细实施方案

> 目标：StoryDirector 负责交互、素材管理和多镜头时间线；9 个 H3 Skills 负责导演方法、风格设计和最终 H3 提示词规范。
>
> 版本：v0.2 | 日期：2026-09-09

---

## 一、总体判断

`ComfyUI_Qwen_H3_Prompt` 最有价值的部分不是本地 Qwen 推理，而是它完整保留了 MiniMax H3 官方的 **9 个 Skills**。StoryDirector 已经具备更完整的交互、素材和时间线能力，两者的融合方向应为：

> **StoryDirector 作为导演台和分镜规划器；9 个 H3 Skills 作为内部导演大脑。**

不是增加第二个节点，不是并存两套推理后端，也不是把官方 Skill 原文整块塞进 system prompt。

---

## 二、9 个 Skills 的正确定位

这 9 个 Skill 不是同一层级，需要区分对待。

### 2.1 基础能力 Skill：`h3-prompt-writing`

这是整个体系的基础编译器，负责：

- H3 五种输入模式（T2VA、I2VA、FL2VA、L2VA、Ref2VA）
- 图片、视频、音频引用编号
- 首帧、尾帧和参考素材语义
- H3 标准字段（integrated_multimodal_description、overall_soundscape、non_diegetic_music 等）
- 时间戳和镜头描述
- 环境声、动作声和非画面音乐
- 最终 prompt 格式

**定位：** 不作为普通风格选项。它是 StoryDirector 所有生成结果最终必须经过的统一 **H3 编译层**。无论选择产品广告、3D 动画还是纸艺科普，最终都由 `h3-prompt-writing` 规范化为 H3 可执行提示词。

### 2.2 八个垂直导演类型 Skills

| Skill ID | 适用场景 | 核心导演知识 |
|---|---|---|
| `3d-animation-short-generator` | 角色故事、3D 动画短片、连续剧情、多场景叙事 | 角色造型锁定、环境连续性、动作因果、表情与表演、镜头连续性 |
| `brand-promo-video-generator` | 品牌宣传、App/网站介绍、商业推广、产品发布 | 品牌事实与创意分离、禁止虚构卖点、痛点—能力—场景—CTA 结构、品牌视觉一致性 |
| `co-op-game-intro-generator` | 双人游戏、角色选择界面、游戏菜单动画、玩家卡片 | 两个角色身份锁定、Player 1/2 布局、UI 动画时序、选择状态与按钮反馈 |
| `handdrawn-live-video-generator` | 真人加手绘、发光线条、物理接触、连续变形、手持追逐 | 真人空间保持真实、手绘粗糙有机感、摄像机反应略晚于事件、手持跟随和追逐运动 |
| `minimalist-product-ad-generator` | 电商产品展示、极简广告、高级静物、产品发布 | 产品身份与材质锁定、干净背景、几何构图、受控反射、微距/环绕/推近/英雄镜头 |
| `music-video-subtitle-generator` | MV、歌词视频、字幕驱动短片、音乐情绪片 | 歌词必须来自用户、歌词与镜头映射、节拍同步、字幕层级与空间关系、高潮间奏结尾结构 |
| `paper-collage-explainer-generator` | 观点解释、知识讲解、抽象概念可视化、旁白配画面 | 将抽象概念变为视觉隐喻、撕纸边缘、半色调印刷、拼贴层级、纸张滑动与替换 |
| `papercraft-stop-motion-explainer` | 教育科普、科学解释、手工纸艺、立体书、微缩景观 | 学习目标分步骤展开、纸艺角色与道具、分层立体布景、弹出/折叠/翻页/旋转机构 |

### 2.3 Skill 之间的关键区分

- **产品广告类**：`brand-promo`（品牌故事 + CTA）vs `minimalist-product-ad`（产品本身 + 高级镜头）
- **纸艺类**：`paper-collage`（二维观点 + 隐喻）vs `papercraft-stop-motion`（三维纸艺空间 + 教学步骤）
- **真人混合**：`handdrawn-live`（单场景接触 + 追逐）不是全 CG，不是恐怖，不追求多场景
- **游戏类**：`co-op-game-intro` 专用性最强，只有出现双人/玩家卡/菜单时才能选

---

## 三、融合后的总体架构

建立四层结构：

```
用户故事与素材
       ↓
导演路由层（自动或手动选择 Skill）
       ↓
垂直 Skill 导演层（应用导演规则和禁止假设）
       ↓
StoryDirector 分镜规划层（生成 Director JSON + 时间线）
       ↓
h3-prompt-writing 编译层（统一 H3 格式）
       ↓
H3 Director JSON / 时间线 JSON / 素材目录 JSON
```

---

## 四、节点 UI 设计

### 4.1 不增加第二个节点

继续使用唯一的 `StoryDirector 故事导演` 节点。用户不需要知道内部实现了什么 Skills。

### 4.2 新增"导演 Skill"选项

在"剧本拆解配置"面板增加一个 Combo 输入：

```
导演 Skill：
├── 自动选择
├── 通用 H3 提示词
├── 3D 动画短片
├── 品牌宣传视频
├── 双人游戏开场
├── 真人手绘融合
├── 极简产品广告
├── MV 与歌词字幕
├── 纸张拼贴解说
└── 纸艺定格科普
```

内部使用稳定的英文 Skill ID，显示使用中文翻译。

默认值：`自动选择`

### 4.3 Skill 选择结果展示

在生成结果面板显示只读信息，不进入最终 prompt：

```
本次导演策略：3D 动画短片
选择原因：故事包含多个持续出场角色及连续叙事场景
```

### 4.4 Skill 与故事风格的关系

两者不是同一个概念：

- **Skill**：生产方法和导演结构
- **故事风格**：美术与类型风格

示例组合：

```
Skill：3D 动画短片
故事风格：古风武侠
```

```
Skill：纸张拼贴解说
故事风格：科幻未来
```

不能互相替换。

### 4.5 优先级规则

```
用户自定义规则
    >
用户明确故事要求
    >
素材事实
    >
用户镜头偏好
    >
选定 Skill 导演规则
    >
故事风格默认规则
```

示例：

- Skill 推荐配乐，但用户要求无背景音乐 → 服从用户
- 产品广告 Skill 推荐文案，但用户没有提供文案 → 不得自行编造
- 3D 动画 Skill 推荐多镜头，但用户要求一镜到底 → 服从用户
- MV Skill 推荐歌词字幕，但用户没有提供歌词 → 不生成歌词

---

## 五、Skill 文件落地方案

在 StoryDirector 新增目录结构：

```
skills/
├── __init__.py
├── registry.py           # Skill 注册表
├── router.py             # 自动路由
├── h3_compiler.py        # h3-prompt-writing 编译层
├── h3_contract.py        # H3 格式验证
├── h3-prompt-writing/
│   ├── SKILL.md
│   └── references/
│       ├── base-en.txt
│       └── ref-en.txt
├── 3d-animation-short-generator/
│   └── SKILL.md          # 本地化后的导演规则
├── brand-promo-video-generator/
├── co-op-game-intro-generator/
├── handdrawn-live-video-generator/
├── minimalist-product-ad-generator/
├── music-video-subtitle-generator/
├── paper-collage-explainer-generator/
└── papercraft-stop-motion-explainer/
```

### 5.1 Skill 本地化原则

官方 Skill 包含 MiniMax Hub 特有流程（向用户提问、素材收集、选择卡、审批门槛、调用生成工具等），StoryDirector 没有这些工具且是一次节点执行。

需要对每个 Skill 进行本地适配，分成三个部分：

```python
@dataclass(frozen=True)
class SkillDefinition:
    id: str
    display_name_zh: str
    description_zh: str

    # 路由信号
    positive_signals: tuple[str, ...]    # 适合的典型描述
    negative_signals: tuple[str, ...]    # 不适合的典型描述

    # 导演规则（已移除 Hub 特有流程）
    director_rules_zh: str
    director_rules_en: str

    # 禁止假设
    forbidden_assumptions: tuple[str, ...]

    # Skill 专用验证器（可选）
    validator: Callable[[dict], list[str]] | None = None
```

### 5.2 每个 Skill 必须声明的禁止假设

| Skill | 必须禁止 |
|---|---|
| `brand-promo-video-generator` | 不得编造产品性能、价格、认证、销量；不得在无授权时使用真实品牌标识 |
| `music-video-subtitle-generator` | 不得编造歌词；对未提供歌词的请求不得生成歌词 |
| `co-op-game-intro-generator` | 不得编造 UI 文案；不得在无授权时使用真实游戏品牌 |
| `paper-collage-explainer-generator` | 不得主动增加旁白、字幕或 BGM |
| `papercraft-stop-motion-explainer` | 不得描述光滑 CG 效果；不得使用真实科学数据除非用户提供 |
| `handdrawn-live-video-generator` | 不得描述恐怖跳跃；不得描述光滑 CG 或毛绒角色 |
| `minimalist-product-ad-generator` | 不得编造产品参数或价格 |
| `3d-animation-short-generator` | 不得在无授权时使用真实 IP 角色 |

### 5.3 Skill 只做知识，不做工具

每个 Skill 不允许：

- 加载模型
- 访问素材文件
- 操作时间线
- 修改节点状态
- 调用网络
- 保存结果
- 向用户提问或等待确认

Skill 只是经过本地适配的导演知识。

---

## 六、Skill 注册表设计

使用简单数据结构，不需要复杂插件框架：

```python
# skills/registry.py

SKILL_IDS = (
    "h3-prompt-writing",
    "3d-animation-short-generator",
    "brand-promo-video-generator",
    "co-op-game-intro-generator",
    "handdrawn-live-video-generator",
    "minimalist-product-ad-generator",
    "music-video-subtitle-generator",
    "paper-collage-explainer-generator",
    "papercraft-stop-motion-explainer",
)

SKILLS: dict[str, SkillDefinition] = {
    "h3-prompt-writing": SkillDefinition(
        id="h3-prompt-writing",
        display_name_zh="通用 H3 提示词",
        description_zh="标准 MiniMax H3 提示词生成，无特殊导演方法",
        positive_signals=(),
        negative_signals=(),
        director_rules_zh="...",
        director_rules_en="...",
        forbidden_assumptions=(),
    ),
    # ... 其余 8 个 Skill
}

def skill_options() -> list[tuple[str, str]]:
    """返回 (id, display_name) 列表，供 UI Combo 使用。"""
    return [(sid, SKILLS[sid].display_name_zh) for sid in SKILL_IDS]

def get_skill(skill_id: str) -> SkillDefinition:
    """获取 Skill 定义，不存在时返回 h3-prompt-writing。"""
    return SKILLS.get(skill_id, SKILLS["h3-prompt-writing"])

def build_skill_system_prompt(skill_id: str, lang: str) -> str:
    """构建 Skill 导演规则 system prompt。"""
    skill = get_skill(skill_id)
    rules = skill.director_rules_zh if lang == "zh" else skill.director_rules_en
    forbiddens = "\n".join(f"- {f}" for f in skill.forbidden_assumptions)
    return f"{rules}\n\n## 禁止假设\n{forbiddens}"
```

---

## 七、自动路由设计

### 7.1 第一版：规则优先

明确特征可直接路由，无需调用 LLM：

| 典型信号 | Skill |
|---|---|
| 双人合作、Player 1/2、游戏菜单、角色选择 | `co-op-game-intro-generator` |
| 商品图、电商、极简广告、产品特写 | `minimalist-product-ad-generator` |
| 品牌、App、网站、发布、推广、CTA | `brand-promo-video-generator` |
| 歌词、MV、字幕、节拍、演唱 | `music-video-subtitle-generator` |
| 真人加手绘、发光线条、追逐、变形 | `handdrawn-live-video-generator` |
| 拼贴、半色调、撕纸、观点解释 | `paper-collage-explainer-generator` |
| 纸艺、立体书、纸板、定格科普 | `papercraft-stop-motion-explainer` |
| 3D 动画、角色故事、动画短片 | `3d-animation-short-generator` |
| 无明显专用特征 | `h3-prompt-writing` |

### 7.2 模糊情况：本地 Qwen 路由

路由提示只要求返回一个 ID（一次轻量 LLM 调用）：

```
根据用户故事、素材类型和制作目标，选择最合适的一个导演 Skill。
只能返回以下一个 ID：
- h3-prompt-writing
- 3d-animation-short-generator
- brand-promo-video-generator
- co-op-game-intro-generator
- handdrawn-live-video-generator
- minimalist-product-ad-generator
- music-video-subtitle-generator
- paper-collage-explainer-generator
- papercraft-stop-motion-explainer

如果没有明显的专用制作类型，返回 h3-prompt-writing。
不要解释，不要理由，不要 markdown，只返回 ID。
```

解析失败时回退：`h3-prompt-writing`

### 7.3 手动选择永远优先

用户手动选择 Skill 后，不再执行自动路由。

---

## 八、统一 Director 中间结构

不要让 8 个 Skill 分别生成不同格式，否则下游会失控。

所有 Skill 生成本地化后，先输出统一中间 JSON：

```json
{
  "selected_skill": "3d-animation-short-generator",
  "global_prompt": "...",
  "overall_soundscape": "...",
  "non_diegetic_music": "...",
  "segments": [
    {
      "purpose": "建立角色与场景",
      "visual_event": "...",
      "subject_action": "...",
      "camera": "...",
      "audio": "...",
      "prompt": "最终完整 H3 prompt"
    }
  ]
}
```

下游 StoryDirector 使用的仍是简化结构：

```json
{
  "global_prompt": "...",
  "overall_soundscape": "...",
  "non_diegetic_music": "...",
  "segments": [{"prompt": "..."}]
}
```

`purpose`、`visual_event` 等字段作为内部调试信息保存，不进入最终 workflow 输出。

---

## 九、两阶段生成流程

### 9.1 推荐方案：一次 worker 生命周期内完成全部

```
加载 Qwen 模型一次
    ↓
路由（如果自动）
    ↓
生成 Director plan（应用 Skill 导演规则）
    ↓
逐段编译 H3 prompt（使用 h3-prompt-writing 格式）
    ↓
结构、时间、素材和 Skill 规则验证
    ↓
必要时自动修复一次
    ↓
关闭 worker
```

不能每个阶段重新启动 worker，否则 Qwen 27B 会反复加载，浪费大量时间。

### 9.2 Worker 协议调整

当前 worker 一次只处理一个请求。建议支持任务列表，但考虑到后续任务依赖前面的结果，最简单可靠的方式是让 worker 内部执行完整导演流程：

```
用户请求
  → [加载模型]
  → [路由 + 规划 + 编译 + 验证 + 修复]
  → [返回结果]
  → [worker 退出]
```

### 9.3 修复策略

发现错误时只自动修复一次。修复请求包含机器生成的具体错误：

```
返回的 Director JSON 不合格，请只修复以下问题：
1. 第 2 段缺少 ===AUDIO_INSTRUCTION===
2. 第 3 段时间戳 00:09.000 超过单段 8 秒
3. 输出包含"请确认是否继续"
返回完整 Director JSON，不要解释，不要理由。
```

第二次仍不合格：

- 停止执行
- 返回短而明确的错误
- 不静默降级为错误格式
- 不使用不完整结果继续

---

## 十、H3 输出质量门

结果必须经过三层验证。

### 10.1 Director JSON 验证

检查项：

- [ ] 根对象类型为 dict
- [ ] 分镜数量准确（与 `segment_count` 一致）
- [ ] `global_prompt` 字段存在且非空
- [ ] `overall_soundscape` 字段存在且非空
- [ ] `segments` 是非空列表
- [ ] 每段 `prompt` 非空
- [ ] 每段 prompt 不含字段标题（如 `subject_definitions:`）
- [ ] 总 prompt 长度合理（不超过 max_chars）

### 10.2 H3 prompt 结构验证

检查项：

- [ ] 标准字段是否存在（模式相关）
- [ ] 字段按正确顺序排列
- [ ] 引用编号在素材范围内
- [ ] Picture/Subject 不越界
- [ ] 时间戳严格递增
- [ ] 时间戳小于单段时长
- [ ] 不含 Markdown 代码块（```）
- [ ] 不含提问、审批、确认或下一步请求
- [ ] 不编造用户未提供的歌词、对白或文案

### 10.3 Skill 专用验证

每个 Skill 可选提供专用验证器：

```python
def music_video_validator(plan: dict) -> list[str]:
    issues = []
    segments = plan.get("segments", [])
    for i, seg in enumerate(segments, 1):
        prompt = seg.get("prompt", "")
        # 歌词必须来自用户，不得自行生成
        # 时间戳对应关系
        # ...
    return issues
```

---

## 十一、和当前 StoryDirector 问题一起修复

Skill 融合前，先修复以下基础问题：

| # | 问题 | 优先级 |
|---|---|---|
| 1 | `gpu_layers` 未传到 worker，固定为 `-1` | 必须修复 |
| 2 | `context_size` 在 Qwen3.8 固定为 `32768`，未生效 | 必须修复 |
| 3 | Qwen3.8 静默覆盖用户的 `top_p`/`min_p` | 必须修复 |
| 4 | worker 无超时和强制终止机制 | 必须修复 |
| 5 | 缺少全局推理锁 | 高 |
| 6 | 推理前未释放 ComfyUI 当前模型（显存冲突风险） | 高 |
| 7 | 素材改名全局替换正文（应只更新明确引用） | 中 |
| 8 | README 声称"只开放 Qwen3.5" | 中 |
| 9 | "二次增强"未真正实现 | 中 |

---

## 十二、实施阶段

### 阶段一：Skill 基础设施

**目标：** 建立 Skill 注册、路由和本地适配体系

**新增文件：**

```
skills/
__init__.py
registry.py
router.py
h3_compiler.py
h3_contract.py
```

**完成标准：**

- [ ] `skill_options()` 返回全部 9 个 Skill
- [ ] `get_skill()` 对未知 ID 返回 `h3-prompt-writing`
- [ ] 自动路由对所有明确特征给出正确 Skill ID
- [ ] 模糊情况调用 LLM 路由，返回允许的 9 个 ID 之一
- [ ] 解析失败时回退到 `h3-prompt-writing`

**验证测试：**

```python
def test_all_skills_registered():
    for sid in SKILL_IDS:
        assert get_skill(sid).id == sid

def test_auto_route_clear_signals():
    assert auto_route("双人合作游戏菜单") == "co-op-game-intro-generator"
    assert auto_route("极简耳机产品广告") == "minimalist-product-ad-generator"
    assert auto_route("手绘线条与真人接触") == "handdrawn-live-video-generator"

def test_auto_route_fallback():
    assert auto_route("一个普通的城市街景") == "h3-prompt-writing"
```

---

### 阶段二：H3 编译与验证层

**目标：** `h3-prompt-writing` 成为所有结果的公共编译规范

**新增文件：**

```
skills/h3-prompt-writing/SKILL.md
skills/h3-prompt-writing/references/base-en.txt
skills/h3-prompt-writing/references/ref-en.txt
skills/h3_contract.py
```

**完成标准：**

- [ ] `h3_compiler.compile(plan, mode, duration)` 将 Director JSON 转成 H3 prompt
- [ ] `h3_contract.validate(text, mode, duration)` 返回错误列表
- [ ] `h3_contract.output_issues()` 检查字段顺序、时间戳、交互输出、静默要求
- [ ] 失败时 `h3_contract.build_repair_prompt(issues)` 生成修复请求

**验证测试：**

```python
def test_h3_compiler_basic():
    plan = {"global_prompt": "风格", "overall_soundscape": "风声",
            "non_diegetic_music": "N/A",
            "segments": [{"prompt": "动作描述"}]}
    result = h3_compiler.compile(plan, "ref2va", 8.0)
    assert "subject_definitions:" in result
    assert "overall_soundscape:" in result

def test_h3_contract_timestamp_order():
    text = "... At 00:02.500, ... At 00:01.000, ..."
    issues = h3_contract.output_issues(text, "ref2va", 8.0)
    assert "Shot timestamps must be strictly increasing" in issues
```

---

### 阶段三：Worker 生命周期修复

**目标：** 让现有参数真正生效，增加可靠性和资源管理

**修复项：**

- [ ] `gpu_layers` 从节点传入 worker，worker 不再固定 `-1`
- [ ] `context_size` 真正传入 worker
- [ ] Qwen3.8 不再静默覆盖 `top_p`/`min_p`
- [ ] worker 增加可配置超时（默认 300 秒）
- [ ] 超时或异常时执行 `terminate → wait(15s) → kill`
- [ ] 增加 `threading.Lock` 推理锁
- [ ] 推理前调用 `comfy.model_management.unload_all_models()`

**验证测试：**

```python
def test_gpu_layers_passed_to_worker():
    with mock.patch.object(backend, "_paths", return_value=(...) ):
        process.communicate.return_value = (b'STORYDIRECTOR_RESULT={"text":"ok"}\n', b"")
        backend.complete({"n_gpu_layers": 32}, "sys", "usr")
    req = json.loads(process.communicate.call_args.args[0].decode())
    assert req["n_gpu_layers"] == 32

def test_worker_timeout_kills_process():
    # mock communicate to never return
    # verify terminate → kill sequence
    pass
```

---

### 阶段四：Skill 完整集成

**目标：** 9 个 Skill 全部接入，生成流程完整可用

**完成标准：**

- [ ] 节点新增 `director_skill` Combo 输入，默认"自动选择"
- [ ] 手动选择后不执行自动路由
- [ ] 每个 Skill 的 `director_rules` 被注入到规划 system prompt
- [ ] 每个 Skill 的 `forbidden_assumptions` 作为明确约束注入
- [ ] 选定的 Skill ID 和路由原因显示在结果面板（只读）
- [ ] README 和前端帮助同步更新

**验证测试：**

```python
def test_skill_injected_into_system_prompt():
    rules = build_skill_system_prompt("brand-promo-video-generator", "zh")
    assert "禁止虚构产品卖点" in rules
    assert "brand-promo" in rules

def test_forbidden_injected():
    rules = build_skill_system_prompt("music-video-subtitle-generator", "zh")
    assert "不得编造歌词" in rules

def test_skill_display_name_in_options():
    opts = skill_options()
    ids = [o[0] for o in opts]
    assert "brand-promo-video-generator" in ids
    assert "music-video-subtitle-generator" in ids
```

---

### 阶段五：端到端验证

**目标：** 真实推理流程可工作

每个 Skill 准备一个固定测试请求：

| Skill | 测试请求 |
|---|---|
| `h3-prompt-writing` | 普通 10 秒城市雨夜镜头 |
| `3d-animation-short-generator` | 两个角色寻找失落钥匙 |
| `brand-promo-video-generator` | 已有功能列表的 App 宣传 |
| `co-op-game-intro-generator` | 两个角色的合作游戏菜单 |
| `handdrawn-live-video-generator` | 真人触碰发光手绘生物 |
| `minimalist-product-ad-generator` | 耳机产品静物广告 |
| `music-video-subtitle-generator` | 用户提供了歌词和时间码的短 MV |
| `paper-collage-explainer-generator` | 用旁白解释拖延心理 |
| `papercraft-stop-motion-explainer` | 用纸艺解释火山喷发 |

每项检查：

- [ ] 路由正确（或手动选择生效）
- [ ] 分镜数量正确
- [ ] 风格规则明显
- [ ] 素材引用正确
- [ ] 不虚构禁止信息
- [ ] 声音逻辑正确
- [ ] H3 格式正确
- [ ] 时间戳合法
- [ ] 没有向用户提问

---

## 十三、最终用户体验

用户仍然只看到一个节点：

```
StoryDirector 故事导演
```

用户操作流程不变，只需额外：

1. 在"剧本拆解配置"选择"自动选择"或手动指定导演 Skill
2. 运行后查看"本次导演策略"显示
3. 编辑分镜 prompt
4. 输出 H3 Director 时间线

内部执行链：

```
解析故事和素材
       ↓
自动选择垂直 Skill（或使用手动选择）
       ↓
应用 Skill 导演规则和禁止假设
       ↓
拆解统一 Director plan
       ↓
h3-prompt-writing 编译每个分镜为 H3 格式
       ↓
结构、时间、素材和 Skill 规则验证
       ↓
必要时自动修复一次
       ↓
输出 StoryDirector 时间线 JSON
```

---

## 十四、不融合的部分

| 原因 | 不融合项 |
|---|---|
| 架构冲突 | Qwen H3 Prompt 的 `llama-server` + `install_runtime.py` — StoryDirector 使用 `llama-cpp-python` subprocess，已验证且无需额外安装 |
| 功能重叠 | Qwen H3 Prompt 的 asset 路由 — StoryDirector 已有完整素材管理 |
| 复杂度 | Qwen H3 Prompt 的 V3 `io.Schema` API — StoryDirector 使用 V1  tuple API，改造成本高且无收益 |
| 定位差异 | Qwen H3 Prompt 是单条 H3 prompt 生成器 — StoryDirector 是故事拆解 + 多镜头时间线，两者目标不同 |

---

## 十五、总结

| 层次 | 当前 StoryDirector | 融入后 |
|---|---|---|
| 交互 | 故事编辑器 + 素材管理 | 不变 |
| 推理 | Qwen3.5/3.8 worker | 不变，但修复参数失效问题 |
| 导演方法 | 内置导演规则 | **9 个官方 H3 Skills 本地化** |
| H3 格式 | 内置验证 | **独立 h3-prompt-writing 编译层** |
| 输出 | Director JSON + 时间线 | 不变，但质量门更强 |

最终形态：**本地多类型 H3 AI 导演台**，从"故事拆解工具"升级为真正的本地多类型视频创作规划系统。
