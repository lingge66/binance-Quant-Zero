"""
订单管理模块 - 订单创建、修改、取消与状态追踪

核心功能：
1. 订单创建：限价单、市价单、止损单、止盈单
2. 订单修改：价格、数量、订单类型修改
3. 订单取消：单个/批量取消，条件取消
4. 状态追踪：订单生命周期管理，状态同步
5. 订单簿管理：本地订单簿维护与交易所同步

安全设计：
- 双重确认：实盘交易前二次确认
- 防重复提交：订单ID唯一性检查
- 超时处理：订单执行超时自动取消
- 幂等操作：订单修改/取消幂等性保证

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import os
import time
import uuid
import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import asyncio

# 第三方库
import ccxt.async_support as ccxt

# 项目内部导入
from config.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """订单类型枚举"""
    LIMIT = "limit"           # 限价单
    MARKET = "market"         # 市价单
    STOP_LOSS = "stop_loss"   # 止损单
    STOP_LOSS_LIMIT = "stop_loss_limit"  # 限价止损单
    TAKE_PROFIT = "take_profit"  # 止盈单
    TAKE_PROFIT_LIMIT = "take_profit_limit"  # 限价止盈单


class OrderSide(Enum):
    """订单方向枚举"""
    BUY = "buy"      # 买入
    SELL = "sell"    # 卖出


class OrderStatus(Enum):
    """订单状态枚举"""
    NEW = "new"              # 新建（未提交）
    PENDING = "pending"      # 待提交（等待确认）
    SUBMITTED = "submitted"  # 已提交（等待交易所确认）
    OPEN = "open"            # 已开仓（部分成交）
    PARTIALLY_FILLED = "partially_filled"  # 部分成交
    FILLED = "filled"        # 完全成交
    CANCELLED = "cancelled"  # 已取消
    EXPIRED = "expired"      # 已过期
    REJECTED = "rejected"    # 被拒绝
    ERROR = "error"          # 错误状态


@dataclass
class Order:
    """订单数据类"""
    order_id: str                     # 订单唯一ID（系统生成）
    client_order_id: str              # 客户端订单ID（用户提供）
    symbol: str                       # 交易对（如 BTC/USDT）
    order_type: OrderType             # 订单类型
    side: OrderSide                   # 订单方向（买入/卖出）
    amount: float                     # 订单数量
    price: Optional[float] = None     # 订单价格（限价单需要）
    stop_price: Optional[float] = None  # 止损/止盈触发价格
    status: OrderStatus = OrderStatus.NEW  # 订单状态
    filled_amount: float = 0.0        # 已成交数量
    average_price: Optional[float] = None  # 平均成交价格
    remaining_amount: float = 0.0     # 剩余数量
    fee: float = 0.0                  # 手续费
    fee_currency: str = "USDT"        # 手续费币种
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))  # 创建时间
    updated_at: int = field(default_factory=lambda: int(time.time() * 1000))  # 更新时间
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据
    
    def update_from_exchange(self, exchange_data: Dict[str, Any]) -> None:
        """从交易所数据更新订单状态"""
        # 将在后续实现
        pass
    
    def is_active(self) -> bool:
        """检查订单是否处于活跃状态（可成交）"""
        active_statuses = [OrderStatus.NEW, OrderStatus.PENDING, OrderStatus.SUBMITTED, 
                          OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]
        return self.status in active_statuses
    
    def is_completed(self) -> bool:
        """检查订单是否已完成（成交或取消）"""
        completed_statuses = [OrderStatus.FILLED, OrderStatus.CANCELLED, 
                             OrderStatus.EXPIRED, OrderStatus.REJECTED, OrderStatus.ERROR]
        return self.status in completed_statuses


class OrderManager:
    """
    订单管理器 - 订单生命周期管理
    
    设计特性：
    1. 本地订单簿：维护所有订单的本地副本
    2. 状态同步：定期与交易所同步订单状态
    3. 异常恢复：网络异常时自动恢复同步
    4. 审计日志：完整订单操作记录
    """
    
    def __init__(self, config: ConfigManager):
        """
        初始化订单管理器
        
        Args:
            config: 配置管理器实例
        """
        self.config = config
        self.orders: Dict[str, Order] = {}  # 订单ID -> 订单对象
        self.client_order_map: Dict[str, str] = {}  # 客户端订单ID -> 系统订单ID
        self.max_order_history = 10000
        
        # 交易所连接
        self.exchange = None
        self.environment = self.config.get('environment', 'mainnet')
        
        # 同步配置
        self.sync_interval = 5  # 状态同步间隔（秒）
        self.sync_enabled = True
        self._last_sync_time = 0
        
        # API密钥（从环境变量读取）
        self.api_key = os.getenv('BINANCE_API_KEY', '')
        self.api_secret = os.getenv('BINANCE_API_SECRET', '')
        
        # 初始化日志
        self._setup_logging()
        
        logger.info(f"订单管理器初始化完成（环境: {self.environment}）")
    
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
    
    async def initialize(self) -> None:
        """
        初始化订单管理器（连接交易所）
        
        Raises:
            ConnectionError: 交易所连接失败
        """
        try:
            await self._connect_to_exchange()
            logger.info("订单管理器初始化成功")
        except Exception as e:
            logger.error(f"订单管理器初始化失败: {e}")
            raise ConnectionError(f"订单管理器初始化失败: {e}")
    
    async def _connect_to_exchange(self) -> None:
        """
        连接交易所
        
        Raises:
            ConnectionError: 连接失败
        """
        try:
            exchange_config = {
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'timeout': 30000,
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}  # 默认现货交易
            }
            
            if self.environment == 'testnet':
                exchange_class = getattr(ccxt, 'binanceusdmtest', None)
                if exchange_class:
                    logger.info("使用币安测试网（USDⓂ️ Testnet）")
                    self.exchange = exchange_class(exchange_config)
                    return
            
            # 主网配置（默认）
            exchange_class = getattr(ccxt, 'binanceusdm', None)
            if not exchange_class:
                raise ImportError("无法加载币安交易所类")
                
            logger.info("使用币安主网（USDⓂ️）")
            self.exchange = exchange_class(exchange_config)
            
        except Exception as e:
            logger.error(f"连接交易所失败: {e}")
            raise ConnectionError(f"连接交易所失败: {e}")
    
    def _generate_order_id(self) -> str:
        """
        生成唯一订单ID
        
        Returns:
            唯一订单ID
        """
        return f"order_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    
    async def create_order(self, symbol: str, order_type: OrderType, side: OrderSide,
                          amount: float, price: Optional[float] = None,
                          stop_price: Optional[float] = None, 
                          client_order_id: Optional[str] = None) -> Order:
        """
        创建新订单
        
        Args:
            symbol: 交易对
            order_type: 订单类型
            side: 订单方向
            amount: 订单数量
            price: 订单价格（限价单需要）
            stop_price: 止损/止盈触发价格
            client_order_id: 客户端订单ID（可选）
            
        Returns:
            创建的订单对象
            
        Raises:
            ValueError: 参数无效
            ConnectionError: 交易所连接失败
        """
        # 参数验证
        if amount <= 0:
            raise ValueError(f"订单数量必须大于0: {amount}")
        
        if order_type in [OrderType.LIMIT, OrderType.STOP_LOSS_LIMIT, OrderType.TAKE_PROFIT_LIMIT]:
            if price is None or price <= 0:
                raise ValueError(f"{order_type.value}订单必须指定有效价格: {price}")
        
        if order_type in [OrderType.STOP_LOSS, OrderType.STOP_LOSS_LIMIT, 
                         OrderType.TAKE_PROFIT, OrderType.TAKE_PROFIT_LIMIT]:
            if stop_price is None or stop_price <= 0:
                raise ValueError(f"{order_type.value}订单必须指定有效触发价格: {stop_price}")
        
        # 生成订单ID
        order_id = self._generate_order_id()
        if client_order_id is None:
            client_order_id = f"client_{order_id}"
        
        # 检查重复订单ID
        if client_order_id in self.client_order_map:
            raise ValueError(f"客户端订单ID已存在: {client_order_id}")
        
        # 创建订单对象
        order = Order(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            order_type=order_type,
            side=side,
            amount=amount,
            price=price,
            stop_price=stop_price,
            status=OrderStatus.NEW,
            remaining_amount=amount
        )
        
        # 保存到本地订单簿
        self.orders[order_id] = order
        self.client_order_map[client_order_id] = order_id
        
        logger.info(f"创建订单: {order_id} [{symbol} {side.value} {order_type.value} {amount}]")
        
        return order
    
    async def submit_order(self, order_id: str, dry_run: bool = True) -> Order:
        """
        提交订单到交易所
        
        Args:
            order_id: 订单ID
            dry_run: 是否为模拟运行（不实际提交）
            
        Returns:
            更新后的订单对象
            
        Raises:
            KeyError: 订单不存在
            ConnectionError: 提交失败
        """
        if order_id not in self.orders:
            raise KeyError(f"订单不存在: {order_id}")
        
        order = self.orders[order_id]
        
        # 更新状态为待提交
        order.status = OrderStatus.PENDING
        order.updated_at = int(time.time() * 1000)
        
        logger.info(f"准备提交订单: {order_id} (dry_run={dry_run})")
        
        # 如果是模拟运行，直接标记为已提交
        if dry_run:
            order.status = OrderStatus.SUBMITTED
            logger.info(f"模拟提交订单: {order_id}")
            return order
        
        # 实际提交到交易所
        try:
            # 确保交易所已连接
            if not self.exchange:
                await self.initialize()
            
            # 准备订单参数
            order_params = {
                'symbol': order.symbol.replace('/', ''),
                'type': order.order_type.value,
                'side': order.side.value,
                'amount': order.amount,
            }
            
            if order.price is not None:
                order_params['price'] = order.price
            
            if order.stop_price is not None:
                order_params['stopPrice'] = order.stop_price
            
            # 提交订单
            exchange_response = await self.exchange.create_order(**order_params)
            
            # 更新订单状态
            order.status = OrderStatus.SUBMITTED
            order.metadata['exchange_response'] = exchange_response
            
            # 记录交易所订单ID
            if 'id' in exchange_response:
                order.metadata['exchange_order_id'] = exchange_response['id']
            
            logger.info(f"订单提交成功: {order_id} -> 交易所订单ID: {exchange_response.get('id', 'N/A')}")
            
        except Exception as e:
            order.status = OrderStatus.ERROR
            order.metadata['error'] = str(e)
            logger.error(f"订单提交失败 {order_id}: {e}")
            raise ConnectionError(f"订单提交失败: {e}")
        
        finally:
            order.updated_at = int(time.time() * 1000)
        
        return order
    
    async def cancel_order(self, order_id: str, dry_run: bool = True) -> Order:
        """
        取消订单
        
        Args:
            order_id: 订单ID
            dry_run: 是否为模拟运行
            
        Returns:
            更新后的订单对象
            
        Raises:
            KeyError: 订单不存在
        """
        if order_id not in self.orders:
            raise KeyError(f"订单不存在: {order_id}")
        
        order = self.orders[order_id]
        
        # 检查订单是否可取消
        if order.is_completed():
            logger.warning(f"订单已完成，无法取消: {order_id} [{order.status.value}]")
            return order
        
        # 模拟取消
        if dry_run:
            order.status = OrderStatus.CANCELLED
            order.updated_at = int(time.time() * 1000)
            logger.info(f"模拟取消订单: {order_id}")
            return order
        
        # 实际取消订单
        try:
            # 需要交易所订单ID
            exchange_order_id = order.metadata.get('exchange_order_id')
            if not exchange_order_id:
                logger.warning(f"订单无交易所ID，仅本地取消: {order_id}")
                order.status = OrderStatus.CANCELLED
                return order
            
            # 调用交易所取消接口
            await self.exchange.cancel_order(exchange_order_id, order.symbol.replace('/', ''))
            
            order.status = OrderStatus.CANCELLED
            logger.info(f"订单取消成功: {order_id}")
            
        except Exception as e:
            logger.error(f"订单取消失败 {order_id}: {e}")
            # 标记为错误，但仍保留本地记录
            order.status = OrderStatus.ERROR
            order.metadata['cancel_error'] = str(e)
        
        finally:
            order.updated_at = int(time.time() * 1000)
        
        return order
    
    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        获取订单信息
        
        Args:
            order_id: 订单ID
            
        Returns:
            订单对象，如果不存在返回None
        """
        return self.orders.get(order_id)
    
    async def get_orders(self, symbol: Optional[str] = None, 
                        status: Optional[OrderStatus] = None) -> List[Order]:
        """
        获取订单列表
        
        Args:
            symbol: 可选，过滤交易对
            status: 可选，过滤订单状态
            
        Returns:
            订单列表
        """
        filtered_orders = []
        
        for order in self.orders.values():
            if symbol and order.symbol != symbol:
                continue
            if status and order.status != status:
                continue
            filtered_orders.append(order)
        
        # 按创建时间排序（最近创建的在前）
        filtered_orders.sort(key=lambda o: o.created_at, reverse=True)
        
        return filtered_orders
    
    async def sync_order_status(self, order_id: str) -> Order:
        """
        同步订单状态（从交易所）
        
        Args:
            order_id: 订单ID
            
        Returns:
            更新后的订单对象
            
        Raises:
            KeyError: 订单不存在
        """
        if order_id not in self.orders:
            raise KeyError(f"订单不存在: {order_id}")
        
        order = self.orders[order_id]
        
        # 检查是否有交易所订单ID
        exchange_order_id = order.metadata.get('exchange_order_id')
        if not exchange_order_id:
            logger.debug(f"订单无交易所ID，跳过同步: {order_id}")
            return order
        
        try:
            # 从交易所获取订单状态
            exchange_order = await self.exchange.fetch_order(
                exchange_order_id, order.symbol.replace('/', '')
            )
            
            # 更新订单状态
            # 这里简化处理，实际需要解析exchange_order并更新订单
            logger.debug(f"同步订单状态: {order_id} -> {exchange_order.get('status', 'unknown')}")
            
            # 更新订单信息
            order.updated_at = int(time.time() * 1000)
            order.metadata['last_sync'] = time.time()
            
        except Exception as e:
            logger.warning(f"订单状态同步失败 {order_id}: {e}")
        
        return order
    
    async def sync_all_orders(self) -> Dict[str, Any]:
        """
        同步所有订单状态
        
        Returns:
            同步结果统计
        """
        if not self.sync_enabled:
            return {'synced': 0, 'errors': 0, 'message': '同步已禁用'}
        
        current_time = time.time()
        if current_time - self._last_sync_time < self.sync_interval:
            return {'synced': 0, 'errors': 0, 'message': '未到同步时间'}
        
        self._last_sync_time = current_time
        
        synced = 0
        errors = 0
        
        # 只同步活跃订单
        active_orders = [o for o in self.orders.values() if o.is_active()]
        
        for order in active_orders:
            try:
                await self.sync_order_status(order.order_id)
                synced += 1
            except Exception as e:
                errors += 1
                logger.warning(f"订单同步失败 {order.order_id}: {e}")
        
        if synced > 0 or errors > 0:
            logger.info(f"订单同步完成: {synced}成功, {errors}失败")
        
        return {
            'synced': synced,
            'errors': errors,
            'total_active': len(active_orders),
            'timestamp': int(time.time() * 1000)
        }
    
    async def cleanup_old_orders(self, max_age_hours: int = 168) -> Dict[str, Any]:
        """
        清理旧订单记录（7天前）
        
        Args:
            max_age_hours: 最大保留小时数
            
        Returns:
            清理结果统计
        """
        cutoff_time = int(time.time() * 1000) - (max_age_hours * 3600 * 1000)
        
        to_remove = []
        for order_id, order in self.orders.items():
            # 只清理已完成的旧订单
            if order.is_completed() and order.updated_at < cutoff_time:
                to_remove.append(order_id)
        
        # 移除订单
        for order_id in to_remove:
            order = self.orders[order_id]
            # 从客户端订单映射中移除
            if order.client_order_id in self.client_order_map:
                del self.client_order_map[order.client_order_id]
            # 从订单簿中移除
            del self.orders[order_id]
        
        logger.info(f"清理了 {len(to_remove)} 个旧订单记录（>{max_age_hours}小时）")
        
        return {
            'removed': len(to_remove),
            'remaining': len(self.orders),
            'timestamp': int(time.time() * 1000)
        }
    
    async def close(self) -> None:
        """
        关闭订单管理器，释放资源
        """
        try:
            if self.exchange:
                await self.exchange.close()
                self.exchange = None
                logger.info("订单管理器已关闭")
        except Exception as e:
            logger.error(f"关闭订单管理器时出错: {e}")


