"""
熔断机制模块 - 交易系统安全熔断器

核心功能：
1. 单日亏损熔断：当日累计亏损超过阈值时停止开仓
2. 连续亏损熔断：连续N次亏损后冷却一段时间
3. 市场异常熔断：波动率突增、流动性不足时暂停交易
4. 系统异常熔断：API故障、网络异常时自动降级

设计特性：
- 状态机管理：正常/预警/熔断/恢复四种状态
- 自动恢复：熔断后按策略自动恢复交易
- 分级熔断：轻度/中度/重度三级熔断响应
- 审计追踪：完整熔断事件日志

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import os
import time
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import asyncio
import json

# 第三方库
import pandas as pd
import numpy as np

# 项目内部导入
from config.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class BreakerState(Enum):
    """熔断器状态枚举"""
    NORMAL = "normal"           # 正常状态，允许所有交易
    WARNING = "warning"         # 预警状态，限制部分交易
    TRIPPED = "tripped"         # 熔断状态，停止所有开仓（允许平仓）
    RECOVERY = "recovery"       # 恢复状态，逐步放宽限制


class BreakerSeverity(Enum):
    """熔断严重程度枚举"""
    MILD = "mild"        # 轻度熔断，仅限制高风险交易
    MODERATE = "moderate"  # 中度熔断，限制大部分开仓
    SEVERE = "severe"    # 重度熔断，停止所有交易


class BreakerType(Enum):
    """熔断类型枚举"""
    DAILY_LOSS = "daily_loss"           # 单日亏损熔断
    CONSECUTIVE_LOSS = "consecutive_loss"  # 连续亏损熔断
    MARKET_VOLATILITY = "market_volatility"  # 市场波动熔断
    LIQUIDITY_CRISIS = "liquidity_crisis"  # 流动性危机熔断
    SYSTEM_ERROR = "system_error"       # 系统错误熔断
    MANUAL = "manual"                   # 手动熔断


@dataclass
class TradeRecord:
    """交易记录数据类"""
    trade_id: str                       # 交易ID
    symbol: str                         # 交易对
    side: str                           # 方向（buy/sell）
    position_side: str                  # 持仓方向（long/short）
    entry_price: float                  # 开仓价格
    position_size: float                # 持仓数量
    exit_price: Optional[float] = None  # 平仓价格（未平仓为None）
    pnl: float = 0.0                    # 盈亏金额
    pnl_percent: float = 0.0            # 盈亏百分比
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))  # 时间戳
    closed: bool = False                # 是否已平仓


@dataclass
class BreakerEvent:
    """熔断事件数据类"""
    event_id: str                       # 事件ID
    breaker_type: BreakerType           # 熔断类型
    severity: BreakerSeverity           # 严重程度
    old_state: BreakerState             # 旧状态
    new_state: BreakerState             # 新状态
    trigger_value: float                # 触发值
    threshold: float                    # 阈值
    message: str                        # 事件描述
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))  # 时间戳
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据


@dataclass
class MarketMetrics:
    """市场指标数据类"""
    symbol: str                         # 交易对
    current_price: float                # 当前价格
    volatility_24h: float               # 24小时波动率
    spread_percent: float               # 买卖价差百分比
    volume_24h: float                   # 24小时交易量
    liquidity_score: float              # 流动性评分（0-1）
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))  # 时间戳


class CircuitBreaker:
    """
    熔断器 - 交易系统安全保护机制
    
    设计原则：
    1. 预防性：在风险积累前提前预警
    2. 响应性：快速检测并触发熔断
    3. 恢复性：熔断后按策略逐步恢复
    4. 透明性：完整的熔断事件日志与状态跟踪
    """
    
    def __init__(self, config: ConfigManager):
        """
        初始化熔断器
        
        Args:
            config: 配置管理器实例
        """
        self.config = config
        self.state = BreakerState.NORMAL
        self.severity = BreakerSeverity.MILD
        self.active_breakers: Set[BreakerType] = set()
        
        # 交易记录
        self.trade_history: List[TradeRecord] = []
        self.max_trade_history = 1000
        
        # 熔断事件历史
        self.event_history: List[BreakerEvent] = []
        self.max_event_history = 500
        
        # 状态追踪
        self._state_start_time = time.time()
        self._last_check_time = 0
        self._check_interval = 5  # 检查间隔（秒）
        
        # 连续亏损计数
        self.consecutive_losses = 0
        self.max_consecutive_losses = 3
        
        # 单日亏损追踪
        self.daily_start_time = self._get_today_start()
        self.daily_pnl = 0.0
        self.daily_loss_limit = -0.05  # 单日最大亏损5%
        
        # 市场异常检测
        self.market_volatility_threshold = 0.10  # 波动率阈值10%
        self.liquidity_threshold = 0.01  # 流动性阈值1%
        
        # 熔断恢复配置
        self.recovery_check_interval = 60  # 恢复检查间隔（秒）
        self.recovery_steps = 3  # 恢复步数
        
        # 初始化日志
        self._setup_logging()
        
        # 加载配置
        self._load_config()
    
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
    
    def _load_config(self) -> None:
        """加载配置"""
        try:
            # 从配置读取熔断参数
            breaker_config = self.config.get('risk.circuit_breaker', {})
            
            if breaker_config:
                self.max_consecutive_losses = breaker_config.get('max_consecutive_losses', 3)
                self.daily_loss_limit = breaker_config.get('daily_loss_limit', -0.05)
                self.market_volatility_threshold = breaker_config.get('market_volatility_threshold', 0.10)
                self.liquidity_threshold = breaker_config.get('liquidity_threshold', 0.01)
                self.recovery_check_interval = breaker_config.get('recovery_check_interval', 60)
                self.recovery_steps = breaker_config.get('recovery_steps', 3)
                
                logger.info(f"熔断配置加载: 连续亏损={self.max_consecutive_losses}, 单日亏损={self.daily_loss_limit:.1%}")
        except Exception as e:
            logger.warning(f"加载熔断配置失败，使用默认值: {e}")
    
    def _get_today_start(self) -> float:
        """获取今日开始时间戳"""
        now = datetime.now()
        today_start = datetime(now.year, now.month, now.day)
        return today_start.timestamp()
    
    def _reset_daily_if_needed(self) -> None:
        """如果需要，重置每日统计"""
        current_time = time.time()
        if current_time - self.daily_start_time >= 86400:  # 24小时
            logger.info("每日统计重置")
            self.daily_start_time = self._get_today_start()
            self.daily_pnl = 0.0
    
    def add_trade_record(self, trade: TradeRecord) -> None:
        """
        添加交易记录
        
        Args:
            trade: 交易记录
        """
        self.trade_history.append(trade)
        
        # 限制历史记录大小
        if len(self.trade_history) > self.max_trade_history:
            self.trade_history = self.trade_history[-self.max_trade_history:]
        
        # 更新统计
        if trade.closed:
            self.daily_pnl += trade.pnl
            
            # 更新连续亏损计数
            if trade.pnl < 0:
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0
            
            logger.debug(f"交易记录添加: {trade.symbol} PnL={trade.pnl:.2f}, 连续亏损={self.consecutive_losses}")
    
    def _create_event(self, breaker_type: BreakerType, severity: BreakerSeverity,
                     old_state: BreakerState, new_state: BreakerState,
                     trigger_value: float, threshold: float, message: str,
                     metadata: Dict[str, Any] = None) -> BreakerEvent:
        """
        创建熔断事件
        
        Args:
            breaker_type: 熔断类型
            severity: 严重程度
            old_state: 旧状态
            new_state: 新状态
            trigger_value: 触发值
            threshold: 阈值
            message: 事件描述
            metadata: 额外元数据
            
        Returns:
            熔断事件
        """
        event_id = f"breaker_{int(time.time() * 1000)}_{breaker_type.value}"
        event = BreakerEvent(
            event_id=event_id,
            breaker_type=breaker_type,
            severity=severity,
            old_state=old_state,
            new_state=new_state,
            trigger_value=trigger_value,
            threshold=threshold,
            message=message,
            timestamp=int(time.time() * 1000),
            metadata=metadata or {}
        )
        
        self.event_history.append(event)
        if len(self.event_history) > self.max_event_history:
            self.event_history = self.event_history[-self.max_event_history:]
        
        return event
    
    def _change_state(self, new_state: BreakerState, breaker_type: BreakerType,
                     severity: BreakerSeverity, trigger_value: float,
                     threshold: float, message: str) -> bool:
        """
        改变熔断器状态
        
        Args:
            new_state: 新状态
            breaker_type: 熔断类型
            severity: 严重程度
            trigger_value: 触发值
            threshold: 阈值
            message: 事件描述
            
        Returns:
            是否成功改变状态
        """
        old_state = self.state
        
        # 如果状态未改变，直接返回
        if old_state == new_state:
            return False
        
        # 创建事件
        event = self._create_event(
            breaker_type=breaker_type,
            severity=severity,
            old_state=old_state,
            new_state=new_state,
            trigger_value=trigger_value,
            threshold=threshold,
            message=message
        )
        
        # 更新状态
        self.state = new_state
        self.severity = severity
        self._state_start_time = time.time()
        
        # 更新活跃熔断器
        if new_state in [BreakerState.WARNING, BreakerState.TRIPPED]:
            self.active_breakers.add(breaker_type)
        else:
            self.active_breakers.discard(breaker_type)
        
        # 记录状态改变
        state_duration = time.time() - self._state_start_time
        
        if new_state == BreakerState.TRIPPED:
            logger.warning(f"熔断器触发: {old_state.value} -> {new_state.value}")
            logger.warning(f"触发原因: {message}")
            logger.warning(f"触发值: {trigger_value:.4f}，阈值: {threshold:.4f}")
        else:
            logger.info(f"熔断器状态改变: {old_state.value} -> {new_state.value}")
            logger.info(f"原因: {message}")
        
        return True
    
    async def check_daily_loss_breaker(self) -> Optional[BreakerEvent]:
        """
        检查单日亏损熔断
        
        Returns:
            熔断事件（如果触发），否则None
        """
        try:
            # 重置每日统计（如果需要）
            self._reset_daily_if_needed()
            
            # 计算每日亏损百分比
            daily_loss_percent = self.daily_pnl / max(abs(self.daily_pnl), 1.0)
            
            # 检查是否触发熔断
            if self.daily_pnl < 0 and daily_loss_percent <= self.daily_loss_limit:
                # 根据严重程度确定新状态
                if abs(daily_loss_percent) <= abs(self.daily_loss_limit) * 1.5:
                    severity = BreakerSeverity.MODERATE
                    new_state = BreakerState.WARNING
                    message = f"单日亏损预警: {daily_loss_percent:.2%} ≤ 限制{self.daily_loss_limit:.2%}"
                else:
                    severity = BreakerSeverity.SEVERE
                    new_state = BreakerState.TRIPPED
                    message = f"单日亏损熔断: {daily_loss_percent:.2%} ≤ 限制{self.daily_loss_limit:.2%}"
                
                # 触发状态改变
                if self._change_state(
                    new_state=new_state,
                    breaker_type=BreakerType.DAILY_LOSS,
                    severity=severity,
                    trigger_value=daily_loss_percent,
                    threshold=self.daily_loss_limit,
                    message=message
                ):
                    return self.event_history[-1]
            
            return None
            
        except Exception as e:
            logger.error(f"检查单日亏损熔断失败: {e}")
            return None
    
    async def check_consecutive_loss_breaker(self) -> Optional[BreakerEvent]:
        """
        检查连续亏损熔断
        
        Returns:
            熔断事件（如果触发），否则None
        """
        try:
            # 检查是否触发熔断
            if self.consecutive_losses >= self.max_consecutive_losses:
                # 计算连续亏损严重程度
                loss_severity = self.consecutive_losses / self.max_consecutive_losses
                
                if loss_severity <= 1.5:
                    severity = BreakerSeverity.MODERATE
                    new_state = BreakerState.WARNING
                    message = f"连续亏损预警: {self.consecutive_losses}次 ≥ 限制{self.max_consecutive_losses}次"
                else:
                    severity = BreakerSeverity.SEVERE
                    new_state = BreakerState.TRIPPED
                    message = f"连续亏损熔断: {self.consecutive_losses}次 ≥ 限制{self.max_consecutive_losses}次"
                
                # 触发状态改变
                if self._change_state(
                    new_state=new_state,
                    breaker_type=BreakerType.CONSECUTIVE_LOSS,
                    severity=severity,
                    trigger_value=self.consecutive_losses,
                    threshold=self.max_consecutive_losses,
                    message=message
                ):
                    return self.event_history[-1]
            
            return None
            
        except Exception as e:
            logger.error(f"检查连续亏损熔断失败: {e}")
            return None
    
    async def check_market_volatility_breaker(self, market_metrics: MarketMetrics) -> Optional[BreakerEvent]:
        """
        检查市场波动熔断
        
        Args:
            market_metrics: 市场指标
            
        Returns:
            熔断事件（如果触发），否则None
        """
        try:
            # 检查波动率是否超过阈值
            if market_metrics.volatility_24h >= self.market_volatility_threshold:
                volatility_ratio = market_metrics.volatility_24h / self.market_volatility_threshold
                
                if volatility_ratio <= 1.5:
                    severity = BreakerSeverity.MILD
                    new_state = BreakerState.WARNING
                    message = f"市场波动预警: {market_metrics.volatility_24h:.2%} ≥ 阈值{self.market_volatility_threshold:.2%}"
                else:
                    severity = BreakerSeverity.MODERATE
                    new_state = BreakerState.TRIPPED
                    message = f"市场波动熔断: {market_metrics.volatility_24h:.2%} ≥ 阈值{self.market_volatility_threshold:.2%}"
                
                # 触发状态改变
                if self._change_state(
                    new_state=new_state,
                    breaker_type=BreakerType.MARKET_VOLATILITY,
                    severity=severity,
                    trigger_value=market_metrics.volatility_24h,
                    threshold=self.market_volatility_threshold,
                    message=message
                ):
                    return self.event_history[-1]
            
            return None
            
        except Exception as e:
            logger.error(f"检查市场波动熔断失败: {e}")
            return None
    
    async def check_liquidity_breaker(self, market_metrics: MarketMetrics) -> Optional[BreakerEvent]:
        """
        检查流动性危机熔断
        
        Args:
            market_metrics: 市场指标
            
        Returns:
            熔断事件（如果触发），否则None
        """
        try:
            # 检查流动性是否低于阈值
            if market_metrics.liquidity_score <= self.liquidity_threshold:
                liquidity_ratio = market_metrics.liquidity_score / self.liquidity_threshold
                
                if liquidity_ratio >= 0.5:
                    severity = BreakerSeverity.MILD
                    new_state = BreakerState.WARNING
                    message = f"流动性预警: {market_metrics.liquidity_score:.4f} ≤ 阈值{self.liquidity_threshold:.4f}"
                else:
                    severity = BreakerSeverity.SEVERE
                    new_state = BreakerState.TRIPPED
                    message = f"流动性危机熔断: {market_metrics.liquidity_score:.4f} ≤ 阈值{self.liquidity_threshold:.4f}"
                
                # 触发状态改变
                if self._change_state(
                    new_state=new_state,
                    breaker_type=BreakerType.LIQUIDITY_CRISIS,
                    severity=severity,
                    trigger_value=market_metrics.liquidity_score,
                    threshold=self.liquidity_threshold,
                    message=message
                ):
                    return self.event_history[-1]
            
            return None
            
        except Exception as e:
            logger.error(f"检查流动性熔断失败: {e}")
            return None
    
    async def check_all_breakers(self, market_metrics: Optional[MarketMetrics] = None) -> List[BreakerEvent]:
        """
        检查所有熔断器
        
        Args:
            market_metrics: 可选，市场指标
            
        Returns:
            触发的熔断事件列表
        """
        triggered_events = []
        
        # 检查时间间隔
        current_time = time.time()
        if current_time - self._last_check_time < self._check_interval:
            return triggered_events
        
        self._last_check_time = current_time
        
        # 检查各种熔断器
        daily_loss_event = await self.check_daily_loss_breaker()
        if daily_loss_event:
            triggered_events.append(daily_loss_event)
        
        consecutive_loss_event = await self.check_consecutive_loss_breaker()
        if consecutive_loss_event:
            triggered_events.append(consecutive_loss_event)
        
        # 如果有市场指标，检查市场相关熔断器
        if market_metrics:
            volatility_event = await self.check_market_volatility_breaker(market_metrics)
            if volatility_event:
                triggered_events.append(volatility_event)
            
            liquidity_event = await self.check_liquidity_breaker(market_metrics)
            if liquidity_event:
                triggered_events.append(liquidity_event)
        
        # 如果触发任何熔断事件，记录日志
        if triggered_events:
            logger.warning(f"检测到 {len(triggered_events)} 个熔断事件")
            for event in triggered_events:
                logger.warning(f"熔断事件: {event.message}")
        
        return triggered_events
    
    async def check_recovery(self) -> bool:
        """
        检查熔断恢复条件
        
        Returns:
            是否成功恢复
        """
        # 仅在熔断或预警状态检查恢复
        if self.state not in [BreakerState.WARNING, BreakerState.TRIPPED]:
            return False
        
        # 检查状态持续时间
        state_duration = time.time() - self._state_start_time
        
        # 不同状态的恢复条件
        if self.state == BreakerState.WARNING:
            # 预警状态：持续30秒后自动恢复
            if state_duration >= 30:
                message = f"预警状态自动恢复，持续 {state_duration:.0f} 秒"
                self._change_state(
                    new_state=BreakerState.NORMAL,
                    breaker_type=list(self.active_breakers)[0] if self.active_breakers else BreakerType.MANUAL,
                    severity=BreakerSeverity.MILD,
                    trigger_value=state_duration,
                    threshold=30,
                    message=message
                )
                return True
        
        elif self.state == BreakerState.TRIPPED:
            # 熔断状态：根据严重程度决定恢复时间
            recovery_time = self.recovery_check_interval
            
            if self.severity == BreakerSeverity.SEVERE:
                recovery_time *= 3  # 重度熔断恢复时间更长
            elif self.severity == BreakerSeverity.MODERATE:
                recovery_time *= 2  # 中度熔断恢复时间中等
            
            # 检查是否达到恢复时间
            if state_duration >= recovery_time:
                # 检查恢复条件是否满足
                recovery_conditions_met = await self._check_recovery_conditions()
                
                if recovery_conditions_met:
                    message = f"熔断状态恢复，持续 {state_duration:.0f} 秒"
                    self._change_state(
                        new_state=BreakerState.RECOVERY,
                        breaker_type=list(self.active_breakers)[0] if self.active_breakers else BreakerType.MANUAL,
                        severity=BreakerSeverity.MILD,
                        trigger_value=state_duration,
                        threshold=recovery_time,
                        message=message
                    )
                    return True
        
        elif self.state == BreakerState.RECOVERY:
            # 恢复状态：逐步放宽限制
            recovery_duration = time.time() - self._state_start_time
            recovery_step_duration = self.recovery_check_interval / self.recovery_steps
            
            # 检查是否完成恢复
            if recovery_duration >= self.recovery_check_interval:
                message = f"恢复完成，总恢复时间 {recovery_duration:.0f} 秒"
                self._change_state(
                    new_state=BreakerState.NORMAL,
                    breaker_type=list(self.active_breakers)[0] if self.active_breakers else BreakerType.MANUAL,
                    severity=BreakerSeverity.MILD,
                    trigger_value=recovery_duration,
                    threshold=self.recovery_check_interval,
                    message=message
                )
                return True
        
        return False
    
    async def _check_recovery_conditions(self) -> bool:
        """
        检查恢复条件是否满足
        
        Returns:
            是否满足恢复条件
        """
        try:
            # 检查所有活跃熔断器的恢复条件
            for breaker_type in self.active_breakers:
                condition_met = False
                
                if breaker_type == BreakerType.DAILY_LOSS:
                    # 单日亏损熔断：检查是否是新的一天或亏损减少
                    self._reset_daily_if_needed()
                    daily_loss_percent = self.daily_pnl / max(abs(self.daily_pnl), 1.0)
                    condition_met = (daily_loss_percent > self.daily_loss_limit * 0.8)  # 亏损减少到阈值的80%
                
                elif breaker_type == BreakerType.CONSECUTIVE_LOSS:
                    # 连续亏损熔断：检查是否有盈利交易
                    condition_met = (self.consecutive_losses < self.max_consecutive_losses)
                
                elif breaker_type == BreakerType.MARKET_VOLATILITY:
                    # 市场波动熔断：检查波动率是否降低
                    condition_met = True  # 简化实现，实际需要市场数据
                
                elif breaker_type == BreakerType.LIQUIDITY_CRISIS:
                    # 流动性危机熔断：检查流动性是否改善
                    condition_met = True  # 简化实现，实际需要市场数据
                
                # 如果任何一个熔断器的恢复条件不满足，则不能恢复
                if not condition_met:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"检查恢复条件失败: {e}")
            return False
    
    def can_open_position(self, symbol: str, position_size: float) -> Tuple[bool, str]:
        """
        检查是否可以开仓
        
        Args:
            symbol: 交易对
            position_size: 仓位大小
            
        Returns:
            (是否允许, 原因)
        """
        if self.state == BreakerState.NORMAL:
            return True, "正常状态，允许开仓"
        
        elif self.state == BreakerState.WARNING:
            # 预警状态：限制高风险开仓
            if self.severity == BreakerSeverity.MILD:
                return True, "轻度预警，允许开仓"
            else:
                return False, f"预警状态 ({self.severity.value})，限制开仓"
        
        elif self.state == BreakerState.TRIPPED:
            # 熔断状态：禁止所有开仓
            return False, f"熔断状态 ({self.severity.value})，禁止开仓"
        
        elif self.state == BreakerState.RECOVERY:
            # 恢复状态：限制性开仓
            recovery_progress = (time.time() - self._state_start_time) / self.recovery_check_interval
            if recovery_progress >= 0.5:  # 恢复进度过半
                return True, f"恢复状态，进度{recovery_progress:.0%}，允许开仓"
            else:
                return False, f"恢复状态，进度{recovery_progress:.0%}，限制开仓"
        
        return False, "未知状态，禁止开仓"
    
    def can_close_position(self, symbol: str) -> Tuple[bool, str]:
        """
        检查是否可以平仓
        
        Args:
            symbol: 交易对
            
        Returns:
            (是否允许, 原因)
        """
        # 所有状态都允许平仓（风险管理需要）
        return True, "允许平仓（风险管理需要）"
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取熔断器状态
        
        Returns:
            状态字典
        """
        state_duration = time.time() - self._state_start_time
        
        return {
            'state': self.state.value,
            'severity': self.severity.value,
            'active_breakers': [b.value for b in self.active_breakers],
            'state_duration_seconds': state_duration,
            'consecutive_losses': self.consecutive_losses,
            'daily_pnl': self.daily_pnl,
            'daily_loss_limit': self.daily_loss_limit,
            'trade_history_count': len(self.trade_history),
            'event_history_count': len(self.event_history),
            'timestamp': int(time.time() * 1000)
        }
    
    def manual_trip(self, breaker_type: BreakerType, message: str) -> bool:
        """
        手动触发熔断
        
        Args:
            breaker_type: 熔断类型
            message: 触发消息
            
        Returns:
            是否成功触发
        """
        return self._change_state(
            new_state=BreakerState.TRIPPED,
            breaker_type=breaker_type,
            severity=BreakerSeverity.MODERATE,
            trigger_value=1.0,
            threshold=0.0,
            message=f"手动熔断: {message}"
        )
    
    def manual_reset(self) -> bool:
        """
        手动重置熔断器
        
        Returns:
            是否成功重置
        """
        if self.state != BreakerState.NORMAL:
            return self._change_state(
                new_state=BreakerState.NORMAL,
                breaker_type=BreakerType.MANUAL,
                severity=BreakerSeverity.MILD,
                trigger_value=0.0,
                threshold=0.0,
                message="手动重置熔断器"
            )
        return False
    
    def get_recent_events(self, limit: int = 10) -> List[BreakerEvent]:
        """
        获取最近熔断事件
        
        Args:
            limit: 限制返回数量
            
        Returns:
            熔断事件列表
        """
        return self.event_history[-limit:] if self.event_history else []
    
    def save_state(self, filepath: str) -> bool:
        """
        保存熔断器状态到文件
        
        Args:
            filepath: 文件路径
            
        Returns:
            是否成功保存
        """
        try:
            state_data = {
                'state': self.state.value,
                'severity': self.severity.value,
                'active_breakers': [b.value for b in self.active_breakers],
                'consecutive_losses': self.consecutive_losses,
                'daily_pnl': self.daily_pnl,
                'daily_start_time': self.daily_start_time,
                'trade_history': [
                    {
                        'trade_id': t.trade_id,
                        'symbol': t.symbol,
                        'side': t.side,
                        'position_side': t.position_side,
                        'entry_price': t.entry_price,
                        'exit_price': t.exit_price,
                        'position_size': t.position_size,
                        'pnl': t.pnl,
                        'pnl_percent': t.pnl_percent,
                        'timestamp': t.timestamp,
                        'closed': t.closed
                    }
                    for t in self.trade_history[-100:]  # 只保存最近100条
                ],
                'timestamp': int(time.time() * 1000)
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"熔断器状态已保存到: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"保存熔断器状态失败: {e}")
            return False
    
    def load_state(self, filepath: str) -> bool:
        """
        从文件加载熔断器状态
        
        Args:
            filepath: 文件路径
            
        Returns:
            是否成功加载
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            # 恢复状态
            self.state = BreakerState(state_data['state'])
            self.severity = BreakerSeverity(state_data['severity'])
            self.active_breakers = {BreakerType(b) for b in state_data['active_breakers']}
            self.consecutive_losses = state_data['consecutive_losses']
            self.daily_pnl = state_data['daily_pnl']
            self.daily_start_time = state_data['daily_start_time']
            
            # 恢复交易历史
            self.trade_history = []
            for t_data in state_data['trade_history']:
                trade = TradeRecord(
                    trade_id=t_data['trade_id'],
                    symbol=t_data['symbol'],
                    side=t_data['side'],
                    position_side=t_data['position_side'],
                    entry_price=t_data['entry_price'],
                    exit_price=t_data['exit_price'],
                    position_size=t_data['position_size'],
                    pnl=t_data['pnl'],
                    pnl_percent=t_data['pnl_percent'],
                    timestamp=t_data['timestamp'],
                    closed=t_data['closed']
                )
                self.trade_history.append(trade)
            
            # 重置状态开始时间
            self._state_start_time = time.time()
            
            logger.info(f"熔断器状态已从文件加载: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"加载熔断器状态失败: {e}")
            return False


# 便捷函数
def create_circuit_breaker(config_path: Optional[str] = None) -> CircuitBreaker:
    """
    创建熔断器实例（工厂函数）
    
    Args:
        config_path: 可选，配置文件路径
        
    Returns:
        熔断器实例
    """
    from config.config_manager import ConfigManager
    
    config = ConfigManager(config_path)
    return CircuitBreaker(config)


if __name__ == "__main__":
    """模块自测"""
    async def test_circuit_breaker():
        import sys
        sys.path.append('/home/lingge/quant_brain/01_codebase/binance_ai_agent')
        
        from config.config_manager import ConfigManager
        
        config = ConfigManager()
        breaker = CircuitBreaker(config)
        
        print(f"初始状态: {breaker.get_status()}")
        
        # 添加一些亏损交易记录
        for i in range(4):
            trade = TradeRecord(
                trade_id=f"test_{i}",
                symbol="BTC/USDT",
                side="buy",
                position_side="long",
                entry_price=50000.0,
                exit_price=49000.0,  # 亏损
                position_size=0.1,
                pnl=-100.0,
                pnl_percent=-0.02,
                closed=True
            )
            breaker.add_trade_record(trade)
        
        # 检查熔断器
        events = await breaker.check_all_breakers()
        
        print(f"\n检查结果: {len(events)} 个熔断事件")
        for event in events:
            print(f"  事件: {event.message}")
        
        print(f"\n当前状态: {breaker.get_status()}")
        
        # 检查是否可以开仓
        can_open, reason = breaker.can_open_position("BTC/USDT", 0.1)
        print(f"\n开仓许可: {can_open} ({reason})")
        
        # 检查恢复
        recovery_result = await breaker.check_recovery()
        print(f"恢复检查: {recovery_result}")
    
    asyncio.run(test_circuit_breaker())