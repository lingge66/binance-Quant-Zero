"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可视化示例脚本
展示如何使用 matplotlib 绘制价格与技术指标图表
"""
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os
import sys

# 添加项目路径以便导入模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.signals.indicators import TechnicalIndicators

def generate_sample_data():
    """生成示例K线数据（用于演示）"""
    np.random.seed(42)
    n = 200
    # 修改后变成这样：
    dates = pd.date_range('2026-01-01', periods=n, freq='1h')
    
    # 模拟价格序列（随机游走）
    price = 50000 + np.cumsum(np.random.randn(n) * 100)
    
    # 添加一些趋势和季节性
    trend = np.linspace(0, 2000, n)
    seasonal = 500 * np.sin(np.linspace(0, 4*np.pi, n))
    price = price + trend + seasonal
    
    # 生成OHLCV数据
    data = []
    for i in range(n):
        open_price = price[i] + np.random.randn() * 50
        close_price = price[i] + np.random.randn() * 50
        high = max(open_price, close_price) + abs(np.random.randn() * 100)
        low = min(open_price, close_price) - abs(np.random.randn() * 100)
        volume = np.random.randint(100, 1000)
        
        data.append({
            'timestamp': dates[i].timestamp() * 1000,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close_price,
            'volume': volume
        })
    
    return data

def plot_price_with_indicators(data_with_indicators):
    """绘制价格与技术指标图表"""
    df = pd.DataFrame(data_with_indicators)
    
    # 创建子图
    fig, axes = plt.subplots(4, 1, figsize=(14, 12), gridspec_kw={'height_ratios': [3, 1, 1, 1]})
    
    # 1. 价格与移动平均线
    ax1 = axes[0]
    ax1.plot(df.index, df['close'], label='收盘价', color='black', linewidth=1.5)
    
    # 绘制移动平均线（如果存在）
    ma_colors = ['blue', 'orange', 'green', 'red', 'purple']
    ma_periods = [5, 10, 20, 30, 60]
    
    for i, period in enumerate(ma_periods):
        col = f'ma_{period}'
        if col in df.columns:
            ax1.plot(df.index, df[col], label=f'MA{period}', color=ma_colors[i], linewidth=1, alpha=0.8)
    
    ax1.set_title('BTCUSDT 价格与移动平均线', fontsize=14, fontweight='bold')
    ax1.set_ylabel('价格 (USDT)', fontsize=12)
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    
    # 2. RSI
    ax2 = axes[1]
    if 'rsi' in df.columns:
        ax2.plot(df.index, df['rsi'], label='RSI', color='purple', linewidth=1.5)
        ax2.axhline(y=70, color='red', linestyle='--', alpha=0.5, label='超买线 (70)')
        ax2.axhline(y=30, color='green', linestyle='--', alpha=0.5, label='超卖线 (30)')
        ax2.axhline(y=50, color='gray', linestyle=':', alpha=0.3)
        ax2.fill_between(df.index, 30, 70, color='gray', alpha=0.1)
        ax2.set_ylabel('RSI', fontsize=12)
        ax2.set_ylim(0, 100)
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
    
    # 3. MACD
    ax3 = axes[2]
    if all(col in df.columns for col in ['macd_dif', 'macd_dea', 'macd_hist']):
        ax3.plot(df.index, df['macd_dif'], label='DIF', color='blue', linewidth=1.5)
        ax3.plot(df.index, df['macd_dea'], label='DEA', color='orange', linewidth=1.5)
        
        # 绘制MACD柱状图
        colors = ['green' if h >= 0 else 'red' for h in df['macd_hist']]
        ax3.bar(df.index, df['macd_hist'], color=colors, alpha=0.5, label='MACD柱', width=0.8)
        
        ax3.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        ax3.set_ylabel('MACD', fontsize=12)
        ax3.legend(loc='upper left')
        ax3.grid(True, alpha=0.3)
    
    # 4. 成交量
    ax4 = axes[3]
    if 'volume' in df.columns:
        colors = ['green' if df['close'].iloc[i] >= df['open'].iloc[i] else 'red' for i in range(len(df))]
        ax4.bar(df.index, df['volume'], color=colors, alpha=0.7, width=0.8)
        ax4.set_ylabel('成交量', fontsize=12)
        ax4.set_xlabel('时间', fontsize=12)
        ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig

def plot_bollinger_bands(data_with_indicators):
    """绘制布林带图表"""
    df = pd.DataFrame(data_with_indicators)
    
    if not all(col in df.columns for col in ['bb_upper', 'bb_middle', 'bb_lower']):
        print("布林带数据不足")
        return None
    
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={'height_ratios': [3, 1]})
    
    # 1. 价格与布林带
    ax1 = axes[0]
    ax1.plot(df.index, df['close'], label='收盘价', color='black', linewidth=1.5)
    ax1.plot(df.index, df['bb_middle'], label='中轨 (SMA20)', color='blue', linewidth=1)
    ax1.plot(df.index, df['bb_upper'], label='上轨', color='red', linewidth=1, linestyle='--')
    ax1.plot(df.index, df['bb_lower'], label='下轨', color='green', linewidth=1, linestyle='--')
    
    # 填充布林带区域
    ax1.fill_between(df.index, df['bb_lower'], df['bb_upper'], color='gray', alpha=0.2)
    
    # 标记突破点
    if 'bb_breakout_upper' in df.columns:
        upper_breakouts = df[df['bb_breakout_upper'] == 1]
        if len(upper_breakouts) > 0:
            ax1.scatter(upper_breakouts.index, upper_breakouts['close'], 
                       color='red', marker='^', s=100, label='上轨突破', zorder=5)
    
    if 'bb_breakout_lower' in df.columns:
        lower_breakouts = df[df['bb_breakout_lower'] == 1]
        if len(lower_breakouts) > 0:
            ax1.scatter(lower_breakouts.index, lower_breakouts['close'],
                       color='green', marker='v', s=100, label='下轨突破', zorder=5)
    
    ax1.set_title('BTCUSDT 布林带分析', fontsize=14, fontweight='bold')
    ax1.set_ylabel('价格 (USDT)', fontsize=12)
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    
    # 2. 布林带宽度 (%B)
    ax2 = axes[1]
    if 'bb_percent_b' in df.columns:
        ax2.plot(df.index, df['bb_percent_b'], label='%B', color='purple', linewidth=1.5)
        ax2.axhline(y=1, color='red', linestyle='--', alpha=0.5, label='上轨 (1.0)')
        ax2.axhline(y=0, color='green', linestyle='--', alpha=0.5, label='下轨 (0.0)')
        ax2.axhline(y=0.5, color='gray', linestyle=':', alpha=0.3, label='中轨 (0.5)')
        ax2.fill_between(df.index, 0, 1, color='gray', alpha=0.1)
        ax2.set_ylabel('%B', fontsize=12)
        ax2.set_ylim(-0.5, 1.5)
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig

def main():
    """主函数"""
    print("生成示例数据...")
    data = generate_sample_data()
    
    print("计算技术指标...")
    data_with_indicators = TechnicalIndicators.calculate_all_indicators(data)
    
    print("绘制图表...")
    
    # 图表1：价格与指标
    fig1 = plot_price_with_indicators(data_with_indicators)
    fig1.savefig('price_indicators.png', dpi=150, bbox_inches='tight')
    print("✓ 已保存: price_indicators.png")
    
    # 图表2：布林带
    fig2 = plot_bollinger_bands(data_with_indicators)
    if fig2:
        fig2.savefig('bollinger_bands.png', dpi=150, bbox_inches='tight')
        print("✓ 已保存: bollinger_bands.png")
    
    # 显示图表（如果环境支持）
    try:
        plt.show()
    except:
        print("图表已保存为PNG文件，请在文件浏览器中查看")
    
    print("\n使用方法:")
    print("1. 安装依赖: pip install matplotlib pandas numpy")
    print("2. 运行脚本: python visualize_example.py")
    print("3. 查看生成的PNG图片")
    print("\n在实际项目中使用:")
    print("1. 将 data 替换为真实的历史K线数据")
    print("2. 调整图表样式和参数")
    print("3. 集成到报告生成或实时监控中")

if __name__ == "__main__":
    # 检查matplotlib是否安装
    try:
        import matplotlib
        main()
    except ImportError:
        print("错误: 请先安装 matplotlib")
        print("安装命令: pip install matplotlib pandas numpy")
        sys.exit(1)