# StoryDirector 故事导演

StoryDirector 是从成熟 H3 故事导演台中减法抽取的单节点前期工作台，不是生成器重设计。它保留故事模式、H3 拆解规则、风格与镜头偏好、丰富提示词编辑/@素材引用、素材卡片与本地预览、重拍/已处理镜头文本编辑和帮助面板；生成、编码、采样、解码与媒体总线均不在本扩展内。

## 使用

1. 在 ComfyUI Python 环境安装 `llama-cpp-python`（仅选择本地模型时需要）。
2. 将 GGUF 放入 `models/LLM`，添加唯一的 `StoryDirector` 节点。
3. 节点内置富文本故事编辑器和资产显示窗。输入 `@` 可搜索图片、视频、音频，支持方向键选择、回车或 Tab 插入；引用会显示为带类型图标和颜色的锁定 Token。点击资产卡片也会在当前光标处插入。素材改名时会同步更新已有引用。
4. 浏览器导入的资产会安全复制到 `input/story_director`，工作流只保存托管相对路径。素材目录支持 JSON 导入、导出。
5. `离线预览` 用同一 H3 块格式检查版面；拆解/生成模式只调用进程内 llama-cpp-python，不访问网络。可选开启二次增强，只重写每段 `detailed_description`。

## 输出契约

唯一注册节点 `StoryDirector` 输出：

- `H3完整剧本`：完整的 `[SHOT_START] ... [SHOT_END]` 分段，保留 `===H3_PROMPT===`、`===SCENE_INSTRUCTION===`、`===VIDEO_INSTRUCTION===`、`===AUDIO_INSTRUCTION===` 及 H3 六段字段；不转换成简化的 Visual/Action schema。
- `素材目录 JSON`：启用状态、类型、角色、描述、顺序及 `story_director/...` 托管路径。

本扩展没有在线 API、密钥、llama-server、安装器、兼容节点或媒体生成流程。
