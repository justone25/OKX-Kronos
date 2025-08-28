#!/usr/bin/env python3
"""
通用工具函数库
统一常用的工具函数，避免重复实现
"""
import os
import sys
import logging
import signal
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List


def setup_project_path(file_path: str) -> Path:
    """
    设置项目路径，统一处理sys.path
    
    Args:
        file_path: 当前文件的__file__路径
        
    Returns:
        项目根目录路径
    """
    project_root = Path(file_path).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    return project_root


def setup_logging(log_level: str = "INFO", 
                 log_file: Optional[str] = None,
                 format_string: Optional[str] = None) -> logging.Logger:
    """
    统一的日志配置
    
    Args:
        log_level: 日志级别
        log_file: 日志文件路径（可选）
        format_string: 自定义格式字符串（可选）
        
    Returns:
        配置好的logger
    """
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    handlers = [logging.StreamHandler()]
    
    if log_file:
        # 确保日志目录存在
        log_dir = Path(log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, mode='a'))
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=format_string,
        handlers=handlers
    )
    
    return logging.getLogger(__name__)


def setup_signal_handlers(cleanup_func: Optional[callable] = None):
    """
    统一的信号处理器设置
    
    Args:
        cleanup_func: 清理函数，在收到信号时调用
    """
    def signal_handler(signum, frame):
        logger = logging.getLogger(__name__)
        logger.info(f"收到信号 {signum}，正在停止程序...")
        
        if cleanup_func:
            try:
                cleanup_func()
            except Exception as e:
                logger.error(f"清理函数执行失败: {e}")
        
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def create_base_parser(description: str) -> argparse.ArgumentParser:
    """
    创建基础的参数解析器，包含常用参数
    
    Args:
        description: 程序描述
        
    Returns:
        配置好的ArgumentParser
    """
    parser = argparse.ArgumentParser(description=description)
    
    # 通用参数
    parser.add_argument("--log-level", type=str, default="INFO",
                       choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="日志级别")
    parser.add_argument("--config", type=str, default="./config/daytime_strategy.yaml",
                       help="配置文件路径")
    parser.add_argument("--dry-run", action="store_true",
                       help="干运行模式（不执行实际操作）")
    
    return parser


def print_banner(title: str, subtitle: str = "", width: int = 60):
    """
    打印程序横幅
    
    Args:
        title: 主标题
        subtitle: 副标题（可选）
        width: 横幅宽度
    """
    print("=" * width)
    print(f"{title:^{width}}")
    if subtitle:
        print(f"{subtitle:^{width}}")
    print("=" * width)


def print_status_info(info_dict: Dict[str, Any], title: str = "状态信息"):
    """
    打印状态信息
    
    Args:
        info_dict: 状态信息字典
        title: 标题
    """
    print(f"\n📊 {title}")
    print("-" * 40)
    for key, value in info_dict.items():
        print(f"{key:20}: {value}")
    print()


def safe_float_convert(value: Any, default: float = 0.0) -> float:
    """
    安全的浮点数转换
    
    Args:
        value: 要转换的值
        default: 默认值
        
    Returns:
        转换后的浮点数
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int_convert(value: Any, default: int = 0) -> int:
    """
    安全的整数转换
    
    Args:
        value: 要转换的值
        default: 默认值
        
    Returns:
        转换后的整数
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def format_timestamp(timestamp: datetime = None, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    格式化时间戳
    
    Args:
        timestamp: 时间戳（默认为当前时间）
        format_str: 格式字符串
        
    Returns:
        格式化后的时间字符串
    """
    if timestamp is None:
        timestamp = datetime.now()
    return timestamp.strftime(format_str)


def ensure_directory(path: str) -> Path:
    """
    确保目录存在
    
    Args:
        path: 目录路径
        
    Returns:
        Path对象
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def get_file_size_mb(file_path: str) -> float:
    """
    获取文件大小（MB）
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件大小（MB）
    """
    try:
        size_bytes = os.path.getsize(file_path)
        return size_bytes / (1024 * 1024)
    except OSError:
        return 0.0


def truncate_string(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """
    截断字符串
    
    Args:
        text: 原始字符串
        max_length: 最大长度
        suffix: 后缀
        
    Returns:
        截断后的字符串
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def validate_config_file(config_path: str) -> bool:
    """
    验证配置文件是否存在
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        是否存在
    """
    return Path(config_path).exists()


def get_memory_usage_mb() -> float:
    """
    获取当前进程内存使用量（MB）
    
    Returns:
        内存使用量（MB）
    """
    try:
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)
    except ImportError:
        return 0.0


def format_number(number: float, precision: int = 2, use_comma: bool = True) -> str:
    """
    格式化数字显示
    
    Args:
        number: 数字
        precision: 小数位数
        use_comma: 是否使用千分位分隔符
        
    Returns:
        格式化后的字符串
    """
    if use_comma:
        return f"{number:,.{precision}f}"
    else:
        return f"{number:.{precision}f}"
