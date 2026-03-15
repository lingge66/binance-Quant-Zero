
# 🌌 领哥量化机甲 (Quant-Zero V1.0 满配版)
**币安 AI 智能交易信号与 SMC 风控 Agent**

基于 OpenClaw 的 AI 驱动交易 Agent，专为币安客户及量化极客打造。
本项目集成了**大语言模型语义解析**、**SMC 机构级盘面推演**与**彭博终端级 UI 面板**，彻底颠覆传统量化机器人的交互体验。

---

## 🎯 核心黑科技 (Core Features)

- **🧠 SMC 机构级参谋大脑**：抓取 48H 链上/盘口数据，AI 自动推演流动性池 (Liquidity Sweep) 与订单块，输出高盈亏比战术预案。
- **⚡️ 极速自然语言执行**：支持自然语言开仓（如：“做空 1000U 的 BTC”），自动测算仓位并换算 U 本位价值。
- **🛡️ 上帝视角独立风控**：彻底告别“裸奔”！智能识别多空方向，独立为现有仓位极速补挂 Algo 条件单（止盈/止损），防范插针。
- **🏦 彭博级金库终端**：一键 `/balance`，直接在 Telegram 渲染树状多空持仓明细与实时盈亏，账户状况一目了然。
- **💥 一键紧急熔断**：发送 `/closeall`，兼容单/双向持仓的三段式暴力平仓引擎瞬间接管，平仓后自动生成详尽的“战损结算清单”。
- **🤖 自动化交易**：发送‘开启自动交易’命令，启动全自动量化轮询引擎（策略无人值守执行），策略可随时优化。
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

为了更安全、稳定地运行本交易机甲，并防止与您现有的 OpenClaw 或其他机器人产生消息冲突，请严格按照以下**“零冲突架构”**进行独立部署。

### 🤖 方式一：OpenClaw 助手一键全自动部署 (极客推荐)

如果您已经在运行 OpenClaw，可以直接向您的 OpenClaw 助手发送以下“魔法咒语”，让它为您代劳基础安装：

**Prompt 提示词：**

> "你好，请帮我在服务器上部署『领哥量化机甲』。请依次执行：1. git clone https://github.com/lingge66/binance-ai-agent.git 2. 进入目录并用 python3 -m venv quant_venv 创建虚拟环境。3. 激活环境并 pip install -r requirements.txt。4. 将 .env.example 复制为 .env。完成后告诉我，我将手动去配置密钥。"

### 💻 方式二：标准手动部署流程

#### 第一步：申请专属的“量化机甲 BOT” (隔离冲突)

为避免消息拦截冲突，请勿使用已有的机器人 Token。

1. 前往 Telegram 搜索 @BotFather
2. 发送 `/newbot`，花 10 秒钟创建一个全新的专属机器人（例如：`lingge_quant_bot`）
3. 复制获取那个崭新的、专属的 Bot Token

#### 第二步：克隆代码与铸造独立环境

切勿污染系统全局 Python 环境，请使用 venv 创建独立隔离区：

```bash
git clone https://github.com/lingge66/binance-ai-agent.git
cd binance-ai-agent
python3 -m venv quant_venv
source quant_venv/bin/activate  # Windows 用户: quant_venv\Scripts\activate
pip install -r requirements.txt
```

#### 第三步：🔐 独立配置 .env 核心密钥 (最高安全优先级)

本系统是完全解耦的，所有私密配置仅留存本地。

```bash
cp .env.example .env
```

打开 `.env` 文件，注入机甲灵魂：

- **TELEGRAM_BOT_TOKEN**: 填入刚在第一步申请的专属 Token
- **BINANCE_API_KEY / SECRET**: 填入您的币安 API（主网或测试网）
- **LLM_API_KEY**: 填入大语言模型（OpenAI / DeepSeek 等）的 API Key 和 Base URL，用于赋能机甲的语义解析大脑

⚠️ **币安 API 权限警告：**  
申请 API Key 时，仅勾选“允许读取”和“允许合约交易”。  
**绝对禁止勾选“允许提现”！** 本系统从不需要、也永远不会要求提现权限。  
重要提醒：实盘API必须绑定IP,关闭提现功能。

#### 第四步：点火启动

```bash
# 启动 Telegram 独立网关 (人工指挥所)
python telegram_gateway.py

# (可选) 新开一个终端窗口，启动全自动交易引擎
python main_auto_bot.py
```

## 🛡️ 国防级安全红线 (Security Guidelines)

用户的资金安全是本系统的最高准则，内置以下四道核心防线：

- **物理隔离**：所有的私密配置必须写入 `.env` 文件，该文件已被 `.gitignore` 永久拉黑，绝不会被推送到 GitHub。
- **拔网线级全撤全平**：触发 `/closeall` 时，优先强制撤销所有待触发挂单释放保证金，再进行三段式暴力重试平仓。
- **防插针挂单**：风控挂单严格采用币安最新 `fapi/v1/algoOrder` 接口，强制绑定 `CONDITIONAL` 和 `closePosition=true` 属性，彻底杜绝止损单变反向开仓。
- **日志脱敏**：任何打印到终端或输出文件的日志，敏感 API Key 均会进行遮罩处理。

---

## 📞 技术支持与声明

**主架构师**：lingge66 & AI 团队

**环境要求**：Ubuntu/Debian Linux, Python 3.9+

**免责声明**：加密货币合约交易具有极高风险。本项目代码开源仅供技术交流与比赛演示。在使用实盘（Live）模式前，请务必在 Testnet（测试网）充分验证。您对自己的所有交易行为及结果负完全责任。

---

Copyright (c) 2026 lingge66. All rights reserved. Licensed under the GPL-3.0 License.
