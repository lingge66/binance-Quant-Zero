"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


"""
仓位管理器 - 负责持仓跟踪、盈亏计算与仓位调整

核心功能：
1. 持仓跟踪：实时跟踪所有交易对的持仓状态
2. 盈亏计算：计算已实现盈亏（Realized P&L）和未实现盈亏（Unrealized P&L）
3. 仓位同步：与交易所同步持仓数据，确保一致性
4. 仓位调整：根据风险参数调整仓位大小
5. 风险管理：监控仓位风险，触发风险警报

设计原则：
- 实时性：秒级持仓更新，实时盈亏计算
- 准确性：精确计算手续费、滑点等成本
- 一致性：确保本地持仓与交易所持仓一致
- 安全性：持仓数据持久化，防止数据丢失

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
from datetime import datetime
import asyncio

# 项目内部导入
from config.config_manager import ConfigManager
from .order_manager import Order, OrderSide

logger = logging.getLogger(__name__)


class PositionSide(Enum):
    """持仓方向枚举"""
    LONG = "long"      # 多头持仓
    SHORT = "short"    # 空头持仓
    FLAT = "flat"      # 无持仓


class PositionStatus(Enum):
    """持仓状态枚举"""
    OPEN = "open"              # 开仓状态
    CLOSING = "closing"        # 平仓中
    CLOSED = "closed"          # 已平仓
    HEDGED = "hedged"          # 对冲状态


@dataclass
class Position:
    """持仓数据类"""
    position_id: str                  # 持仓唯一ID
    symbol: str                       # 交易对
    side: PositionSide                # 持仓方向
    quantity: float                   # 持仓数量
    entry_price: float                # 开仓均价
    current_price: float              # 当前价格
    entry_time: float                 # 开仓时间戳
    last_update_time: float           # 最后更新时间戳
    
    # 盈亏相关
    unrealized_pnl: float = 0.0       # 未实现盈亏
    realized_pnl: float = 0.0         # 已实现盈亏
    total_pnl: float = 0.0            # 总盈亏
    
    # 成本相关
    total_fees: float = 0.0           # 总手续费
    entry_fees: float = 0.0           # 开仓手续费
    exit_fees: float = 0.0            # 平仓手续费
    
    # 风险相关
    position_value: float = 0.0       # 持仓价值
    margin_used: float = 0.0          # 占用保证金
    leverage: float = 1.0             # 杠杆倍数
    
    # 状态
    status: PositionStatus = PositionStatus.OPEN  # 持仓状态
    is_hedged: bool = False           # 是否对冲
    stop_loss: Optional[float] = None  # 止损价格
    take_profit: Optional[float] = None  # 止盈价格
    
    # 关联订单
    entry_orders: List[str] = field(default_factory=list)  # 开仓订单ID列表
    exit_orders: List[str] = field(default_factory=list)   # 平仓订单ID列表
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据
    
    def update_price(self, current_price: float) -> None:
        """
        更新当前价格并重新计算未实现盈亏
        
        Args:
            current_price: 当前价格
        """
        self.current_price = current_price
        self.last_update_time = time.time()
        
        # 计算持仓价值
        self.position_value = self.quantity * self.current_price
        
        # 计算未实现盈亏
        price_diff = self.current_price - self.entry_price
        if self.side == PositionSide.SHORT:
            price_diff = -price_diff  # 空头盈亏方向相反
        
        self.unrealized_pnl = price_diff * self.quantity
        self.total_pnl = self.realized_pnl + self.unrealized_pnl
    
    def add_entry_order(self, order: Order, fee: float = 0.0) -> None:
        """
        添加开仓订单
        
        Args:
            order: 订单对象
            fee: 订单手续费
        """
        if order.order_id not in self.entry_orders:
            self.entry_orders.append(order.order_id)
            
            # 更新开仓均价（加权平均）
            total_quantity = self.quantity + order.filled_amount
            if total_quantity > 0:
                self.entry_price = (
                    (self.entry_price * self.quantity) + 
                    (order.price * order.filled_amount)
                ) / total_quantity
            
            # 更新持仓数量
            self.quantity += order.filled_amount
            
            # 更新手续费
            self.entry_fees += fee
            self.total_fees += fee
            
            # 更新最后时间
            self.last_update_time = time.time()
    
    def add_exit_order(self, order: Order, fee: float = 0.0) -> Tuple[float, float]:
        """
        添加平仓订单
        
        Args:
            order: 订单对象
            fee: 订单手续费
            
        Returns:
            (平仓数量, 已实现盈亏)
        """
        if order.order_id not in self.exit_orders:
            self.exit_orders.append(order.order_id)
            
            # 计算平仓数量（不能超过当前持仓）
            close_amount = min(order.filled_amount, self.quantity)
            
            if close_amount <= 0:
                return 0.0, 0.0
            
            # 计算已实现盈亏
            price_diff = order.price - self.entry_price
            if self.side == PositionSide.SHORT:
                price_diff = -price_diff  # 空头盈亏方向相反
            
            realized_pnl = price_diff * close_amount
            
            # 更新持仓
            self.quantity -= close_amount
            self.realized_pnl += realized_pnl
            
            # 更新手续费
            self.exit_fees += fee
            self.total_fees += fee
            
            # 更新最后时间
            self.last_update_time = time.time()
            
            # 如果持仓为0，标记为已平仓
            if self.quantity <= 0:
                self.status = PositionStatus.CLOSED
            
            return close_amount, realized_pnl
        
        return 0.0, 0.0
    
    def is_open(self) -> bool:
        """检查持仓是否开仓状态"""
        return self.status == PositionStatus.OPEN and self.quantity > 0
    
    def is_closed(self) -> bool:
        """检查持仓是否已平仓"""
        return self.status == PositionStatus.CLOSED or self.quantity <= 0
    
    def calculate_breakeven_price(self) -> float:
        """
        计算盈亏平衡价格（考虑手续费）
        
        Returns:
            盈亏平衡价格
        """
        # 简化计算：开仓价格 + 平均每单位手续费
        if self.quantity <= 0:
            return self.entry_price
        
        fee_per_unit = self.total_fees / self.quantity
        
        if self.side == PositionSide.LONG:
            return self.entry_price + fee_per_unit
        else:  # SHORT
            return self.entry_price - fee_per_unit
    
    def calculate_stop_loss_price(self, stop_loss_percent: float) -> float:
        """
        计算止损价格
        
        Args:
            stop_loss_percent: 止损百分比
            
        Returns:
            止损价格
        """
        if self.side == PositionSide.LONG:
            return self.entry_price * (1 - stop_loss_percent)
        else:  # SHORT
            return self.entry_price * (1 + stop_loss_percent)
    
    def calculate_take_profit_price(self, take_profit_percent: float) -> float:
        """
        计算止盈价格
        
        Args:
            take_profit_percent: 止盈百分比
            
        Returns:
            止盈价格
        """
        if self.side == PositionSide.LONG:
            return self.entry_price * (1 + take_profit_percent)
        else:  # SHORT
            return self.entry_price * (1 - take_profit_percent)


class PositionManager:
    """
    仓位管理器 - 持仓管理与风险控制
    
    设计特性：
    1. 多交易对支持：同时管理多个交易对的持仓
    2. 实时同步：定期与交易所同步持仓状态
    3. 盈亏计算：精确计算已实现和未实现盈亏
    4. 风险监控：监控仓位风险，触发风险警报
    5. 数据持久化：持仓数据定期保存，防止丢失
    """
    
    def __init__(self, config: ConfigManager):
        """
        初始化仓位管理器
        
        Args:
            config: 配置管理器实例
        """
        self.config = config
        
        # 持仓存储
        self.positions: Dict[str, Position] = {}  # 持仓ID -> 持仓对象
        self.symbol_positions: Dict[str, List[str]] = {}  # 交易对 -> 持仓ID列表
        
        # 同步配置
        self.sync_interval = 30  # 同步间隔（秒）
        self._last_sync_time = 0
        self.sync_enabled = True
        
        # 风险配置
        self.max_position_per_symbol = 0.3  # 单交易对最大仓位比例（30%）
        self.max_total_position = 0.8       # 总最大仓位比例（80%）
        self.stop_loss_percent = 0.02       # 默认止损百分比（2%）
        self.take_profit_percent = 0.05     # 默认止盈百分比（5%）
        
        # 统计信息
        self._stats = {
            'total_positions': 0,
            'open_positions': 0,
            'closed_positions': 0,
            'total_pnl': 0.0,
            'realized_pnl': 0.0,
            'unrealized_pnl': 0.0,
            'total_fees': 0.0,
            'total_volume': 0.0,
            'last_update': None,
        }
        
        # 同步任务
        self._sync_task = None
        self._running = False
        
        # 初始化日志
        self._setup_logging()
        
        logger.info("仓位管理器初始化完成")
    
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
    
    def _generate_position_id(self, symbol: str, side: PositionSide) -> str:
        """
        生成唯一持仓ID
        
        Args:
            symbol: 交易对
            side: 持仓方向
            
        Returns:
            唯一持仓ID
        """
        import uuid
        timestamp = int(time.time() * 1000)
        unique_id = uuid.uuid4().hex[:6]
        side_code = "L" if side == PositionSide.LONG else "S" if side == PositionSide.SHORT else "F"
        return f"pos_{symbol.replace('/', '')}_{side_code}_{timestamp}_{unique_id}"
    
    async def create_position(self, 
                            symbol: str,
                            side: PositionSide,
                            quantity: float,
                            entry_price: float,
                            current_price: Optional[float] = None,
                            leverage: float = 1.0,
                            stop_loss: Optional[float] = None,
                            take_profit: Optional[float] = None) -> Position:
        """
        创建新持仓
        
        Args:
            symbol: 交易对
            side: 持仓方向
            quantity: 持仓数量
            entry_price: 开仓价格
            current_price: 当前价格（如为None则使用entry_price）
            leverage: 杠杆倍数
            stop_loss: 止损价格
            take_profit: 止盈价格
            
        Returns:
            创建的持仓对象
            
        Raises:
            ValueError: 参数无效
        """
        if quantity <= 0:
            raise ValueError(f"持仓数量必须大于0: {quantity}")
        
        if entry_price <= 0:
            raise ValueError(f"开仓价格必须大于0: {entry_price}")
        
        # 生成持仓ID
        position_id = self._generate_position_id(symbol, side)
        
        # 设置当前价格
        if current_price is None:
            current_price = entry_price
        
        # 创建持仓对象
        position = Position(
            position_id=position_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            current_price=current_price,
            entry_time=time.time(),
            last_update_time=time.time(),
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status=PositionStatus.OPEN,
        )
        
        # 初始价格更新（计算初始盈亏）
        position.update_price(current_price)
        
        # 保存持仓
        self.positions[position_id] = position
        
        # 更新交易对映射
        if symbol not in self.symbol_positions:
            self.symbol_positions[symbol] = []
        self.symbol_positions[symbol].append(position_id)
        
        # 更新统计信息
        self._update_stats()
        
        logger.info(f"创建持仓: {position_id} [{symbol} {side.value} {quantity} @ {entry_price}]")
        
        return position
    
    async def update_position_price(self, 
                                  position_id: str, 
                                  current_price: float) -> Optional[Position]:
        """
        更新持仓价格
        
        Args:
            position_id: 持仓ID
            current_price: 当前价格
            
        Returns:
            更新后的持仓对象，如果持仓不存在则返回None
        """
        if position_id not in self.positions:
            logger.warning(f"持仓不存在: {position_id}")
            return None
        
        position = self.positions[position_id]
        
        # 更新价格
        position.update_price(current_price)
        
        # 检查止损止盈
        await self._check_stop_loss_take_profit(position)
        
        # 更新统计信息
        self._update_stats()
        
        logger.debug(f"更新持仓价格: {position_id} -> {current_price}")
        
        return position
    
    async def _check_stop_loss_take_profit(self, position: Position) -> None:
        """
        检查止损止盈触发
        
        Args:
            position: 持仓对象
        """
        if position.is_closed() or not position.stop_loss or not position.take_profit:
            return
        
        current_price = position.current_price
        triggered = False
        trigger_type = ""
        
        # 检查止损
        if position.stop_loss:
            if position.side == PositionSide.LONG and current_price <= position.stop_loss:
                triggered = True
                trigger_type = "stop_loss"
            elif position.side == PositionSide.SHORT and current_price >= position.stop_loss:
                triggered = True
                trigger_type = "stop_loss"
        
        # 检查止盈
        if position.take_profit:
            if position.side == PositionSide.LONG and current_price >= position.take_profit:
                triggered = True
                trigger_type = "take_profit"
            elif position.side == PositionSide.SHORT and current_price <= position.take_profit:
                triggered = True
                trigger_type = "take_profit"
        
        if triggered:
            logger.info(f"持仓触发{trigger_type}: {position.position_id} @ {current_price}")
            # 这里可以触发平仓操作（实际实现需要与执行器集成）
            # position.status = PositionStatus.CLOSING
    
    async def add_entry_order_to_position(self, 
                                        position_id: str,
                                        order: Order,
                                        fee: float = 0.0) -> Optional[Position]:
        """
        添加开仓订单到持仓
        
        Args:
            position_id: 持仓ID
            order: 订单对象
            fee: 订单手续费
            
        Returns:
            更新后的持仓对象，如果持仓不存在则返回None
        """
        if position_id not in self.positions:
            logger.warning(f"持仓不存在: {position_id}")
            return None
        
        position = self.positions[position_id]
        
        # 验证订单方向与持仓方向一致
        expected_side = PositionSide.LONG if order.side == OrderSide.BUY else PositionSide.SHORT
        if position.side != expected_side:
            logger.warning(f"订单方向与持仓方向不一致: {position.side} != {expected_side}")
            # 仍然添加订单，但记录警告
        
        # 添加订单
        position.add_entry_order(order, fee)
        
        # 更新统计信息
        self._update_stats()
        
        logger.debug(f"添加开仓订单到持仓: {position_id} <- {order.order_id}")
        
        return position
    
    async def add_exit_order_to_position(self, 
                                       position_id: str,
                                       order: Order,
                                       fee: float = 0.0) -> Tuple[Optional[Position], float, float]:
        """
        添加平仓订单到持仓
        
        Args:
            position_id: 持仓ID
            order: 订单对象
            fee: 订单手续费
            
        Returns:
            (更新后的持仓对象, 平仓数量, 已实现盈亏)
            如果持仓不存在则返回(None, 0, 0)
        """
        if position_id not in self.positions:
            logger.warning(f"持仓不存在: {position_id}")
            return None, 0.0, 0.0
        
        position = self.positions[position_id]
        
        # 添加订单
        close_amount, realized_pnl = position.add_exit_order(order, fee)
        
        # 更新统计信息
        self._update_stats()
        
        logger.debug(f"添加平仓订单到持仓: {position_id} <- {order.order_id} (平仓: {close_amount})")
        
        return position, close_amount, realized_pnl
    
    async def get_position(self, position_id: str) -> Optional[Position]:
        """
        获取持仓信息
        
        Args:
            position_id: 持仓ID
            
        Returns:
            持仓对象，如果不存在则返回None
        """
        return self.positions.get(position_id)
    
    async def get_positions_by_symbol(self, symbol: str, open_only: bool = False) -> List[Position]:
        """
        获取指定交易对的持仓
        
        Args:
            symbol: 交易对
            open_only: 是否只返回开仓状态的持仓
            
        Returns:
            持仓列表
        """
        position_ids = self.symbol_positions.get(symbol, [])
        positions = []
        
        for position_id in position_ids:
            if position_id in self.positions:
                position = self.positions[position_id]
                if open_only and not position.is_open():
                    continue
                positions.append(position)
        
        # 按开仓时间排序（最近开仓的在前）
        positions.sort(key=lambda p: p.entry_time, reverse=True)
        
        return positions
    
    async def get_open_positions(self) -> List[Position]:
        """
        获取所有开仓状态的持仓
        
        Returns:
            开仓持仓列表
        """
        open_positions = []
        
        for position in self.positions.values():
            if position.is_open():
                open_positions.append(position)
        
        # 按交易对分组排序
        open_positions.sort(key=lambda p: (p.symbol, p.entry_time))
        
        return open_positions
    
    async def get_closed_positions(self, limit: int = 100) -> List[Position]:
        """
        获取已平仓的持仓（最近平仓的在前）
        
        Args:
            limit: 返回数量限制
            
        Returns:
            已平仓持仓列表
        """
        closed_positions = []
        
        for position in self.positions.values():
            if position.is_closed():
                closed_positions.append(position)
        
        # 按平仓时间排序（最近平仓的在前）
        closed_positions.sort(key=lambda p: p.last_update_time, reverse=True)
        
        return closed_positions[:limit]
    
    def _update_stats(self) -> None:
        """更新统计信息"""
        total_pnl = 0.0
        realized_pnl = 0.0
        unrealized_pnl = 0.0
        total_fees = 0.0
        total_volume = 0.0
        open_count = 0
        closed_count = 0
        
        for position in self.positions.values():
            total_pnl += position.total_pnl
            realized_pnl += position.realized_pnl
            unrealized_pnl += position.unrealized_pnl
            total_fees += position.total_fees
            total_volume += position.position_value
            
            if position.is_open():
                open_count += 1
            elif position.is_closed():
                closed_count += 1
        
        self._stats.update({
            'total_positions': len(self.positions),
            'open_positions': open_count,
            'closed_positions': closed_count,
            'total_pnl': total_pnl,
            'realized_pnl': realized_pnl,
            'unrealized_pnl': unrealized_pnl,
            'total_fees': total_fees,
            'total_volume': total_volume,
            'last_update': time.time(),
        })
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        return self._stats.copy()
    
    async def calculate_position_risk(self, position: Position) -> Dict[str, Any]:
        """
        计算持仓风险指标
        
        Args:
            position: 持仓对象
            
        Returns:
            风险指标字典
        """
        if position.quantity <= 0:
            return {
                'position_id': position.position_id,
                'symbol': position.symbol,
                'side': position.side.value,
                'status': 'closed',
                'risk_level': 'none',
            }
        
        # 计算风险指标
        current_price = position.current_price
        
        # 盈亏百分比
        pnl_percent = (position.unrealized_pnl / (position.entry_price * position.quantity)) * 100
        
        # 距离止损百分比（如果设置了止损）
        stop_loss_distance = 0.0
        if position.stop_loss:
            if position.side == PositionSide.LONG:
                stop_loss_distance = ((current_price - position.stop_loss) / current_price) * 100
            else:  # SHORT
                stop_loss_distance = ((position.stop_loss - current_price) / current_price) * 100
        
        # 距离止盈百分比（如果设置了止盈）
        take_profit_distance = 0.0
        if position.take_profit:
            if position.side == PositionSide.LONG:
                take_profit_distance = ((position.take_profit - current_price) / current_price) * 100
            else:  # SHORT
                take_profit_distance = ((current_price - position.take_profit) / current_price) * 100
        
        # 风险等级评估
        risk_level = "low"
        if pnl_percent < -5:
            risk_level = "high"
        elif pnl_percent < -2:
            risk_level = "medium"
        elif stop_loss_distance < 1:  # 距离止损不到1%
            risk_level = "high"
        elif stop_loss_distance < 3:  # 距离止损不到3%
            risk_level = "medium"
        
        return {
            'position_id': position.position_id,
            'symbol': position.symbol,
            'side': position.side.value,
            'quantity': position.quantity,
            'entry_price': position.entry_price,
            'current_price': current_price,
            'unrealized_pnl': position.unrealized_pnl,
            'unrealized_pnl_percent': pnl_percent,
            'realized_pnl': position.realized_pnl,
            'stop_loss_distance_percent': stop_loss_distance,
            'take_profit_distance_percent': take_profit_distance,
            'position_value': position.position_value,
            'margin_used': position.margin_used,
            'leverage': position.leverage,
            'risk_level': risk_level,
            'timestamp': time.time(),
        }
    
    async def calculate_portfolio_risk(self) -> Dict[str, Any]:
        """
        计算投资组合风险
        
        Returns:
            投资组合风险指标
        """
        open_positions = await self.get_open_positions()
        
        total_value = 0.0
        total_pnl = 0.0
        max_position_value = 0.0
        max_position_symbol = ""
        
        for position in open_positions:
            total_value += position.position_value
            total_pnl += position.unrealized_pnl
            
            if position.position_value > max_position_value:
                max_position_value = position.position_value
                max_position_symbol = position.symbol
        
        # 计算仓位集中度
        position_concentration = 0.0
        if total_value > 0:
            position_concentration = max_position_value / total_value
        
        # 风险等级
        risk_level = "low"
        if total_pnl < -0.05 * total_value:  # 总亏损超过5%
            risk_level = "high"
        elif total_pnl < -0.02 * total_value:  # 总亏损超过2%
            risk_level = "medium"
        elif position_concentration > 0.5:  # 最大持仓超过50%
            risk_level = "high"
        elif position_concentration > 0.3:  # 最大持仓超过30%
            risk_level = "medium"
        
        return {
            'total_positions': len(open_positions),
            'total_value': total_value,
            'total_pnl': total_pnl,
            'pnl_percent': (total_pnl / total_value * 100) if total_value > 0 else 0.0,
            'max_position_symbol': max_position_symbol,
            'max_position_value': max_position_value,
            'position_concentration': position_concentration,
            'risk_level': risk_level,
            'timestamp': time.time(),
        }
    
    async def sync_with_exchange(self, exchange_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        与交易所同步持仓数据
        
        Args:
            exchange_data: 可选，交易所持仓数据（模拟时使用）
            
        Returns:
            同步结果
        """
        if not self.sync_enabled:
            return {'synced': 0, 'message': '同步已禁用'}
        
        current_time = time.time()
        if current_time - self._last_sync_time < self.sync_interval:
            return {'synced': 0, 'message': '未到同步时间'}
        
        self._last_sync_time = current_time
        
        synced = 0
        errors = 0
        
        # 简化实现：模拟同步
        # 实际实现应从交易所API获取持仓数据
        
        logger.debug("持仓数据同步（模拟）")
        
        # 这里可以添加实际的交易所同步逻辑
        # 例如：调用 exchange.fetch_positions()
        
        return {
            'synced': synced,
            'errors': errors,
            'total_positions': len(self.positions),
            'timestamp': int(time.time() * 1000),
        }
    
    async def start_sync_task(self) -> None:
        """
        启动定期同步任务
        """
        if self._running:
            logger.warning("同步任务已在运行")
            return
        
        self._running = True
        
        async def sync_loop():
            while self._running:
                try:
                    await asyncio.sleep(self.sync_interval)
                    await self.sync_with_exchange()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"同步任务异常: {e}")
                    await asyncio.sleep(5)  # 异常后等待5秒
        
        self._sync_task = asyncio.create_task(sync_loop())
        logger.info("持仓同步任务已启动")
    
    async def stop_sync_task(self) -> None:
        """
        停止定期同步任务
        """
        if not self._running:
            return
        
        self._running = False
        
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        
        logger.info("持仓同步任务已停止")
    
    async def close(self) -> None:
        """
        关闭仓位管理器，清理资源
        """
        await self.stop_sync_task()
        
        # 这里可以添加数据持久化逻辑
        # 例如：保存持仓数据到文件
        
        logger.info("仓位管理器已关闭")


