# AI 短剧平台

输入一段小说梗概，一键生成带配音字幕的竖屏短剧（480×832）。

**访问地址**：`http://36.212.51.4:10045`（API 文档：`http://36.212.51.4:10046/docs`）

## 架构与端口

| 端口 | 服务 | 绑定 | 说明 |
|---|---|---|---|
| 10045 | 前端静态站 | 0.0.0.0 | 用户入口 |
| 10046 | 编排后端 FastAPI | 0.0.0.0 | 流水线引擎 / SQLite / WebSocket 进度 |
| 10047 | ComfyUI (SDXL) | 127.0.0.1 | 角色定妆照 + 分镜首帧（GPU1） |
| 10048 | vLLM Qwen3.5-9B | 127.0.0.1 | 剧本生成（GPU1，常驻 ~21G） |
| 10049 | CosyVoice-300M-SFT | 127.0.0.1 | 多音色配音（GPU1） |
| 10050 | MiniMax-H3 (NF4) | 127.0.0.1 | 视频片段生成，音画同步（**GPU0**，显存自动管理，最低 8G） |

> 仅 10045/10046 对公网开放；10047-10050 仅本机内部调用（无鉴权，勿对外映射）。

## 流水线

梗概 → S0 LLM 结构化剧本(JSON) → S1 SDXL 角色定妆照 → S2 SDXL 分镜首帧 → S3 CosyVoice 台词配音 → S4 MiniMax-H3 视频片段 → S5 FFmpeg 音画对齐/字幕/拼接 → 成片

- 剧本生成后可人工编辑（台词/提示词/角色音色），也可全自动一键出片
- 支持单镜头重生成（重绘图 / 重视频 / 重配音）、断点续跑
- 视频阶段前自动调用 ComfyUI `/free` 释放显存，避免与 vLLM 争抢

## 快速开始

```bash
# 启动全部服务
bash /data/liyangyang/ai_drama/scripts/start_all.sh

# 查看健康状态（llm/comfy/video/tts 应为全 true）
bash /data/liyangyang/ai_drama/scripts/status.sh

# 停止全部
bash /data/liyangyang/ai_drama/scripts/stop_all.sh
```

浏览器打开 `http://36.212.51.4:10045` → 新建短剧 → 粘贴梗概 → 生成剧本 → （可选编辑）→ 开始制作 → 监控页看实时进度 → 成片页播放/下载。

## API 示例

```bash
# 创建项目（auto_produce=true 全自动）
curl -X POST http://36.212.51.4:10046/api/projects \
  -H "Content-Type: application/json" \
  -d '{"synopsis":"外卖员暴雨夜救下千金小姐……","style":"都市","episodes":1,"shots_per_episode":6,"auto_produce":true}'

# 查询进度
curl http://36.212.51.4:10046/api/projects/{pid}

# 单镜头重生成
curl -X POST "http://36.212.51.4:10046/api/projects/{pid}/shots/1/2/regen?stage=video"
```

## 耗时参考（实测）

| 阶段 | 耗时 |
|---|---|
| 剧本（1集6镜头） | ~1-2 分钟 |
| 角色/分镜图（每张） | ~10 秒 |
| 配音（每句） | ~5 秒 |
| 视频片段（每个 ~3.8s/90帧/50步） | 视显存余量 ~15-30 分钟（disk offload） |
| 1 集 6 镜头成片 | ~1 小时 |

## 环境说明（均未污染外部）

| 用途 | 环境 |
|---|---|
| LLM / 视频服务 / 后端 | 复用 `/data/liyangyang/qwen35_env`（已含 vllm/torch2.11） |
| ComfyUI | 源码已 vendored 于 `services/comfyui/ComfyUI`，venv 用 `scripts/setup_env.sh` 重建 |
| CosyVoice | 源码已 vendored 于 `services/tts/CosyVoice`，venv 同上（`setuptools<81` 已固定在 requirements 中） |
| 前端 | node18 + vite 构建，python http.server 托管 dist |

### 全新克隆后的初始化

```bash
git clone git@github.com:lyy-ai/ai_drama.git /data/liyangyang/ai_drama

# 1. 重建 services 的两个 venv（torch 2.13+cu13 等大包，耗时较长）
bash /data/liyangyang/ai_drama/scripts/setup_env.sh

# 2. 构建前端
cd /data/liyangyang/ai_drama/frontend && npm install && npm run build

# 3. 模型文件按 ModelScope 下载到 /data/liyangyang/models/（见下）

# 4. 启动
bash /data/liyangyang/ai_drama/scripts/start_all.sh
```

> venv 不入库（单文件超 GitHub 100MB 限制且路径写死）；`requirements.txt` 已锁定全部依赖版本，重建结果与原环境一致。

模型：`/data/liyangyang/models/` 下 `MiniMax-H3-NF4`（视频，FL2VA 四件套）、`MiniMax-H3`（仅 FL2VA/processor 配置）、`sdxl`、`CosyVoice-300M-SFT`、`Qwen3-0.6B`，全部经 ModelScope 下载。旧 `Wan2.1-T2V-1.3B` 已下线（服务备份为 `services/video/server_wan21.py`）。

## 已知注意事项

1. **GPU 显存分配**：GPU1 被 vLLM 常驻占 21G，ComfyUI/CosyVoice 按需加载（各 ~5-8G）可与 vLLM 共存；Wan2.1 峰值 ~10G 安排在 GPU0（与 veyforge/isaac 错峰，余量 14G）。若 GPU0 被占满，需把 video 服务 env 改回 GPU1 并先停 ComfyUI。
2. **vLLM 启动参数**：`VLLM_USE_FLASHINFER_SAMPLER=0`（flashinfer 与 CUDA13 cub 编译冲突）、`--enforce-eager`（省显存）、`LD_LIBRARY_PATH` 指向 nvidia/cu13/lib。
3. **MiniMax-H3 推理**：DiffSynth-Studio（PyPI `diffsynth==2.1.0`）+ bitsandbytes NF4，disk offload，帧数自动对齐 17n+5、24fps 出片；mp4 自带音轨在 S5 被丢弃，仍用 CosyVoice 配音。
4. CosyVoice2-0.5B 无内置音色，本平台改用 CosyVoice-300M-SFT（内置 中文男/中文女 等 7 个音色）。
5. 中文字幕依赖系统字体 Droid Sans Fallback（已装）。

## 二期路线

- 下载 `Wan2.1-I2V-14B-480P`，分镜首帧直接图生视频，人物一致性大幅提升
- 角色 LoRA / IP-Adapter 训练固定人物
- BGM 自动匹配、转场特效、片头片尾模板
- 多项目并发队列
