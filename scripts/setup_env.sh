#!/bin/bash
# clone 后一键重建 services 运行环境（venv + 依赖）
# 用法: bash /data/liyangyang/ai_drama/scripts/setup_env.sh
# 前置: 系统 python3.12；模型文件需按 README 另行下载到 /data/liyangyang/models/

set -e
ROOT=/data/liyangyang/ai_drama

build_venv() {
  local dir=$1
  echo "==> 创建 venv: $dir/venv"
  python3.12 -m venv "$dir/venv"
  "$dir/venv/bin/pip" install --upgrade pip
  echo "==> 安装依赖: $dir/requirements.txt (torch 等大包, 耗时较长)"
  "$dir/venv/bin/pip" install -r "$dir/requirements.txt"
}

build_venv "$ROOT/services/comfyui"
build_venv "$ROOT/services/tts"
build_venv "$ROOT/services/video"

echo "完成。启动: bash $ROOT/scripts/start_all.sh"
