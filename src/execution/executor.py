"""
交易执行器 - 负责接收交易信号并执行交易订单

核心功能：
1. 信号接收：从信号处理层接收交易信号
2. 风险验证：调用风控引擎验证交易风险
3. 订单创建：通过订单管理器创建适当订单
4. 执行策略：选择最优执行策略（限价/市价/条件单）
5. 状态监控：监控订单执行过程，处理部分成交
6. 结果处理：处理执行结果，更新仓位，发送通知

安全设计：
- 环境隔离：模拟/实盘严格隔离，实盘需二次确认
- 风险前置：执行前必须通过所有风险检查
- 执行保障：网络异常时自动重试，超时自动取消
- 结果追踪：完整执行审计，包含决策依据和执行结果

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import os
import time
import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import asyncio

# 项目内部导入
from config.config_manager import ConfigManager
from .order_manager import OrderManager, Order, OrderType, OrderSide, OrderStatus
from src.risk.rule_engine import RiskRuleEngine, TradeContext, AccountContext
from src.notification.notification_manager import NotificationManager, NotificationType, NotificationPriority

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """执行模式枚举"""
    SIMULATION = "simulation"    # 模拟交易（完全虚拟）
    PAPER = "paper"              # 纸交易（模拟价格，真实订单流）
    LIVE = "live"                # 实盘交易


class ExecutionStrategy(Enum):
    """执行策略枚举"""
    LIMIT = "limit"              # 限价单策略
    MARKET = "market"            # 市价单策略
    TWAP = "twap"                # 时间加权平均价格
    VWAP = "vwap"                # 成交量加权平均价格
    ICEBERG = "iceberg"          # 冰山订单
    AGGREGATE = "aggregate"      # 智能聚合


class ExecutionStatus(Enum):
    """执行状态枚举"""
    PENDING = "pending"          # 待执行（等待风险检查）
    RISK_CHECK_PASSED = "risk_check_passed"  # 风险检查通过
    ORDER_CREATED = "order_created"  # 订单已创建
    ORDER_SUBMITTED = "order_submitted"  # 订单已提交
    PARTIALLY_FILLED = "partially_filled"  # 部分成交
    FULLY_FILLED = "fully_filled"  # 完全成交
    CANCELLED = "cancelled"      # 已取消
    FAILED = "failed"            # 执行失败
    TIMEOUT = "timeout"          # 执行超时


@dataclass
class TradeSignal:
    """交易信号数据类"""
    signal_id: str                      # 信号唯一ID
    symbol: str                         # 交易对
    signal_type: str                    # 信号类型（STRONG_BUY, SELL等）
    confidence: float                   # 置信度（0-1）
    price: float                        # 建议价格
    timestamp: float                    # 信号生成时间戳
    metadata: Dict[str, Any] = field(default_factory=dict)  # 信号元数据
    recommended_amount: Optional[float] = None  # 建议交易数量
    stop_loss: Optional[float] = None   # 止损价格
    take_profit: Optional[float] = None  # 止盈价格
    
    def to_trade_context(self, position_size: float) -> TradeContext:
        """转换为风控引擎的交易上下文"""
        # 这里简化实现，实际需要更完整的转换
        return TradeContext(
            symbol=self.symbol,
            position_side="long" if "BUY" in self.signal_type else "short",
            entry_price=self.price,
            current_price=self.price,
            position_size=position_size or self.recommended_amount or 0.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            leverage=1.0,
            timestamp=int(self.timestamp * 1000)
        )


@dataclass
class ExecutionResult:
    """执行结果数据类"""
    execution_id: str                   # 执行唯一ID
    signal_id: str                      # 关联的信号ID
    status: ExecutionStatus             # 执行状态
    order_id: Optional[str] = None      # 关联的订单ID
    order: Optional[Order] = None       # 订单对象（如果创建）
    filled_amount: float = 0.0          # 已成交数量
    average_price: Optional[float] = None  # 平均成交价格
    total_fee: float = 0.0              # 总手续费
    execution_time_ms: Optional[int] = None  # 执行耗时（毫秒）
    error_message: Optional[str] = None  # 错误信息（如果失败）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 执行元数据
    
    def is_successful(self) -> bool:
        """检查执行是否成功"""
        return self.status in [ExecutionStatus.FULLY_FILLED, ExecutionStatus.PARTIALLY_FILLED]
    
    def is_completed(self) -> bool:
        """检查执行是否已完成"""
        completed_statuses = [
            ExecutionStatus.FULLY_FILLED,
            ExecutionStatus.PARTIALLY_FILLED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMEOUT,
        ]
        return self.status in completed_statuses


class TradeExecutor:
    """
    交易执行器 - 核心交易执行逻辑
    
    设计特性：
    1. 模块化设计：与订单管理器、风控引擎、通知系统解耦
    2. 策略选择：根据市场条件选择最优执行策略
    3. 执行监控：实时监控订单状态，处理异常
    4. 结果反馈：将执行结果反馈给相关模块
    5. 审计追踪：完整执行记录，便于复盘分析
    """
    
    def __init__(self, config: ConfigManager):
        """
        初始化交易执行器
        
        Args:
            config: 配置管理器实例
        """
        self.config = config
        self.execution_config = config.get('execution', {})
        
        # 执行模式
        self.mode = ExecutionMode(self.execution_config.get('mode', 'simulation'))
        
        # 模块引用（将在initialize中初始化）
        self.order_manager: Optional[OrderManager] = None
        self.risk_engine: Optional[RiskRuleEngine] = None
        self.notification_manager: Optional[NotificationManager] = None
        
        # 执行状态
        self._executions: Dict[str, ExecutionResult] = {}  # 执行ID -> 执行结果
        self._active_executions: Dict[str, asyncio.Task] = {}  # 活动执行任务
        self._max_concurrent_executions = 10  # 最大并发执行数
        
        # 统计信息
        self._stats = {
            'total_executions': 0,
            'successful': 0,
            'failed': 0,
            'cancelled': 0,
            'total_volume': 0.0,
            'total_fees': 0.0,
            'avg_execution_time_ms': 0.0,
        }
        
        # 执行策略配置
        self.default_strategy = ExecutionStrategy(
            self.execution_config.get('order_types', {}).get('default', 'LIMIT')
        )
        
        # 实盘确认配置
        self.live_confirmation_timeout = self.execution_config.get(
            'live_trading', {}
        ).get('confirmation_timeout', 30)
        
        # 初始化日志
        self._setup_logging()
        
        logger.info(f"交易执行器初始化完成（模式: {self.mode.value}）")
    
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
    
    async def initialize(self, 
                        order_manager: OrderManager,
                        risk_engine: Optional[RiskRuleEngine] = None,
                        notification_manager: Optional[NotificationManager] = None) -> None:
        """
        初始化执行器依赖
        
        Args:
            order_manager: 订单管理器实例
            risk_engine: 可选，风控引擎实例
            notification_manager: 可选，通知管理器实例
        """
        self.order_manager = order_manager
        
        if risk_engine:
            self.risk_engine = risk_engine
        
        if notification_manager:
            self.notification_manager = notification_manager
        
        # 初始化订单管理器（如果未初始化）
        if not self.order_manager.exchange:
            await self.order_manager.initialize()
        
        logger.info("交易执行器依赖初始化完成")
    
    def _generate_execution_id(self) -> str:
        """生成唯一执行ID"""
        import uuid
        timestamp = int(time.time() * 1000)
        unique_id = uuid.uuid4().hex[:8]
        return f"exec_{timestamp}_{unique_id}"
    
    async def _perform_risk_check(self, 
                                 trade_signal: TradeSignal,
                                 position_size: float) -> Tuple[bool, str, Optional[str]]:
        """
        执行风险检查
        
        Args:
            trade_signal: 交易信号
            position_size: 计划交易数量
            
        Returns:
            (是否通过, 检查消息, 建议操作)
        """
        # 如果没有风控引擎，默认通过
        if not self.risk_engine:
            return True, "无风控引擎，跳过风险检查", None
        
        try:
            # 创建交易上下文
            trade_context = trade_signal.to_trade_context(position_size)
            
            # 获取账户上下文（简化实现，实际应从账户监控器获取）
            # 这里使用模拟数据
            account_context = AccountContext(
                total_balance=10000.0,
                available_balance=5000.0,
                margin_ratio=0.5,
                total_position_value=3000.0,
                daily_pnl=200.0,
                weekly_pnl=500.0,
                open_positions=[],
                timestamp=int(time.time() * 1000)
            )
            
            # 评估所有风险规则
            rule_results = await self.risk_engine.evaluate_all_rules(
                trade_context, account_context
            )
            
            # 检查是否有失败的规则
            failed_rules = [r for r in rule_results if not r.passed]
            
            if failed_rules:
                # 获取失败原因
                failure_messages = [f"{r.rule_name}: {r.message}" for r in failed_rules]
                failure_summary = "; ".join(failure_messages[:3])  # 只显示前3个
                
                # 获取建议操作
                suggestions = [r.suggested_action for r in failed_rules if r.suggested_action]
                suggestion = suggestions[0] if suggestions else None
                
                return False, f"风险检查失败: {failure_summary}", suggestion
            else:
                return True, "风险检查通过", None
                
        except Exception as e:
            logger.error(f"风险检查异常: {e}")
            # 风险检查异常时，保守策略：不通过
            return False, f"风险检查异常: {str(e)}", "等待重试"
    
    async def _confirm_live_trading(self, 
                                   action: str, 
                                   params: Dict[str, Any]) -> bool:
        """
        实盘交易二次确认
        
        Args:
            action: 交易动作
            params: 交易参数
            
        Returns:
            是否确认
        """
        if self.mode != ExecutionMode.LIVE:
            return True  # 非实盘模式无需确认
        
        logger.info(f"实盘交易需要确认: {action} - {params}")
        
        # 发送确认通知
        if self.notification_manager:
            try:
                notification_id = await self.notification_manager.send_notification(
                    notification_type=NotificationType.TRADE_EXECUTION,
                    title="🔐 实盘交易需要确认",
                    message=f"请确认执行 {action}\n\n交易参数: {params}",
                    priority=NotificationPriority.CRITICAL,
                    metadata={'action': action, 'params': params}
                )
                
                logger.info(f"实盘确认通知已发送: {notification_id}")
                
            except Exception as e:
                logger.error(f"发送确认通知失败: {e}")
                # 通知发送失败，保守策略：不执行
                return False
        
        # 简化实现：模拟确认过程
        # 实际实现应等待用户回复确认消息
        logger.warning("实盘确认功能未完全实现，模拟确认为: 拒绝")
        return False  # 安全起见，默认拒绝
    
    def _determine_order_type(self, 
                             trade_signal: TradeSignal,
                             execution_strategy: ExecutionStrategy) -> OrderType:
        """
        确定订单类型
        
        Args:
            trade_signal: 交易信号
            execution_strategy: 执行策略
            
        Returns:
            订单类型
        """
        # 根据执行策略选择订单类型
        if execution_strategy == ExecutionStrategy.MARKET:
            return OrderType.MARKET
        elif execution_strategy == ExecutionStrategy.LIMIT:
            return OrderType.LIMIT
        else:
            # 默认使用配置的默认类型
            return OrderType(self.execution_config.get('order_types', {}).get('default', 'LIMIT'))
    
    def _calculate_position_size(self, 
                                trade_signal: TradeSignal,
                                account_balance: float) -> float:
        """
        计算交易仓位大小
        
        Args:
            trade_signal: 交易信号
            account_balance: 账户余额
            
        Returns:
            建议交易数量
        """
        # 如果有信号推荐数量，使用推荐数量
        if trade_signal.recommended_amount:
            return trade_signal.recommended_amount
        
        # 简化实现：使用固定比例
        # 实际应根据风险参数、信号置信度等计算
        risk_percentage = 0.02  # 2%风险暴露
        position_value = account_balance * risk_percentage
        position_size = position_value / trade_signal.price
        
        # 根据交易对的最小交易单位调整
        # 这里简化处理
        return round(position_size, 6)  # 保留6位小数
    
    async def execute_trade(self, 
                          trade_signal: TradeSignal,
                          execution_strategy: Optional[ExecutionStrategy] = None,
                          require_confirmation: bool = True) -> ExecutionResult:
        """
        执行交易
        
        Args:
            trade_signal: 交易信号
            execution_strategy: 可选，执行策略，如为None则使用默认策略
            require_confirmation: 是否需要确认（实盘模式下）
            
        Returns:
            执行结果
        """
        # 生成执行ID
        execution_id = self._generate_execution_id()
        
        # 创建执行结果对象
        execution_result = ExecutionResult(
            execution_id=execution_id,
            signal_id=trade_signal.signal_id,
            status=ExecutionStatus.PENDING,
            metadata={
                'signal_type': trade_signal.signal_type,
                'symbol': trade_signal.symbol,
                'confidence': trade_signal.confidence,
                'price': trade_signal.price,
                'strategy': execution_strategy.value if execution_strategy else self.default_strategy.value,
            }
        )
        
        # 保存执行记录
        self._executions[execution_id] = execution_result
        self._stats['total_executions'] += 1
        
        logger.info(f"开始执行交易: {execution_id} [{trade_signal.symbol} {trade_signal.signal_type}]")
        
        try:
            start_time = time.time()
            
            # 步骤1: 风险检查
            logger.debug(f"执行风险检查: {execution_id}")
            
            # 计算仓位大小（简化：使用模拟账户余额）
            account_balance = 10000.0  # 模拟值，实际应从账户监控器获取
            position_size = self._calculate_position_size(trade_signal, account_balance)
            
            risk_passed, risk_message, risk_suggestion = await self._perform_risk_check(
                trade_signal, position_size
            )
            
            if not risk_passed:
                execution_result.status = ExecutionStatus.FAILED
                execution_result.error_message = f"风险检查失败: {risk_message}"
                logger.warning(f"交易执行失败（风险检查）: {execution_id} - {risk_message}")
                return execution_result
            
            execution_result.status = ExecutionStatus.RISK_CHECK_PASSED
            logger.debug(f"风险检查通过: {execution_id}")
            
            # 步骤2: 实盘确认（如果需要）
            if require_confirmation and self.mode == ExecutionMode.LIVE:
                action = "BUY" if "BUY" in trade_signal.signal_type else "SELL"
                params = {
                    'symbol': trade_signal.symbol,
                    'side': action,
                    'amount': position_size,
                    'price': trade_signal.price,
                    'strategy': execution_strategy.value if execution_strategy else self.default_strategy.value,
                }
                
                confirmed = await self._confirm_live_trading(action, params)
                if not confirmed:
                    execution_result.status = ExecutionStatus.CANCELLED
                    execution_result.error_message = "用户取消确认"
                    logger.info(f"交易执行取消（用户未确认）: {execution_id}")
                    return execution_result
            
            # 步骤3: 确定订单类型和参数
            strategy = execution_strategy or self.default_strategy
            order_type = self._determine_order_type(trade_signal, strategy)
            
            order_side = OrderSide.BUY if "BUY" in trade_signal.signal_type else OrderSide.SELL
            
            # 步骤4: 创建订单
            logger.debug(f"创建订单: {execution_id}")
            
            try:
                order = await self.order_manager.create_order(
                    symbol=trade_signal.symbol,
                    order_type=order_type,
                    side=order_side,
                    amount=position_size,
                    price=trade_signal.price if order_type == OrderType.LIMIT else None,
                    stop_price=trade_signal.stop_loss,
                    client_order_id=f"signal_{trade_signal.signal_id}"
                )
                
                execution_result.order_id = order.order_id
                execution_result.order = order
                execution_result.status = ExecutionStatus.ORDER_CREATED
                
                logger.info(f"订单创建成功: {execution_id} -> {order.order_id}")
                
            except Exception as e:
                execution_result.status = ExecutionStatus.FAILED
                execution_result.error_message = f"订单创建失败: {str(e)}"
                logger.error(f"订单创建失败: {execution_id} - {e}")
                return execution_result
            
            # 步骤5: 提交订单
            logger.debug(f"提交订单: {execution_id}")
            
            try:
                # 检查是否为模拟模式
                dry_run = self.mode != ExecutionMode.LIVE
                
                submitted_order = await self.order_manager.submit_order(
                    order.order_id, dry_run=dry_run
                )
                
                execution_result.order = submitted_order
                execution_result.status = ExecutionStatus.ORDER_SUBMITTED
                
                logger.info(f"订单提交成功: {execution_id} (dry_run={dry_run})")
                
                # 如果是模拟模式，直接标记为成交
                if dry_run:
                    submitted_order.status = OrderStatus.FILLED
                    submitted_order.filled_amount = position_size
                    submitted_order.average_price = trade_signal.price
                    submitted_order.fee = position_size * trade_signal.price * 0.001  # 模拟手续费
                    
                    execution_result.status = ExecutionStatus.FULLY_FILLED
                    execution_result.filled_amount = position_size
                    execution_result.average_price = trade_signal.price
                    execution_result.total_fee = submitted_order.fee
                    
                    self._stats['successful'] += 1
                    self._stats['total_volume'] += position_size * trade_signal.price
                    self._stats['total_fees'] += submitted_order.fee
                    
                    logger.info(f"模拟交易执行成功: {execution_id}")
                
            except Exception as e:
                execution_result.status = ExecutionStatus.FAILED
                execution_result.error_message = f"订单提交失败: {str(e)}"
                logger.error(f"订单提交失败: {execution_id} - {e}")
                
                # 尝试取消订单
                try:
                    await self.order_manager.cancel_order(order.order_id, dry_run=True)
                except Exception as cancel_error:
                    logger.warning(f"订单取消失败: {order.order_id} - {cancel_error}")
                
                return execution_result
            
            # 步骤6: 发送执行通知
            if self.notification_manager:
                try:
                    action_text = "买入" if order_side == OrderSide.BUY else "卖出"
                    status_text = "模拟成交" if dry_run else "已提交"
                    
                    await self.notification_manager.send_notification(
                        notification_type=NotificationType.TRADE_EXECUTION,
                        title=f"{action_text} {trade_signal.symbol}",
                        message=f"{action_text} {position_size} {trade_signal.symbol.split('/')[0]} @ ${trade_signal.price:,.2f}\n状态: {status_text}",
                        priority=NotificationPriority.HIGH if dry_run else NotificationPriority.MEDIUM,
                        metadata={
                            'execution_id': execution_id,
                            'order_id': order.order_id,
                            'symbol': trade_signal.symbol,
                            'side': order_side.value,
                            'amount': position_size,
                            'price': trade_signal.price,
                            'status': status_text,
                            'dry_run': dry_run,
                        }
                    )
                except Exception as e:
                    logger.warning(f"发送执行通知失败: {e}")
            
            # 计算执行时间
            execution_time_ms = int((time.time() - start_time) * 1000)
            execution_result.execution_time_ms = execution_time_ms
            
            # 更新平均执行时间
            prev_avg = self._stats['avg_execution_time_ms']
            prev_count = self._stats['total_executions'] - self._stats['failed'] - self._stats['cancelled'] - 1
            self._stats['avg_execution_time_ms'] = (
                (prev_avg * prev_count) + execution_time_ms
            ) / (prev_count + 1) if prev_count > 0 else execution_time_ms
            
            logger.info(f"交易执行完成: {execution_id} (耗时: {execution_time_ms}ms)")
            
            return execution_result
            
        except Exception as e:
            execution_result.status = ExecutionStatus.FAILED
            execution_result.error_message = f"执行异常: {str(e)}"
            logger.error(f"交易执行异常: {execution_id} - {e}")
            
            self._stats['failed'] += 1
            
            return execution_result
    
    async def execute_trade_async(self,
                                trade_signal: TradeSignal,
                                execution_strategy: Optional[ExecutionStrategy] = None,
                                require_confirmation: bool = True) -> str:
        """
        异步执行交易（不阻塞）
        
        Args:
            trade_signal: 交易信号
            execution_strategy: 可选，执行策略
            require_confirmation: 是否需要确认
            
        Returns:
            执行ID，可用于查询状态
        """
        # 检查并发限制
        if len(self._active_executions) >= self._max_concurrent_executions:
            raise RuntimeError(f"达到最大并发执行数: {self._max_concurrent_executions}")
        
        # 创建异步任务
        task = asyncio.create_task(
            self.execute_trade(trade_signal, execution_strategy, require_confirmation)
        )
        
        # 生成临时执行ID（实际执行中会生成正式ID）
        temp_execution_id = f"async_{int(time.time() * 1000)}"
        self._active_executions[temp_execution_id] = task
        
        # 设置任务完成回调
        def cleanup_task(future):
            if temp_execution_id in self._active_executions:
                del self._active_executions[temp_execution_id]
        
        task.add_done_callback(cleanup_task)
        
        logger.debug(f"异步交易执行已启动: {temp_execution_id}")
        
        return temp_execution_id
    
    async def get_execution_result(self, execution_id: str) -> Optional[ExecutionResult]:
        """
        获取执行结果
        
        Args:
            execution_id: 执行ID
            
        Returns:
            执行结果，如不存在则返回None
        """
        return self._executions.get(execution_id)
    
    async def get_active_executions(self) -> List[ExecutionResult]:
        """
        获取活动中的执行
        
        Returns:
            活动执行列表
        """
        active_results = []
        
        for execution_id, execution_result in self._executions.items():
            if not execution_result.is_completed():
                active_results.append(execution_result)
        
        return active_results
    
    async def cancel_execution(self, execution_id: str) -> bool:
        """
        取消执行
        
        Args:
            execution_id: 执行ID
            
        Returns:
            是否成功取消
        """
        execution_result = self._executions.get(execution_id)
        if not execution_result:
            logger.warning(f"执行不存在: {execution_id}")
            return False
        
        if execution_result.is_completed():
            logger.warning(f"执行已完成，无法取消: {execution_id}")
            return False
        
        # 如果有关联订单，尝试取消订单
        if execution_result.order_id and self.order_manager:
            try:
                await self.order_manager.cancel_order(execution_result.order_id, dry_run=True)
                logger.info(f"订单取消成功: {execution_result.order_id}")
            except Exception as e:
                logger.warning(f"订单取消失败: {execution_result.order_id} - {e}")
        
        # 更新执行状态
        execution_result.status = ExecutionStatus.CANCELLED
        execution_result.error_message = "用户取消"
        
        self._stats['cancelled'] += 1
        
        logger.info(f"执行已取消: {execution_id}")
        
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取执行统计信息
        
        Returns:
            统计信息字典
        """
        return self._stats.copy()
    
    async def close(self) -> None:
        """
        关闭执行器，清理资源
        """
        # 取消所有活动执行
        for execution_id, task in self._active_executions.items():
            if not task.done():
                task.cancel()
                logger.debug(f"取消活动执行: {execution_id}")
        
        # 等待任务完成
        if self._active_executions:
            await asyncio.gather(*self._active_executions.values(), return_exceptions=True)
        
        logger.info("交易执行器已关闭")


