"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
"""
OpenClaw 脑机接口 - FastAPI 独立微服务版
功能：将本地的底层量化武器库，暴露为 OpenClaw 后台服务可调用的 HTTP 接口。
"""

import sys
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# 引入我们昨天锻造的重装武器库
from openclaw_skills import get_account_status, get_market_quote, execute_smart_trade, arsenal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - ⚡ API网关 - %(message)s')
logger = logging.getLogger("SkillsAPI")

app = FastAPI(title="OpenClaw Quant Skills API", description="提供给 OpenClaw AI 大脑调用的专业量化接口")

# ==========================================
# 接口数据模型 (严格规范 AI 传过来的参数)
# ==========================================
class QuoteRequest(BaseModel):
    symbol: str

class TradeRequest(BaseModel):
    symbol: str
    side: str
    amount: float

# ==========================================
# 路由暴露 (暴露给 OpenClaw 的四个电钮)
# ==========================================
@app.on_event("startup")
async def startup_event():
    """微服务启动时，预热量化引擎"""
    logger.info("正在唤醒底层量化引擎与风控系统...")
    await arsenal.initialize()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("正在安全关闭引擎...")
    await arsenal.shutdown()

@app.get("/api/account/status")
async def api_get_account():
    """查询资金状态"""
    try:
        res = await get_account_status()
        return {"status": "success", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/market/quote")
async def api_get_quote(req: QuoteRequest):
    """查询行情"""
    try:
        res = await get_market_quote(req.symbol)
        return {"status": "success", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trade/execute")
async def api_execute_trade(req: TradeRequest):
    """【高危】触发开仓，强制经过底层风控"""
    logger.warning(f"🚨 接收到 AI 交易指令: {req.side} {req.amount} {req.symbol}")
    try:
        res = await execute_smart_trade(req.symbol, req.side, req.amount)
        return {"status": "success", "data": res}
    except Exception as e:
        logger.error(f"指令执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # 启动在本地的 8080 端口，专供 OpenClaw 调用
    uvicorn.run(app, host="127.0.0.1", port=8080)