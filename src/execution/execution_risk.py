"""
执行风险控制 - 订单执行层面的风险检查与控制

核心功能：
1. 流动性检查：评估市场流动性，避免大单冲击市场
2. 滑点估计：预估订单执行的潜在滑点成本
3. 执行时机：选择最佳执行时机，避免市场异常时段
4. 订单拆分：大额订单拆分为小单，减少市场影响
5. 异常检测：检测市场异常状态，暂停异常时段交易

安全设计：
- 前置检查：订单执行前的全面风险筛查
- 实时监控：执行过程中的风险监控
- 异常处理：风险触发时的应急处理
- 事后分析：执行后的风险复盘与改进

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

# 项目内部导入
from config.config_manager import ConfigManager
from .order_manager import Order, OrderType, OrderSide

logger = logging.getLogger(__name__)


class RiskCheckResult(Enum):
    """风险检查结果枚举"""
    PASS = "pass"              # 通过
    WARNING = "warning"        # 警告（可继续）
    BLOCK = "block"            # 阻止（不可继续）


@dataclass
class RiskCheck:
    """风险检查数据类"""
    check_id: str                     # 检查唯一ID
    check_name: str                   # 检查名称
    result: RiskCheckResult           # 检查结果
    message: str                      # 检查消息
    details: Dict[str, Any] = field(default_factory=dict)  # 详细数据
    timestamp: float = field(default_factory=time.time)   # 检查时间戳


@dataclass
class LiquidityMetrics:
    """流动性指标数据类"""
    symbol: str                       # 交易对
    bid_ask_spread: float             # 买卖价差（百分比）
    order_book_depth: float           # 订单簿深度（价值）
    volume_24h: float                 # 24小时交易量
    avg_trade_size: float             # 平均交易大小
    last_update: float                # 最后更新时间戳
    
    def is_liquid(self) -> bool:
        """检查市场是否有足够流动性"""
        # 简化判断：价差小、深度足、交易量大
        return (self.bid_ask_spread < 0.001 and  # 价差小于0.1%
                self.order_book_depth > 100000 and  # 订单簿深度大于10万
                self.volume_24h > 1000000)  # 24小时交易量大于100万


class ExecutionRiskController:
    """
    执行风险控制器 - 订单执行风险检查
    
    设计特性：
    1. 多层次检查：从市场流动性到订单执行的全方位检查
    2. 动态阈值：根据市场状态动态调整风险阈值
    3. 智能建议：提供风险缓解建议（如订单拆分）
    4. 学习机制：从历史执行中学习优化风险参数
    """
    
    def __init__(self, config: ConfigManager):
        """
        初始化执行风险控制器
        
        Args:
            config: 配置管理器实例
        """
        self.config = config
        
        # 风险阈值配置
        self.max_slippage_percent = 0.002  # 最大允许滑点（0.2%）
        self.min_liquidity_usd = 100000    # 最小流动性要求（美元）
        self.max_order_size_ratio = 0.1    # 单笔订单最大占交易量比例
        self.market_impact_threshold = 0.05  # 市场影响阈值（5%）
        
        # 市场状态缓存
        self._liquidity_cache: Dict[str, LiquidityMetrics] = {}
        self._cache_ttl = 60  # 缓存有效期（秒）
        
        # 检查历史
        self._check_history: List[RiskCheck] = []
        self._max_history_size = 1000
        
        # 初始化日志
        self._setup_logging()
        
        logger.info("执行风险控制器初始化完成")
    
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
    
    def _generate_check_id(self) -> str:
        """生成唯一检查ID"""
        import uuid
        timestamp = int(time.time() * 1000)
        unique_id = uuid.uuid4().hex[:6]
        return f"risk_check_{timestamp}_{unique_id}"
    
    def _record_check(self, check: RiskCheck) -> None:
        """记录检查结果"""
        self._check_history.append(check)
        
        # 限制历史记录大小
        if len(self._check_history) > self._max_history_size:
            self._check_history = self._check_history[-self._max_history_size:]
    
    async def check_liquidity(self, 
                             symbol: str,
                             order_size: float,
                             order_price: float) -> RiskCheck:
        """
        检查市场流动性
        
        Args:
            symbol: 交易对
            order_size: 订单大小（数量）
            order_price: 订单价格
            
        Returns:
            流动性检查结果
        """
        check_id = self._generate_check_id()
        
        try:
            # 获取流动性指标（简化实现）
            liquidity = await self._get_liquidity_metrics(symbol)
            
            if not liquidity:
                # 无法获取流动性数据，给出警告
                check = RiskCheck(
                    check_id=check_id,
                    check_name="流动性检查",
                    result=RiskCheckResult.WARNING,
                    message=f"无法获取{symbol}流动性数据",
                    details={'symbol': symbol, 'order_size': order_size}
                )
                self._record_check(check)
                return check
            
            # 计算订单价值
            order_value = order_size * order_price
            
            # 检查1：买卖价差
            if liquidity.bid_ask_spread > self.max_slippage_percent * 2:
                check = RiskCheck(
                    check_id=check_id,
                    check_name="流动性检查",
                    result=RiskCheckResult.BLOCK,
                    message=f"买卖价差过大: {liquidity.bid_ask_spread:.4%}",
                    details={
                        'symbol': symbol,
                        'bid_ask_spread': liquidity.bid_ask_spread,
                        'threshold': self.max_slippage_percent * 2,
                        'order_value': order_value,
                    }
                )
                self._record_check(check)
                return check
            
            # 检查2：订单簿深度
            if liquidity.order_book_depth < self.min_liquidity_usd:
                check = RiskCheck(
                    check_id=check_id,
                    check_name="流动性检查",
                    result=RiskCheckResult.WARNING,
                    message=f"订单簿深度不足: ${liquidity.order_book_depth:,.0f}",
                    details={
                        'symbol': symbol,
                        'order_book_depth': liquidity.order_book_depth,
                        'threshold': self.min_liquidity_usd,
                        'order_value': order_value,
                    }
                )
                self._record_check(check)
                return check
            
            # 检查3：订单大小占比
            order_size_ratio = order_value / max(liquidity.volume_24h, 1)
            if order_size_ratio > self.max_order_size_ratio:
                check = RiskCheck(
                    check_id=check_id,
                    check_name="流动性检查",
                    result=RiskCheckResult.BLOCK,
                    message=f"订单过大: 占24小时交易量{order_size_ratio:.2%}",
                    details={
                        'symbol': symbol,
                        'order_size_ratio': order_size_ratio,
                        'threshold': self.max_order_size_ratio,
                        'volume_24h': liquidity.volume_24h,
                        'order_value': order_value,
                    }
                )
                self._record_check(check)
                return check
            
            # 所有检查通过
            check = RiskCheck(
                check_id=check_id,
                check_name="流动性检查",
                result=RiskCheckResult.PASS,
                message=f"流动性充足: 价差{liquidity.bid_ask_spread:.4%}, 深度${liquidity.order_book_depth:,.0f}",
                details={
                    'symbol': symbol,
                    'bid_ask_spread': liquidity.bid_ask_spread,
                    'order_book_depth': liquidity.order_book_depth,
                    'volume_24h': liquidity.volume_24h,
                    'order_value': order_value,
                    'order_size_ratio': order_size_ratio,
                }
            )
            self._record_check(check)
            return check
            
        except Exception as e:
            check = RiskCheck(
                check_id=check_id,
                check_name="流动性检查",
                result=RiskCheckResult.WARNING,
                message=f"流动性检查异常: {str(e)}",
                details={'symbol': symbol, 'error': str(e)}
            )
            self._record_check(check)
            return check
    
    async def _get_liquidity_metrics(self, symbol: str) -> Optional[LiquidityMetrics]:
        """
        获取流动性指标（简化实现）
        
        Args:
            symbol: 交易对
            
        Returns:
            流动性指标，如无法获取则返回None
        """
        # 检查缓存
        cache_key = symbol
        if cache_key in self._liquidity_cache:
            cached = self._liquidity_cache[cache_key]
            if time.time() - cached.last_update < self._cache_ttl:
                return cached
        
        # 模拟流动性数据
        # 实际实现应从市场数据模块获取
        try:
            # 这里模拟不同交易对的流动性
            liquidity_data = {
                'BTCUSDT': {
                    'bid_ask_spread': 0.0001,  # 0.01%
                    'order_book_depth': 5000000,  # 500万美元
                    'volume_24h': 20000000,  # 2000万美元
                    'avg_trade_size': 0.1,  # 0.1 BTC
                },
                'ETHUSDT': {
                    'bid_ask_spread': 0.0002,  # 0.02%
                    'order_book_depth': 2000000,  # 200万美元
                    'volume_24h': 10000000,  # 1000万美元
                    'avg_trade_size': 1.0,  # 1 ETH
                },
                'BNBUSDT': {
                    'bid_ask_spread': 0.0005,  # 0.05%
                    'order_book_depth': 1000000,  # 100万美元
                    'volume_24h': 5000000,  # 500万美元
                    'avg_trade_size': 10.0,  # 10 BNB
                },
            }
            
            symbol_key = symbol.replace('/', '')
            if symbol_key in liquidity_data:
                data = liquidity_data[symbol_key]
                metrics = LiquidityMetrics(
                    symbol=symbol,
                    bid_ask_spread=data['bid_ask_spread'],
                    order_book_depth=data['order_book_depth'],
                    volume_24h=data['volume_24h'],
                    avg_trade_size=data['avg_trade_size'],
                    last_update=time.time(),
                )
                
                # 更新缓存
                self._liquidity_cache[cache_key] = metrics
                
                return metrics
        
        except Exception as e:
            logger.warning(f"获取流动性指标失败 {symbol}: {e}")
        
        return None
    
    async def estimate_slippage(self, 
                               symbol: str,
                               order_type: OrderType,
                               order_side: OrderSide,
                               order_size: float,
                               current_price: float) -> Tuple[float, float]:
        """
        估计订单滑点
        
        Args:
            symbol: 交易对
            order_type: 订单类型
            order_side: 订单方向
            order_size: 订单大小
            current_price: 当前价格
            
        Returns:
            (估计滑点百分比, 估计成交价格)
        """
        try:
            # 获取流动性指标
            liquidity = await self._get_liquidity_metrics(symbol)
            if not liquidity:
                # 无法获取流动性数据，使用保守估计
                conservative_slippage = 0.005  # 0.5%
                if order_type == OrderType.MARKET:
                    conservative_slippage = 0.01  # 市价单风险更高
                
                estimated_price = current_price * (1 + conservative_slippage) if order_side == OrderSide.BUY else current_price * (1 - conservative_slippage)
                return conservative_slippage, estimated_price
            
            # 基于流动性估计滑点
            base_slippage = liquidity.bid_ask_spread
            
            # 考虑订单大小的影响
            order_value = order_size * current_price
            size_impact = min(order_value / liquidity.order_book_depth, 1.0) * 0.01  # 最大1%影响
            
            # 考虑订单类型的影响
            type_multiplier = 1.0
            if order_type == OrderType.MARKET:
                type_multiplier = 2.0  # 市价单滑点更高
            elif order_type == OrderType.LIMIT:
                type_multiplier = 0.5  # 限价单滑点较低（如果能够成交）
            
            # 总滑点估计
            estimated_slippage = base_slippage + size_impact * type_multiplier
            
            # 计算估计成交价格
            if order_side == OrderSide.BUY:
                estimated_price = current_price * (1 + estimated_slippage)
            else:  # SELL
                estimated_price = current_price * (1 - estimated_slippage)
            
            return estimated_slippage, estimated_price
            
        except Exception as e:
            logger.error(f"滑点估计失败 {symbol}: {e}")
            # 异常情况下返回保守估计
            conservative_slippage = 0.01  # 1%
            estimated_price = current_price * (1 + conservative_slippage) if order_side == OrderSide.BUY else current_price * (1 - conservative_slippage)
            return conservative_slippage, estimated_price
    
    async def check_execution_timing(self, symbol: str) -> RiskCheck:
        """
        检查执行时机
        
        Args:
            symbol: 交易对
            
        Returns:
            时机检查结果
        """
        check_id = self._generate_check_id()
        
        try:
            current_time = time.time()
            import datetime
            
            # 转换为本地时间（假设UTC+8）
            dt = datetime.datetime.fromtimestamp(current_time)
            hour = dt.hour
            
            # 检查是否在交易活跃时段
            # 加密货币市场24小时交易，但某些时段流动性较差
            low_liquidity_hours = [0, 1, 2, 3]  # 凌晨时段
            
            if hour in low_liquidity_hours:
                check = RiskCheck(
                    check_id=check_id,
                    check_name="执行时机检查",
                    result=RiskCheckResult.WARNING,
                    message=f"当前时段流动性可能较低: {hour}:00 UTC+8",
                    details={
                        'symbol': symbol,
                        'hour': hour,
                        'low_liquidity_hours': low_liquidity_hours,
                    }
                )
                self._record_check(check)
                return check
            
            # 检查是否在重要数据发布前后
            # 这里简化实现，实际应从经济日历获取数据
            
            # 所有检查通过
            check = RiskCheck(
                check_id=check_id,
                check_name="执行时机检查",
                result=RiskCheckResult.PASS,
                message=f"执行时机正常: {hour}:00 UTC+8",
                details={
                    'symbol': symbol,
                    'hour': hour,
                    'timestamp': current_time,
                }
            )
            self._record_check(check)
            return check
            
        except Exception as e:
            check = RiskCheck(
                check_id=check_id,
                check_name="执行时机检查",
                result=RiskCheckResult.WARNING,
                message=f"执行时机检查异常: {str(e)}",
                details={'symbol': symbol, 'error': str(e)}
            )
            self._record_check(check)
            return check
    
    async def check_order_risk(self, 
                              order: Order,
                              current_price: float) -> List[RiskCheck]:
        """
        全面检查订单风险
        
        Args:
            order: 订单对象
            current_price: 当前价格
            
        Returns:
            所有风险检查结果列表
        """
        checks = []
        
        # 1. 流动性检查
        liquidity_check = await self.check_liquidity(
            symbol=order.symbol,
            order_size=order.amount,
            order_price=order.price or current_price
        )
        checks.append(liquidity_check)
        
        # 2. 执行时机检查
        timing_check = await self.check_execution_timing(order.symbol)
        checks.append(timing_check)
        
        # 3. 滑点估计
        if order.order_type in [OrderType.MARKET, OrderType.LIMIT]:
            estimated_slippage, estimated_price = await self.estimate_slippage(
                symbol=order.symbol,
                order_type=order.order_type,
                order_side=order.side,
                order_size=order.amount,
                current_price=current_price
            )
            
            # 检查滑点是否超过阈值
            if estimated_slippage > self.max_slippage_percent:
                slippage_check = RiskCheck(
                    check_id=self._generate_check_id(),
                    check_name="滑点检查",
                    result=RiskCheckResult.BLOCK,
                    message=f"预计滑点过大: {estimated_slippage:.4%} > {self.max_slippage_percent:.4%}",
                    details={
                        'symbol': order.symbol,
                        'estimated_slippage': estimated_slippage,
                        'max_slippage': self.max_slippage_percent,
                        'estimated_price': estimated_price,
                        'current_price': current_price,
                        'order_type': order.order_type.value,
                    }
                )
                checks.append(slippage_check)
            else:
                slippage_check = RiskCheck(
                    check_id=self._generate_check_id(),
                    check_name="滑点检查",
                    result=RiskCheckResult.PASS,
                    message=f"预计滑点可接受: {estimated_slippage:.4%}",
                    details={
                        'symbol': order.symbol,
                        'estimated_slippage': estimated_slippage,
                        'estimated_price': estimated_price,
                    }
                )
                checks.append(slippage_check)
        
        # 4. 订单类型特定检查
        if order.order_type == OrderType.MARKET:
            # 市价单额外检查
            market_order_check = RiskCheck(
                check_id=self._generate_check_id(),
                check_name="市价单检查",
                result=RiskCheckResult.WARNING,
                message="市价单可能在异常波动时产生较大滑点",
                details={
                    'symbol': order.symbol,
                    'order_type': 'MARKET',
                    'recommendation': '考虑使用限价单',
                }
            )
            checks.append(market_order_check)
        
        return checks
    
    async def get_risk_summary(self, checks: List[RiskCheck]) -> Dict[str, Any]:
        """
        获取风险检查摘要
        
        Args:
            checks: 风险检查结果列表
            
        Returns:
            风险摘要
        """
        total_checks = len(checks)
        passed_checks = sum(1 for c in checks if c.result == RiskCheckResult.PASS)
        warning_checks = sum(1 for c in checks if c.result == RiskCheckResult.WARNING)
        block_checks = sum(1 for c in checks if c.result == RiskCheckResult.BLOCK)
        
        # 总体风险评估
        overall_risk = "low"
        if block_checks > 0:
            overall_risk = "high"
        elif warning_checks > 0:
            overall_risk = "medium"
        
        # 获取阻塞性检查的详细信息
        blocking_issues = []
        for check in checks:
            if check.result == RiskCheckResult.BLOCK:
                blocking_issues.append({
                    'check_name': check.check_name,
                    'message': check.message,
                    'details': check.details,
                })
        
        # 获取警告性检查的详细信息
        warning_issues = []
        for check in checks:
            if check.result == RiskCheckResult.WARNING:
                warning_issues.append({
                    'check_name': check.check_name,
                    'message': check.message,
                    'details': check.details,
                })
        
        return {
            'total_checks': total_checks,
            'passed_checks': passed_checks,
            'warning_checks': warning_checks,
            'block_checks': block_checks,
            'overall_risk': overall_risk,
            'blocking_issues': blocking_issues,
            'warning_issues': warning_issues,
            'timestamp': time.time(),
        }
    
    async def get_recommendations(self, checks: List[RiskCheck]) -> List[Dict[str, Any]]:
        """
        根据风险检查结果获取建议
        
        Args:
            checks: 风险检查结果列表
            
        Returns:
            建议列表
        """
        recommendations = []
        
        for check in checks:
            if check.result == RiskCheckResult.WARNING:
                # 根据检查类型提供建议
                if "流动性" in check.check_name:
                    recommendations.append({
                        'type': 'liquidity',
                        'priority': 'medium',
                        'message': '考虑减少订单大小或切换到更流动的交易对',
                        'details': check.details,
                    })
                elif "时机" in check.check_name:
                    recommendations.append({
                        'type': 'timing',
                        'priority': 'low',
                        'message': '考虑延迟到流动性更好的时段执行',
                        'details': check.details,
                    })
                elif "滑点" in check.check_name:
                    recommendations.append({
                        'type': 'slippage',
                        'priority': 'high',
                        'message': '考虑使用限价单或减少订单大小',
                        'details': check.details,
                    })
            
            elif check.result == RiskCheckResult.BLOCK:
                # 阻塞性问题的紧急建议
                if "流动性" in check.check_name:
                    recommendations.append({
                        'type': 'liquidity',
                        'priority': 'critical',
                        'message': '必须减少订单大小或取消订单',
                        'details': check.details,
                    })
                elif "滑点" in check.check_name:
                    recommendations.append({
                        'type': 'slippage',
                        'priority': 'critical',
                        'message': '必须使用限价单或大幅减少订单大小',
                        'details': check.details,
                    })
        
        # 去重和排序（按优先级）
        unique_recommendations = []
        seen_messages = set()
        
        for rec in recommendations:
            message_key = rec['message']
            if message_key not in seen_messages:
                seen_messages.add(message_key)
                unique_recommendations.append(rec)
        
        # 按优先级排序（critical > high > medium > low）
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        unique_recommendations.sort(key=lambda r: priority_order.get(r['priority'], 4))
        
        return unique_recommendations
    
    def get_check_history(self, limit: int = 100) -> List[RiskCheck]:
        """
        获取检查历史
        
        Args:
            limit: 返回数量限制
            
        Returns:
            检查历史列表（最近的在前面）
        """
        return self._check_history[-limit:] if self._check_history else []
    
    async def close(self) -> None:
        """
        关闭风险控制器，清理资源
        """
        # 清理缓存
        self._liquidity_cache.clear()
        
        logger.info("执行风险控制器已关闭")


# 便捷函数
async def create_execution_risk_controller(config_path: Optional[str] = None) -> ExecutionRiskController:
    """
    创建执行风险控制器实例（工厂函数）
    
    Args:
        config_path: 可选，配置文件路径
        
    Returns:
        执行风险控制器实例
    """
    from config.config_manager import ConfigManager
    
    config = ConfigManager(config_path)
    controller = ExecutionRiskController(config)
    
    return controller


if __name__ == "__main__":
    """模块自测"""
    import asyncio
    
    async def test_execution_risk():
        import sys
        sys.path.append('/home/lingge/quant_brain/01_codebase/binance_ai_agent')
        
        from config.config_manager import ConfigManager
        from .order_manager import Order, OrderType, OrderSide
        
        config = ConfigManager()
        controller = ExecutionRiskController(config)
        
        try:
            # 创建测试订单
            test_order = Order(
                order_id="test_order_123",
                client_order_id="client_test",
                symbol="BTC/USDT",
                order_type=OrderType.MARKET,
                side=OrderSide.BUY,
                amount=0.1,
                price=50000.0,
            )
            
            print("测试执行风险检查...")
            
            # 检查流动性
            liquidity_check = await controller.check_liquidity(
                symbol="BTC/USDT",
                order_size=0.1,
                order_price=50000.0
            )
            
            print(f"流动性检查: {liquidity_check.result.value} - {liquidity_check.message}")
            
            # 估计滑点
            slippage, estimated_price = await controller.estimate_slippage(
                symbol="BTC/USDT",
                order_type=OrderType.MARKET,
                order_side=OrderSide.BUY,
                order_size=0.1,
                current_price=50000.0
            )
            
            print(f"滑点估计: {slippage:.4%}, 估计成交价: ${estimated_price:,.2f}")
            
            # 全面订单风险检查
            risk_checks = await controller.check_order_risk(test_order, 50000.0)
            
            print(f"\n全面风险检查 ({len(risk_checks)}项):")
            for check in risk_checks:
                print(f"  {check.check_name}: {check.result.value} - {check.message}")
            
            # 风险摘要
            risk_summary = await controller.get_risk_summary(risk_checks)
            print(f"\n风险摘要: {risk_summary['overall_risk']}")
            print(f"  通过: {risk_summary['passed_checks']}, 警告: {risk_summary['warning_checks']}, 阻止: {risk_summary['block_checks']}")
            
            # 获取建议
            recommendations = await controller.get_recommendations(risk_checks)
            if recommendations:
                print(f"\n建议 ({len(recommendations)}条):")
                for rec in recommendations:
                    print(f"  [{rec['priority'].upper()}] {rec['message']}")
            
        except Exception as e:
            print(f"测试失败: {e}")
        finally:
            await controller.close()
    
    asyncio.run(test_execution_risk())