# 币安AI智能交易信号与风控Agent

基于OpenClaw的AI驱动交易Agent，参与币安AI大赛。

## 🎯 项目概述

### 核心功能
- **实时监控**：币安现货市场多币种实时数据
- **AI信号生成**：技术指标 + 轻量ML模型预测
- **智能风控**：账户保护、动态止损、亏损熔断
- **安全交易**：模拟/实盘切换、二次确认机制
- **即时通知**：Telegram推送、日报生成

### 对币安生态的价值
1. **用户体验**：降低新手爆仓率，提供专业交易辅助
2. **生态展示**：展示币安API稳定性与丰富性
3. **安全示范**：贯彻"最小权限原则"，树立安全典范
4. **创新示例**：AI+交易的实际落地案例

## 📁 项目结构

```
binance_ai_agent/
├── config/                    # 配置文件
│   ├── config.yaml           # 主配置文件
│   └── symbols.yaml          # 交易对详细配置
├── src/                      # 源代码
│   ├── data/                 # 数据采集层
│   │   ├── data_collector.py # 数据采集器主类
│   │   ├── websocket_client.py # WebSocket客户端
│   │   └── historical_data.py # 历史数据获取
│   ├── signals/              # 信号处理层
│   ├── risk/                 # 风控引擎
│   ├── execution/            # 交易执行层
│   ├── notification/         # 通知层
│   └── utils/                # 工具函数
│       ├── config_loader.py  # 配置加载器
│       └── exponential_backoff.py # 指数退避算法
├── scripts/                  # 脚本
│   ├── test_data_collector.py # 数据采集层测试
│   └── start_agent.py        # 启动脚本
├── tests/                    # 单元测试
├── logs/                     # 日志目录
├── data/                     # 数据存储
├── .env.example              # 环境变量示例
└── README.md                 # 本文档
```

## 🚀 快速开始

### 1. 环境准备
```bash
# 使用外部隔离虚拟环境（必须）
# 禁止在项目目录内创建虚拟环境

# 激活虚拟环境
source /home/lingge/quant_venv/bin/activate

# 安装依赖
python -m pip install websockets ccxt pandas numpy aiohttp python-telegram-bot
```

### 2. 配置文件
```bash
# 复制环境变量示例
cp .env.example .env

# 编辑 .env 文件，填写API密钥
# 重要：.env文件切勿提交到版本控制
```

### 3. 运行测试
```bash
# 测试数据采集层
python scripts/test_data_collector.py
```

### 4. 启动Agent
```bash
# 启动Agent（开发中）
python scripts/start_agent.py
```

## ⚙️ 配置说明

### 环境变量 (.env)
- `BINANCE_API_KEY`：币安API密钥
- `BINANCE_SECRET_KEY`：币安Secret密钥
- `BINANCE_TESTNET`：是否使用测试网 (true/false)
- `TELEGRAM_BOT_TOKEN`：Telegram Bot Token
- `TELEGRAM_CHAT_ID`：Telegram Chat ID

### 主配置文件 (config.yaml)
- **binance**：币安API配置
- **data**：数据采集配置（交易对、间隔、WebSocket参数）
- **signals**：信号生成配置（技术指标、AI模型参数）
- **risk**：风控配置（账户监控、止损规则）
- **execution**：交易执行配置（模式、订单类型）
- **notification**：通知配置（Telegram、报告）
- **logging**：日志配置

### 交易对配置 (symbols.yaml)
- **基础信息**：base_asset, quote_asset
- **交易参数**：min_notional, min_quantity, step_size, tick_size
- **风控参数**：max_position_ratio, volatility_multiplier
- **信号权重**：signal_weight

## 🔧 核心模块

### 数据采集层 (已完成)
- **WebSocket客户端**：实时数据订阅、断线重连、数据解析
- **历史数据获取**：使用ccxt获取历史K线、数据缓存、文件存储
- **配置加载器**：YAML配置文件 + 环境变量合并
- **指数退避算法**：网络请求重试、连接重连

### 信号处理层 (开发中)
- **技术指标**：MA, RSI, 布林带, MACD, ATR, KDJ
- **AI模型**：LSTM/Transformer预测未来价格走势
- **信号融合**：多指标权重融合、信号等级划分

### 风控引擎 (待开发)
- **账户监控**：保证金率、仓位比例、单日亏损
- **动态止损**：ATR移动止损、跟踪止盈
- **熔断机制**：连续亏损停止、市场异常暂停

