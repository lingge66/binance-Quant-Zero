"""
账户监控模块 - 实时监控币安账户资金与风险状态

核心功能：
1. 账户余额监控（现货、合约、保证金账户）
2. 风险指标计算（保证金率、杠杆率、可用资金）
3. 持仓监控（多头/空头仓位、未实现盈亏）
4. 实时预警（资金不足、强平价接近）

安全设计：
- API密钥零硬编码，从环境变量读取
- 日志脱敏处理，不暴露敏感信息
- 指数退避重试机制，网络异常自动恢复
- 主网/测试网环境隔离

版本: 1.0.0
作者: Coder
创建日期: 2026-03-12
"""

import os
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import time
import json

# 第三方库
import ccxt.async_support as ccxt
import pandas as pd
import numpy as np

# 项目内部导入
from config.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class AccountType(Enum):
    """账户类型枚举"""
    SPOT = "spot"           # 现货账户
    FUTURES = "futures"     # U本位合约
    MARGIN = "margin"       # 杠杆账户
    ISOLATED = "isolated"   # 逐仓保证金


@dataclass
class AccountBalance:
    """账户余额数据类"""
    total_balance: float          # 总余额（USDT）
    available_balance: float      # 可用余额（USDT）
    locked_balance: float         # 锁定余额（USDT）
    margin_ratio: float           # 保证金率（0-1，仅限合约）
    leverage: float               # 杠杆倍数（仅限合约）
    unrealized_pnl: float         # 未实现盈亏（USDT）
    realized_pnl: float           # 已实现盈亏（USDT）
    timestamp: int                # 时间戳（毫秒）


@dataclass
class PositionInfo:
    """持仓信息数据类"""
    symbol: str                   # 交易对（如 BTC/USDT）
    position_side: str            # 持仓方向（long/short）
    position_amount: float        # 持仓数量
    entry_price: float            # 开仓均价
    mark_price: float             # 标记价格
    unrealized_pnl: float         # 未实现盈亏
    liquidation_price: float      # 强平价格
    leverage: float               # 杠杆倍数
    margin_type: str              # 保证金类型（isolated/cross）
    timestamp: int                # 时间戳


