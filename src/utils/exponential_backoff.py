"""
Copyright (c) 2026 lingge66. All rights reserved.
This code is part of the Binance AI Agent project and is protected by copyright law.
Unauthorized copying, modification, distribution, or use of this code is strictly prohibited.
"""


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指数退避算法
用于网络请求重试、连接重连等场景
"""
import random
import time
import logging

logger = logging.getLogger(__name__)


class ExponentialBackoff:
    """
    指数退避算法
    
    特性:
    - 指数增长延迟时间
    - 随机抖动避免多个客户端同时重试
    - 最大延迟限制
    - 最大重试次数限制
    """
    
    def __init__(self, base_delay: float = 1.0, max_delay: float = 64.0,
                 max_attempts: int = 10, jitter: bool = True):
        """
        初始化指数退避器
        
        Args:
            base_delay: 基础延迟（秒）
            max_delay: 最大延迟（秒）
            max_attempts: 最大重试次数
            jitter: 是否添加随机抖动
        """
        self.base_delay = max(0.1, base_delay)  # 最小0.1秒
        self.max_delay = max(base_delay, max_delay)
        self.max_attempts = max(1, max_attempts)
        self.jitter = jitter
        
        self.attempts = 0
        self.last_delay = 0.0
        self.last_attempt_time = 0.0
        
    def next_delay(self) -> float:
        """
        计算下一次重试的延迟时间
        
        Returns:
            float: 延迟时间（秒）
        """
        self.attempts += 1
        
        if self.attempts > self.max_attempts:
            logger.warning(f"已达到最大重试次数: {self.max_attempts}")
            return self.max_delay
        
        # 指数退避公式: delay = base_delay * 2^(attempts-1)
        delay = self.base_delay * (2 ** (self.attempts - 1))
        
        # 添加随机抖动（±25%）
        if self.jitter:
            jitter_factor = random.uniform(0.75, 1.25)
            delay *= jitter_factor
        
        # 限制最大延迟
        delay = min(delay, self.max_delay)
        
        # 确保最小延迟
        delay = max(delay, self.base_delay)
        
        self.last_delay = delay
        self.last_attempt_time = time.time()
        
        logger.debug(f"第 {self.attempts} 次重试，延迟: {delay:.2f} 秒")
        return delay
    
    def reset(self):
        """重置退避器"""
        self.attempts = 0
        self.last_delay = 0.0
        self.last_attempt_time = 0.0
        logger.debug("指数退避器已重置")
    
    def get_attempts(self) -> int:
        """获取当前重试次数"""
        return self.attempts
    
    def can_retry(self) -> bool:
        """检查是否还可以重试"""
        return self.attempts < self.max_attempts
    
    def wait(self):
        """等待当前延迟时间"""
        if self.last_delay > 0:
            time.sleep(self.last_delay)
    
    async def wait_async(self):
        """异步等待当前延迟时间"""
        if self.last_delay > 0:
            import asyncio
            await asyncio.sleep(self.last_delay)


class AdaptiveExponentialBackoff(ExponentialBackoff):
    """
    自适应指数退避算法
    
    根据成功率动态调整基础延迟
    """
    
    def __init__(self, base_delay: float = 1.0, max_delay: float = 64.0,
                 max_attempts: int = 10, jitter: bool = True,
                 success_threshold: float = 0.8, adjustment_factor: float = 0.5):
        """
        初始化自适应指数退避器
        
        Args:
            base_delay: 基础延迟（秒）
            max_delay: 最大延迟（秒）
            max_attempts: 最大重试次数
            jitter: 是否添加随机抖动
            success_threshold: 成功率阈值，高于此值减少延迟
            adjustment_factor: 调整因子（0-1）
        """
        super().__init__(base_delay, max_delay, max_attempts, jitter)
        self.success_threshold = max(0.1, min(0.9, success_threshold))
        self.adjustment_factor = max(0.1, min(0.9, adjustment_factor))
        
        self.success_count = 0
        self.total_attempts = 0
        self.original_base_delay = base_delay
    
    def record_success(self):
        """记录成功"""
        self.success_count += 1
        self.total_attempts += 1
        self._adjust_delay()
    
    def record_failure(self):
        """记录失败"""
        self.total_attempts += 1
        self._adjust_delay()
    
    def _adjust_delay(self):
        """根据成功率调整基础延迟"""
        if self.total_attempts < 10:  # 最少10次尝试后才调整
            return
        
        success_rate = self.success_count / self.total_attempts
        
        if success_rate > self.success_threshold:
            # 成功率高，减少延迟
            self.base_delay *= self.adjustment_factor
            logger.debug(f"成功率 {success_rate:.2f} > {self.success_threshold}，"
                        f"减少基础延迟至 {self.base_delay:.2f}")
        else:
            # 成功率低，增加延迟
            self.base_delay /= self.adjustment_factor
        
        # 限制基础延迟范围
        self.base_delay = max(0.1, min(self.original_base_delay * 2, self.base_delay))
    
    def reset(self):
        """重置退避器"""
        super().reset()
        self.success_count = 0
        self.total_attempts = 0
        self.base_delay = self.original_base_delay
    
    def get_success_rate(self) -> float:
        """获取成功率"""
        if self.total_attempts == 0:
            return 0.0
        return self.success_count / self.total_attempts


def retry_with_backoff(func, max_attempts: int = 5, base_delay: float = 1.0,
                       max_delay: float = 32.0, exceptions: tuple = (Exception,)):
    """
    使用指数退避重试装饰器
    
    Args:
        func: 要重试的函数
        max_attempts: 最大重试次数
        base_delay: 基础延迟
        max_delay: 最大延迟
        exceptions: 要捕获的异常类型
        
    Returns:
        装饰后的函数
    """
    import functools
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        backoff = ExponentialBackoff(base_delay, max_delay, max_attempts)
        
        for attempt in range(max_attempts):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                if attempt == max_attempts - 1:
                    raise e
                
                delay = backoff.next_delay()
                logger.warning(f"函数 {func.__name__} 第 {attempt + 1} 次失败: {e}，"
                              f"等待 {delay:.2f} 秒后重试")
                time.sleep(delay)
        
        # 理论上不会执行到这里
        raise RuntimeError(f"函数 {func.__name__} 重试 {max_attempts} 次后仍失败")
    
    return wrapper


async def retry_with_backoff_async(func, max_attempts: int = 5, base_delay: float = 1.0,
                                   max_delay: float = 32.0, exceptions: tuple = (Exception,)):
    """
    使用指数退避重试装饰器（异步版本）
    
    Args:
        func: 要重试的异步函数
        max_attempts: 最大重试次数
        base_delay: 基础延迟
        max_delay: 最大延迟
        exceptions: 要捕获的异常类型
        
    Returns:
        装饰后的异步函数
    """
    import functools
    import asyncio
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        backoff = ExponentialBackoff(base_delay, max_delay, max_attempts)
        
        for attempt in range(max_attempts):
            try:
                return await func(*args, **kwargs)
            except exceptions as e:
                if attempt == max_attempts - 1:
                    raise e
                
                delay = backoff.next_delay()
                logger.warning(f"异步函数 {func.__name__} 第 {attempt + 1} 次失败: {e}，"
                              f"等待 {delay:.2f} 秒后重试")
                await asyncio.sleep(delay)
        
        # 理论上不会执行到这里
        raise RuntimeError(f"异步函数 {func.__name__} 重试 {max_attempts} 次后仍失败")
    
    return wrapper