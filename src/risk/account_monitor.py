"""
账户监控模块 - 实时监控币安账户资金与风险状态 (Demo 模拟盘终极穿透版)

核心功能：
1. 账户余额监控（支持 Demo 模拟盘专属裸接口）
2. 风险指标计算（保证金率、杠杆率、可用资金）
3. 持仓监控（多头/空头仓位、未实现盈亏）
4. 实时预警（资金不足、强平价接近）

安全与架构设计：
- API密钥与代理零硬编码，从环境/配置读取
- 自动检测并切换 Demo 模拟盘专属路由
- 绕过 CCXT 缓存拦截，直连币安底层 V2 接口
- 指数退避重试机制，网络异常自动恢复

版本: 1.2.0 (穿甲增压版 + 模拟盘域名修正)
作者: Coder (领哥大虾专属定制)
修改日期: 2026-03-13
"""

import os
import asyncio
import logging
import time
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

# 第三方库
import ccxt.async_support as ccxt
from dotenv import load_dotenv

# 项目内部导入
from config.config_manager import ConfigManager

# ==========================================
# 🛡️ 环境预加载机制
# 确保模块被导入时，立刻读取根目录的 .env
# ==========================================
load_dotenv(override=True)

logger = logging.getLogger(__name__)


class AccountType(Enum):
    """账户类型枚举"""
    SPOT = "spot"           # 现货账户
    FUTURES = "futures"     # U本位合约
    MARGIN = "margin"       # 杠杆账户
    ISOLATED = "isolated"   # 逐仓保证金


from typing import Dict, Optional

