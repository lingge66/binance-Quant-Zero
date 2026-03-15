"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
"""
OpenClaw AI 核心网关
功能：连接大模型，赋予其调用底层武器库 (openclaw_skills) 的能力。
"""

import os
import json
import asyncio
import logging
from openai import AsyncOpenAI # 如果没有安装，请 pip install openai

# 导入咱们刚才打造的重型武器库
from openclaw_skills import get_account_status, get_market_quote, execute_smart_trade, arsenal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - 🤖 AI指挥官 - %(message)s')
logger = logging.getLogger("OpenClaw_Brain")

# ==========================================
# 1. 注册给大模型的工具清单 (Tool Schema)
# ==========================================
tools_definition = [
    {
        "type": "function",
        "function": {
            "name": "get_account_status",
            "description": "获取量化账户的当前资金状况、可用余额和风险度（下单前必查）。"
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_quote",
            "description": "获取指定交易对的实时价格和涨跌幅。",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "例如: BTC/USDT"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_smart_trade",
            "description": "执行风控级实盘开仓交易。系统会在底层自动计算止损并校验资金。",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "例如: BTC/USDT"},
                    "side": {"type": "string", "enum": ["buy", "sell"], "description": "做多(buy)还是做空(sell)"},
                    "amount": {"type": "number", "description": "交易数量，例如 0.01"}
                },
                "required": ["symbol", "side", "amount"]
            }
        }
    }
]

# 工具映射表
available_functions = {
    "get_account_status": get_account_status,
    "get_market_quote": get_market_quote,
    "execute_smart_trade": execute_smart_trade,
}

# ==========================================
# 2. 大脑核心循环
# ==========================================
async def chat_with_openclaw():
    # ⚠️ 领哥：这里填入你的 OpenClaw (或任何大模型) 的 API 配置
    # 你可以把它们加到 .env 里，这里用 os.getenv 读取
    api_key = os.getenv("OPENCLAW_API_KEY", "你的OpenClaw/OpenAI密钥") 
    base_url = os.getenv("OPENCLAW_BASE_URL", "https://api.openai.com/v1") # 如果是自建网关填自建的
    
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    
    system_prompt = """你是领哥的专属量化指挥官。你连接到了极其专业的 Binance Futures 底层架构。
    纪律要求：
    1. 你可以分析市场，但绝不直接瞎给建议。
    2. 当领哥让你分析时，你必须先调用工具获取真实数据再回答。
    3. 当领哥下达开单指令时，你必须严格调用 execute_smart_trade 工具执行。
    4. 说话风格要干练、专业、有军工感。"""

    messages = [{"role": "system", "content": system_prompt}]
    
    print("\n" + "="*50)
    print("🟢 OpenClaw AI 战术终端已上线 (输入 'exit' 退出)")
    print("="*50 + "\n")

    try:
        while True:
            user_input = input("\n[领哥 指令] >>> ")
            if user_input.lower() in ['exit', 'quit']:
                break
                
            messages.append({"role": "user", "content": user_input})
            
            # 第一轮：向 AI 发送请求，带上工具清单
            logger.info("正在请求 OpenClaw 大脑分析...")
            response = await client.chat.completions.create(
                model="gpt-4o", # 替换为你 OpenClaw 实际使用的模型名
                messages=messages,
                tools=tools_definition,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            messages.append(response_message) # 把 AI 的回复加入历史

            # 检查 AI 是否决定调用底层工具！
            tool_calls = response_message.tool_calls
            if tool_calls:
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_to_call = available_functions[function_name]
                    function_args = json.loads(tool_call.function.arguments)
                    
                    logger.warning(f"⚡ AI 触发了底层系统操作: {function_name} | 参数: {function_args}")
                    
                    # 真正执行底层代码！
                    function_response = await function_to_call(**function_args)
                    
                    # 将执行结果喂回给 AI
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                    })
                
                # 第二轮：AI 拿到底层执行结果后，给你总结汇报
                logger.info("底层系统执行完毕，AI 正在生成最终战报...")
                second_response = await client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages
                )
                final_reply = second_response.choices[0].message.content
                print(f"\n🤖 [OpenClaw 指挥官]:\n{final_reply}")
                messages.append({"role": "assistant", "content": final_reply})
            else:
                # AI 只是陪聊，没调用工具
                print(f"\n🤖 [OpenClaw 指挥官]:\n{response_message.content}")

    except Exception as e:
        logger.error(f"核心网关异常: {e}")
    finally:
        await arsenal.shutdown()
        print("\n🔴 OpenClaw AI 战术终端已关闭。")

if __name__ == "__main__":
    asyncio.run(chat_with_openclaw())