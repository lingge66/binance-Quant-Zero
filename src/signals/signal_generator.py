"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信号生成器模块
基于技术指标生成交易信号，支持规则引擎和信号融合
"""
import logging
import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple, Union, Any
from enum import Enum

from .indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型枚举"""
    STRONG_BUY = 5
    BUY = 4
    WEAK_BUY = 3
    NEUTRAL = 2
    WEAK_SELL = 1
    SELL = 0
    STRONG_SELL = -1


class SignalStrength(Enum):
    """信号强度枚举"""
    VERY_STRONG = 4
    STRONG = 3
    MEDIUM = 2
    WEAK = 1
    VERY_WEAK = 0


class Signal:
    """交易信号类"""
    
    def __init__(self, 
                 signal_type: SignalType,
                 strength: SignalStrength,
                 confidence: float,
                 timestamp: int,
                 symbol: str,
                 price: float,
                 indicators: Dict[str, Any],
                 reasoning: str,
                 metadata: Optional[Dict] = None):
        """
        初始化交易信号
        
        Args:
            signal_type: 信号类型
            strength: 信号强度
            confidence: 置信度 (0-1)
            timestamp: 时间戳
            symbol: 交易对
            price: 当前价格
            indicators: 技术指标值
            reasoning: 信号生成理由
            metadata: 元数据
        """
        self.signal_type = signal_type
        self.strength = strength
        self.confidence = max(0.0, min(1.0, confidence))  # 限制在0-1之间
        self.timestamp = timestamp
        self.symbol = symbol
        self.price = price
        self.indicators = indicators or {}
        self.reasoning = reasoning
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'signal_type': self.signal_type.name,
            'signal_type_value': self.signal_type.value,
            'strength': self.strength.name,
            'strength_value': self.strength.value,
            'confidence': self.confidence,
            'timestamp': self.timestamp,
            'symbol': self.symbol,
            'price': self.price,
            'indicators': self.indicators,
            'reasoning': self.reasoning,
            'metadata': self.metadata
        }
    
    def __str__(self) -> str:
        return (f"Signal({self.signal_type.name}, strength={self.strength.name}, "
                f"confidence={self.confidence:.2f}, symbol={self.symbol})")


