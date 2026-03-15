"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信号处理器主类
整合技术指标计算和信号生成，提供统一接口
"""
import asyncio
import logging
import time
from typing import List, Dict, Optional, Tuple, Union, Any
import pandas as pd

from .indicators import TechnicalIndicators
from .signal_generator import SignalGenerator, Signal, SignalType

logger = logging.getLogger(__name__)


class SignalProcessor:
    """信号处理器"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化信号处理器
        
        Args:
            config: 配置文件
        """
        self.config = config or {}
        self.indicators_calculator = TechnicalIndicators()
        self.signal_generator = SignalGenerator(config)
        
        # 缓存
        self.indicators_cache: Dict[str, Dict[str, List[Dict]]] = {}
        self.signals_cache: Dict[str, List[Signal]] = {}
        
        # 状态
        self.is_initialized = False
        self.last_process_time = 0
        
        # 性能统计
        self.process_stats = {
            'total_processes': 0,
            'successful_processes': 0,
            'failed_processes': 0,
            'average_process_time': 0,
            'total_signals_generated': 0
        }
        
        logger.info("信号处理器初始化完成")
    
    async def initialize(self) -> bool:
        """
        初始化信号处理器
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            # 检查配置
            if not self.config:
                logger.warning("信号处理器配置为空，使用默认配置")
            
            self.is_initialized = True
            logger.info("信号处理器初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"信号处理器初始化失败: {e}")
            return False
    
    async def process_symbol(self, 
                           symbol: str,
                           data: List[Dict],
                           intervals: Optional[List[str]] = None,
                           generate_signals: bool = True) -> Dict[str, Any]:
        """
        处理单个交易对的数据
        
        Args:
            symbol: 交易对
            data: K线数据
            intervals: 时间间隔列表，None表示使用所有数据
            generate_signals: 是否生成信号
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        start_time = time.time()
        
        try:
            self.process_stats['total_processes'] += 1
            
            if not data:
                logger.warning(f"{symbol}: 数据为空")
                self.process_stats['failed_processes'] += 1
                return {'success': False, 'error': '数据为空'}
            
            # 验证数据
            if not self.indicators_calculator.validate_data_for_indicators(data):
                logger.warning(f"{symbol}: 数据验证失败")
                self.process_stats['failed_processes'] += 1
                return {'success': False, 'error': '数据验证失败'}
            
            # 如果指定了时间间隔，按间隔分组处理
            if intervals:
                results = {}
                for interval in intervals:
                    # 按间隔过滤数据（实际应用中可能需要从数据采集层获取不同间隔的数据）
                    # 这里假设数据已经是特定间隔的
                    interval_data = [d for d in data if d.get('interval') == interval]
                    
                    if interval_data:
                        result = await self._process_single_interval(
                            symbol, interval_data, interval, generate_signals
                        )
                        results[interval] = result
                    else:
                        results[interval] = {'success': False, 'error': f'无{interval}间隔数据'}
                
                # 综合多时间框架信号
                if generate_signals and len(results) > 1:
                    combined_signals = self._combine_multi_timeframe_signals(results, symbol)
                    results['combined_signals'] = combined_signals
                
                process_result = {
                    'success': True,
                    'symbol': symbol,
                    'results': results,
                    'processing_time': time.time() - start_time
                }
                
            else:
                # 单时间框架处理
                process_result = await self._process_single_interval(
                    symbol, data, data[0].get('interval', 'unknown'), generate_signals
                )
            
            self.process_stats['successful_processes'] += 1
            
            # 更新平均处理时间
            process_time = time.time() - start_time
            total_processes = self.process_stats['successful_processes'] + self.process_stats['failed_processes']
            self.process_stats['average_process_time'] = (
                (self.process_stats['average_process_time'] * (total_processes - 1) + process_time) / total_processes
            )
            
            logger.info(f"{symbol}: 信号处理完成，耗时: {process_time:.2f}秒")
            return process_result
            
        except Exception as e:
            self.process_stats['failed_processes'] += 1
            logger.error(f"{symbol}: 信号处理失败: {e}", exc_info=True)
            return {'success': False, 'error': str(e), 'processing_time': time.time() - start_time}
    
    async def _process_single_interval(self,
                                     symbol: str,
                                     data: List[Dict],
                                     interval: str,
                                     generate_signals: bool) -> Dict[str, Any]:
        """处理单个时间间隔的数据"""
        try:
            # 计算技术指标
            indicators_start = time.time()
            data_with_indicators = self.indicators_calculator.calculate_all_indicators(data)
            indicators_time = time.time() - indicators_start
            
            if not data_with_indicators:
                return {'success': False, 'error': '技术指标计算失败'}
            
            # 缓存指标数据
            cache_key = f"{symbol}_{interval}"
            if symbol not in self.indicators_cache:
                self.indicators_cache[symbol] = {}
            self.indicators_cache[symbol][interval] = data_with_indicators
            
            # 生成信号
            signals = []
            if generate_signals:
                signals_start = time.time()
                signals = self.signal_generator.generate_signals(data_with_indicators, symbol)
                signals_time = time.time() - signals_start
                
                if signals:
                    # 缓存信号
                    if symbol not in self.signals_cache:
                        self.signals_cache[symbol] = []
                    self.signals_cache[symbol].extend(signals)
                    
                    # 限制缓存大小（保留最近100个信号）
                    if len(self.signals_cache[symbol]) > 100:
                        self.signals_cache[symbol] = self.signals_cache[symbol][-100:]
                    
                    self.process_stats['total_signals_generated'] += len(signals)
            
            # 获取指标摘要
            indicators_summary = self.indicators_calculator.get_indicator_summary(data_with_indicators)
            
            # 获取信号摘要
            signals_summary = self.signal_generator.generate_signal_summary(signals) if signals else {}
            
            return {
                'success': True,
                'symbol': symbol,
                'interval': interval,
                'data_count': len(data),
                'indicators_count': len(data_with_indicators[0]) if data_with_indicators else 0,
                'indicators_summary': indicators_summary,
                'signals': [signal.to_dict() for signal in signals],
                'signals_summary': signals_summary,
                'processing_times': {
                    'indicators': indicators_time,
                    'signals': signals_time if generate_signals else 0,
                    'total': time.time() - indicators_start
                }
            }
            
        except Exception as e:
            logger.error(f"{symbol} {interval}: 单间隔处理失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _combine_multi_timeframe_signals(self, 
                                       results: Dict[str, Dict[str, Any]], 
                                       symbol: str) -> Dict[str, Any]:
        """综合多时间框架信号"""
        try:
            # 收集所有时间框架的信号
            all_signals = []
            timeframe_weights = {
                '1m': 0.15,   # 1分钟权重最低
                '5m': 0.20,
                '15m': 0.25,
                '1h': 0.30,   # 1小时权重最高
                '4h': 0.25,
                '1d': 0.20
            }
            
            for interval, result in results.items():
                if result.get('success') and 'signals' in result and result['signals']:
                    # 获取最新信号
                    signals_data = result['signals']
                    if signals_data:
                        latest_signal_data = signals_data[-1]
                        
                        # 转换为Signal对象（简化处理）
                        weight = timeframe_weights.get(interval, 0.15)
                        signal_value = latest_signal_data.get('signal_type_value', 0)
                        
                        all_signals.append({
                            'interval': interval,
                            'signal_value': signal_value,
                            'weight': weight,
                            'confidence': latest_signal_data.get('confidence', 0.5)
                        })
            
            if not all_signals:
                return {'success': False, 'error': '无有效信号'}
            
            # 加权计算综合信号
            weighted_sum = 0.0
            total_weight = 0.0
            weighted_confidence = 0.0
            
            for signal_info in all_signals:
                weighted_sum += signal_info['signal_value'] * signal_info['weight']
                total_weight += signal_info['weight']
                weighted_confidence += signal_info['confidence'] * signal_info['weight']
            
            if total_weight > 0:
                combined_value = weighted_sum / total_weight
                combined_confidence = weighted_confidence / total_weight
            else:
                combined_value = 0
                combined_confidence = 0
            
            # 根据综合值确定信号类型
            if combined_value >= 3.5:
                signal_type = "STRONG_BUY"
            elif combined_value >= 2.5:
                signal_type = "BUY"
            elif combined_value >= 1.5:
                signal_type = "WEAK_BUY"
            elif combined_value <= -3.5:
                signal_type = "STRONG_SELL"
            elif combined_value <= -2.5:
                signal_type = "SELL"
            elif combined_value <= -1.5:
                signal_type = "WEAK_SELL"
            else:
                signal_type = "NEUTRAL"
            
            return {
                'success': True,
                'symbol': symbol,
                'combined_signal': signal_type,
                'combined_value': combined_value,
                'confidence': combined_confidence,
                'timeframe_count': len(all_signals),
                'timeframe_details': all_signals
            }
            
        except Exception as e:
            logger.error(f"{symbol}: 多时间框架信号综合失败: {e}")
            return {'success': False, 'error': str(e)}
    
    async def batch_process(self, 
                          symbols_data: Dict[str, List[Dict]],
                          generate_signals: bool = True) -> Dict[str, Any]:
        """
        批量处理多个交易对
        
        Args:
            symbols_data: 交易对数据字典，key为symbol，value为数据列表
            generate_signals: 是否生成信号
            
        Returns:
            Dict[str, Any]: 批量处理结果
        """
        start_time = time.time()
        
        try:
            if not symbols_data:
                return {'success': False, 'error': '无数据', 'processing_time': 0}
            
            logger.info(f"开始批量处理 {len(symbols_data)} 个交易对")
            
            # 并行处理各个交易对
            tasks = []
            for symbol, data in symbols_data.items():
                task = self.process_symbol(symbol, data, generate_signals=generate_signals)
                tasks.append(task)
            
            # 等待所有任务完成
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            processed_results = {}
            successful_count = 0
            failed_count = 0
            
            for i, (symbol, result) in enumerate(zip(symbols_data.keys(), results)):
                if isinstance(result, Exception):
                    processed_results[symbol] = {'success': False, 'error': str(result)}
                    failed_count += 1
                    logger.error(f"{symbol}: 处理异常: {result}")
                else:
                    processed_results[symbol] = result
                    if result.get('success'):
                        successful_count += 1
                    else:
                        failed_count += 1
            
            processing_time = time.time() - start_time
            
            summary = {
                'success': successful_count > 0,
                'total_symbols': len(symbols_data),
                'successful_symbols': successful_count,
                'failed_symbols': failed_count,
                'processing_time': processing_time,
                'average_time_per_symbol': processing_time / len(symbols_data) if symbols_data else 0,
                'signals_generated': sum(len(r.get('signals', [])) for r in processed_results.values() if isinstance(r, dict))
            }
            
            logger.info(f"批量处理完成: {successful_count}成功/{failed_count}失败, 总耗时: {processing_time:.2f}秒")
            
            return {
                'success': True,
                'summary': summary,
                'results': processed_results
            }
            
        except Exception as e:
            logger.error(f"批量处理失败: {e}", exc_info=True)
            return {'success': False, 'error': str(e), 'processing_time': time.time() - start_time}
    
    def get_cached_indicators(self, symbol: str, interval: Optional[str] = None) -> Optional[List[Dict]]:
        """获取缓存的指标数据"""
        try:
            if symbol in self.indicators_cache:
                if interval:
                    return self.indicators_cache[symbol].get(interval)
                else:
                    # 返回所有间隔
                    all_data = []
                    for interval_data in self.indicators_cache[symbol].values():
                        all_data.extend(interval_data)
                    return all_data
            return None
        except Exception as e:
            logger.error(f"获取缓存指标数据失败: {e}")
            return None
    
    def get_cached_signals(self, symbol: str, limit: int = 10) -> List[Dict]:
        """获取缓存的信号"""
        try:
            if symbol in self.signals_cache:
                signals = self.signals_cache[symbol][-limit:] if limit > 0 else self.signals_cache[symbol]
                return [signal.to_dict() for signal in signals]
            return []
        except Exception as e:
            logger.error(f"获取缓存信号失败: {e}")
            return []
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态信息"""
        return {
            'is_initialized': self.is_initialized,
            'process_stats': self.process_stats,
            'cache_stats': {
                'cached_symbols': len(self.indicators_cache),
                'cached_signals': sum(len(signals) for signals in self.signals_cache.values()),
                'indicators_cache_size': sum(
                    len(data) for symbol_data in self.indicators_cache.values() 
                    for data in symbol_data.values()
                )
            },
            'last_process_time': self.last_process_time,
            'current_time': time.time()
        }
    
    def clear_cache(self, symbol: Optional[str] = None):
        """清空缓存"""
        try:
            if symbol:
                if symbol in self.indicators_cache:
                    del self.indicators_cache[symbol]
                if symbol in self.signals_cache:
                    del self.signals_cache[symbol]
                logger.info(f"已清除{symbol}的缓存")
            else:
                self.indicators_cache.clear()
                self.signals_cache.clear()
                logger.info("已清除所有缓存")
        except Exception as e:
            logger.error(f"清除缓存失败: {e}")
    
    async def close(self):
        """关闭资源"""
        try:
            self.clear_cache()
            self.is_initialized = False
            logger.info("信号处理器资源已关闭")
        except Exception as e:
            logger.error(f"关闭信号处理器失败: {e}")