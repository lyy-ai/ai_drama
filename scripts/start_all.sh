#!/bin/bash
# AI 短剧平台一键启动脚本（setsid 启动，脱离终端进程组）
# 用法: bash scripts/start_all.sh [llm|comfy|video|backend|frontend|all]

ROOT=/data/liyangyang/ai_drama
QWEN_ENV=/data/liyangyang/qwen35_env
LOGS=$ROOT/logs
mkdir -p $LOGS $ROOT/output/video_clips $ROOT/output/audio

start_llm() {
  echo "[start] LLM (vLLM Qwen3-0.6B) 127.0.0.1:10048  GPU1"
  setsid env CUDA_VISIBLE_DEVICES=1 \
    PATH=$QWEN_ENV/bin:/usr/bin:/bin \
    LD_LIBRARY_PATH=$QWEN_ENV/lib/python3.12/site-packages/nvidia/cu13/lib \
    VLLM_USE_FLASHINFER_SAMPLER=0 \
    $QWEN_ENV/bin/vllm serve /data/liyangyang/models/Qwen3-0.6B \
      --served-model-name qwen35-9b --host 127.0.0.1 --port 10048 \
      --gpu-memory-utilization 0.15 --max-model-len 4096 --enforce-eager --trust-remote-code \
    > $LOGS/vllm.log 2>&1 < /dev/null &
}

start_comfy() {
  echo "[start] ComfyUI (SDXL) 127.0.0.1:10047  GPU1"
  cd $ROOT/services/comfyui/ComfyUI
  setsid env CUDA_VISIBLE_DEVICES=1 \
    $ROOT/services/comfyui/venv/bin/python main.py --listen 127.0.0.1 --port 10047 \
    > $LOGS/comfyui.log 2>&1 < /dev/null &
}

start_video() {
  echo "[start] MiniMax-H3 视频服务 127.0.0.1:10050 (生成跑在 GPU0)"
  cd $ROOT/services/video
  setsid env CUDA_VISIBLE_DEVICES=0 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    $ROOT/services/video/venv/bin/uvicorn server:app --host 127.0.0.1 --port 10050 \
    > $LOGS/video_service.log 2>&1 < /dev/null &
}

start_backend() {
  echo "[start] 编排后端 0.0.0.0:10046"
  cd $ROOT/backend
  setsid $QWEN_ENV/bin/uvicorn app.main:app --host 0.0.0.0 --port 10046 \
    > $LOGS/backend.log 2>&1 < /dev/null &
}

start_frontend() {
  echo "[start] 前端 0.0.0.0:10045"
  setsid $QWEN_ENV/bin/python -m http.server 10045 --bind 0.0.0.0 \
    --directory $ROOT/frontend/dist > $LOGS/frontend.log 2>&1 < /dev/null &
}

case "${1:-all}" in
  llm) start_llm ;;
  comfy) start_comfy ;;
  video) start_video ;;
  backend) start_backend ;;
  frontend) start_frontend ;;
  all)
    start_llm; start_comfy; start_video; start_backend; start_frontend
    echo "全部服务已后台启动，日志在 $LOGS/"
    echo "LLM/TTS 首次加载模型需 1-3 分钟，可用 bash scripts/status.sh 查看健康状态"
    ;;
  *) echo "未知服务: $1"; exit 1 ;;
esac
