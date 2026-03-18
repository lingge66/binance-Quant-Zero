"""
风控引擎模块 - 负责交易风险控制与管理

模块组成：
1. account_monitor - 账户监控与资金管理
2. rule_engine - 风险规则引擎（止损止盈、仓位控制）
3. circuit_breaker - 熔断机制（单日亏损、连续亏损、市场异常）
4. reporter - 风险报告与仪表盘

设计原则：
- 实时监控：秒级监控账户状态
- 多层防御：规则引擎 + 熔断机制双重保护
- 静默恢复：异常时自动降级而非崩溃
- 审计追踪：所有风险事件完整记录

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

from .account_monitor import AccountMonitor
from .rule_engine import RiskRuleEngine
from .circuit_breaker import CircuitBreaker
from .reporter import RiskReporter

__all__ = [
    'AccountMonitor',
    'RiskRuleEngine', 
    'CircuitBreaker',
    'RiskReporter',
]

__version__ = '1.0.0'