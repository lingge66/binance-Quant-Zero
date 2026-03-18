#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史数据获取模块
使用ccxt库获取币安历史K线数据
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import ccxt.async_support as ccxt
from pathlib import Path

from ..utils.exponential_backoff import retry_with_backoff_async


logger = logging.getLogger(__name__)


class HistoricalDataFetcher:
    """历史数据获取器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化历史数据获取器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.hist_config = config['data']['historical']
        
        # ccxt交易所实例
        self.exchange: Optional[ccxt.Exchange] = None
        
        # 数据缓存
        self.data_cache: Dict[str, Dict[str, List[Dict]]] = {}
        
        # 状态
        self.is_initialized = False
        self.last_fetch_time = 0
        
        # 性能统计
        self.fetch_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_kline_count': 0
        }
    
    async def initialize(self) -> bool:
        """
        初始化历史数据获取器
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            logger.info("初始化历史数据获取器...")
            
            # 创建ccxt交易所实例
            await self._create_exchange()
            
            # 加载市场信息
            await self._load_markets()
            
            # 创建数据目录
            self._create_data_directories()
            
            self.is_initialized = True
            logger.info("历史数据获取器初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"历史数据获取器初始化失败: {e}", exc_info=True)
            return False
    
    async def _create_exchange(self):
        """创建ccxt交易所实例"""
        try:
            # 强制使用主网进行测试，避免testnet 404错误
            environment = 'mainnet'
            # environment = self.config['binance']['environment']
            
            if environment == 'testnet':
                exchange_class = ccxt.binance
                exchange_config = {
                    'apiKey': self.config['binance'].get('api_key', ''),
                    'secret': self.config['binance'].get('secret_key', ''),
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot',
                        'adjustForTimeDifference': True
                    },
                    'urls': {
                        'api': {
                            'public': 'https://testnet.binance.vision/api',
                            'private': 'https://testnet.binance.vision/api'
                        }
                    }
                }
            else:
                exchange_class = ccxt.binance
                exchange_config = {
                    'apiKey': self.config['binance'].get('api_key', ''),
                    'secret': self.config['binance'].get('secret_key', ''),
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot',
                        'adjustForTimeDifference': True
                    }
                }
            
            # 创建交易所实例
            self.exchange = exchange_class(exchange_config)
            
            # 设置请求超时和重试
            self.exchange.timeout = 30000  # 30秒超时
            self.exchange.rateLimit = 1000  # 请求间隔（毫秒）
            
            logger.info(f"ccxt交易所实例创建成功，环境: {environment}")
            
        except Exception as e:
            logger.error(f"创建ccxt交易所实例失败: {e}")
            raise
    
    async def _load_markets(self):
        """加载市场信息"""
        try:
            if not self.exchange:
                raise RuntimeError("交易所实例未创建")
            
            logger.info("加载市场信息...")
            
            # 加载市场
            markets = await self.exchange.load_markets()
            
            # 记录支持的交易对数量
            spot_markets = [symbol for symbol, market in markets.items() 
                          if market.get('spot', False) and market.get('active', False)]
            
            logger.info(f"市场信息加载完成，共 {len(spot_markets)} 个活跃现货交易对")
            
            # 验证配置中的交易对是否支持
            symbols = self.config['data']['symbols']
            for symbol in symbols:
                if symbol not in markets:
                    logger.warning(f"交易对 {symbol} 不在支持列表中")
                elif not markets[symbol].get('active', False):
                    logger.warning(f"交易对 {symbol} 不活跃")
                else:
                    logger.debug(f"交易对 {symbol} 验证通过")
            
        except Exception as e:
            logger.error(f"加载市场信息失败: {e}")
            # 不抛出异常，允许继续运行
    
    def _create_data_directories(self):
        """创建数据目录"""
        try:
            data_dir = Path("data/historical")
            data_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建子目录
            for format_type in ['parquet', 'csv', 'cache']:
                (data_dir / format_type).mkdir(parents=True, exist_ok=True)
            
            logger.info(f"数据目录创建完成: {data_dir}")
            
        except Exception as e:
            logger.error(f"创建数据目录失败: {e}")
    
    @retry_with_backoff_async
    async def fetch_klines(self, symbol: str, interval: str = '1m', 
                          days: int = 30, limit: Optional[int] = None) -> List[Dict]:
        """
        获取历史K线数据
        
        Args:
            symbol: 交易对
            interval: K线间隔
            days: 获取天数
            limit: 每次请求限制数量，None使用配置默认值
            
        Returns:
            List[Dict]: K线数据列表
        """
        try:
            self.fetch_stats['total_requests'] += 1
            
            if not self.exchange:
                raise RuntimeError("交易所实例未初始化")
            
            # 计算时间范围
            end_time = int(time.time() * 1000)  # 毫秒时间戳
            start_time = end_time - (days * 24 * 60 * 60 * 1000)
            
            # 设置每次请求限制
            if limit is None:
                limit = self.hist_config['limit_per_request']
            
            all_klines = []
            current_start = start_time
            
            logger.info(f"开始获取 {symbol} {interval} 历史数据，时间范围: {days}天")
            
            # 分批获取数据
            while current_start < end_time:
                try:
                    # 计算本次请求的结束时间
                    current_end = min(current_start + (limit * self._interval_to_ms(interval)), end_time)
                    
                    # 如果时间范围太小，跳出循环
                    if current_end <= current_start:
                        break
                    
                    logger.debug(f"获取 {symbol} {interval} 数据: "
                                f"{self._timestamp_to_str(current_start)} - {self._timestamp_to_str(current_end)}")
                    
                    # 调用ccxt API
                    klines = await self.exchange.fetch_ohlcv(
                        symbol=symbol,
                        timeframe=interval,
                        since=current_start,
                        limit=limit,
                        params={}
                    )
                    
                    if not klines:
                        logger.debug(f"未获取到数据，可能已达时间范围终点")
                        break
                    
                    # 转换数据格式
                    formatted_klines = self._format_klines(klines, symbol, interval)
                    all_klines.extend(formatted_klines)
                    
                    # 更新统计
                    self.fetch_stats['successful_requests'] += 1
                    self.fetch_stats['total_kline_count'] += len(formatted_klines)
                    
                    # 更新起始时间（最后一条K线的收盘时间+1毫秒）
                    last_kline_time = klines[-1][0]
                    current_start = last_kline_time + 1
                    
                    # 遵守API速率限制
                    await asyncio.sleep(self.exchange.rateLimit / 1000)
                    
                except ccxt.NetworkError as e:
                    logger.warning(f"网络错误获取 {symbol} 数据: {e}")
                    await asyncio.sleep(5)  # 网络错误等待5秒
                    continue
                except ccxt.ExchangeError as e:
                    logger.error(f"交易所错误获取 {symbol} 数据: {e}")
                    break
                except Exception as e:
                    logger.error(f"获取 {symbol} 数据异常: {e}", exc_info=True)
                    break
            
            # 按时间排序（确保顺序正确）
            all_klines.sort(key=lambda x: x['timestamp'])
            
            logger.info(f"{symbol} {interval} 历史数据获取完成: {len(all_klines)} 条记录")
            
            # 缓存数据
            self._cache_data(symbol, interval, all_klines)
            
            # 保存到文件
            await self._save_to_file(symbol, interval, all_klines)
            
            return all_klines
            
        except Exception as e:
            self.fetch_stats['failed_requests'] += 1
            logger.error(f"获取 {symbol} {interval} 历史数据失败: {e}", exc_info=True)
            return []
    
    def _format_klines(self, klines: List[List], symbol: str, interval: str) -> List[Dict]:
        """
        格式化K线数据
        
        Args:
            klines: 原始K线数据
            symbol: 交易对
            interval: K线间隔
            
        Returns:
            List[Dict]: 格式化后的K线数据
        """
        formatted = []
        
        for kline in klines:
            formatted_kline = {
                'symbol': symbol,
                'interval': interval,
                'timestamp': kline[0],  # 开盘时间
                'open': float(kline[1]),
                'high': float(kline[2]),
                'low': float(kline[3]),
                'close': float(kline[4]),
                'volume': float(kline[5]),
                'close_time': kline[6] if len(kline) > 6 else None,
                'quote_volume': float(kline[7]) if len(kline) > 7 else None,
                'trades': kline[8] if len(kline) > 8 else None,
                'taker_buy_base': float(kline[9]) if len(kline) > 9 else None,
                'taker_buy_quote': float(kline[10]) if len(kline) > 10 else None,
                'ignore': kline[11] if len(kline) > 11 else None
            }
            formatted.append(formatted_kline)
        
        return formatted
    
    def _cache_data(self, symbol: str, interval: str, data: List[Dict]):
        """缓存数据"""
        cache_key = f"{symbol}_{interval}"
        
        if symbol not in self.data_cache:
            self.data_cache[symbol] = {}
        
        # 限制缓存大小
        cache_size = self.hist_config.get('cache_size', 1000)
        if len(data) > cache_size:
            data = data[-cache_size:]
        
        self.data_cache[symbol][interval] = data
        logger.debug(f"数据已缓存: {symbol} {interval}, {len(data)} 条记录")
    
    async def _save_to_file(self, symbol: str, interval: str, data: List[Dict]):
        """保存数据到文件"""
        try:
            if not data:
                return
            
            # 创建DataFrame
            df = pd.DataFrame(data)
            
            # 确定存储格式
            storage_format = self.hist_config.get('storage_format', 'parquet')
            
            # 文件名
            filename = f"{symbol}_{interval}_{int(time.time())}"
            
            if storage_format == 'parquet':
                filepath = Path(f"data/historical/parquet/{filename}.parquet")
                df.to_parquet(filepath, index=False, compression='snappy')
            else:
                filepath = Path(f"data/historical/csv/{filename}.csv")
                df.to_csv(filepath, index=False)
            
            logger.debug(f"数据已保存到文件: {filepath}")
            
        except Exception as e:
            logger.error(f"保存数据到文件失败: {e}")
    
    async def load_from_cache(self, symbol: str, interval: str) -> Optional[List[Dict]]:
        """
        从缓存加载数据
        
        Args:
            symbol: 交易对
            interval: K线间隔
            
        Returns:
            Optional[List[Dict]]: 缓存数据，不存在返回None
        """
        if symbol in self.data_cache and interval in self.data_cache[symbol]:
            data = self.data_cache[symbol][interval]
            logger.debug(f"从缓存加载数据: {symbol} {interval}, {len(data)} 条记录")
            return data
        
        # 尝试从文件加载
        return await self.load_from_file(symbol, interval)
    
    async def load_from_file(self, symbol: str, interval: str) -> Optional[List[Dict]]:
        """
        从文件加载数据
        
        Args:
            symbol: 交易对
            interval: K线间隔
            
        Returns:
            Optional[List[Dict]]: 文件数据，不存在返回None
        """
        try:
            storage_format = self.hist_config.get('storage_format', 'parquet')
            
            # 查找最新的数据文件
            if storage_format == 'parquet':
                data_dir = Path("data/historical/parquet")
                pattern = f"{symbol}_{interval}_*.parquet"
            else:
                data_dir = Path("data/historical/csv")
                pattern = f"{symbol}_{interval}_*.csv"
            
            files = list(data_dir.glob(pattern))
            if not files:
                return None
            
            # 选择最新的文件
            latest_file = max(files, key=lambda f: f.stat().st_mtime)
            
            # 读取文件
            if storage_format == 'parquet':
                df = pd.read_parquet(latest_file)
            else:
                df = pd.read_csv(latest_file)
            
            # 转换为字典列表
            data = df.to_dict('records')
            
            # 缓存数据
            self._cache_data(symbol, interval, data)
            
            logger.info(f"从文件加载数据: {latest_file}, {len(data)} 条记录")
            return data
            
        except Exception as e:
            logger.error(f"从文件加载数据失败: {e}")
            return None
    
    def _interval_to_ms(self, interval: str) -> int:
        """将K线间隔转换为毫秒数"""
        interval_map = {
            '1s': 1000,
            '1m': 60 * 1000,
            '3m': 3 * 60 * 1000,
            '5m': 5 * 60 * 1000,
            '15m': 15 * 60 * 1000,
            '30m': 30 * 60 * 1000,
            '1h': 60 * 60 * 1000,
            '2h': 2 * 60 * 60 * 1000,
            '4h': 4 * 60 * 60 * 1000,
            '6h': 6 * 60 * 60 * 1000,
            '8h': 8 * 60 * 60 * 1000,
            '12h': 12 * 60 * 60 * 1000,
            '1d': 24 * 60 * 60 * 1000,
            '3d': 3 * 24 * 60 * 60 * 1000,
            '1w': 7 * 24 * 60 * 60 * 1000,
            '1M': 30 * 24 * 60 * 60 * 1000  # 近似值
        }
        
        return interval_map.get(interval, 60 * 1000)  # 默认1分钟
    
    def _timestamp_to_str(self, timestamp_ms: int) -> str:
        """将时间戳转换为字符串"""
        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    
    async def close(self):
        """关闭资源"""
        try:
            if self.exchange:
                await self.exchange.close()
                logger.info("ccxt交易所连接已关闭")
            
            self.is_initialized = False
            
        except Exception as e:
            logger.error(f"关闭历史数据获取器失败: {e}")
    
    async def fetch_historical_data(self, symbol: str, interval: str = '1m', 
                                   days: int = 30, limit: Optional[int] = None) -> List[Dict]:
        """
        获取历史数据（fetch_klines的别名）
        
        Args:
            symbol: 交易对
            interval: K线间隔
            days: 获取天数
            limit: 每次请求限制数量，None使用配置默认值
            
        Returns:
            List[Dict]: K线数据列表
        """
        return await self.fetch_klines(symbol, interval, days, limit)
    
    def get_data(self, symbol: str, interval: str = '1m') -> Optional[List[Dict]]:
        """
        获取数据（优先从缓存）
        
        Args:
            symbol: 交易对
            interval: K线间隔
            
        Returns:
            Optional[List[Dict]]: 数据，不存在返回None
        """
        if symbol in self.data_cache and interval in self.data_cache[symbol]:
            return self.data_cache[symbol][interval]
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取状态信息
        
        Returns:
            Dict[str, Any]: 状态信息
        """
        return {
            'is_initialized': self.is_initialized,
            'data_cache': {
                'symbols': list(self.data_cache.keys()),
                'total_intervals': sum(len(v) for v in self.data_cache.values())
            },
            'fetch_stats': self.fetch_stats,
            'last_fetch_time': self.last_fetch_time
        }
    
    def __del__(self):
        """析构函数"""
        if self.exchange and self.is_initialized:
            asyncio.create_task(self.close())