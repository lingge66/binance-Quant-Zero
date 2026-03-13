#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技术指标计算模块
实现常用的量化交易技术指标，使用pandas和numpy进行高效向量化计算
"""
import logging
import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple, Union, Any

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """技术指标计算器"""
    
    @staticmethod
    def calculate_all_indicators(data: List[Dict], 
                                include_indicators: Optional[List[str]] = None) -> List[Dict]:
        """
        计算所有技术指标
        
        Args:
            data: K线数据列表，每条数据包含timestamp, open, high, low, close, volume等字段
            include_indicators: 需要计算的指标列表，None表示计算所有
            
        Returns:
            List[Dict]: 添加了技术指标的数据列表
        """
        if not data:
            return []
        
        # 转换为DataFrame以便高效计算
        df = pd.DataFrame(data)
        
        # 确保数据按时间排序
        if 'timestamp' in df.columns:
            df = df.sort_values('timestamp').reset_index(drop=True)
        
        # 计算基础价格序列
        close_prices = df['close'].values
        high_prices = df['high'].values
        low_prices = df['low'].values
        volumes = df['volume'].values
        
        # 默认计算所有指标
        if include_indicators is None:
            include_indicators = ['ma', 'ema', 'rsi', 'bb', 'macd', 'atr', 'obv', 'stoch']
        
        # 计算各个指标
        if 'ma' in include_indicators:
            df = TechnicalIndicators._add_moving_averages(df, close_prices)
        
        if 'ema' in include_indicators:
            df = TechnicalIndicators._add_exponential_moving_averages(df, close_prices)
        
        if 'rsi' in include_indicators:
            df = TechnicalIndicators._add_rsi(df, close_prices)
        
        if 'bb' in include_indicators:
            df = TechnicalIndicators._add_bollinger_bands(df, close_prices)
        
        if 'macd' in include_indicators:
            df = TechnicalIndicators._add_macd(df, close_prices)
        
        if 'atr' in include_indicators:
            df = TechnicalIndicators._add_atr(df, high_prices, low_prices, close_prices)
        
        if 'obv' in include_indicators:
            df = TechnicalIndicators._add_obv(df, close_prices, volumes)
        
        if 'stoch' in include_indicators:
            df = TechnicalIndicators._add_stochastic(df, high_prices, low_prices, close_prices)
        
        # 转换回字典列表
        result = df.to_dict('records')
        
        logger.debug(f"计算了 {len(include_indicators)} 个技术指标，数据长度: {len(result)}")
        return result
    
    @staticmethod
    def _add_moving_averages(df: pd.DataFrame, close_prices: np.ndarray) -> pd.DataFrame:
        """添加移动平均线"""
        try:
            # SMA 简单移动平均
            periods = [5, 10, 20, 30, 60]  # 常用周期
            
            for period in periods:
                if len(close_prices) >= period:
                    sma = pd.Series(close_prices).rolling(window=period, min_periods=1).mean()
                    df[f'ma_{period}'] = sma.values
                    
                    # 计算价格与MA的偏离度
                    df[f'price_ma{period}_diff'] = ((close_prices - df[f'ma_{period}']) / df[f'ma_{period}']) * 100
                    df[f'price_ma{period}_diff_pct'] = df[f'price_ma{period}_diff']
                else:
                    df[f'ma_{period}'] = np.nan
                    df[f'price_ma{period}_diff'] = np.nan
                    df[f'price_ma{period}_diff_pct'] = np.nan
            
            # 金叉死叉信号
            if 'ma_5' in df.columns and 'ma_10' in df.columns:
                df['ma_cross'] = 0  # 0:无信号, 1:金叉, -1:死叉
                
                # 计算交叉
                ma5_above_ma10 = df['ma_5'] > df['ma_10']
                ma5_below_ma10 = df['ma_5'] < df['ma_10']
                
                # 金叉：MA5上穿MA10
                golden_cross = ma5_above_ma10 & ma5_below_ma10.shift(1)
                df.loc[golden_cross, 'ma_cross'] = 1
                
                # 死叉：MA5下穿MA10
                death_cross = ma5_below_ma10 & ma5_above_ma10.shift(1)
                df.loc[death_cross, 'ma_cross'] = -1
            
            logger.debug(f"移动平均线计算完成，周期: {periods}")
            
        except Exception as e:
            logger.error(f"计算移动平均线失败: {e}")
        
        return df
    
    @staticmethod
    def _add_exponential_moving_averages(df: pd.DataFrame, close_prices: np.ndarray) -> pd.DataFrame:
        """添加指数移动平均线"""
        try:
            periods = [12, 26]  # MACD常用周期
            
            for period in periods:
                if len(close_prices) >= period:
                    ema = pd.Series(close_prices).ewm(span=period, adjust=False).mean()
                    df[f'ema_{period}'] = ema.values
                else:
                    df[f'ema_{period}'] = np.nan
            
            logger.debug(f"指数移动平均线计算完成，周期: {periods}")
            
        except Exception as e:
            logger.error(f"计算指数移动平均线失败: {e}")
        
        return df
    
    @staticmethod
    def _add_rsi(df: pd.DataFrame, close_prices: np.ndarray) -> pd.DataFrame:
        """添加相对强弱指数"""
        try:
            period = 14  # 标准RSI周期
            
            if len(close_prices) >= period:
                # 计算价格变化
                delta = pd.Series(close_prices).diff()
                
                # 分离上涨和下跌
                gain = delta.where(delta > 0, 0)
                loss = -delta.where(delta < 0, 0)
                
                # 计算平均上涨和平均下跌
                avg_gain = gain.rolling(window=period, min_periods=1).mean()
                avg_loss = loss.rolling(window=period, min_periods=1).mean()
                
                # 计算RS
                rs = avg_gain / avg_loss
                
                # 计算RSI
                rsi = 100 - (100 / (1 + rs))
                df['rsi'] = rsi.values
                
                # RSI超买超卖信号
                df['rsi_overbought'] = (df['rsi'] > 70).astype(int)
                df['rsi_oversold'] = (df['rsi'] < 30).astype(int)
                
                # RSI背离检测（简化版）
                if len(close_prices) >= period * 2:
                    # 价格创新高但RSI未创新高
                    price_new_high = close_prices == pd.Series(close_prices).rolling(window=period).max()
                    rsi_not_new_high = df['rsi'] < pd.Series(df['rsi']).rolling(window=period).max()
                    df['rsi_bearish_divergence'] = (price_new_high & rsi_not_new_high).astype(int)
                    
                    # 价格创新低但RSI未创新低
                    price_new_low = close_prices == pd.Series(close_prices).rolling(window=period).min()
                    rsi_not_new_low = df['rsi'] > pd.Series(df['rsi']).rolling(window=period).min()
                    df['rsi_bullish_divergence'] = (price_new_low & rsi_not_new_low).astype(int)
                else:
                    df['rsi_bearish_divergence'] = 0
                    df['rsi_bullish_divergence'] = 0
                
                logger.debug(f"RSI计算完成，周期: {period}")
            else:
                df['rsi'] = np.nan
                df['rsi_overbought'] = 0
                df['rsi_oversold'] = 0
                df['rsi_bearish_divergence'] = 0
                df['rsi_bullish_divergence'] = 0
                
        except Exception as e:
            logger.error(f"计算RSI失败: {e}")
        
        return df
    
    @staticmethod
    def _add_bollinger_bands(df: pd.DataFrame, close_prices: np.ndarray) -> pd.DataFrame:
        """添加布林带"""
        try:
            period = 20  # 标准布林带周期
            std_mult = 2  # 标准差倍数
            
            if len(close_prices) >= period:
                # 计算中轨（SMA）
                sma = pd.Series(close_prices).rolling(window=period, min_periods=1).mean()
                
                # 计算标准差
                std = pd.Series(close_prices).rolling(window=period, min_periods=1).std()
                
                # 计算上下轨
                upper_band = sma + (std * std_mult)
                lower_band = sma - (std * std_mult)
                
                # 添加到DataFrame
                df['bb_middle'] = sma.values
                df['bb_upper'] = upper_band.values
                df['bb_lower'] = lower_band.values
                
                # 布林带宽度（带宽）
                df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
                
                # 价格相对于布林带的位置（%B）
                df['bb_percent_b'] = (close_prices - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
                
                # 布林带挤压信号（带宽收缩）
                bb_width_sma = df['bb_width'].rolling(window=period).mean()
                df['bb_squeeze'] = (df['bb_width'] < bb_width_sma * 0.8).astype(int)
                
                # 价格突破信号
                df['bb_breakout_upper'] = (close_prices > df['bb_upper']).astype(int)
                df['bb_breakout_lower'] = (close_prices < df['bb_lower']).astype(int)
                
                logger.debug(f"布林带计算完成，周期: {period}, 标准差倍数: {std_mult}")
            else:
                df['bb_middle'] = np.nan
                df['bb_upper'] = np.nan
                df['bb_lower'] = np.nan
                df['bb_width'] = np.nan
                df['bb_percent_b'] = np.nan
                df['bb_squeeze'] = 0
                df['bb_breakout_upper'] = 0
                df['bb_breakout_lower'] = 0
                
        except Exception as e:
            logger.error(f"计算布林带失败: {e}")
        
        return df
    
    @staticmethod
    def _add_macd(df: pd.DataFrame, close_prices: np.ndarray) -> pd.DataFrame:
        """添加MACD"""
        try:
            fast_period = 12
            slow_period = 26
            signal_period = 9
            
            if len(close_prices) >= slow_period:
                # 计算快线（12日EMA）和慢线（26日EMA）
                ema_fast = pd.Series(close_prices).ewm(span=fast_period, adjust=False).mean()
                ema_slow = pd.Series(close_prices).ewm(span=slow_period, adjust=False).mean()
                
                # 计算DIF（快线-慢线）
                dif = ema_fast - ema_slow
                
                # 计算DEA（DIF的9日EMA）
                dea = dif.ewm(span=signal_period, adjust=False).mean()
                
                # 计算MACD柱状图（DIF-DEA）
                macd_hist = dif - dea
                
                # 添加到DataFrame
                df['macd_fast'] = ema_fast.values
                df['macd_slow'] = ema_slow.values
                df['macd_dif'] = dif.values
                df['macd_dea'] = dea.values
                df['macd_hist'] = macd_hist.values
                
                # MACD金叉死叉信号
                df['macd_cross'] = 0  # 0:无信号, 1:金叉, -1:死叉
                
                # 金叉：DIF上穿DEA
                dif_above_dea = df['macd_dif'] > df['macd_dea']
                dif_below_dea = df['macd_dif'] < df['macd_dea']
                
                golden_cross = dif_above_dea & dif_below_dea.shift(1)
                df.loc[golden_cross, 'macd_cross'] = 1
                
                # 死叉：DIF下穿DEA
                death_cross = dif_below_dea & dif_above_dea.shift(1)
                df.loc[death_cross, 'macd_cross'] = -1
                
                # MACD背离检测（简化版）
                if len(close_prices) >= slow_period * 2:
                    # 价格创新高但MACD柱状图未创新高
                    price_new_high = close_prices == pd.Series(close_prices).rolling(window=slow_period).max()
                    macd_not_new_high = df['macd_hist'] < pd.Series(df['macd_hist']).rolling(window=slow_period).max()
                    df['macd_bearish_divergence'] = (price_new_high & macd_not_new_high).astype(int)
                    
                    # 价格创新低但MACD柱状图未创新低
                    price_new_low = close_prices == pd.Series(close_prices).rolling(window=slow_period).min()
                    macd_not_new_low = df['macd_hist'] > pd.Series(df['macd_hist']).rolling(window=slow_period).min()
                    df['macd_bullish_divergence'] = (price_new_low & macd_not_new_low).astype(int)
                else:
                    df['macd_bearish_divergence'] = 0
                    df['macd_bullish_divergence'] = 0
                
                logger.debug(f"MACD计算完成，快线: {fast_period}, 慢线: {slow_period}, 信号线: {signal_period}")
            else:
                df['macd_fast'] = np.nan
                df['macd_slow'] = np.nan
                df['macd_dif'] = np.nan
                df['macd_dea'] = np.nan
                df['macd_hist'] = np.nan
                df['macd_cross'] = 0
                df['macd_bearish_divergence'] = 0
                df['macd_bullish_divergence'] = 0
                
        except Exception as e:
            logger.error(f"计算MACD失败: {e}")
        
        return df
    
    @staticmethod
    def _add_atr(df: pd.DataFrame, high_prices: np.ndarray, low_prices: np.ndarray, 
                close_prices: np.ndarray) -> pd.DataFrame:
        """添加平均真实波幅"""
        try:
            period = 14  # 标准ATR周期
            
            if len(close_prices) >= period:
                # 计算真实波幅（TR）
                high_low = high_prices - low_prices
                high_close_prev = np.abs(high_prices - np.roll(close_prices, 1))
                low_close_prev = np.abs(low_prices - np.roll(close_prices, 1))
                
                # 第一行的处理
                high_close_prev[0] = 0
                low_close_prev[0] = 0
                
                # TR = max(high-low, |high-close_prev|, |low-close_prev|)
                tr = np.maximum(high_low, np.maximum(high_close_prev, low_close_prev))
                
                # 计算ATR（TR的移动平均）
                atr = pd.Series(tr).rolling(window=period, min_periods=1).mean()
                
                df['atr'] = atr.values
                df['atr_percent'] = (df['atr'] / close_prices) * 100
                
                logger.debug(f"ATR计算完成，周期: {period}")
            else:
                df['atr'] = np.nan
                df['atr_percent'] = np.nan
                
        except Exception as e:
            logger.error(f"计算ATR失败: {e}")
        
        return df
    
    @staticmethod
    def _add_obv(df: pd.DataFrame, close_prices: np.ndarray, volumes: np.ndarray) -> pd.DataFrame:
        """添加能量潮指标"""
        try:
            if len(close_prices) >= 2:
                # 计算价格变化方向
                price_changes = np.diff(close_prices)
                price_changes = np.insert(price_changes, 0, 0)  # 第一行设为0
                
                # OBV计算
                obv = np.zeros_like(close_prices, dtype=float)
                obv[0] = volumes[0]  # 初始OBV
                
                for i in range(1, len(close_prices)):
                    if price_changes[i] > 0:
                        obv[i] = obv[i-1] + volumes[i]
                    elif price_changes[i] < 0:
                        obv[i] = obv[i-1] - volumes[i]
                    else:
                        obv[i] = obv[i-1]
                
                df['obv'] = obv
                
                # OBV均线（20日）
                if len(obv) >= 20:
                    obv_ma = pd.Series(obv).rolling(window=20, min_periods=1).mean()
                    df['obv_ma20'] = obv_ma.values
                    
                    # OBV突破信号
                    df['obv_breakout'] = (obv > obv_ma).astype(int)
                else:
                    df['obv_ma20'] = np.nan
                    df['obv_breakout'] = 0
                
                logger.debug(f"OBV计算完成")
            else:
                df['obv'] = np.nan
                df['obv_ma20'] = np.nan
                df['obv_breakout'] = 0
                
        except Exception as e:
            logger.error(f"计算OBV失败: {e}")
        
        return df
    
    @staticmethod
    def _add_stochastic(df: pd.DataFrame, high_prices: np.ndarray, low_prices: np.ndarray, 
                       close_prices: np.ndarray) -> pd.DataFrame:
        """添加随机指标"""
        try:
            k_period = 14
            d_period = 3
            
            if len(close_prices) >= k_period:
                # 计算%K
                lowest_low = pd.Series(low_prices).rolling(window=k_period, min_periods=1).min()
                highest_high = pd.Series(high_prices).rolling(window=k_period, min_periods=1).max()
                
                stoch_k = 100 * ((close_prices - lowest_low) / (highest_high - lowest_low))
                stoch_k = stoch_k.fillna(50)  # 处理除零情况
                
                # 计算%D（%K的3日简单移动平均）
                stoch_d = stoch_k.rolling(window=d_period, min_periods=1).mean()
                
                df['stoch_k'] = stoch_k.values
                df['stoch_d'] = stoch_d.values
                
                # 随机指标超买超卖信号
                df['stoch_overbought'] = (df['stoch_k'] > 80).astype(int)
                df['stoch_oversold'] = (df['stoch_k'] < 20).astype(int)
                
                # 金叉死叉
                df['stoch_cross'] = 0
                k_above_d = df['stoch_k'] > df['stoch_d']
                k_below_d = df['stoch_k'] < df['stoch_d']
                
                golden_cross = k_above_d & k_below_d.shift(1)
                df.loc[golden_cross, 'stoch_cross'] = 1
                
                death_cross = k_below_d & k_above_d.shift(1)
                df.loc[death_cross, 'stoch_cross'] = -1
                
                logger.debug(f"随机指标计算完成，%K周期: {k_period}, %D周期: {d_period}")
            else:
                df['stoch_k'] = np.nan
                df['stoch_d'] = np.nan
                df['stoch_overbought'] = 0
                df['stoch_oversold'] = 0
                df['stoch_cross'] = 0
                
        except Exception as e:
            logger.error(f"计算随机指标失败: {e}")
        
        return df
    
    @staticmethod
    def get_indicator_summary(data_with_indicators: List[Dict]) -> Dict[str, Any]:
        """
        获取技术指标摘要
        
        Args:
            data_with_indicators: 包含技术指标的数据
            
        Returns:
            Dict[str, Any]: 技术指标摘要
        """
        if not data_with_indicators:
            return {}
        
        df = pd.DataFrame(data_with_indicators)
        latest = df.iloc[-1] if len(df) > 0 else {}
        
        summary = {
            'timestamp': latest.get('timestamp', 0),
            'price': latest.get('close', 0),
            'indicators': {}
        }
        
        # 收集各个指标的当前值
        indicator_fields = [
            'ma_5', 'ma_10', 'ma_20', 'ma_60',
            'rsi', 'bb_middle', 'bb_upper', 'bb_lower',
            'macd_dif', 'macd_dea', 'macd_hist',
            'atr', 'atr_percent', 'obv'
        ]
        
        for field in indicator_fields:
            if field in latest and pd.notna(latest[field]):
                summary['indicators'][field] = float(latest[field])
        
        # 收集信号
        signal_fields = [
            'ma_cross', 'rsi_overbought', 'rsi_oversold',
            'bb_breakout_upper', 'bb_breakout_lower', 'bb_squeeze',
            'macd_cross', 'obv_breakout', 'stoch_cross'
        ]
        
        for field in signal_fields:
            if field in latest:
                summary['indicators'][field] = int(latest[field])
        
        return summary
    
    @staticmethod
    def validate_data_for_indicators(data: List[Dict], min_records: int = 60) -> bool:
        """
        验证数据是否足够计算技术指标
        
        Args:
            data: K线数据
            min_records: 最少需要的数据记录数
            
        Returns:
            bool: 数据是否足够
        """
        if not data:
            logger.warning("数据为空")
            return False
        
        if len(data) < min_records:
            logger.warning(f"数据记录不足: {len(data)} < {min_records}")
            return False
        
        # 检查必要字段
        required_fields = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        first_record = data[0]
        
        for field in required_fields:
            if field not in first_record:
                logger.warning(f"数据缺少必要字段: {field}")
                return False
        
        return True