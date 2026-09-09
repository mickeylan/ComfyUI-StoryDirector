# StoryDirector 故事导演

StoryDirector 是单节点本地 H3 前期导演台，负责故事拆解、素材管理、导演 Skill、分镜规划和 MiniMaxH3 Director 时间线输出；不包含编码、采样、解码、视频生成或在线 API。

## 使用

1. 在 ComfyUI Python 环境安装带 MTMD 支持的 `llama-cpp-python`。
2. 将配套的 Qwen3.5 或 Qwen3.8 主模型与 mmproj GGUF 放入 `models/LLM`，在“剧本拆解配置”中分别选择。
3. 在富文本故事编辑器中输入故事；输入 `@` 或点击素材卡片可插入图片、视频和音频引用。
4. 选择“自动选择”或手动指定导演 Skill。Skill 是制作方法，故事风格是美术与类型，两者独立。
5. 运行节点，将 `MiniMaxH3 Director 时间线 JSON` 连接到 MiniMaxH3 Director 的 `timeline_data`。

## 9 个导演 Skills

- 通用 H3 提示词
- 3D 动画短片
- 品牌宣传视频
- 双人游戏开场
- 真人手绘融合
- 极简产品广告
- MV 与歌词字幕
- 纸张拼贴解说
- 纸艺定格科普

明确特征由本地规则选择；模糊请求由同一次本地 Qwen 推理选择。所有结果统一经过 H3 字段、分镜数量、时间戳、素材引用和 Skill 专用质量检查。结构错误会在同一 Worker 生命周期内修复一次，仍不合格则停止并报告具体问题。

## 输出契约

唯一注册节点 `StoryDirector` 输出：

- `总提示词`：跨分镜稳定的风格、场景、角色定义和保留约束。
- `MiniMaxH3 Director 时间线 JSON`：分镜、时长、声音、Skill ID 和选择原因。
- `素材目录 JSON`：素材类型、名称、用途、描述和托管相对路径。
- `参考图片`：故事中明确引用且启用的图片批次。

## 本地推理

- Qwen3.5 与 Qwen3.8 使用各自独立的 disposable Worker。
- `context_size`、`gpu_layers` 和采样参数按节点设置传入。
- 推理前释放 ComfyUI 已加载模型，进程间使用推理锁。
- Worker 默认超时300秒，超时后终止并清理。
- “拆解后二次增强”会在同一 Worker 中对已生成分镜执行一次真实增强。

本扩展不会联网，不包含密钥、llama-server、安装器或媒体生成流程。
