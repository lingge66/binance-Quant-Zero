#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据采集层主类
负责协调WebSocket实时数据、历史数据获取和数据存储
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any
import yaml
from pathlib import Path

from .websocket_client import BinanceWebSocketClient
from .historical_data import HistoricalDataFetcher
from ..utils.config_loader import ConfigLoader


logger = logging.getLogger(__name__)


class DataCollector:
    """数据采集器主类"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        初始化数据采集器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = None
        self.symbols_config = None
        
        # 组件
        self.ws_client: Optional[BinanceWebSocketClient] = None
        self.historical_fetcher: Optional[HistoricalDataFetcher] = None
        
        # 数据缓存
        self.realtime_data: Dict[str, Dict] = {}
        self.historical_data: Dict[str, Dict] = {}
        
        # 状态
        self.is_running = False
        self.health_status = "stopped"
        
    async def initialize(self) -> bool:
        """
        初始化数据采集器
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            logger.info("初始化数据采集器...")
            
            # 加载配置
            self.config = ConfigLoader.load_config(self.config_path)
            symbols_config_path = Path(self.config_path).parent / "symbols.yaml"
            self.symbols_config = ConfigLoader.load_config(str(symbols_config_path))
            
            # 初始化WebSocket客户端
            self.ws_client = BinanceWebSocketClient(self.config)
            await self.ws_client.initialize()
            
            # 初始化历史数据获取器
            self.historical_fetcher = HistoricalDataFetcher(self.config)
            await self.historical_fetcher.initialize()
            
            # 初始化数据缓存
            symbols = self.config['data']['symbols']
            for symbol in symbols:
                self.realtime_data[symbol] = {
                    'kline': {},
                    'depth': {},
                    'trade': {},
                    'ticker': {},
                    'last_update': None
                }
                
            logger.info("数据采集器初始化完成")
            self.health_status = "initialized"
            return True
            
        except Exception as e:
            logger.error(f"数据采集器初始化失败: {e}", exc_info=True)
            self.health_status = "error"
            return False
    
    async def start(self) -> bool:
        """
        启动数据采集
        
        Returns:
            bool: 启动是否成功
        """
        try:
            if not self.ws_client or not self.historical_fetcher:
                logger.error("数据采集器未初始化")
                return False
                
            logger.info("启动数据采集...")
            
            # 启动WebSocket连接
            await self.ws_client.start()
            
            # 获取历史数据
            await self.fetch_historical_data()
            
            self.is_running = True
            self.health_status = "running"
            logger.info("数据采集启动成功")
            return True
            
        except Exception as e:
            logger.error(f"启动数据采集失败: {e}", exc_info=True)
            self.health_status = "error"
            return False
    
    async def fetch_historical_data(self):
        """获取历史数据"""
        try:
            symbols = self.config['data']['symbols']
            intervals = self.config['data']['intervals']
            days = self.config['data']['historical']['days']
            
            logger.info(f"开始获取历史数据: {len(symbols)}个交易对, {len(intervals)}个周期, {days}天")
            
            for symbol in symbols:
                self.historical_data[symbol] = {}
                for interval in intervals:
                    logger.info(f"获取 {symbol} {interval} 历史数据...")
                    data = await self.historical_fetcher.fetch_klines(
                        symbol=symbol,
                        interval=interval,
                        days=days
                    )
                    self.historical_data[symbol][interval] = data
                    logger.info(f"{symbol} {interval} 历史数据获取完成: {len(data)}条记录")
            
            logger.info("历史数据获取完成")
            
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}", exc_info=True)
    
    async def stop(self):
        """停止数据采集"""
        try:
            logger.info("停止数据采集...")
            
            if self.ws_client:
                await self.ws_client.stop()
                
            self.is_running = False
            self.health_status = "stopped"
            logger.info("数据采集已停止")
            
        except Exception as e:
            logger.error(f"停止数据采集失败: {e}", exc_info=True)
    
    def get_realtime_data(self, symbol: str, data_type: str = 'kline') -> Optional[Dict]:
        """
        获取实时数据
        
        Args:
            symbol: 交易对
            data_type: 数据类型 (kline, depth, trade, ticker)
            
        Returns:
            Optional[Dict]: 实时数据，不存在返回None
        """
        if symbol not in self.realtime_data:
            return None
            
        return self.realtime_data[symbol].get(data_type)
    
    def get_historical_data(self, symbol: str, interval: str = '1m') -> Optional[List[Dict]]:
        """
        获取历史数据
        
        Args:
            symbol: 交易对
            interval: K线间隔
            
        Returns:
            Optional[List[Dict]]: 历史数据，不存在返回None
        """
        if symbol not in self.historical_data:
            return None
            
        return self.historical_data[symbol].get(interval, [])
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        获取健康状态
        
        Returns:
            Dict[str, Any]: 健康状态信息
        """
        ws_status = self.ws_client.get_status() if self.ws_client else {}
        hist_status = self.historical_fetcher.get_status() if self.historical_fetcher else {}
        
        return {
            'collector_status': self.health_status,
            'is_running': self.is_running,
            'websocket': ws_status,
            'historical': hist_status,
            'data_counts': {
                'realtime': len(self.realtime_data),
                'historical_symbols': len(self.historical_data)
            }
        }
    
    async def update_realtime_data(self, symbol: str, data_type: str, data: Dict):
        """
        更新实时数据（由WebSocket客户端调用）
        
        Args:
            symbol: 交易对
            data_type: 数据类型
            data: 数据内容
        """
        if symbol not in self.realtime_data:
            self.realtime_data[symbol] = {
                'kline': {},
                'depth': {},
                'trade': {},
                'ticker': {},
                'last_update': None
            }
            
        self.realtime_data[symbol][data_type] = data
        self.realtime_data[symbol]['last_update'] = asyncio.get_event_loop().time()
    
    async def run(self):
        """主运行循环"""
        try:
            if not await self.initialize():
                logger.error("数据采集器初始化失败，无法运行")
                return
                
            if not await self.start():
                logger.error("数据采集器启动失败")
                return
                
            logger.info("数据采集器运行中...")
            
            # 主循环
            while self.is_running:
                try:
                    # 健康检查
                    await self.health_check()
                    
                    # 数据质量检查
                    await self.data_quality_check()
                    
                    # 等待下次循环
                    await asyncio.sleep(self.config['system']['main_loop_interval'])
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"数据采集器主循环异常: {e}", exc_info=True)
                    await asyncio.sleep(5)  # 异常后等待5秒
                    
        except Exception as e:
            logger.error(f"数据采集器运行失败: {e}", exc_info=True)
        finally:
            await self.stop()
    
    async def health_check(self):
        """健康检查"""
        # 检查WebSocket连接
        if self.ws_client:
            status = self.ws_client.get_status()
            if status.get('status') != 'connected':
                logger.warning(f"WebSocket连接状态异常: {status}")
    
    async def data_quality_check(self):
        """数据质量检查"""
        current_time = asyncio.get_event_loop().time()
        timeout = 60  # 60秒无更新视为超时
        
        for symbol, data in self.realtime_data.items():
            last_update = data.get('last_update')
            if last_update and (current_time - last_update) > timeout:
                logger.warning(f"{symbol} 实时数据超过{timeout}秒未更新")
    
    def __del__(self):
        """析构函数，确保资源释放"""
        if self.is_running:
            asyncio.create_task(self.stop())