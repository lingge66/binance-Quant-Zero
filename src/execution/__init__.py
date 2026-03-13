"""
交易执行层模块 - 负责订单管理、交易执行与仓位管理

模块组成：
1. order_manager - 订单创建、修改、取消与状态追踪
2. executor - 交易执行器（模拟/实盘切换、执行策略）
3. position_manager - 仓位管理与同步
4. execution_risk - 执行风险控制

设计原则：
- 安全隔离：模拟与实盘环境严格隔离
- 容错执行：指数退避重试、异常恢复
- 实时同步：仓位与订单状态秒级同步
- 审计追踪：完整交易记录与执行日志

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

__version__ = '1.0.0'
__author__ = 'Coder'

# 导出模块
from .order_manager import OrderManager, Order, OrderType, OrderSide, OrderStatus
from .executor import TradeExecutor, ExecutionMode, ExecutionStrategy, ExecutionStatus, TradeSignal, ExecutionResult
from .position_manager import PositionManager, Position, PositionSide, PositionStatus
from .execution_risk import ExecutionRiskController, RiskCheckResult, RiskCheck, LiquidityMetrics

__all__ = [
    # 订单管理
    'OrderManager', 'Order', 'OrderType', 'OrderSide', 'OrderStatus',
    
    # 交易执行
    'TradeExecutor', 'ExecutionMode', 'ExecutionStrategy', 'ExecutionStatus', 
    'TradeSignal', 'ExecutionResult',
    
    # 仓位管理
    'PositionManager', 'Position', 'PositionSide', 'PositionStatus',
    
    # 执行风险
    'ExecutionRiskController', 'RiskCheckResult', 'RiskCheck', 'LiquidityMetrics',
]