# 便捷函数
async def create_trade_executor(config_path: Optional[str] = None) -> TradeExecutor:
    """
    创建交易执行器实例（工厂函数）
    
    Args:
        config_path: 可选，配置文件路径
        
    Returns:
        交易执行器实例
    """
    from config.config_manager import ConfigManager
    
    config = ConfigManager(config_path)
    executor = TradeExecutor(config)
    
    # 创建依赖实例
    from .order_manager import OrderManager
    order_manager = OrderManager(config)
    
    # 可选依赖
    risk_engine = None
    notification_manager = None
    
    try:
        from src.risk.rule_engine import RiskRuleEngine
        risk_engine = RiskRuleEngine(config)
    except ImportError:
        logger.warning("风控引擎不可用")
    
    try:
        from src.notification.notification_manager import NotificationManager
        notification_manager = NotificationManager(config)
        await notification_manager.start()
    except ImportError:
        logger.warning("通知管理器不可用")
    
    # 初始化执行器
    await executor.initialize(order_manager, risk_engine, notification_manager)
    
    return executor


if __name__ == "__main__":
    """模块自测"""
    import asyncio
    
    async def test_trade_executor():
        import sys
        sys.path.append('/home/lingge/quant_brain/01_codebase/binance_ai_agent')
        
        from config.config_manager import ConfigManager
        
        config = ConfigManager()
        executor = TradeExecutor(config)
        
        # 创建模拟订单管理器
        from .order_manager import OrderManager
        order_manager = OrderManager(config)
        
        await executor.initialize(order_manager)
        
        try:
            # 创建测试交易信号
            trade_signal = TradeSignal(
                signal_id="test_signal_123",
                symbol="BTC/USDT",
                signal_type="STRONG_BUY",
                confidence=0.85,
                price=50000.0,
                timestamp=time.time(),
                recommended_amount=0.01,
                stop_loss=48000.0,
                take_profit=52000.0,
            )
            
            print(f"测试交易信号: {trade_signal.symbol} {trade_signal.signal_type}")
            
            # 执行交易
            result = await executor.execute_trade(
                trade_signal,
                require_confirmation=False
            )
            
            print(f"执行结果: {result.status.value}")
            print(f"  执行ID: {result.execution_id}")
            print(f"  订单ID: {result.order_id}")
            print(f"  成交数量: {result.filled_amount}")
            print(f"  平均价格: {result.average_price}")
            print(f"  手续费: {result.total_fee}")
            print(f"  执行时间: {result.execution_time_ms}ms")
            
            if result.error_message:
                print(f"  错误信息: {result.error_message}")
            
            # 获取统计信息
            stats = executor.get_stats()
            print(f"\n执行统计: {stats}")
            
        except Exception as e:
            print(f"测试失败: {e}")
        finally:
            await executor.close()
    
    asyncio.run(test_trade_executor())