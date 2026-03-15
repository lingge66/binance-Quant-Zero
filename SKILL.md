---
name: binance-quick
description: Binance 快速指令（查余额、平仓、行情等）
metadata:
  openclaw:
    command-dispatch: tool
    command-tool:
      "/balance": get_quant_account_status
      "/closeall": emergency_close_all_positions
      "/quote": get_quant_market_quote
      "/predict": get_local_ai_prediction
      "/simulate": simulate_trade_risk
      "/execute": execute_advanced_order
    requires:
      env:
        - BINANCE_API_KEY
        - BINANCE_SECRET_KEY
    primaryEnv: BINANCE_API_KEY
---
## Binance 快速指令技能
提供直接调用 Binance API 的快捷命令，无需 AI 处理，响应极速。