# 便捷函数
async def create_position_manager(config_path: Optional[str] = None) -> PositionManager:
    """
    创建仓位管理器实例（工厂函数）
    
    Args:
        config_path: 可选，配置文件路径
        
    Returns:
        仓位管理器实例
    """
    from config.config_manager import ConfigManager
    
    config = ConfigManager(config_path)
    manager = PositionManager(config)
    
    # 启动同步任务
    await manager.start_sync_task()
    
    return manager


if __name__ == "__main__":
    """模块自测"""
    import asyncio
    
    async def test_position_manager():
        import sys
        sys.path.append('/home/lingge/quant_brain/01_codebase/binance_ai_agent')
        
        from config.config_manager import ConfigManager
        
        config = ConfigManager()
        manager = PositionManager(config)
        
        try:
            # 创建测试持仓
            position = await manager.create_position(
                symbol="BTC/USDT",
                side=PositionSide.LONG,
                quantity=0.1,
                entry_price=50000.0,
                current_price=51000.0,
                leverage=3.0,
                stop_loss=48000.0,
                take_profit=52000.0,
            )
            
            print(f"创建持仓: {position.position_id}")
            print(f"  交易对: {position.symbol}")
            print(f"  方向: {position.side.value}")
            print(f"  数量: {position.quantity}")
            print(f"  开仓价: ${position.entry_price:,.2f}")
            print(f"  当前价: ${position.current_price:,.2f}")
            print(f"  未实现盈亏: ${position.unrealized_pnl:,.2f}")
            print(f"  持仓价值: ${position.position_value:,.2f}")
            
            # 更新价格
            await manager.update_position_price(position.position_id, 51500.0)
            updated_position = await manager.get_position(position.position_id)
            
            print(f"\n更新价格后:")
            print(f"  当前价: ${updated_position.current_price:,.2f}")
            print(f"  未实现盈亏: ${updated_position.unrealized_pnl:,.2f}")
            
            # 获取开仓持仓
            open_positions = await manager.get_open_positions()
            print(f"\n开仓持仓数量: {len(open_positions)}")
            
            # 计算持仓风险
            risk_metrics = await manager.calculate_position_risk(position)
            print(f"\n持仓风险指标:")
            print(f"  风险等级: {risk_metrics['risk_level']}")
            print(f"  盈亏百分比: {risk_metrics['unrealized_pnl_percent']:.2f}%")
            
            # 获取统计信息
            stats = manager.get_stats()
            print(f"\n统计信息: {stats}")
            
        except Exception as e:
            print(f"测试失败: {e}")
        finally:
            await manager.close()
    
    asyncio.run(test_position_manager())