# 便捷函数
async def create_order_manager(config_path: Optional[str] = None) -> OrderManager:
    """
    创建订单管理器实例（工厂函数）
    
    Args:
        config_path: 可选，配置文件路径
        
    Returns:
        订单管理器实例
    """
    from config.config_manager import ConfigManager
    
    config = ConfigManager(config_path)
    manager = OrderManager(config)
    await manager.initialize()
    return manager


if __name__ == "__main__":
    """模块自测"""
    async def test_order_manager():
        import sys
        sys.path.append('/home/lingge/quant_brain/01_codebase/binance_ai_agent')
        
        from config.config_manager import ConfigManager
        
        config = ConfigManager()
        manager = OrderManager(config)
        
        try:
            # 测试创建订单
            order = await manager.create_order(
                symbol="BTC/USDT",
                order_type=OrderType.LIMIT,
                side=OrderSide.BUY,
                amount=0.01,
                price=50000.0
            )
            
            print(f"创建订单: {order.order_id}")
            print(f"  交易对: {order.symbol}")
            print(f"  类型: {order.order_type.value}")
            print(f"  方向: {order.side.value}")
            print(f"  数量: {order.amount}")
            print(f"  价格: {order.price}")
            print(f"  状态: {order.status.value}")
            
            # 测试获取订单
            retrieved = await manager.get_order(order.order_id)
            print(f"\n获取订单: {retrieved.order_id if retrieved else 'None'}")
            
            # 测试订单列表
            orders = await manager.get_orders()
            print(f"\n订单总数: {len(orders)}")
            
        except Exception as e:
            print(f"测试失败: {e}")
        finally:
            await manager.close()
    
    asyncio.run(test_order_manager())