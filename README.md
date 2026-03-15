
# 🌌 领哥量化机甲 (Quant-Zero V1.0 满配版)
**币安 AI 智能交易信号与 SMC 风控 Agent**

基于 OpenClaw 的 AI 驱动交易 Agent，专为币安大客户及量化极客打造。
本项目集成了**大语言模型语义解析**、**SMC 机构级盘面推演**与**彭博终端级 UI 面板**，彻底颠覆传统量化机器人的交互体验。

---

## 🎯 核心黑科技 (Core Features)

- **🧠 SMC 机构级参谋大脑**：抓取 48H 链上/盘口数据，AI 自动推演流动性池 (Liquidity Sweep) 与订单块，输出高盈亏比战术预案。
- **⚡️ 极速自然语言执行**：支持自然语言开仓（如：“做空 1000U 的 BTC”），自动测算仓位并换算 U 本位价值。
- **🛡️ 上帝视角独立风控**：彻底告别“裸奔”！智能识别多空方向，独立为现有仓位极速补挂 Algo 条件单（止盈/止损），防范插针。
- **🏦 彭博级金库终端**：一键 `/balance`，直接在 Telegram 渲染树状多空持仓明细与实时盈亏，账户状况一目了然。
- **💥 一键紧急熔断**：发送 `/closeall`，兼容单/双向持仓的三段式暴力平仓引擎瞬间接管，平仓后自动生成详尽的“战损结算清单”。

---

## 📁 核心架构蓝图 (Project Structure)

我们采用了严谨的模块化分层架构，确保数据抓取、信号推演与实盘风控的绝对隔离：

```text
binance-ai-agent/
├── config/                    # 静态策略与全局配置
│   ├── config.yaml            # 主配置文件 (API、网络、日志参数)
│   └── symbols.yaml           # 交易对详细风控参数 (限额、滑点、精度)
├── src/                       # 量化底座引擎核心 (Core)
│   ├── data/                  # 数据采集层 (WebSocket 实盘流, ccxt 历史数据)
│   ├── signals/               # 信号处理层 (传统技术指标共振, AI 模型对接)
│   ├── risk/                  # 风控引擎 (SMC风控逻辑, 账户状态监控, 动态止损)
│   └── execution/             # 交易执行层 (单/双向持仓智能适配, 订单生命周期管理)
├── scripts/                   # 自动化任务与运维脚本
├── tests/                     # 单元测试与边界压测模块
├── logs/                      # 运行日志存储 (已在 gitignore 中隔离)
├── data/                      # 本地数据缓存 (K线快照、盘口深度)
├── telegram_gateway.py        # 🌟 AI 语义交互主网关 (控制台入口)
├── main_auto_bot.py           # 🤖 全自动量化轮询引擎 (策略无人值守执行)
├── requirements.txt           # Python 依赖清单
├── .env.example               # 环境变量与密钥配置示例
└── README.md                  # 机甲说明书
```

---

## 🚀 极速安装指南 (Quick Start)

为了保证您的 API 密钥安全，并避免环境冲突，请严格按照以下标准流程部署：

### 1. 克隆机甲仓库

```bash
git clone https://github.com/lingge66/binance-ai-agent.git
cd binance-ai-agent
```

### 2. 铸造独立运行环境 (强烈推荐)

切勿污染系统全局 Python 环境，请使用 venv 创建独立隔离区：

```bash
# 创建名为 quant_venv 的虚拟环境
python3 -m venv quant_venv

# 激活环境 (Linux / macOS)
source quant_venv/bin/activate
# Windows 用户请使用: quant_venv\Scripts\activate

# 一键安装底层驱动依赖
pip install -r requirements.txt
```

### 3. 🔐 配置核心密钥 (安全最高优先级)

机甲的运行依赖币安 API 和 Telegram 机器人授权。我们采用“零信任”设计，所有密钥仅存在于本地。

```bash
# 复制配置模板
cp .env.example .env
```

用编辑器打开 `.env` 文件，填入您的密钥信息。

⚠️ **币安 API 权限警告**：  
申请 API Key 时，仅勾选“允许读取”和“允许合约交易”。  
**绝对禁止勾选“允许提现”！** 本程序从不需要、也永远不会要求提现权限。

### 4. 点火启动

```bash
# 启动 Telegram 独立网关
python telegram_gateway.py
```

（推荐进阶用户使用 `pm2 start telegram_gateway.py --name Quant-Bot` 进行后台守护运行）

---

## 🛡️ 国防级安全红线 (Security Guidelines)

本项目将用户的资金安全置于绝对的第一优先级。我们内置了以下物理与逻辑防线：

1. **密钥物理隔离**：所有的私密配置必须写入 `.env` 文件。该文件已被 `.gitignore` 永久拉黑，绝不会被意外推送到 GitHub。
2. **Algo 接口防漏**：所有风控挂单严格采用币安最新 `fapi/v1/algoOrder` 接口，强制要求 `CONDITIONAL` 和 `closePosition=true` 属性，防止止损单变反向开仓。
3. **单日亏损熔断**：风控引擎实时监控（Margin Ratio），触发阈值强制停止开仓。
4. **日志自动脱敏**：任何打印到终端或文件的日志，API Key 均会进行 `***` 遮罩处理。

---

## 📊 路线图与开发状态

| 核心模块 | 功能描述 | 状态 |
|----------|----------|------|
| SMC 行情雷达 | 抓取资金费率、OI，推演订单块与盈亏比 | ✅ 完成 |
| UI 渲染引擎 | 彭博级树状资产与持仓盈亏结算面板 | ✅ 完成 |
| 智能风控挂载 | 多空智能识别，独立补挂止损/止盈 | ✅ 完成 |
| 全天候平仓器 | 兼容 One-way 与 Hedge 模式的一键熔断 | ✅ 完成 |
| 多模型融合 | 接入 LSTM / Transformer 本地走势预测 | 🔄 优化中 |

---

## 📞 技术支持与联系

- **开发者**：lingge66 和 AI 团队
- **运行环境要求**：Ubuntu/Debian Linux, Python 3.9+

---

## ⚠️ 免责声明

加密货币合约交易具有极高风险。本项目代码开源仅供技术交流与比赛演示。在使用实盘（Live）模式前，请务必在 Testnet（测试网）充分验证。您对自己的所有交易结果负完全责任。

---

Copyright (c) 2026 lingge66. All rights reserved. Licensed under the GPL-3.0 License.
