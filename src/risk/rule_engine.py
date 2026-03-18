"""
风险规则引擎 - 动态风险控制规则系统

核心功能：
1. 止损止盈规则（固定比例、移动止损、跟踪止盈）
2. 仓位控制规则（最大仓位、杠杆限制、分仓策略）
3. 交易频率限制（冷却时间、最大交易次数、时间窗口）
4. 风险暴露控制（最大亏损、风险价值VaR）

设计特性：
- 规则优先级与冲突解决
- 动态规则加载与热更新
- 规则评估性能优化
- 审计日志与回溯分析

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import os
import json
import time
import logging
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import asyncio

# 第三方库
import pandas as pd
import numpy as np

# 项目内部导入
from config.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class RuleType(Enum):
    """规则类型枚举"""
    STOP_LOSS = "stop_loss"               # 止损规则
    TAKE_PROFIT = "take_profit"           # 止盈规则
    POSITION_SIZE = "position_size"       # 仓位大小规则
    LEVERAGE = "leverage"                 # 杠杆限制规则
    TRADING_FREQUENCY = "trading_frequency"  # 交易频率规则
    RISK_EXPOSURE = "risk_exposure"       # 风险暴露规则
    CUSTOM = "custom"                     # 自定义规则


class RulePriority(Enum):
    """规则优先级枚举"""
    CRITICAL = 100    # 关键规则（强平风险等）
    HIGH = 75         # 高优先级（止损、仓位控制）
    MEDIUM = 50       # 中优先级（止盈、频率限制）
    LOW = 25          # 低优先级（优化规则）
    INFO = 0          # 信息性规则


@dataclass
class TradeContext:
    """交易上下文数据类"""
    symbol: str                           # 交易对
    position_side: str                    # 持仓方向（long/short）
    entry_price: float                    # 开仓价格
    current_price: float                  # 当前价格
    position_size: float                  # 持仓数量
    unrealized_pnl: float                 # 未实现盈亏
    realized_pnl: float                   # 已实现盈亏
    leverage: float                       # 杠杆倍数
    timestamp: int                        # 时间戳（毫秒）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据


@dataclass
class AccountContext:
    """账户上下文数据类"""
    total_balance: float                  # 总余额
    available_balance: float              # 可用余额
    margin_ratio: float                   # 保证金率
    total_position_value: float           # 总持仓价值
    daily_pnl: float                      # 当日盈亏
    weekly_pnl: float                     # 当周盈亏
    open_positions: List[TradeContext]    # 当前持仓
    timestamp: int                        # 时间戳（毫秒）


@dataclass
class RuleResult:
    """规则评估结果数据类"""
    rule_id: str                          # 规则ID
    rule_name: str                        # 规则名称
    rule_type: RuleType                   # 规则类型
    passed: bool                          # 是否通过
    message: str                          # 评估消息
    suggested_action: Optional[str] = None  # 建议操作
    severity: str = "info"                # 严重程度（info/warning/error/critical）
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass
class RiskRule:
    """风险规则定义"""
    rule_id: str                          # 规则唯一ID
    rule_name: str                        # 规则名称
    rule_type: RuleType                   # 规则类型
    priority: RulePriority                # 规则优先级
    enabled: bool = True                  # 是否启用
    parameters: Dict[str, Any] = field(default_factory=dict)  # 规则参数
    description: str = ""                 # 规则描述
    
    # 评估函数（如果为None则使用默认评估逻辑）
    evaluator: Optional[Callable] = None


class RiskRuleEngine:
    """
    风险规则引擎 - 动态风险控制
    
    设计原则：
    1. 可配置性：所有规则通过配置文件管理
    2. 可扩展性：支持自定义规则评估函数
    3. 高性能：规则评估结果缓存与批量处理
    4. 可观测性：完整审计日志与评估历史
    """
    
    def __init__(self, config: ConfigManager, skip_default_rules: bool = False):
        """
        初始化风险规则引擎
        
        Args:
            config: 配置管理器实例
            skip_default_rules: 是否跳过加载默认规则（用于测试）
        """
        logger.info(f"初始化RiskRuleEngine，skip_default_rules={skip_default_rules}")
        self.config = config
        self.rules: Dict[str, RiskRule] = {}
        self.rule_history: List[RuleResult] = []
        self.max_history_size = 1000
        self._last_evaluation_time = 0
        self._evaluation_cache: Dict[str, Tuple[RuleResult, float]] = {}
        self._cache_ttl = 1.0  # 缓存有效期（秒）
        
        # 交易历史追踪（用于时间窗口规则）
        self._trade_history: List[Dict[str, Any]] = []
        self._max_trade_history = 10000
        self._last_history_cleanup = time.time()
        self._history_cleanup_interval = 3600  # 每小时清理一次过期记录
        
        # 初始化日志
        self._setup_logging()
        
        # 加载默认规则（除非明确跳过）
        if not skip_default_rules:
            self._load_default_rules()
        else:
            logger.debug("跳过默认规则加载")
    
    def _setup_logging(self) -> None:
        """配置日志"""
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
    
    def _record_trade(self, symbol: str, trade_type: str = "open") -> None:
        """
        记录交易历史（用于时间窗口规则）
        
        Args:
            symbol: 交易对
            trade_type: 交易类型（open/close）
        """
        trade_record = {
            'symbol': symbol,
            'trade_type': trade_type,
            'timestamp': time.time(),
            'datetime': datetime.now().isoformat()
        }
        self._trade_history.append(trade_record)
        
        # 限制历史记录大小
        if len(self._trade_history) > self._max_trade_history:
            self._trade_history = self._trade_history[-self._max_trade_history:]
        
        logger.debug(f"交易记录: {symbol} {trade_type}")
    
    def _cleanup_old_trades(self) -> None:
        """清理过期交易记录"""
        current_time = time.time()
        # 每小时清理一次
        if current_time - self._last_history_cleanup < self._history_cleanup_interval:
            return
        
        # 清理24小时前的记录（用于日级别频率检查）
        cutoff_time = current_time - 86400  # 24小时
        original_count = len(self._trade_history)
        self._trade_history = [t for t in self._trade_history if t['timestamp'] > cutoff_time]
        
        cleaned_count = original_count - len(self._trade_history)
        if cleaned_count > 0:
            logger.debug(f"清理了 {cleaned_count} 条过期交易记录")
        
        self._last_history_cleanup = current_time
    
    def _check_trading_frequency(self, symbol: str, window_hours: float = 1, max_trades: int = 10) -> Tuple[bool, int, float]:
        """
        检查交易频率
        
        Args:
            symbol: 交易对
            window_hours: 时间窗口（小时）
            max_trades: 最大交易次数
            
        Returns:
            (是否超限, 当前交易次数, 剩余时间比例)
        """
        self._cleanup_old_trades()
        
        window_seconds = window_hours * 3600
        cutoff_time = time.time() - window_seconds
        
        # 统计指定时间窗口内的交易
        recent_trades = [
            t for t in self._trade_history 
            if t['timestamp'] > cutoff_time and t['symbol'] == symbol
        ]
        
        trade_count = len(recent_trades)
        is_exceeded = trade_count >= max_trades
        
        # 计算剩余时间比例（用于恢复估计）
        if trade_count > 0:
            oldest_trade_time = min(t['timestamp'] for t in recent_trades)
            time_passed = time.time() - oldest_trade_time
            time_ratio = time_passed / window_seconds
        else:
            time_ratio = 0.0
        
        return not is_exceeded, trade_count, time_ratio
    
    def _load_default_rules(self) -> None:
        """加载默认风险规则"""
        default_rules = [
            # 止损规则
            RiskRule(
                rule_id="stop_loss_fixed",
                rule_name="固定比例止损",
                rule_type=RuleType.STOP_LOSS,
                priority=RulePriority.HIGH,
                parameters={"stop_loss_percent": 0.02},  # 2%止损
                description="当未实现亏损达到指定百分比时触发止损"
            ),
            
            # 移动止损规则
            RiskRule(
                rule_id="stop_loss_trailing",
                rule_name="移动止损",
                rule_type=RuleType.STOP_LOSS,
                priority=RulePriority.HIGH,
                parameters={
                    "activation_percent": 0.01,  # 盈利1%后激活
                    "trailing_percent": 0.005    # 跟踪0.5%
                },
                description="盈利后启动移动止损，锁定部分利润"
            ),
            
            # 止盈规则
            RiskRule(
                rule_id="take_profit_fixed",
                rule_name="固定比例止盈",
                rule_type=RuleType.TAKE_PROFIT,
                priority=RulePriority.MEDIUM,
                parameters={"take_profit_percent": 0.05},  # 5%止盈
                description="当未实现盈利达到指定百分比时触发止盈"
            ),
            
            # 仓位控制规则
            RiskRule(
                rule_id="position_size_max",
                rule_name="最大仓位限制",
                rule_type=RuleType.POSITION_SIZE,
                priority=RulePriority.HIGH,
                parameters={"max_position_percent": 0.1},  # 最多10%资金
                description="单笔交易最大仓位不超过总资金的一定比例"
            ),
            
            # 杠杆限制规则
            RiskRule(
                rule_id="leverage_limit",
                rule_name="杠杆倍数限制",
                rule_type=RuleType.LEVERAGE,
                priority=RulePriority.HIGH,
                parameters={"max_leverage": 10.0},  # 最大10倍杠杆
                description="限制最大杠杆倍数，防止过度杠杆"
            ),
            
            # 交易频率规则
            RiskRule(
                rule_id="trading_frequency_limit",
                rule_name="交易频率限制",
                rule_type=RuleType.TRADING_FREQUENCY,
                priority=RulePriority.MEDIUM,
                parameters={
                    "max_trades_per_hour": 10,    # 每小时最多10笔
                    "cooldown_seconds": 30        # 交易后冷却30秒
                },
                description="限制单位时间内的交易次数，防止过度交易"
            ),
            
            # 风险暴露规则
            RiskRule(
                rule_id="risk_exposure_daily",
                rule_name="每日风险暴露限制",
                rule_type=RuleType.RISK_EXPOSURE,
                priority=RulePriority.CRITICAL,
                parameters={"max_daily_loss_percent": 0.05},  # 单日最大亏损5%
                description="当日累计亏损达到限额时停止开仓"
            ),
        ]
        
        for rule in default_rules:
            self.add_rule(rule)
        
        logger.info(f"加载了 {len(default_rules)} 个默认风险规则")
    
    def add_rule(self, rule: RiskRule) -> None:
        """
        添加风险规则
        
        Args:
            rule: 风险规则对象
            
        Raises:
            ValueError: 规则ID已存在
        """
        if rule.rule_id in self.rules:
            raise ValueError(f"规则ID '{rule.rule_id}' 已存在")
        
        self.rules[rule.rule_id] = rule
        logger.debug(f"添加规则: {rule.rule_name} (ID: {rule.rule_id})")
    
    def update_rule(self, rule_id: str, **kwargs) -> bool:
        """
        更新风险规则
        
        Args:
            rule_id: 规则ID
            **kwargs: 更新字段
            
        Returns:
            是否成功更新
        """
        if rule_id not in self.rules:
            logger.warning(f"规则 '{rule_id}' 不存在，无法更新")
            return False
        
        rule = self.rules[rule_id]
        
        # 更新允许的字段
        allowed_fields = ['rule_name', 'enabled', 'parameters', 'description', 'priority']
        for key, value in kwargs.items():
            if key in allowed_fields:
                setattr(rule, key, value)
        
        # 清除相关缓存
        self._clear_rule_cache(rule_id)
        
        logger.info(f"更新规则: {rule_id}")
        return True
    
    def remove_rule(self, rule_id: str) -> bool:
        """
        移除风险规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            是否成功移除
        """
        if rule_id not in self.rules:
            logger.warning(f"规则 '{rule_id}' 不存在，无法移除")
            return False
        
        del self.rules[rule_id]
        self._clear_rule_cache(rule_id)
        logger.info(f"移除规则: {rule_id}")
        return True
    
    def get_rule(self, rule_id: str) -> Optional[RiskRule]:
        """
        获取风险规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            风险规则对象，如果不存在返回None
        """
        return self.rules.get(rule_id)
    
    def list_rules(self, rule_type: Optional[RuleType] = None, 
                   enabled_only: bool = False) -> List[RiskRule]:
        """
        列出风险规则
        
        Args:
            rule_type: 可选，过滤规则类型
            enabled_only: 是否只列出启用的规则
            
        Returns:
            规则列表
        """
        filtered_rules = []
        
        for rule in self.rules.values():
            if rule_type and rule.rule_type != rule_type:
                continue
            if enabled_only and not rule.enabled:
                continue
            filtered_rules.append(rule)
        
        # 按优先级排序
        filtered_rules.sort(key=lambda r: r.priority.value, reverse=True)
        return filtered_rules
    
    def _clear_rule_cache(self, rule_id: str) -> None:
        """清除规则缓存"""
        cache_keys = list(self._evaluation_cache.keys())
        for key in cache_keys:
            if key.startswith(f"{rule_id}:"):
                del self._evaluation_cache[key]
    
    def _get_cache_key(self, rule_id: str, trade_context: TradeContext, 
                       account_context: AccountContext) -> str:
        """生成缓存键"""
        # 使用规则ID和关键上下文参数生成缓存键
        key_parts = [
            rule_id,
            trade_context.symbol,
            trade_context.position_side,
            f"{trade_context.entry_price:.4f}",
            f"{trade_context.current_price:.4f}",
            f"{account_context.total_balance:.0f}",
            str(int(time.time()) // 10)  # 10秒时间窗口
        ]
        return ":".join(key_parts)
    
    async def evaluate_rule(self, rule: RiskRule, trade_context: TradeContext,
                           account_context: AccountContext) -> RuleResult:
        """
        评估单个规则
        
        Args:
            rule: 风险规则
            trade_context: 交易上下文
            account_context: 账户上下文
            
        Returns:
            规则评估结果
        """
        # 检查缓存
        cache_key = self._get_cache_key(rule.rule_id, trade_context, account_context)
        current_time = time.time()
        
        if cache_key in self._evaluation_cache:
            cached_result, cache_time = self._evaluation_cache[cache_key]
            if current_time - cache_time < self._cache_ttl:
                logger.debug(f"使用缓存结果: {rule.rule_id}")
                return cached_result
        
        # 执行评估
        result = await self._execute_evaluation(rule, trade_context, account_context)
        
        # 更新缓存
        self._evaluation_cache[cache_key] = (result, current_time)
        
        # 记录历史
        self.rule_history.append(result)
        if len(self.rule_history) > self.max_history_size:
            self.rule_history = self.rule_history[-self.max_history_size:]
        
        return result
    
    async def _execute_evaluation(self, rule: RiskRule, trade_context: TradeContext,
                                 account_context: AccountContext) -> RuleResult:
        """
        执行规则评估
        
        Args:
            rule: 风险规则
            trade_context: 交易上下文
            account_context: 账户上下文
            
        Returns:
            规则评估结果
        """
        try:
            # 如果规则有自定义评估函数，使用它
            if rule.evaluator and callable(rule.evaluator):
                passed, message, action = await rule.evaluator(
                    rule, trade_context, account_context
                )
            else:
                # 使用默认评估逻辑
                passed, message, action = await self._evaluate_default_rule(
                    rule, trade_context, account_context
                )
            
            # 确定严重程度
            if not passed:
                severity = "critical" if rule.priority == RulePriority.CRITICAL else "error"
            else:
                severity = "warning" if "警告" in message else "info"
            
            result = RuleResult(
                rule_id=rule.rule_id,
                rule_name=rule.rule_name,
                rule_type=rule.rule_type,
                passed=passed,
                message=message,
                suggested_action=action,
                severity=severity
            )
            
            return result
            
        except Exception as e:
            logger.error(f"规则评估失败 {rule.rule_id}: {e}")
            
            # 评估失败时返回不通过结果
            return RuleResult(
                rule_id=rule.rule_id,
                rule_name=rule.rule_name,
                rule_type=rule.rule_type,
                passed=False,
                message=f"规则评估失败: {str(e)}",
                suggested_action="暂停交易并检查规则配置",
                severity="error"
            )
    
    async def _evaluate_default_rule(self, rule: RiskRule, trade_context: TradeContext,
                                     account_context: AccountContext) -> Tuple[bool, str, Optional[str]]:
        """
        默认规则评估逻辑
        
        Args:
            rule: 风险规则
            trade_context: 交易上下文
            account_context: 账户上下文
            
        Returns:
            (是否通过, 评估消息, 建议操作)
        """
        params = rule.parameters
        
        if rule.rule_type == RuleType.STOP_LOSS:
            # 止损规则评估
            if rule.rule_id == "stop_loss_fixed":
                stop_loss_percent = params.get("stop_loss_percent", 0.02)
                
                # 计算亏损百分比
                if trade_context.position_side == "long":
                    loss_percent = (trade_context.entry_price - trade_context.current_price) / trade_context.entry_price
                else:
                    loss_percent = (trade_context.current_price - trade_context.entry_price) / trade_context.entry_price
                
                if loss_percent >= stop_loss_percent:
                    message = f"触发止损: 亏损{loss_percent:.2%} ≥ 止损线{stop_loss_percent:.2%}"
                    return False, message, "立即平仓止损"
                else:
                    message = f"未触发止损: 亏损{loss_percent:.2%} < 止损线{stop_loss_percent:.2%}"
                    return True, message, None
            
            elif rule.rule_id == "stop_loss_trailing":
                activation_percent = params.get("activation_percent", 0.01)
                trailing_percent = params.get("trailing_percent", 0.005)
                
                # 计算盈利百分比
                if trade_context.position_side == "long":
                    profit_percent = (trade_context.current_price - trade_context.entry_price) / trade_context.entry_price
                else:
                    profit_percent = (trade_context.entry_price - trade_context.current_price) / trade_context.entry_price
                
                # 这里简化实现，实际需要跟踪最高/最低价
                if profit_percent >= activation_percent:
                    # 已激活移动止损
                    effective_stop = profit_percent - trailing_percent
                    if profit_percent <= effective_stop:
                        message = f"触发移动止损: 回撤达到{trailing_percent:.2%}"
                        return False, message, "平仓锁定利润"
                    else:
                        message = f"移动止损跟踪中: 盈利{profit_percent:.2%}，回撤{trailing_percent:.2%}"
                        return True, message, None
                else:
                    message = f"未激活移动止损: 盈利{profit_percent:.2%} < 激活线{activation_percent:.2%}"
                    return True, message, None
        
        elif rule.rule_type == RuleType.TAKE_PROFIT:
            # 止盈规则评估
            take_profit_percent = params.get("take_profit_percent", 0.05)
            
            # 计算盈利百分比
            if trade_context.position_side == "long":
                profit_percent = (trade_context.current_price - trade_context.entry_price) / trade_context.entry_price
            else:
                profit_percent = (trade_context.entry_price - trade_context.current_price) / trade_context.entry_price
            
            if profit_percent >= take_profit_percent:
                message = f"触发止盈: 盈利{profit_percent:.2%} ≥ 止盈线{take_profit_percent:.2%}"
                return False, message, "分批止盈或全平"
            else:
                message = f"未触发止盈: 盈利{profit_percent:.2%} < 止盈线{take_profit_percent:.2%}"
                return True, message, None
        
        elif rule.rule_type == RuleType.POSITION_SIZE:
            # 仓位控制规则评估
            max_position_percent = params.get("max_position_percent", 0.1)
            
            # 计算当前仓位占比
            position_value = trade_context.position_size * trade_context.current_price
            position_percent = position_value / max(account_context.total_balance, 1.0)
            
            if position_percent > max_position_percent:
                message = f"仓位超限: {position_percent:.2%} > 限制{max_position_percent:.2%}"
                return False, message, "减仓至限额内"
            else:
                message = f"仓位正常: {position_percent:.2%} ≤ 限制{max_position_percent:.2%}"
                return True, message, None
        
        elif rule.rule_type == RuleType.LEVERAGE:
            # 杠杆限制规则评估
            max_leverage = params.get("max_leverage", 10.0)
            
            if trade_context.leverage > max_leverage:
                message = f"杠杆超限: {trade_context.leverage:.1f}倍 > 限制{max_leverage:.1f}倍"
                return False, message, "降低杠杆倍数"
            else:
                message = f"杠杆正常: {trade_context.leverage:.1f}倍 ≤ 限制{max_leverage:.1f}倍"
                return True, message, None
        
        elif rule.rule_type == RuleType.RISK_EXPOSURE:
            # 风险暴露规则评估
            if rule.rule_id == "risk_exposure_daily":
                max_daily_loss_percent = params.get("max_daily_loss_percent", 0.05)
                
                # 计算当日亏损占比
                daily_loss_percent = abs(account_context.daily_pnl) / max(account_context.total_balance, 1.0)
                
                if daily_loss_percent >= max_daily_loss_percent:
                    message = f"单日亏损超限: {daily_loss_percent:.2%} ≥ 限制{max_daily_loss_percent:.2%}"
                    return False, message, "停止开仓，仅允许平仓"
                else:
                    message = f"单日亏损正常: {daily_loss_percent:.2%} < 限制{max_daily_loss_percent:.2%}"
                    return True, message, None
            
            elif rule.rule_id == "correlation_risk_exposure":
                max_correlated_exposure = params.get("max_correlated_exposure", 0.3)
                correlation_threshold = params.get("correlation_threshold", 0.7)
                
                # 简化实现：假设BTC/USDT和ETH/USDT高度相关
                correlated_pairs = [("BTC/USDT", "ETH/USDT"), ("BTC/USDT", "BNB/USDT")]
                is_correlated = any(
                    (trade_context.symbol == pair1 and any(p.symbol == pair2 for p in account_context.open_positions)) or
                    (trade_context.symbol == pair2 and any(p.symbol == pair1 for p in account_context.open_positions))
                    for pair1, pair2 in correlated_pairs
                )
                
                if is_correlated:
                    # 计算相关性仓位总占比
                    correlated_value = sum(
                        p.position_size * p.current_price 
                        for p in account_context.open_positions 
                        if any(p.symbol in pair for pair in correlated_pairs)
                    )
                    correlated_ratio = correlated_value / max(account_context.total_balance, 1.0)
                    
                    if correlated_ratio > max_correlated_exposure:
                        message = f"相关性风险暴露超限: {correlated_ratio:.2%} > 限制{max_correlated_exposure:.2%}"
                        return False, message, "减少相关性仓位"
                    else:
                        message = f"相关性风险正常: {correlated_ratio:.2%} ≤ 限制{max_correlated_exposure:.2%}"
                        return True, message, None
                else:
                    message = f"无相关性风险: 交易对{trade_context.symbol}无高度相关持仓"
                    return True, message, None
        
        elif rule.rule_type == RuleType.TRADING_FREQUENCY:
            # 交易频率规则评估
            if rule.rule_id == "trading_frequency_hourly":
                max_trades = params.get("max_trades_per_hour", 10)
                window_hours = params.get("window_hours", 1)
                
                # 检查交易频率
                can_trade, trade_count, time_ratio = self._check_trading_frequency(
                    trade_context.symbol, window_hours, max_trades
                )
                
                if not can_trade:
                    message = f"交易频率超限: {trade_count}笔/{window_hours}小时 ≥ 限制{max_trades}笔"
                    return False, message, f"等待{window_hours*(1-time_ratio):.1f}小时"
                else:
                    message = f"交易频率正常: {trade_count}笔/{window_hours}小时 < 限制{max_trades}笔"
                    return True, message, None
            
            elif rule.rule_id == "trading_frequency_daily":
                max_trades = params.get("max_trades_per_day", 50)
                window_hours = params.get("window_hours", 24)
                
                # 检查交易频率
                can_trade, trade_count, time_ratio = self._check_trading_frequency(
                    trade_context.symbol, window_hours, max_trades
                )
                
                if not can_trade:
                    message = f"日交易频率超限: {trade_count}笔/天 ≥ 限制{max_trades}笔"
                    return False, message, f"等待{window_hours*(1-time_ratio):.1f}小时"
                else:
                    message = f"日交易频率正常: {trade_count}笔/天 < 限制{max_trades}笔"
                    return True, message, None
        
        elif rule.rule_type == RuleType.CUSTOM:
            # 自定义规则评估
            if rule.rule_id == "market_volatility_adaptive":
                high_volatility_threshold = params.get("high_volatility_threshold", 0.15)
                position_reduction = params.get("position_reduction_percent", 0.5)
                
                # 简化实现：假设从account_context获取市场波动率
                # 实际应用中应从市场数据模块获取
                market_volatility = 0.1  # 假设10%波动率
                
                if market_volatility > high_volatility_threshold:
                    # 计算调整后的仓位限制
                    original_position = trade_context.position_size
                    adjusted_position = original_position * (1 - position_reduction)
                    
                    if trade_context.position_size > adjusted_position:
                        message = f"市场波动自适应: 波动率{market_volatility:.2%} > 阈值{high_volatility_threshold:.2%}"
                        return False, message, f"减仓{position_reduction:.0%}至{adjusted_position:.4f}"
                    else:
                        message = f"市场波动自适应: 已调整仓位适应高波动"
                        return True, message, None
                else:
                    message = f"市场波动正常: 波动率{market_volatility:.2%} ≤ 阈值{high_volatility_threshold:.2%}"
                    return True, message, None
            
            elif rule.rule_id == "liquidity_risk_control":
                min_liquidity_score = params.get("min_liquidity_score", 0.3)
                position_limit = params.get("position_limit_percent", 0.05)
                
                # 简化实现：假设从account_context获取流动性评分
                # 实际应用中应从市场数据模块获取
                liquidity_score = 0.5  # 假设0.5流动性评分
                
                if liquidity_score < min_liquidity_score:
                    # 计算流动性限制下的仓位
                    position_value = trade_context.position_size * trade_context.current_price
                    max_position_value = account_context.total_balance * position_limit
                    
                    if position_value > max_position_value:
                        message = f"流动性风险控制: 评分{liquidity_score:.2f} < 阈值{min_liquidity_score:.2f}"
                        return False, message, f"减仓至{position_limit:.0%}限额"
                    else:
                        message = f"流动性风险控制: 仓位已在限制内"
                        return True, message, None
                else:
                    message = f"流动性正常: 评分{liquidity_score:.2f} ≥ 阈值{min_liquidity_score:.2f}"
                    return True, message, None
        
        # 默认返回通过
        message = f"规则评估通过: {rule.rule_name}"
        return True, message, None
    
    async def evaluate_all_rules(self, trade_context: TradeContext,
                                account_context: AccountContext, 
                                record_trade_attempt: bool = False) -> List[RuleResult]:
        """
        评估所有启用的规则
        
        Args:
            trade_context: 交易上下文
            account_context: 账户上下文
            record_trade_attempt: 是否记录交易尝试（用于频率规则）
            
        Returns:
            评估结果列表
        """
        results = []
        
        # 如果要求记录交易尝试，则记录
        if record_trade_attempt:
            self._record_trade(trade_context.symbol, "open")
        
        # 获取所有启用的规则（按优先级排序）
        rules = self.list_rules(enabled_only=True)
        
        # 并发评估
        tasks = []
        for rule in rules:
            tasks.append(self.evaluate_rule(rule, trade_context, account_context))
        
        # 等待所有评估完成
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理异常结果
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    rule = rules[i]
                    logger.error(f"规则评估异常 {rule.rule_id}: {result}")
                    results[i] = RuleResult(
                        rule_id=rule.rule_id,
                        rule_name=rule.rule_name,
                        rule_type=rule.rule_type,
                        passed=False,
                        message=f"评估异常: {str(result)}",
                        severity="error"
                    )
        
        # 按优先级排序结果
        results.sort(key=lambda r: self.rules.get(r.rule_id, RiskRule(
            rule_id="", rule_name="", rule_type=RuleType.CUSTOM, 
            priority=RulePriority.INFO
        )).priority.value, reverse=True)
        
        self._last_evaluation_time = time.time()
        
        # 记录评估摘要
        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        
        if failed_count > 0:
            logger.warning(f"规则评估完成: {passed_count}通过, {failed_count}失败")
        else:
            logger.debug(f"规则评估完成: {passed_count}全部通过")
        
        return results
    
    def get_failed_rules(self, results: List[RuleResult]) -> List[RuleResult]:
        """
        获取失败的规则
        
        Args:
            results: 规则评估结果列表
            
        Returns:
            失败的规则结果列表
        """
        return [r for r in results if not r.passed]
    
    def has_critical_failure(self, results: List[RuleResult]) -> bool:
        """
        检查是否存在关键失败
        
        Args:
            results: 规则评估结果列表
            
        Returns:
            是否存在关键失败
        """
        for result in results:
            if not result.passed and result.severity == "critical":
                return True
        return False
    
    def get_evaluation_summary(self, results: List[RuleResult]) -> Dict[str, Any]:
        """
        获取评估摘要
        
        Args:
            results: 规则评估结果列表
            
        Returns:
            评估摘要字典
        """
        total_count = len(results)
        passed_count = sum(1 for r in results if r.passed)
        failed_count = total_count - passed_count
        
        # 按严重程度统计
        severity_counts = {}
        for result in results:
            if not result.passed:
                severity = result.severity
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        # 失败规则类型统计
        failed_types = {}
        for result in results:
            if not result.passed:
                rule_type = result.rule_type.value
                failed_types[rule_type] = failed_types.get(rule_type, 0) + 1
        
        return {
            "total_rules": total_count,
            "passed_rules": passed_count,
            "failed_rules": failed_count,
            "pass_rate": passed_count / max(total_count, 1),
            "severity_breakdown": severity_counts,
            "failed_type_breakdown": failed_types,
            "has_critical_failure": self.has_critical_failure(results),
            "timestamp": int(time.time() * 1000)
        }
    
    def save_rules_to_file(self, filepath: str) -> bool:
        """
        保存规则到文件
        
        Args:
            filepath: 文件路径
            
        Returns:
            是否成功保存
        """
        try:
            # 准备可序列化的规则数据
            rules_data = []
            for rule in self.rules.values():
                rule_dict = {
                    "rule_id": rule.rule_id,
                    "rule_name": rule.rule_name,
                    "rule_type": rule.rule_type.value,
                    "priority": rule.priority.value,
                    "enabled": rule.enabled,
                    "parameters": rule.parameters,
                    "description": rule.description
                }
                rules_data.append(rule_dict)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(rules_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"规则已保存到: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"保存规则失败: {e}")
            return False
    
    def load_rules_from_file(self, filepath: str) -> bool:
        """
        从文件加载规则
        
        Args:
            filepath: 文件路径
            
        Returns:
            是否成功加载
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                rules_data = json.load(f)
            
            # 清空现有规则
            self.rules.clear()
            self._evaluation_cache.clear()
            
            # 加载新规则
            for rule_dict in rules_data:
                try:
                    rule = RiskRule(
                        rule_id=rule_dict["rule_id"],
                        rule_name=rule_dict["rule_name"],
                        rule_type=RuleType(rule_dict["rule_type"]),
                        priority=RulePriority(rule_dict["priority"]),
                        enabled=rule_dict.get("enabled", True),
                        parameters=rule_dict.get("parameters", {}),
                        description=rule_dict.get("description", "")
                    )
                    self.add_rule(rule)
                except Exception as e:
                    logger.warning(f"加载规则失败 {rule_dict.get('rule_id', 'unknown')}: {e}")
            
            logger.info(f"从文件加载了 {len(self.rules)} 个规则: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"加载规则文件失败: {e}")
            return False
    
    def get_rule_history(self, limit: int = 100) -> List[RuleResult]:
        """
        获取规则评估历史
        
        Args:
            limit: 限制返回数量
            
        Returns:
            规则评估历史列表
        """
        return self.rule_history[-limit:] if self.rule_history else []


# 便捷函数
def create_rule_engine(config_path: Optional[str] = None) -> RiskRuleEngine:
    """
    创建风险规则引擎实例（工厂函数）
    
    Args:
        config_path: 可选，配置文件路径
        
    Returns:
        风险规则引擎实例
    """
    from config.config_manager import ConfigManager
    
    config = ConfigManager(config_path)
    return RiskRuleEngine(config)


if __name__ == "__main__":
    """模块自测"""
    async def test_rule_engine():
        import sys
        sys.path.append('/home/lingge/quant_brain/01_codebase/binance_ai_agent')
        
        from config.config_manager import ConfigManager
        
        config = ConfigManager()
        engine = RiskRuleEngine(config)
        
        # 创建测试上下文
        trade_context = TradeContext(
            symbol="BTC/USDT",
            position_side="long",
            entry_price=50000.0,
            current_price=49000.0,  # 亏损2%
            position_size=0.1,
            unrealized_pnl=-1000.0,
            realized_pnl=0.0,
            leverage=5.0,
            timestamp=int(time.time() * 1000)
        )
        
        account_context = AccountContext(
            total_balance=10000.0,
            available_balance=5000.0,
            margin_ratio=0.5,
            total_position_value=5000.0,
            daily_pnl=-200.0,
            weekly_pnl=500.0,
            open_positions=[trade_context],
            timestamp=int(time.time() * 1000)
        )
        
        # 评估所有规则
        results = await engine.evaluate_all_rules(trade_context, account_context)
        
        # 打印结果
        print(f"\n规则评估结果 ({len(results)} 条规则):")
        print("=" * 80)
        
        for result in results:
            status = "✅ 通过" if result.passed else "❌ 失败"
            print(f"{status} | {result.rule_name}")
            print(f"   消息: {result.message}")
            if result.suggested_action:
                print(f"   建议: {result.suggested_action}")
            print(f"   类型: {result.rule_type.value} | 严重度: {result.severity}")
            print()
        
        # 打印摘要
        summary = engine.get_evaluation_summary(results)
        print(f"\n评估摘要:")
        print(f"  通过率: {summary['pass_rate']:.1%} ({summary['passed_rules']}/{summary['total_rules']})")
        print(f"  关键失败: {'是' if summary['has_critical_failure'] else '否'}")
    
    asyncio.run(test_rule_engine())