class SignalGenerator:
    """信号生成器"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化信号生成器
        
        Args:
            config: 配置文件
        """
        self.config = config or {}
        self.indicators_calculator = TechnicalIndicators()
        
        # 信号权重配置
        self.signal_weights = self.config.get('signal_weights', {
            'trend': 0.35,      # 趋势信号权重
            'momentum': 0.30,   # 动量信号权重
            'volatility': 0.20, # 波动率信号权重
            'volume': 0.15      # 成交量信号权重
        })
        
        # 最小置信度阈值
        self.min_confidence = self.config.get('min_confidence', 0.6)
        
        logger.info("信号生成器初始化完成")
    
    def generate_signals(self, 
                        data_with_indicators: List[Dict],
                        symbol: str,
                        lookback_period: int = 20) -> List[Signal]:
        """
        生成交易信号
        
        Args:
            data_with_indicators: 包含技术指标的数据
            symbol: 交易对
            lookback_period: 回看周期
            
        Returns:
            List[Signal]: 生成的交易信号列表
        """
        if not data_with_indicators:
            logger.warning(f"{symbol}: 数据为空，无法生成信号")
            return []
        
        # 验证数据
        if not self.indicators_calculator.validate_data_for_indicators(data_with_indicators):
            logger.warning(f"{symbol}: 数据验证失败")
            return []
        
        try:
            # 转换为DataFrame
            df = pd.DataFrame(data_with_indicators)
            
            # 只分析最近的数据
            if len(df) > lookback_period:
                df = df.tail(lookback_period).copy()
            
            if len(df) < 5:  # 至少需要5条数据
                logger.warning(f"{symbol}: 数据不足，无法分析")
                return []
            
            # 获取最新数据
            latest = df.iloc[-1].to_dict()
            timestamp = latest.get('timestamp', 0)
            price = latest.get('close', 0)
            
            # 分析各个维度的信号
            trend_analysis = self._analyze_trend(df, symbol)
            momentum_analysis = self._analyze_momentum(df, symbol)
            volatility_analysis = self._analyze_volatility(df, symbol)
            volume_analysis = self._analyze_volume(df, symbol)
            
            # 综合信号
            combined_signal = self._combine_signals(
                trend_analysis, momentum_analysis, 
                volatility_analysis, volume_analysis
            )
            
            # 生成最终信号
            signals = self._generate_final_signals(
                combined_signal, timestamp, symbol, price, latest
            )
            
            logger.info(f"{symbol}: 生成 {len(signals)} 个信号，最新信号: {signals[-1] if signals else '无'}")
            return signals
            
        except Exception as e:
            logger.error(f"{symbol}: 生成信号失败: {e}", exc_info=True)
            return []
    
    def _analyze_trend(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """分析趋势信号"""
        try:
            # 获取最新数据
            latest = df.iloc[-1].to_dict()
            
            # 检查移动平均线排列
            ma_signals = []
            
            # 检查MA排列（多头排列：短周期在上，长周期在下）
            if 'ma_5' in df.columns and 'ma_10' in df.columns and 'ma_20' in df.columns:
                ma5 = df['ma_5'].values
                ma10 = df['ma_10'].values
                ma20 = df['ma_20'].values
                
                # 检查最新值的排列
                if ma5[-1] > ma10[-1] > ma20[-1]:
                    ma_signals.append(('ma_bullish_alignment', 0.8, "MA多头排列"))
                elif ma5[-1] < ma10[-1] < ma20[-1]:
                    ma_signals.append(('ma_bearish_alignment', -0.8, "MA空头排列"))
            
            # 检查MA交叉
            if 'ma_cross' in df.columns:
                latest_cross = df['ma_cross'].iloc[-1]
                if latest_cross == 1:
                    ma_signals.append(('ma_golden_cross', 0.7, "MA金叉"))
                elif latest_cross == -1:
                    ma_signals.append(('ma_death_cross', -0.7, "MA死叉"))
            
            # 检查价格与MA的关系
            if 'close' in df.columns and 'ma_20' in df.columns:
                price = df['close'].values
                ma20 = df['ma_20'].values
                
                # 价格在MA20之上还是之下
                if price[-1] > ma20[-1] * 1.02:  # 高于MA20 2%
                    ma_signals.append(('price_above_ma20', 0.6, "价格高于MA20"))
                elif price[-1] < ma20[-1] * 0.98:  # 低于MA20 2%
                    ma_signals.append(('price_below_ma20', -0.6, "价格低于MA20"))
            
            # MACD趋势分析
            macd_signals = []
            if 'macd_cross' in df.columns:
                latest_macd_cross = df['macd_cross'].iloc[-1]
                if latest_macd_cross == 1:
                    macd_signals.append(('macd_golden_cross', 0.6, "MACD金叉"))
                elif latest_macd_cross == -1:
                    macd_signals.append(('macd_death_cross', -0.6, "MACD死叉"))
            
            # MACD柱状图方向
            if 'macd_hist' in df.columns:
                macd_hist = df['macd_hist'].values
                if len(macd_hist) >= 3:
                    # 检查MACD柱状图是否在增长
                    if macd_hist[-1] > macd_hist[-2] > macd_hist[-3]:
                        macd_signals.append(('macd_hist_increasing', 0.4, "MACD柱状图增长"))
                    elif macd_hist[-1] < macd_hist[-2] < macd_hist[-3]:
                        macd_signals.append(('macd_hist_decreasing', -0.4, "MACD柱状图下降"))
            
            # 综合趋势信号
            trend_score = 0.0
            trend_reasons = []
            
            for signal_name, score, reason in ma_signals + macd_signals:
                trend_score += score
                trend_reasons.append(reason)
            
            # 归一化到-1到1之间
            trend_score = max(-1.0, min(1.0, trend_score))
            
            return {
                'score': trend_score,
                'reasons': trend_reasons,
                'signals': ma_signals + macd_signals
            }
            
        except Exception as e:
            logger.error(f"{symbol}: 趋势分析失败: {e}")
            return {'score': 0.0, 'reasons': [], 'signals': []}
    
    def _analyze_momentum(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """分析动量信号"""
        try:
            momentum_signals = []
            
            # RSI分析
            if 'rsi' in df.columns:
                rsi_values = df['rsi'].values
                latest_rsi = rsi_values[-1] if len(rsi_values) > 0 else 50
                
                if latest_rsi < 30:
                    momentum_signals.append(('rsi_oversold', 0.8, f"RSI超卖: {latest_rsi:.1f}"))
                elif latest_rsi > 70:
                    momentum_signals.append(('rsi_overbought', -0.8, f"RSI超买: {latest_rsi:.1f}"))
                elif latest_rsi < 40:
                    momentum_signals.append(('rsi_near_oversold', 0.4, f"RSI接近超卖: {latest_rsi:.1f}"))
                elif latest_rsi > 60:
                    momentum_signals.append(('rsi_near_overbought', -0.4, f"RSI接近超买: {latest_rsi:.1f}"))
            
            # 随机指标分析
            if 'stoch_k' in df.columns and 'stoch_d' in df.columns:
                stoch_k = df['stoch_k'].values
                stoch_d = df['stoch_d'].values
                
                if len(stoch_k) > 0 and len(stoch_d) > 0:
                    latest_stoch_k = stoch_k[-1]
                    latest_stoch_d = stoch_d[-1]
                    
                    if latest_stoch_k < 20 and latest_stoch_d < 20:
                        momentum_signals.append(('stoch_oversold', 0.7, f"随机指标超卖: K={latest_stoch_k:.1f}, D={latest_stoch_d:.1f}"))
                    elif latest_stoch_k > 80 and latest_stoch_d > 80:
                        momentum_signals.append(('stoch_overbought', -0.7, f"随机指标超买: K={latest_stoch_k:.1f}, D={latest_stoch_d:.1f}"))
            
            # RSI背离检测
            if 'rsi_bullish_divergence' in df.columns and 'rsi_bearish_divergence' in df.columns:
                latest_bullish_div = df['rsi_bullish_divergence'].iloc[-1]
                latest_bearish_div = df['rsi_bearish_divergence'].iloc[-1]
                
                if latest_bullish_div == 1:
                    momentum_signals.append(('rsi_bullish_divergence', 0.6, "RSI看涨背离"))
                elif latest_bearish_div == 1:
                    momentum_signals.append(('rsi_bearish_divergence', -0.6, "RSI看跌背离"))
            
            # 动量指标综合评分
            momentum_score = 0.0
            momentum_reasons = []
            
            for signal_name, score, reason in momentum_signals:
                momentum_score += score
                momentum_reasons.append(reason)
            
            momentum_score = max(-1.0, min(1.0, momentum_score))
            
            return {
                'score': momentum_score,
                'reasons': momentum_reasons,
                'signals': momentum_signals
            }
            
        except Exception as e:
            logger.error(f"{symbol}: 动量分析失败: {e}")
            return {'score': 0.0, 'reasons': [], 'signals': []}
    
    def _analyze_volatility(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """分析波动率信号"""
        try:
            volatility_signals = []
            
            # 布林带分析
            if 'bb_percent_b' in df.columns:
                bb_percent_b = df['bb_percent_b'].values
                if len(bb_percent_b) > 0:
                    latest_bb_pb = bb_percent_b[-1]
                    
                    if latest_bb_pb > 0.8:
                        volatility_signals.append(('bb_near_upper', -0.6, f"价格接近布林带上轨: {latest_bb_pb:.2f}"))
                    elif latest_bb_pb < 0.2:
                        volatility_signals.append(('bb_near_lower', 0.6, f"价格接近布林带下轨: {latest_bb_pb:.2f}"))
            
            # 布林带突破
            if 'bb_breakout_upper' in df.columns and 'bb_breakout_lower' in df.columns:
                latest_upper_breakout = df['bb_breakout_upper'].iloc[-1]
                latest_lower_breakout = df['bb_breakout_lower'].iloc[-1]
                
                if latest_upper_breakout == 1:
                    volatility_signals.append(('bb_upper_breakout', -0.7, "价格突破布林带上轨"))
                elif latest_lower_breakout == 1:
                    volatility_signals.append(('bb_lower_breakout', 0.7, "价格突破布林带下轨"))
            
            # 布林带挤压
            if 'bb_squeeze' in df.columns:
                latest_squeeze = df['bb_squeeze'].iloc[-1]
                if latest_squeeze == 1:
                    volatility_signals.append(('bb_squeeze', 0.3, "布林带挤压，可能即将突破"))
            
            # ATR分析（波动率）
            if 'atr_percent' in df.columns:
                atr_percent = df['atr_percent'].values
                if len(atr_percent) > 0:
                    latest_atr_pct = atr_percent[-1]
                    
                    if latest_atr_pct > 3.0:  # 高波动率
                        volatility_signals.append(('high_volatility', -0.4, f"高波动率: ATR={latest_atr_pct:.1f}%"))
                    elif latest_atr_pct < 0.5:  # 低波动率
                        volatility_signals.append(('low_volatility', 0.2, f"低波动率: ATR={latest_atr_pct:.1f}%"))
            
            # 综合波动率评分
            volatility_score = 0.0
            volatility_reasons = []
            
            for signal_name, score, reason in volatility_signals:
                volatility_score += score
                volatility_reasons.append(reason)
            
            volatility_score = max(-1.0, min(1.0, volatility_score))
            
            return {
                'score': volatility_score,
                'reasons': volatility_reasons,
                'signals': volatility_signals
            }
            
        except Exception as e:
            logger.error(f"{symbol}: 波动率分析失败: {e}")
            return {'score': 0.0, 'reasons': [], 'signals': []}
    
    def _analyze_volume(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """分析成交量信号"""
        try:
            volume_signals = []
            
            # 成交量分析（需要价格数据）
            if 'volume' in df.columns and 'close' in df.columns:
                volumes = df['volume'].values
                closes = df['close'].values
                
                if len(volumes) >= 5 and len(closes) >= 5:
                    # 计算成交量均线
                    volume_ma = pd.Series(volumes).rolling(window=5, min_periods=1).mean().values
                    
                    # 最新成交量与均线比较
                    latest_volume = volumes[-1]
                    latest_volume_ma = volume_ma[-1]
                    
                    if latest_volume > latest_volume_ma * 1.5:  # 成交量放大50%
                        # 结合价格变化判断
                        if len(closes) >= 2:
                            price_change = (closes[-1] - closes[-2]) / closes[-2] * 100
                            
                            if price_change > 1:  # 价涨量增
                                volume_signals.append(('volume_price_rise', 0.7, f"价涨量增: 成交量放大{latest_volume/latest_volume_ma:.1f}倍"))
                            elif price_change < -1:  # 价跌量增
                                volume_signals.append(('volume_price_fall', -0.7, f"价跌量增: 成交量放大{latest_volume/latest_volume_ma:.1f}倍"))
                            else:
                                volume_signals.append(('high_volume', 0.3, f"高成交量: 放大{latest_volume/latest_volume_ma:.1f}倍"))
            
            # OBV分析
            if 'obv_breakout' in df.columns:
                latest_obv_breakout = df['obv_breakout'].iloc[-1]
                if latest_obv_breakout == 1:
                    volume_signals.append(('obv_breakout', 0.5, "OBV突破"))
            
            # 综合成交量评分
            volume_score = 0.0
            volume_reasons = []
            
            for signal_name, score, reason in volume_signals:
                volume_score += score
                volume_reasons.append(reason)
            
            volume_score = max(-1.0, min(1.0, volume_score))
            
            return {
                'score': volume_score,
                'reasons': volume_reasons,
                'signals': volume_signals
            }
            
        except Exception as e:
            logger.error(f"{symbol}: 成交量分析失败: {e}")
            return {'score': 0.0, 'reasons': [], 'signals': []}
    
    def _combine_signals(self, 
                        trend_analysis: Dict[str, Any],
                        momentum_analysis: Dict[str, Any],
                        volatility_analysis: Dict[str, Any],
                        volume_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """综合各个维度的信号"""
        
        # 加权综合得分
        combined_score = (
            trend_analysis['score'] * self.signal_weights['trend'] +
            momentum_analysis['score'] * self.signal_weights['momentum'] +
            volatility_analysis['score'] * self.signal_weights['volatility'] +
            volume_analysis['score'] * self.signal_weights['volume']
        )
        
        # 收集所有理由
        all_reasons = []
        all_reasons.extend(trend_analysis['reasons'])
        all_reasons.extend(momentum_analysis['reasons'])
        all_reasons.extend(volatility_analysis['reasons'])
        all_reasons.extend(volume_analysis['reasons'])
        
        # 收集所有信号
        all_signals = []
        all_signals.extend(trend_analysis['signals'])
        all_signals.extend(momentum_analysis['signals'])
        all_signals.extend(volatility_analysis['signals'])
        all_signals.extend(volume_analysis['signals'])
        
        # 计算置信度（基于信号数量和一致性）
        signal_count = len(all_signals)
        consistency_score = 0.0
        
        if signal_count > 0:
            # 计算信号一致性（同向信号的比例）
            positive_signals = sum(1 for _, score, _ in all_signals if score > 0)
            negative_signals = sum(1 for _, score, _ in all_signals if score < 0)
            
            if positive_signals > negative_signals:
                consistency_score = positive_signals / signal_count
            elif negative_signals > positive_signals:
                consistency_score = negative_signals / signal_count
        
        # 置信度 = 一致性分数 * 信号强度（归一化到0-1）
        confidence = consistency_score * min(1.0, abs(combined_score))
        
        return {
            'combined_score': combined_score,
            'confidence': confidence,
            'reasons': all_reasons,
            'signals': all_signals,
            'component_scores': {
                'trend': trend_analysis['score'],
                'momentum': momentum_analysis['score'],
                'volatility': volatility_analysis['score'],
                'volume': volume_analysis['score']
            }
        }
    
    def _generate_final_signals(self, 
                               combined_signal: Dict[str, Any],
                               timestamp: int,
                               symbol: str,
                               price: float,
                               latest_indicators: Dict[str, Any]) -> List[Signal]:
        """生成最终交易信号"""
        signals = []
        
        combined_score = combined_signal['combined_score']
        confidence = combined_signal['confidence']
        reasons = combined_signal['reasons']
        
        # 如果置信度低于阈值，不生成信号
        if confidence < self.min_confidence:
            neutral_signal = Signal(
                signal_type=SignalType.NEUTRAL,
                strength=SignalStrength.VERY_WEAK,
                confidence=confidence,
                timestamp=timestamp,
                symbol=symbol,
                price=price,
                indicators=latest_indicators,
                reasoning="信号置信度过低"
            )
            signals.append(neutral_signal)
            return signals
        
        # 根据综合得分确定信号类型
        if combined_score >= 0.6:
            signal_type = SignalType.STRONG_BUY
            strength = SignalStrength.VERY_STRONG
        elif combined_score >= 0.3:
            signal_type = SignalType.BUY
            strength = SignalStrength.STRONG
        elif combined_score >= 0.1:
            signal_type = SignalType.WEAK_BUY
            strength = SignalStrength.MEDIUM
        elif combined_score <= -0.6:
            signal_type = SignalType.STRONG_SELL
            strength = SignalStrength.VERY_STRONG
        elif combined_score <= -0.3:
            signal_type = SignalType.SELL
            strength = SignalStrength.STRONG
        elif combined_score <= -0.1:
            signal_type = SignalType.WEAK_SELL
            strength = SignalStrength.MEDIUM
        else:
            signal_type = SignalType.NEUTRAL
            strength = SignalStrength.WEAK
        
        # 生成理由字符串
        reasoning = " | ".join(reasons) if reasons else "无明确信号"
        reasoning = f"综合得分: {combined_score:.2f}, 置信度: {confidence:.2f} | {reasoning}"
        
        # 创建信号
        signal = Signal(
            signal_type=signal_type,
            strength=strength,
            confidence=confidence,
            timestamp=timestamp,
            symbol=symbol,
            price=price,
            indicators=latest_indicators,
            reasoning=reasoning,
            metadata={
                'combined_score': combined_score,
                'component_scores': combined_signal['component_scores']
            }
        )
        
        signals.append(signal)
        return signals
    
    def generate_signal_summary(self, signals: List[Signal]) -> Dict[str, Any]:
        """
        生成信号摘要
        
        Args:
            signals: 信号列表
            
        Returns:
            Dict[str, Any]: 信号摘要
        """
        if not signals:
            return {'signal_count': 0, 'signals': []}
        
        # 获取最新信号
        latest_signal = signals[-1]
        
        # 统计信号类型
        signal_types = {}
        for signal in signals:
            signal_type = signal.signal_type.name
            signal_types[signal_type] = signal_types.get(signal_type, 0) + 1
        
        return {
            'signal_count': len(signals),
            'latest_signal': latest_signal.to_dict(),
            'signal_types': signal_types,
            'timestamp': latest_signal.timestamp,
            'symbol': latest_signal.symbol,
            'price': latest_signal.price
        }