class AccountMonitor:
    """
    账户监控器 - 实时监控币安账户状态
    
    设计特性：
    1. 多账户类型支持（现货、合约、保证金）
    2. 实时监控与缓存机制（减少API调用）
    3. 异常处理与自动重试
    4. 内存安全与性能优化
    """
    
    def __init__(self, config: ConfigManager):
        """
        初始化账户监控器
        
        Args:
            config: 配置管理器实例
        """
        self.config = config
        self.exchange = None
        self.account_type = AccountType.SPOT  # 默认现货账户
        self._balance_cache: Optional[AccountBalance] = None
        self._positions_cache: List[PositionInfo] = []
        self._last_update_time = 0
        self._cache_ttl = 5  # 缓存有效期（秒）
        self._max_retries = 3  # 最大重试次数
        self._retry_delay = 1.0  # 重试延迟（秒）
        
        # 从配置读取API密钥
        self.api_key = os.getenv('BINANCE_API_KEY', '')
        self.api_secret = os.getenv('BINANCE_API_SECRET', '')
        
        # 环境检测（主网/测试网）
        self.environment = self.config.get('environment', 'mainnet')
        self._validate_api_keys()
        
        # 初始化日志
        self._setup_logging()
    
    def _validate_api_keys(self) -> None:
        """
        验证API密钥配置
        
        Raises:
            ValueError: API密钥未配置
        """
        if not self.api_key or not self.api_secret:
            logger.warning("API密钥未配置，将使用公开API（仅限查询功能）")
            # 对于公开API，可以继续运行但交易功能受限
            return
        
        # 脱敏显示密钥（前5后4字符）
        masked_key = f"{self.api_key[:5]}...{self.api_key[-4:]}" if len(self.api_key) > 9 else "***"
        masked_secret = f"{self.api_secret[:5]}...{self.api_secret[-4:]}" if len(self.api_secret) > 9 else "***"
        logger.info(f"API密钥已加载（环境: {self.environment}，密钥: {masked_key}）")
    
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
    
    async def _create_exchange(self) -> ccxt.Exchange:
        """
        创建ccxt交易所实例
        
        Returns:
            ccxt交易所实例
            
        Raises:
            ConnectionError: 交易所连接失败
        """
        try:
            # 配置交易所参数
            exchange_config = {
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'timeout': 30000,
                'enableRateLimit': True,
                'options': {
                    'defaultType': self.account_type.value,
                }
            }
            
            # 测试网配置
            if self.environment == 'testnet':
                exchange_class = getattr(ccxt, 'binanceusdmtest', None)
                if exchange_class:
                    logger.info("使用币安测试网（USDⓂ️ Testnet）")
                    return exchange_class(exchange_config)
            
            # 主网配置（默认）
            exchange_class = getattr(ccxt, 'binanceusdm', None)
            if not exchange_class:
                raise ImportError("无法加载币安交易所类")
                
            logger.info("使用币安主网（USDⓂ️）")
            return exchange_class(exchange_config)
            
        except Exception as e:
            logger.error(f"创建交易所实例失败: {e}")
            raise ConnectionError(f"交易所连接失败: {e}")
    
    async def _safe_api_call(self, func, *args, **kwargs) -> Any:
        """
        安全的API调用（带重试机制）
        
        Args:
            func: 要调用的API函数
            *args: 函数参数
            **kwargs: 关键字参数
            
        Returns:
            API调用结果
            
        Raises:
            Exception: 所有重试失败后的异常
        """
        last_exception = None
        
        for attempt in range(self._max_retries):
            try:
                if attempt > 0:
                    delay = self._retry_delay * (2 ** (attempt - 1))  # 指数退避
                    logger.warning(f"API调用重试 {attempt}/{self._max_retries}，等待 {delay:.1f}秒")
                    await asyncio.sleep(delay)
                
                result = await func(*args, **kwargs)
                return result
                
            except (ccxt.NetworkError, ccxt.ExchangeError, asyncio.TimeoutError) as e:
                last_exception = e
                logger.warning(f"API调用失败（尝试 {attempt+1}/{self._max_retries}）: {type(e).__name__}: {e}")
                continue
            except Exception as e:
                logger.error(f"API调用意外错误: {type(e).__name__}: {e}")
                raise
        
        # 所有重试失败
        logger.error(f"API调用失败，所有 {self._max_retries} 次尝试均失败")
        raise last_exception or Exception("API调用失败")
    
    async def initialize(self) -> None:
        """
        初始化账户监控器
        
        Raises:
            ConnectionError: 初始化失败
        """
        try:
            if not self.exchange:
                self.exchange = await self._create_exchange()
                logger.info("账户监控器初始化成功")
                
                # 测试连接
                await self._safe_api_call(self.exchange.fetch_time)
                logger.debug("交易所连接测试通过")
                
        except Exception as e:
            logger.error(f"账户监控器初始化失败: {e}")
            raise ConnectionError(f"账户监控器初始化失败: {e}")
    
    async def fetch_account_balance(self, force_refresh: bool = False) -> AccountBalance:
        """
        获取账户余额信息
        
        Args:
            force_refresh: 强制刷新缓存
            
        Returns:
            账户余额对象
        """
        # 检查缓存
        current_time = time.time()
        if (not force_refresh and self._balance_cache and 
            (current_time - self._last_update_time) < self._cache_ttl):
            return self._balance_cache
        
        try:
            # 确保交易所已初始化
            if not self.exchange:
                await self.initialize()
            
            # 获取余额
            balance_data = await self._safe_api_call(self.exchange.fetch_balance)
            
            # 解析余额数据（以USDT为基准）
            total_usdt = 0.0
            available_usdt = 0.0
            locked_usdt = 0.0
            
            # 提取USDT余额
            if 'USDT' in balance_data.get('total', {}):
                total_usdt = float(balance_data['total']['USDT'])
                available_usdt = float(balance_data['free']['USDT'])
                locked_usdt = float(balance_data['used']['USDT'])
            
            # 计算合约账户指标（如果可用）
            margin_ratio = 0.0
            leverage = 1.0
            unrealized_pnl = 0.0
            realized_pnl = 0.0
            
            if self.account_type in [AccountType.FUTURES, AccountType.ISOLATED]:
                # 获取合约账户信息
                try:
                    positions = await self._safe_api_call(self.exchange.fetch_positions)
                    
                    # 计算未实现盈亏
                    for pos in positions:
                        if pos.get('symbol'):
                            unrealized_pnl += float(pos.get('unrealizedPnl', 0))
                            realized_pnl += float(pos.get('realizedPnl', 0))
                    
                    # 获取账户信息（杠杆、保证金率）
                    account_info = await self._safe_api_call(self.exchange.fetch_account)
                    if 'info' in account_info:
                        info = account_info['info']
                        margin_ratio = float(info.get('marginRatio', 0))
                        leverage = float(info.get('leverage', 1.0))
                        
                except Exception as e:
                    logger.warning(f"获取合约账户信息失败: {e}")
            
            # 创建余额对象
            balance = AccountBalance(
                total_balance=total_usdt,
                available_balance=available_usdt,
                locked_balance=locked_usdt,
                margin_ratio=margin_ratio,
                leverage=leverage,
                unrealized_pnl=unrealized_pnl,
                realized_pnl=realized_pnl,
                timestamp=int(time.time() * 1000)
            )
            
            # 更新缓存
            self._balance_cache = balance
            self._last_update_time = current_time
            
            logger.debug(f"账户余额更新: 总余额={total_usdt:.2f} USDT, 可用={available_usdt:.2f} USDT")
            return balance
            
        except Exception as e:
            logger.error(f"获取账户余额失败: {e}")
            
            # 返回缓存数据（如果可用）
            if self._balance_cache:
                logger.warning("使用缓存的余额数据")
                return self._balance_cache
            
            # 返回默认值
            return AccountBalance(
                total_balance=0.0,
                available_balance=0.0,
                locked_balance=0.0,
                margin_ratio=0.0,
                leverage=1.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                timestamp=int(time.time() * 1000)
            )
    
    async def fetch_positions(self, symbol: Optional[str] = None) -> List[PositionInfo]:
        """
        获取持仓信息
        
        Args:
            symbol: 可选，指定交易对
            
        Returns:
            持仓信息列表
        """
        try:
            # 仅合约账户支持持仓查询
            if self.account_type not in [AccountType.FUTURES, AccountType.ISOLATED, AccountType.MARGIN]:
                logger.debug("现货账户无持仓信息")
                return []
            
            # 确保交易所已初始化
            if not self.exchange:
                await self.initialize()
            
            # 获取持仓
            positions_data = await self._safe_api_call(self.exchange.fetch_positions)
            
            positions = []
            for pos_data in positions_data:
                # 过滤指定交易对
                if symbol and pos_data.get('symbol') != symbol:
                    continue
                
                # 跳过零持仓
                position_amount = float(pos_data.get('positionAmt', 0))
                if abs(position_amount) < 1e-8:
                    continue
                
                # 解析持仓方向
                position_side = 'long' if position_amount > 0 else 'short'
                
                # 创建持仓信息对象
                position = PositionInfo(
                    symbol=pos_data.get('symbol', ''),
                    position_side=position_side,
                    position_amount=abs(position_amount),
                    entry_price=float(pos_data.get('entryPrice', 0)),
                    mark_price=float(pos_data.get('markPrice', 0)),
                    unrealized_pnl=float(pos_data.get('unrealizedPnl', 0)),
                    liquidation_price=float(pos_data.get('liquidationPrice', 0)),
                    leverage=float(pos_data.get('leverage', 1.0)),
                    margin_type=pos_data.get('marginType', 'cross'),
                    timestamp=int(time.time() * 1000)
                )
                
                positions.append(position)
            
            # 更新缓存
            self._positions_cache = positions
            
            logger.debug(f"获取到 {len(positions)} 个持仓")
            return positions
            
        except Exception as e:
            logger.error(f"获取持仓信息失败: {e}")
            return self._positions_cache  # 返回缓存数据
    
    async def calculate_risk_metrics(self) -> Dict[str, Any]:
        """
        计算风险指标
        
        Returns:
            风险指标字典
        """
        try:
            # 获取账户余额
            balance = await self.fetch_account_balance()
            
            # 获取持仓
            positions = await self.fetch_positions()
            
            # 计算总风险指标
            total_position_value = 0.0
            total_unrealized_pnl = 0.0
            max_leverage = 1.0
            
            for position in positions:
                position_value = position.position_amount * position.mark_price
                total_position_value += position_value
                total_unrealized_pnl += position.unrealized_pnl
                max_leverage = max(max_leverage, position.leverage)
            
            # 计算关键风险指标
            metrics = {
                'total_balance': balance.total_balance,
                'available_balance': balance.available_balance,
                'margin_ratio': balance.margin_ratio,
                'leverage': balance.leverage,
                'total_position_value': total_position_value,
                'total_unrealized_pnl': total_unrealized_pnl,
                'max_leverage': max_leverage,
                'position_ratio': total_position_value / max(balance.total_balance, 1.0),  # 仓位占比
                'pnl_ratio': total_unrealized_pnl / max(balance.total_balance, 1.0),      # 盈亏占比
                'timestamp': int(time.time() * 1000)
            }
            
            logger.debug(f"风险指标计算完成: 仓位占比={metrics['position_ratio']:.2%}, 盈亏占比={metrics['pnl_ratio']:.2%}")
            return metrics
            
        except Exception as e:
            logger.error(f"计算风险指标失败: {e}")
            return {
                'total_balance': 0.0,
                'available_balance': 0.0,
                'margin_ratio': 0.0,
                'leverage': 1.0,
                'total_position_value': 0.0,
                'total_unrealized_pnl': 0.0,
                'max_leverage': 1.0,
                'position_ratio': 0.0,
                'pnl_ratio': 0.0,
                'timestamp': int(time.time() * 1000)
            }
    
    async def check_liquidation_risk(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        检查强平风险
        
        Args:
            symbol: 可选，指定交易对
            
        Returns:
            强平风险分析
        """
        try:
            positions = await self.fetch_positions(symbol)
            
            risk_analysis = {
                'has_risk': False,
                'high_risk_positions': [],
                'closest_liquidation_ratio': 1.0,  # 距离强平的百分比（1.0=无风险）
                'timestamp': int(time.time() * 1000)
            }
            
            for position in positions:
                if position.liquidation_price <= 0:
                    continue
                
                # 计算当前价格距离强平价的百分比
                if position.position_side == 'long':
                    # 多头：价格下跌到强平价
                    current_price = position.mark_price
                    liquidation_price = position.liquidation_price
                    if current_price > liquidation_price:
                        ratio = (current_price - liquidation_price) / current_price
                    else:
                        ratio = 0.0  # 已强平
                else:
                    # 空头：价格上涨到强平价
                    current_price = position.mark_price
                    liquidation_price = position.liquidation_price
                    if liquidation_price > current_price:
                        ratio = (liquidation_price - current_price) / current_price
                    else:
                        ratio = 0.0  # 已强平
                
                # 记录高风险持仓（距离强平<5%）
                if ratio < 0.05:
                    risk_analysis['has_risk'] = True
                    risk_analysis['high_risk_positions'].append({
                        'symbol': position.symbol,
                        'side': position.position_side,
                        'liquidation_distance_ratio': ratio,
                        'liquidation_price': position.liquidation_price,
                        'current_price': position.mark_price
                    })
                
                # 更新最近强平距离
                risk_analysis['closest_liquidation_ratio'] = min(
                    risk_analysis['closest_liquidation_ratio'], ratio
                )
            
            if risk_analysis['has_risk']:
                logger.warning(f"检测到强平风险: {len(risk_analysis['high_risk_positions'])} 个高风险持仓")
            
            return risk_analysis
            
        except Exception as e:
            logger.error(f"检查强平风险失败: {e}")
            return {
                'has_risk': False,
                'high_risk_positions': [],
                'closest_liquidation_ratio': 1.0,
                'timestamp': int(time.time() * 1000)
            }
    
    async def close(self) -> None:
        """
        关闭账户监控器，释放资源
        """
        try:
            if self.exchange:
                await self.exchange.close()
                self.exchange = None
                logger.info("账户监控器已关闭")
        except Exception as e:
            logger.error(f"关闭账户监控器时出错: {e}")
    
    def __del__(self):
        """析构函数，确保资源释放"""
        if self.exchange and not self.exchange.closed:
            try:
                asyncio.run(self.close())
            except:
                pass


# 便捷函数
async def create_account_monitor(config_path: Optional[str] = None) -> AccountMonitor:
    """
    创建账户监控器实例（工厂函数）
    
    Args:
        config_path: 可选，配置文件路径
        
    Returns:
        账户监控器实例
    """
    from config.config_manager import ConfigManager
    
    config = ConfigManager(config_path)
    monitor = AccountMonitor(config)
    await monitor.initialize()
    return monitor


if __name__ == "__main__":
    """模块自测"""
    async def test_monitor():
        import sys
        sys.path.append('/home/lingge/quant_brain/01_codebase/binance_ai_agent')
        
        from config.config_manager import ConfigManager
        
        config = ConfigManager()
        monitor = AccountMonitor(config)
        
        try:
            await monitor.initialize()
            
            # 测试余额查询
            balance = await monitor.fetch_account_balance()
            print(f"账户余额: {balance.total_balance:.2f} USDT")
            
            # 测试风险指标
            metrics = await monitor.calculate_risk_metrics()
            print(f"风险指标: {metrics}")
            
            # 测试强平风险
            risk = await monitor.check_liquidation_risk()
            print(f"强平风险: {risk}")
            
        except Exception as e:
            print(f"测试失败: {e}")
        finally:
            await monitor.close()
    
    asyncio.run(test_monitor())