### 交易执行层 (待开发)
- **订单管理**：限价单、市价单、条件单
- **模式切换**：simulation, paper, live 三种模式
- **二次确认**：主网交易前必须用户确认

### 通知层 (待开发)
- **Telegram Bot**：实时信号推送、风险警报
- **报告生成**：日报、周报、交易统计
- **OpenClaw集成**：自然语言交互、状态查询

## 🛡️ 安全架构

### 零信任安全隔离
- 所有API密钥从环境变量读取，代码零硬编码
- 日志中敏感信息自动脱敏（显示前5后4字符）
- 配置文件分离，Git禁止提交.env文件

### 极端容错设计
- WebSocket断线指数退避重连（1s, 2s, 4s... max 64s）
- API请求失败自动重试，失败熔断
- 心跳检测，异常自动重启

### 交易安全保护
- 主网交易前强制二次确认（输入"CONFIRM"）
- 单日亏损熔断（默认5%停止开仓）
- 最大仓位限制（默认单一币种30%）
- 提现权限绝对禁止

## 📊 演示计划

### 演示视频要点 (3分钟)
1. **开场**：项目介绍与价值主张 (30s)
2. **架构**：系统架构图讲解 (60s)
3. **功能演示**：完整交易流程 (90s)
   - 实时数据展示
   - AI信号生成
   - 风险警报触发
   - Testnet下单演示
4. **安全特性**：密钥隔离、二次确认 (60s)
5. **总结**：对币安生态的价值 (30s)

### 图文材料
- **架构图**：Mermaid/PlantUML绘制
- **代码片段**：突出安全性与专业性
- **运行截图**：终端输出、Telegram消息
- **数据图表**：信号准确性、风险控制效果

## 📅 开发时间表

| 阶段 | 时间 | 交付物 | 状态 |
|------|------|--------|------|
| 详细设计 | 3月12日 | 架构设计文档 | ✅ 完成 |
| 数据采集层 | 3月13日 | WebSocket+历史数据 | ✅ 完成 |
| 信号处理层 | 3月14日 | 技术指标+AI模型 | 🔄 进行中 |
| 风控引擎 | 3月15日 | 账户监控+止损 | ⏳ 待开始 |
| 交易执行层 | 3月16日 | 订单管理+模式切换 | ⏳ 待开始 |
| 通知与集成 | 3月17日 | Telegram+OpenClaw | ⏳ 待开始 |
| 测试优化 | 3月18日 | 单元测试+压力测试 | ⏳ 待开始 |
| 演示准备 | 3月18日 | 视频录制+文档整理 | ⏳ 待开始 |

## 🚨 安全红线

### 绝对禁止
1. **禁止**在 `/home/lingge/quant_brain/` 下创建虚拟环境
2. **禁止**在代码中硬编码API密钥
3. **禁止**在日志中打印完整密钥信息
4. **禁止**Git提交.env配置文件

### 必须遵守
1. **必须**使用外部隔离环境：`/home/lingge/quant_venv/`
2. **必须**从环境变量读取敏感配置
3. **必须**实现二次确认机制（主网交易）
4. **必须**设置交易限额和亏损熔断

## 🐛 故障排除

### 常见问题

#### Q: WebSocket连接失败
```
解决方案：
1. 检查网络连接
2. 验证API密钥权限
3. 确认测试网/主网环境
4. 查看防火墙设置
```

#### Q: 历史数据获取为空
```
解决方案：
1. 检查交易对是否支持
2. 验证时间范围是否有效
3. 确认ccxt版本兼容性
4. 查看API速率限制
```

#### Q: 配置文件加载错误
```
解决方案：
1. 检查YAML格式是否正确
2. 确认文件路径
3. 验证环境变量设置
4. 查看配置文件权限
```

### 日志查看
```bash
# 查看实时日志
tail -f logs/agent.log

# 查看错误日志
grep -i error logs/agent.log

# 查看WebSocket连接日志
grep -i websocket logs/agent.log
```

## 📞 联系方式

- **项目负责人**：Coder (OpenClaw Agent)
- **开发环境**：Ubuntu Linux, Python 3.9+
- **项目仓库**：`/home/lingge/quant_brain/01_codebase/binance_ai_agent/`
- **最后更新**：2026-03-13

## 📄 许可证

本项目为币安AI大赛参赛作品，代码仅供参考学习。
请勿用于未经授权的商业用途。

---

**免责声明**：加密货币交易具有高风险，本项目仅为技术演示。
使用实盘交易功能前，请充分了解风险并自行承担交易后果。