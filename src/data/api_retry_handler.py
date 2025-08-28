#!/usr/bin/env python3
"""
API重试处理器
实现指数退避重试机制和错误恢复
"""
import time
import logging
import random
from typing import Callable, Any, Optional, Dict, List
from functools import wraps
from dataclasses import dataclass
from enum import Enum

class RetryStrategy(Enum):
    """重试策略"""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    FIXED_INTERVAL = "fixed_interval"
    LINEAR_BACKOFF = "linear_backoff"

@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    jitter: bool = True
    backoff_factor: float = 2.0

class APIRetryHandler:
    """API重试处理器"""
    
    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
        self.logger = logging.getLogger(__name__)
        
        # 错误统计
        self.error_stats = {
            'total_calls': 0,
            'failed_calls': 0,
            'retry_calls': 0,
            'success_after_retry': 0,
            'permanent_failures': 0
        }
        
        # 可重试的错误类型
        self.retryable_errors = {
            'network_errors': [
                'Connection error',
                'Timeout',
                'Read timeout',
                'Connection timeout',
                'DNS resolution failed'
            ],
            'api_errors': [
                'Rate limit exceeded',
                'Server error',
                'Service unavailable',
                'Internal server error',
                '50001',  # OKX服务器错误
                '50004',  # OKX请求超时
                '50011',  # OKX系统繁忙
            ],
            'temporary_errors': [
                'Temporary failure',
                'Try again later',
                'Service temporarily unavailable'
            ]
        }
    
    def retry_on_failure(self, config: RetryConfig = None):
        """
        装饰器：在失败时重试
        
        Args:
            config: 重试配置，如果为None则使用默认配置
        """
        retry_config = config or self.config
        
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                return self._execute_with_retry(func, retry_config, *args, **kwargs)
            return wrapper
        return decorator
    
    def _execute_with_retry(self, func: Callable, config: RetryConfig, *args, **kwargs) -> Any:
        """执行函数并在失败时重试"""
        self.error_stats['total_calls'] += 1
        last_exception = None
        
        for attempt in range(config.max_attempts):
            try:
                result = func(*args, **kwargs)
                
                # 成功执行
                if attempt > 0:
                    self.error_stats['success_after_retry'] += 1
                    self.logger.info(f"函数 {func.__name__} 在第{attempt+1}次尝试后成功")
                
                return result
                
            except Exception as e:
                last_exception = e
                error_msg = str(e)
                
                # 记录错误
                if attempt == 0:
                    self.error_stats['failed_calls'] += 1
                else:
                    self.error_stats['retry_calls'] += 1
                
                # 检查是否为可重试错误
                if not self._is_retryable_error(error_msg):
                    self.logger.error(f"函数 {func.__name__} 遇到不可重试错误: {error_msg}")
                    self.error_stats['permanent_failures'] += 1
                    raise e
                
                # 如果是最后一次尝试，抛出异常
                if attempt == config.max_attempts - 1:
                    self.logger.error(f"函数 {func.__name__} 在{config.max_attempts}次尝试后仍然失败: {error_msg}")
                    self.error_stats['permanent_failures'] += 1
                    raise e
                
                # 计算延迟时间
                delay = self._calculate_delay(attempt, config)
                
                self.logger.warning(f"函数 {func.__name__} 第{attempt+1}次尝试失败: {error_msg}, {delay:.1f}秒后重试")
                time.sleep(delay)
        
        # 理论上不会到达这里
        raise last_exception
    
    def _is_retryable_error(self, error_msg: str) -> bool:
        """判断错误是否可重试"""
        error_msg_lower = error_msg.lower()
        
        # 检查所有可重试错误类型
        for error_category, error_patterns in self.retryable_errors.items():
            for pattern in error_patterns:
                if pattern.lower() in error_msg_lower:
                    return True
        
        return False
    
    def _calculate_delay(self, attempt: int, config: RetryConfig) -> float:
        """计算延迟时间"""
        if config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = config.base_delay * (config.backoff_factor ** attempt)
        elif config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = config.base_delay * (attempt + 1)
        else:  # FIXED_INTERVAL
            delay = config.base_delay
        
        # 限制最大延迟
        delay = min(delay, config.max_delay)
        
        # 添加随机抖动
        if config.jitter:
            jitter_range = delay * 0.1  # 10%的抖动
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0.1, delay)  # 最小延迟0.1秒
    
    def execute_with_fallback(self, primary_func: Callable, fallback_func: Callable, 
                            *args, **kwargs) -> Any:
        """
        执行主函数，失败时使用备用函数
        
        Args:
            primary_func: 主函数
            fallback_func: 备用函数
            *args, **kwargs: 函数参数
            
        Returns:
            函数执行结果
        """
        try:
            return self._execute_with_retry(primary_func, self.config, *args, **kwargs)
        except Exception as e:
            self.logger.warning(f"主函数 {primary_func.__name__} 失败，尝试备用函数: {e}")
            try:
                result = fallback_func(*args, **kwargs)
                self.logger.info(f"备用函数 {fallback_func.__name__} 执行成功")
                return result
            except Exception as fallback_error:
                self.logger.error(f"备用函数 {fallback_func.__name__} 也失败: {fallback_error}")
                raise e  # 抛出原始错误
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """获取错误统计信息"""
        total_calls = self.error_stats['total_calls']
        if total_calls == 0:
            return {
                'success_rate': 100.0,
                'retry_rate': 0.0,
                'failure_rate': 0.0,
                **self.error_stats
            }
        
        success_calls = total_calls - self.error_stats['permanent_failures']
        
        return {
            'success_rate': (success_calls / total_calls) * 100,
            'retry_rate': (self.error_stats['retry_calls'] / total_calls) * 100,
            'failure_rate': (self.error_stats['permanent_failures'] / total_calls) * 100,
            **self.error_stats
        }
    
    def reset_statistics(self):
        """重置错误统计"""
        self.error_stats = {
            'total_calls': 0,
            'failed_calls': 0,
            'retry_calls': 0,
            'success_after_retry': 0,
            'permanent_failures': 0
        }
    
    def log_statistics(self):
        """记录统计信息"""
        stats = self.get_error_statistics()
        
        self.logger.info("API重试统计:")
        self.logger.info(f"  总调用次数: {stats['total_calls']}")
        self.logger.info(f"  成功率: {stats['success_rate']:.1f}%")
        self.logger.info(f"  重试率: {stats['retry_rate']:.1f}%")
        self.logger.info(f"  失败率: {stats['failure_rate']:.1f}%")
        self.logger.info(f"  重试后成功: {stats['success_after_retry']}")
        self.logger.info(f"  永久失败: {stats['permanent_failures']}")

# 全局重试处理器实例
default_retry_handler = APIRetryHandler()

# 便捷装饰器
def retry_on_api_error(max_attempts: int = 3, base_delay: float = 1.0):
    """便捷的重试装饰器"""
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF
    )
    return default_retry_handler.retry_on_failure(config)

def retry_with_linear_backoff(max_attempts: int = 3, base_delay: float = 2.0):
    """线性退避重试装饰器"""
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        strategy=RetryStrategy.LINEAR_BACKOFF
    )
    return default_retry_handler.retry_on_failure(config)
