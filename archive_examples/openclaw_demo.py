"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


import asyncio
from src.notification.message_formatter import MessageFormatter
from src.risk.account_monitor import AccountMonitor
from src.signals.signal_generator import SignalGenerator

async def main():
    print("🤖 正在启动 OpenClaw 交互模式...")
    print("👨‍💻 领哥 (输入): 'OpenClaw，立刻帮我生成一份 BTC 实时风控与交易信号研报！'")
    print("-" * 50)
    await asyncio.sleep(2) # 模拟 AI 思考时间
    
    print("🤖 OpenClaw (正在调用量化后端接口...)")
    await asyncio.sleep(1)
    
    # 模拟从你的系统中获取真实数据
    mock_risk_data = {
        "margin_ratio": "854.2%",
        "daily_drawdown": "-1.2%",
        "circuit_breaker_status": "🟢 安全 (未熔断)"
    }
    mock_signal_data = {
        "symbol": "BTC/USDT",
        "signal": "STRONG_BUY",
        "confidence": 88,
        "price": 65241.50
    }
    
    # 使用你写好的 MessageFormatter 生成专业排版
    formatter = MessageFormatter()
    
    print("\n" + "="*50)
    print("🤖 OpenClaw 回复领哥：")
    print(formatter.format_system_status("RUNNING", "系统运行正常，API连接稳定", None, "markdown"))
    
    print("\n📊 【盘面信号分析】")
    print(formatter.format_signal(
        mock_signal_data['symbol'], 
        mock_signal_data['signal'], 
        mock_signal_data['confidence'], 
        mock_signal_data['price'], 
        format_type="markdown"
    ))
    
    print("\n🛡️ 【风控中心报告】")
    print(formatter.format_risk_alert(
        "ROUTINE_CHECK", "INFO", 
        f"保证金率健康 ({mock_risk_data['margin_ratio']})。当前回撤 {mock_risk_data['daily_drawdown']}，未触发熔断机制。",
        format_type="markdown"
    ))
    print("="*50)
    print("\n👨‍💻 领哥 (输入): '授权按此信号以 0.01 BTC 仓位执行买入，并开启移动止损！'")
    print("🤖 OpenClaw: '指令已确认！[EXEC] Executor 已接管，正在向 Binance Testnet 发送订单...'")

if __name__ == "__main__":
    asyncio.run(main())