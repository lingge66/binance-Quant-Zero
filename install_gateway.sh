#!/bin/bash
# 领哥量化底座 - 一键部署神经网关脚本

echo "🚀 开始将电报神经网关注册为系统守护进程..."

# 获取当前绝对路径
PROJECT_DIR=$(pwd)
VENV_PYTHON="/home/lingge/quant_venv/bin/python" # 强制使用外部隔离环境

# 生成 systemd 配置文件
cat <<EOF | sudo tee /etc/systemd/system/quant_tg_gateway.service
[Unit]
Description=Quant Telegram Gateway (Fast/Smart Router)
After=network.target openclaw.service

[Service]
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$VENV_PYTHON $PROJECT_DIR/telegram_gateway.py
Restart=always
RestartSec=5
EnvironmentFile=$PROJECT_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

# 重新加载配置并启动
sudo systemctl daemon-reload
sudo systemctl enable quant_tg_gateway.service
sudo systemctl restart quant_tg_gateway.service

echo "✅ 部署完成！网关已在后台运行。"
echo "您可以随时使用 'sudo systemctl status quant_tg_gateway' 查看状态。"