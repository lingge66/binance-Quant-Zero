#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
币安WebSocket客户端
实现实时数据订阅、断线重连、数据解析等功能
"""
import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Callable
import websockets
from websockets.client import WebSocketClientProtocol

from ..utils.exponential_backoff import ExponentialBackoff


logger = logging.getLogger(__name__)


class BinanceWebSocketClient:
    """币安WebSocket客户端"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化WebSocket客户端
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.ws_config = config['data']['websocket']
        
        # WebSocket连接
        self.ws: Optional[WebSocketClientProtocol] = None
        self.ws_url: str = ""
        
        # 连接状态
        self.is_connected = False
        self.is_running = False
        self.reconnect_attempts = 0
        self.last_heartbeat = 0
        
        # 退避重连器
        self.backoff = ExponentialBackoff(
            base_delay=self.ws_config['reconnect_base_delay'],
            max_delay=self.ws_config['max_reconnect_delay'],
            max_attempts=self.ws_config['max_reconnect_attempts']
        )
        
        # 数据回调函数
        self.data_callbacks: Dict[str, List[Callable]] = {
            'kline': [],
            'depth': [],
            'trade': [],
            'ticker': [],
            'error': []
        }
        
        # 订阅列表
        self.subscriptions: List[str] = []
        
        # 数据缓存
        self.data_cache: Dict[str, Dict] = {}
        
    async def initialize(self):
        """初始化WebSocket客户端"""
        try:
            # 确定WebSocket URL
            environment = self.config['binance']['environment']
            self.ws_url = self.config['binance']['ws_urls'][environment]
            
            # 构建订阅列表
            symbols = self.config['data']['symbols']
            self._build_subscriptions(symbols)
            
            # 初始化数据缓存
            for symbol in symbols:
                self.data_cache[symbol] = {
                    'kline': {},
                    'depth': {},
                    'trade': {},
                    'ticker': {},
                    'last_update': 0
                }
            
            logger.info(f"WebSocket客户端初始化完成，环境: {environment}")
            logger.info(f"订阅 {len(self.subscriptions)} 个数据流")
            
        except Exception as e:
            logger.error(f"WebSocket客户端初始化失败: {e}", exc_info=True)
            raise
    
    def _build_subscriptions(self, symbols: List[str]):
        """构建订阅列表"""
        self.subscriptions = []
        
        # K线数据
        intervals = self.config['data']['intervals']
        for symbol in symbols:
            for interval in intervals:
                stream = f"{symbol.lower()}@kline_{interval}"
                self.subscriptions.append(stream)
        
        # 深度数据 (可选)
        # for symbol in symbols:
        #     stream = f"{symbol.lower()}@depth20"
        #     self.subscriptions.append(stream)
        
        # 成交数据 (可选)
        # for symbol in symbols:
        #     stream = f"{symbol.lower()}@trade"
        #     self.subscriptions.append(stream)
        
        # 24hr ticker (可选)
        # for symbol in symbols:
        #     stream = f"{symbol.lower()}@ticker"
        #     self.subscriptions.append(stream)
    
    async def connect(self) -> bool:
        """
        连接WebSocket服务器
        
        Returns:
            bool: 连接是否成功
        """
        try:
            logger.info(f"连接WebSocket服务器: {self.ws_url}")
            
            # 创建连接
            self.ws = await websockets.connect(
                self.ws_url,
                ping_interval=self.ws_config.get('heartbeat_interval', 30),
                ping_timeout=self.ws_config.get('connect_timeout', 10),
                close_timeout=5
            )
            
            self.is_connected = True
            self.reconnect_attempts = 0
            self.last_heartbeat = time.time()
            self.backoff.reset()
            
            logger.info("WebSocket连接成功")
            return True
            
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            self.is_connected = False
            return False
    
    async def subscribe(self) -> bool:
        """
        订阅数据流
        
        Returns:
            bool: 订阅是否成功
        """
        try:
            if not self.ws or not self.is_connected:
                logger.error("WebSocket未连接，无法订阅")
                return False
            
            # 批量订阅（币安支持批量订阅）
            batch_size = 100  # 币安批量订阅限制
            for i in range(0, len(self.subscriptions), batch_size):
                batch = self.subscriptions[i:i + batch_size]
                
                # 构建订阅消息
                subscribe_msg = {
                    "method": "SUBSCRIBE",
                    "params": batch,
                    "id": int(time.time() * 1000)
                }
                
                await self.ws.send(json.dumps(subscribe_msg))
                logger.info(f"订阅数据流: {len(batch)}个")
                
                # 等待响应
                response = await asyncio.wait_for(self.ws.recv(), timeout=5)
                response_data = json.loads(response)
                
                if 'result' in response_data:
                    logger.info(f"订阅成功: {response_data.get('result')}")
                else:
                    logger.warning(f"订阅响应: {response_data}")
            
            logger.info(f"全部订阅完成，共 {len(self.subscriptions)} 个数据流")
            return True
            
        except asyncio.TimeoutError:
            logger.error("订阅超时")
            return False
        except Exception as e:
            logger.error(f"订阅失败: {e}", exc_info=True)
            return False
    
    async def start(self):
        """启动WebSocket客户端"""
        try:
            self.is_running = True
            
            # 连接和订阅
            while self.is_running:
                if await self._connect_and_subscribe():
                    # 连接成功，开始接收数据
                    await self._receive_loop()
                else:
                    # 连接失败，等待重试
                    if self.is_running:
                        await self._handle_reconnect()
            
        except Exception as e:
            logger.error(f"WebSocket客户端启动失败: {e}", exc_info=True)
            self.is_running = False
    
    async def _connect_and_subscribe(self) -> bool:
        """连接并订阅"""
        if not await self.connect():
            return False
        
        if not await self.subscribe():
            # 订阅失败，关闭连接
            await self.close()
            return False
        
        return True
    
    async def _receive_loop(self):
        """接收数据循环"""
        try:
            logger.info("开始接收WebSocket数据...")
            
            while self.is_connected and self.is_running and self.ws:
                try:
                    # 接收数据
                    message = await asyncio.wait_for(
                        self.ws.recv(),
                        timeout=self.ws_config.get('heartbeat_interval', 30) + 5
                    )
                    
                    # 更新心跳时间
                    self.last_heartbeat = time.time()
                    
                    # 处理消息
                    await self._process_message(message)
                    
                except asyncio.TimeoutError:
                    # 心跳超时，发送ping
                    await self._send_heartbeat()
                except websockets.exceptions.ConnectionClosed as e:
                    logger.warning(f"WebSocket连接关闭: {e}")
                    self.is_connected = False
                    break
                except Exception as e:
                    logger.error(f"接收数据异常: {e}", exc_info=True)
                    # 继续循环，不断开连接
        
        except Exception as e:
            logger.error(f"接收数据循环异常: {e}", exc_info=True)
        finally:
            if self.is_connected:
                await self.close()
    
    async def _process_message(self, message: str):
        """处理接收到的消息"""
        try:
            data = json.loads(message)
            
            # 处理不同的消息类型
            if 'e' in data:  # 事件类型
                event_type = data['e']
                
                if event_type == 'kline':
                    await self._handle_kline(data)
                elif event_type == 'depthUpdate':
                    await self._handle_depth(data)
                elif event_type == 'trade':
                    await self._handle_trade(data)
                elif event_type == '24hrTicker':
                    await self._handle_ticker(data)
                else:
                    logger.debug(f"未知事件类型: {event_type}")
            
            # 处理订阅响应
            elif 'id' in data and 'result' in data:
                logger.debug(f"订阅响应: {data}")
            
            # 处理错误
            elif 'error' in data:
                logger.error(f"WebSocket错误: {data}")
                await self._notify_callbacks('error', data)
            
            else:
                logger.debug(f"未知消息格式: {data}")
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}, 消息: {message[:100]}")
        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)
    
    async def _handle_kline(self, data: Dict):
        """处理K线数据"""
        try:
            symbol = data['s']  # 交易对
            kline = data['k']
            
            kline_data = {
                'symbol': symbol,
                'interval': kline['i'],
                'open_time': kline['t'],
                'close_time': kline['T'],
                'open': float(kline['o']),
                'high': float(kline['h']),
                'low': float(kline['l']),
                'close': float(kline['c']),
                'volume': float(kline['v']),
                'quote_volume': float(kline['q']),
                'trades': kline['n'],
                'is_closed': kline['x']
            }
            
            # 更新缓存
            self.data_cache[symbol]['kline'] = kline_data
            self.data_cache[symbol]['last_update'] = time.time()
            
            # 通知回调
            await self._notify_callbacks('kline', kline_data)
            
            # 日志（频率控制）
            if kline_data['is_closed']:
                logger.debug(f"K线闭合: {symbol} {kline_data['interval']} "
                           f"收盘价: {kline_data['close']}")
                
        except Exception as e:
            logger.error(f"处理K线数据失败: {e}", exc_info=True)
    
    async def _handle_depth(self, data: Dict):
        """处理深度数据"""
        try:
            symbol = data['s']
            
            depth_data = {
                'symbol': symbol,
                'event_time': data['E'],
                'first_update_id': data['U'],
                'final_update_id': data['u'],
                'bids': [[float(p), float(q)] for p, q in data['b']],
                'asks': [[float(p), float(q)] for p, q in data['a']]
            }
            
            # 更新缓存
            self.data_cache[symbol]['depth'] = depth_data
            self.data_cache[symbol]['last_update'] = time.time()
            
            # 通知回调
            await self._notify_callbacks('depth', depth_data)
            
        except Exception as e:
            logger.error(f"处理深度数据失败: {e}", exc_info=True)
    
    async def _handle_trade(self, data: Dict):
        """处理成交数据"""
        try:
            symbol = data['s']
            
            trade_data = {
                'symbol': symbol,
                'trade_id': data['t'],
                'price': float(data['p']),
                'quantity': float(data['q']),
                'buyer_order_id': data['b'],
                'seller_order_id': data['a'],
                'trade_time': data['T'],
                'is_buyer_maker': data['m']
            }
            
            # 更新缓存
            self.data_cache[symbol]['trade'] = trade_data
            self.data_cache[symbol]['last_update'] = time.time()
            
            # 通知回调
            await self._notify_callbacks('trade', trade_data)
            
        except Exception as e:
            logger.error(f"处理成交数据失败: {e}", exc_info=True)
    
    async def _handle_ticker(self, data: Dict):
        """处理Ticker数据"""
        try:
            symbol = data['s']
            
            ticker_data = {
                'symbol': symbol,
                'price_change': float(data['p']),
                'price_change_percent': float(data['P']),
                'weighted_avg_price': float(data['w']),
                'prev_close_price': float(data['x']),
                'last_price': float(data['c']),
                'last_quantity': float(data['Q']),
                'bid_price': float(data['b']),
                'bid_quantity': float(data['B']),
                'ask_price': float(data['a']),
                'ask_quantity': float(data['A']),
                'open_price': float(data['o']),
                'high_price': float(data['h']),
                'low_price': float(data['l']),
                'volume': float(data['v']),
                'quote_volume': float(data['q']),
                'open_time': data['O'],
                'close_time': data['C'],
                'first_trade_id': data['F'],
                'last_trade_id': data['L'],
                'total_trades': data['n']
            }
            
            # 更新缓存
            self.data_cache[symbol]['ticker'] = ticker_data
            self.data_cache[symbol]['last_update'] = time.time()
            
            # 通知回调
            await self._notify_callbacks('ticker', ticker_data)
            
        except Exception as e:
            logger.error(f"处理Ticker数据失败: {e}", exc_info=True)
    
    async def _send_heartbeat(self):
        """发送心跳"""
        try:
            if self.ws and self.is_connected:
                # WebSocket库会自动发送ping，这里只需要检查超时
                current_time = time.time()
                if current_time - self.last_heartbeat > self.ws_config.get('heartbeat_interval', 30) * 2:
                    logger.warning("心跳超时，连接可能已断开")
                    self.is_connected = False
                    
        except Exception as e:
            logger.error(f"发送心跳失败: {e}")
    
    async def _handle_reconnect(self):
        """处理重连"""
        if not self.is_running:
            return
        
        self.reconnect_attempts += 1
        
        # 计算等待时间
        wait_time = self.backoff.next_delay()
        logger.warning(f"WebSocket连接断开，第 {self.reconnect_attempts} 次重试，等待 {wait_time:.1f} 秒")
        
        # 等待
        await asyncio.sleep(wait_time)
    
    async def close(self):
        """关闭WebSocket连接"""
        try:
            if self.ws:
                await self.ws.close()
                self.ws = None
            
            self.is_connected = False
            logger.info("WebSocket连接已关闭")
            
        except Exception as e:
            logger.error(f"关闭WebSocket连接失败: {e}")
    
    async def stop(self):
        """停止WebSocket客户端"""
        self.is_running = False
        await self.close()
        logger.info("WebSocket客户端已停止")
    
    def register_callback(self, data_type: str, callback: Callable):
        """
        注册数据回调函数
        
        Args:
            data_type: 数据类型 (kline, depth, trade, ticker, error)
            callback: 回调函数，接收一个字典参数
        """
        if data_type in self.data_callbacks:
            self.data_callbacks[data_type].append(callback)
            logger.debug(f"注册 {data_type} 回调函数")
        else:
            logger.warning(f"未知数据类型: {data_type}")
    
    async def _notify_callbacks(self, data_type: str, data: Dict):
        """通知回调函数"""
        if data_type not in self.data_callbacks:
            return
        
        for callback in self.data_callbacks[data_type]:
            try:
                await callback(data) if asyncio.iscoroutinefunction(callback) else callback(data)
            except Exception as e:
                logger.error(f"回调函数执行失败: {e}", exc_info=True)
    
    def get_data(self, symbol: str, data_type: str = 'kline') -> Optional[Dict]:
        """
        获取缓存数据
        
        Args:
            symbol: 交易对
            data_type: 数据类型
            
        Returns:
            Optional[Dict]: 缓存数据
        """
        if symbol in self.data_cache:
            return self.data_cache[symbol].get(data_type)
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取状态信息
        
        Returns:
            Dict[str, Any]: 状态信息
        """
        return {
            'is_connected': self.is_connected,
            'is_running': self.is_running,
            'reconnect_attempts': self.reconnect_attempts,
            'subscriptions_count': len(self.subscriptions),
            'last_heartbeat': self.last_heartbeat,
            'data_cache_size': len(self.data_cache),
            'callbacks_count': {k: len(v) for k, v in self.data_callbacks.items()}
        }
    
    def __del__(self):
        """析构函数"""
        if self.is_running:
            asyncio.create_task(self.stop())