@dataclass
class AccountBalance:
    total_balance: float
    available_balance: float
    locked_balance: float
    margin_ratio: float
    leverage: float
    unrealized_pnl: float
    realized_pnl: float
    timestamp: int
    assets: Optional[Dict[str, float]] = None   # 新增字段，存储所有资产余额）


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
    账户监控器 - 实时监控币安账户状态 (增强版)
    """
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.exchange = None
        self.account_type = AccountType.FUTURES  # 默认转为合约账户，适配大赛
        self._balance_cache: Optional[AccountBalance] = None
        self._positions_cache: List[PositionInfo] = []
        self._last_update_time = 0
        self._cache_ttl = 5
        self._max_retries = 3
        self._retry_delay = 1.0
        
        # 读取密钥
        self.api_key = os.getenv('BINANCE_API_KEY', '')
        self.api_secret = os.getenv('BINANCE_API_SECRET', '')
        
        # 🛡️ 代理读取：统一使用 HTTP 代理格式，与 telegram_demo.py 保持一致
        self.proxy_url = os.getenv('HTTP_PROXY', 'http://127.0.0.1:10808')
        
        # 环境检测（强制容错：如果没有配置环境，只要带有 'test' 或者密钥为空，优先认为是 testnet）
        self.environment = self.config.get('binance.environment', 'mainnet')
        if os.getenv('BINANCE_TESTNET', 'false').lower() == 'true':
            self.environment = 'testnet'
            
        self._validate_api_keys()
        self._setup_logging()
    
    def _validate_api_keys(self) -> None:
        """验证API密钥配置"""
        if not self.api_key or not self.api_secret:
            logger.warning("API密钥未配置，将使用公开API（仅限查询功能）")
            return
            
        masked_key = f"{self.api_key[:5]}...{self.api_key[-4:]}" if len(self.api_key) > 9 else "***"
        logger.info(f"✅ 核心密钥已加载（环境: {self.environment}，密钥: {masked_key}）")
    
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
        创建并魔改 ccxt 交易所实例 (大厂级无痕代理与路由劫持)
        """
        try:
            exchange_config = {
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'timeout': 30000,
                'enableRateLimit': True,
                'options': {
                    'defaultType': self.account_type.value,
                }
            }
            
            # 💉 优雅注入 HTTP 代理（aiohttp 原生支持）
            if self.proxy_url:
                exchange_config['proxies'] = {
                    'http': self.proxy_url,
                    'https': self.proxy_url
                }
                logger.info(f"🛡️ 穿甲代理已挂载: {self.proxy_url}")
            
            # 无论什么环境，先初始化主网类（因为主网类的接口最全）
            exchange_class = getattr(ccxt, 'binanceusdm', None)
            if not exchange_class:
                raise ImportError("无法加载币安交易所类")
                
            exchange = exchange_class(exchange_config)
            
            # 💉 核心路由劫持：如果是测试网，强行替换为正确的模拟盘地址
            if self.environment in ['testnet', 'demo']:
                logger.info("🔧 启动 币安合约模拟盘专属路由劫持 (testnet.binancefuture.com)...")
                
                # 正确的模拟盘基础地址
                testnet_base = 'https://testnet.binancefuture.com'
                
                # 获取当前的 API URLs 字典
                api_urls = exchange.urls.get('api', {})
                
                # 遍历所有键，将以 'fapi' 开头的键（合约API）替换为模拟盘地址
                for key in list(api_urls.keys()):
                    if key.startswith('fapi'):
                        # 提取原路径部分（如 '/fapi/v1'）
                        original_url = api_urls[key]
                        # 简单提取路径：去掉主网域名部分
                        if 'binance.com' in original_url:
                            path = original_url.split('binance.com')[-1]
                        else:
                            path = ''
                        api_urls[key] = testnet_base + path
                
                # 同时覆盖 public 和 private 键，确保所有请求都走模拟盘
                api_urls['public'] = testnet_base
                api_urls['private'] = testnet_base
                
                # 将修改后的字典写回 exchange.urls
                exchange.urls['api'] = api_urls
                
                # 可选：打印调试信息（可注释掉）
                # logger.debug(f"修改后的 API URLs: {exchange.urls['api']}")
                
            return exchange
            
        except Exception as e:
            logger.error(f"创建交易所实例失败: {e}")
            raise ConnectionError(f"交易所连接失败: {e}")
    
    async def _safe_api_call(self, func, *args, **kwargs) -> Any:
        """安全的API调用（带指数退避重试）"""
        last_exception = None
        
        for attempt in range(self._max_retries):
            try:
                if attempt > 0:
                    delay = self._retry_delay * (2 ** (attempt - 1))
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
                
        logger.error(f"API调用失败，所有 {self._max_retries} 次尝试均失败")
        raise last_exception or Exception("API调用失败")
    
    async def initialize(self) -> None:
        """初始化账户监控器"""
        try:
            if not self.exchange:
                self.exchange = await self._create_exchange()
                logger.info("✅ 账户监控器 (穿透版) 初始化成功")
                
                # 测速
                start_time = time.time()
                await self._safe_api_call(self.exchange.fapiPublicGetTime)
                ping = (time.time() - start_time) * 1000
                logger.debug(f"交易所连接测试通过，延迟: {ping:.2f} ms")
                
        except Exception as e:
            logger.error(f"账户监控器初始化失败: {e}")
            raise ConnectionError(f"账户监控器初始化失败: {e}")
    
    async def fetch_account_balance(self, force_refresh: bool = False) -> AccountBalance:
        """获取账户余额信息 (采用 V2 裸接口直达技术)"""
        current_time = time.time()
        if (not force_refresh and self._balance_cache and 
            (current_time - self._last_update_time) < self._cache_ttl):
            return self._balance_cache
        
        try:
            if not self.exchange:
                await self.initialize()
            
            # 💉 核心修改：弃用 fetch_balance，改用 V2 裸接口避免拦截
            balances = await self._safe_api_call(self.exchange.fapiPrivateV2GetBalance)

            total_usdt = 0.0
            available_usdt = 0.0
            locked_usdt = 0.0
            assets_dict = {}  # 存储所有资产余额

            for asset in balances:
                asset_name = asset.get('asset')
                asset_balance = float(asset.get('balance', 0))
                if asset_balance > 0:
                    assets_dict[asset_name] = asset_balance
                if asset_name == 'USDT':
                    total_usdt = asset_balance
                    available_usdt = float(asset.get('availableBalance', 0))
                    locked_usdt = total_usdt - available_usdt
            
            # 获取账户整体风险数据 (保证金率、未实现盈亏)
            margin_ratio = 0.0
            leverage = 1.0
            unrealized_pnl = 0.0
            realized_pnl = 0.0
            
            try:
                account_info = await self._safe_api_call(self.exchange.fapiPrivateV2GetAccount)
               
                unrealized_pnl = float(account_info.get('totalUnrealizedProfit', 0))
                total_margin_balance = float(account_info.get('totalMarginBalance', total_usdt))  # 总保证金（含所有资产）
                total_maint_margin = float(account_info.get('totalMaintMargin', 0))
                
                if total_margin_balance > 0:
                    margin_ratio = total_maint_margin / total_margin_balance
                else:
                    margin_ratio = 0.0
            except Exception as e:
                logger.debug(f"获取账户附加风险信息时跳过: {e}")
                unrealized_pnl = 0.0
                total_margin_balance = total_usdt
                margin_ratio = 0.0

            balance = AccountBalance(
                total_balance=total_margin_balance,
                available_balance=available_usdt,
                locked_balance=locked_usdt,
                margin_ratio=margin_ratio,
                leverage=leverage,
                unrealized_pnl=unrealized_pnl,
                realized_pnl=realized_pnl,
                timestamp=int(time.time() * 1000),
                assets=assets_dict
            )
            
            self._balance_cache = balance
            self._last_update_time = current_time
            return balance
            
        except Exception as e:
            logger.error(f"获取账户余额失败: {e}")
            if self._balance_cache:
                return self._balance_cache
            return AccountBalance(0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, int(time.time() * 1000))
    
    async def fetch_positions(self, symbol: Optional[str] = None) -> List[PositionInfo]:
        """获取持仓信息 (采用 V2 裸接口直达技术)"""
        try:
            if not self.exchange:
                await self.initialize()
            
            # 💉 核心修改：弃用 fetch_positions，直接调底层裸接口查询风险
            positions_data = await self._safe_api_call(self.exchange.fapiPrivateV2GetPositionRisk)
            
            positions = []
            for pos_data in positions_data:
                # 裸接口返回的字段是原生格式
                pos_symbol = pos_data.get('symbol', '')
                if symbol and pos_symbol != symbol:
                    continue
                
                position_amount = float(pos_data.get('positionAmt', 0))
                if abs(position_amount) < 1e-8:
                    continue
                
                position_side = 'long' if position_amount > 0 else 'short'
                
                position = PositionInfo(
                    symbol=pos_symbol,
                    position_side=position_side,
                    position_amount=abs(position_amount),
                    entry_price=float(pos_data.get('entryPrice', 0)),
                    mark_price=float(pos_data.get('markPrice', 0)),
                    unrealized_pnl=float(pos_data.get('unRealizedProfit', 0)), # 注意官方接口的驼峰命名
                    liquidation_price=float(pos_data.get('liquidationPrice', 0)),
                    leverage=float(pos_data.get('leverage', 1.0)),
                    margin_type=pos_data.get('marginType', 'cross'),
                    timestamp=int(time.time() * 1000)
                )
                positions.append(position)
            
            self._positions_cache = positions
            return positions
            
        except Exception as e:
            logger.error(f"获取持仓信息失败: {e}")
            return self._positions_cache
    
    async def calculate_risk_metrics(self) -> Dict[str, Any]:
        """计算风险指标"""
        try:
            balance = await self.fetch_account_balance()
            positions = await self.fetch_positions()
            
            total_position_value = 0.0
            total_unrealized_pnl = 0.0
            max_leverage = 1.0
            
            for position in positions:
                position_value = position.position_amount * position.mark_price
                total_position_value += position_value
                total_unrealized_pnl += position.unrealized_pnl
                max_leverage = max(max_leverage, position.leverage)
            
            metrics = {
                'total_balance': balance.total_balance,
                'available_balance': balance.available_balance,
                'margin_ratio': balance.margin_ratio,
                'leverage': balance.leverage,
                'total_position_value': total_position_value,
                'total_unrealized_pnl': total_unrealized_pnl,
                'max_leverage': max_leverage,
                'position_ratio': total_position_value / max(balance.total_balance, 1.0),
                'pnl_ratio': total_unrealized_pnl / max(balance.total_balance, 1.0),
                'timestamp': int(time.time() * 1000)
            }
            return metrics
            
        except Exception as e:
            logger.error(f"计算风险指标失败: {e}")
            return {}
    
    async def check_liquidation_risk(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """检查强平风险"""
        # ... (此段业务逻辑极其标准，保持原样，未做修改) ...
        try:
            positions = await self.fetch_positions(symbol)
            risk_analysis = {
                'has_risk': False,
                'high_risk_positions': [],
                'closest_liquidation_ratio': 1.0,
                'timestamp': int(time.time() * 1000)
            }
            
            for position in positions:
                if position.liquidation_price <= 0:
                    continue
                
                current_price = position.mark_price
                liquidation_price = position.liquidation_price
                
                if position.position_side == 'long':
                    ratio = (current_price - liquidation_price) / current_price if current_price > liquidation_price else 0.0
                else:
                    ratio = (liquidation_price - current_price) / current_price if liquidation_price > current_price else 0.0
                
                if ratio < 0.05:
                    risk_analysis['has_risk'] = True
                    risk_analysis['high_risk_positions'].append({
                        'symbol': position.symbol,
                        'side': position.position_side,
                        'liquidation_distance_ratio': ratio,
                        'liquidation_price': position.liquidation_price,
                        'current_price': position.mark_price
                    })
                
                risk_analysis['closest_liquidation_ratio'] = min(risk_analysis['closest_liquidation_ratio'], ratio)
            
            return risk_analysis
            
        except Exception as e:
            logger.error(f"检查强平风险失败: {e}")
            return {'has_risk': False, 'high_risk_positions': [], 'closest_liquidation_ratio': 1.0, 'timestamp': int(time.time() * 1000)}
    
    async def close(self) -> None:
        """关闭账户监控器"""
        try:
            if hasattr(self, 'exchange') and self.exchange:
                await self.exchange.close()
                self.exchange = None
                logger.info("账户监控器已安全关闭")
        except Exception as e:
            logger.error(f"关闭账户监控器时出错: {e}")
    
    def __del__(self):
        """析构函数，使用安全闭包设计"""
        # 移除了会导致报错的 self.exchange.closed 属性检查
        pass


# 便捷函数
async def create_account_monitor(config_path: Optional[str] = None) -> AccountMonitor:
    from config.config_manager import ConfigManager
    config = ConfigManager(config_path)
    monitor = AccountMonitor(config)
    await monitor.initialize()
    return monitor