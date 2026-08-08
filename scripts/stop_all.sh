#!/bin/bash
# 停止 AI 短剧平台所有服务
pkill -f "[v]llm serve"
pkill -f "[m]ain.py --listen 127.0.0.1 --port 10047"
pkill -f "[u]vicorn server:app --host 127.0.0.1 --port 10050"
pkill -f "[u]vicorn app.main:app --host 0.0.0.0 --port 10046"
pkill -f "[h]ttp.server 10045"
echo "已停止全部服务"
