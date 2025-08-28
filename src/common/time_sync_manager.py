#!/usr/bin/env python3
"""
时间同步管理器
解决不同数据源的时间同步问题
"""
import time
import logging
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

class DataSource(Enum):
    """数据源类型"""
    OKX_REALTIME = "okx_realtime"
    AI_PREDICTION = "ai_prediction"
    KRONOS_PREDICTION = "kronos_prediction"
    TECHNICAL_SIGNAL = "technical_signal"

@dataclass
class TimestampedData:
    """带时间戳的数据"""
    data: Any
    timestamp: datetime
    source: DataSource
    validity_seconds: int = 300  # 数据有效期（秒）
    
    @property
    def is_valid(self) -> bool:
        """检查数据是否仍然有效"""
        age = (datetime.now() - self.timestamp).total_seconds()
        return age <= self.validity_seconds
    
    @property
    def age_seconds(self) -> float:
        """获取数据年龄（秒）"""
        return (datetime.now() - self.timestamp).total_seconds()

class TimeSyncManager:
    """时间同步管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 数据存储
        self._data_cache: Dict[DataSource, TimestampedData] = {}
        
        # 时间同步配置
        self.sync_tolerance = {
            DataSource.OKX_REALTIME: 10,      # 实时数据10秒容忍度
            DataSource.AI_PREDICTION: 300,    # AI预测5分钟容忍度
            DataSource.KRONOS_PREDICTION: 600, # Kronos预测10分钟容忍度
            DataSource.TECHNICAL_SIGNAL: 60   # 技术信号1分钟容忍度
        }
        
        # 数据有效期配置
        self.validity_periods = {
            DataSource.OKX_REALTIME: 30,      # 实时数据30秒有效
            DataSource.AI_PREDICTION: 300,    # AI预测5分钟有效
            DataSource.KRONOS_PREDICTION: 600, # Kronos预测10分钟有效
            DataSource.TECHNICAL_SIGNAL: 120  # 技术信号2分钟有效
        }
        
        # 统计信息
        self.stats = {
            'total_updates': 0,
            'sync_conflicts': 0,
            'expired_data_removed': 0,
            'successful_syncs': 0
        }
    
    def update_data(self, source: DataSource, data: Any, 
                   timestamp: Optional[datetime] = None) -> bool:
        """
        更新数据源的数据
        
        Args:
            source: 数据源类型
            data: 数据内容
            timestamp: 数据时间戳，如果为None则使用当前时间
            
        Returns:
            是否更新成功
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # 创建时间戳数据
        validity_seconds = self.validity_periods.get(source, 300)
        timestamped_data = TimestampedData(
            data=data,
            timestamp=timestamp,
            source=source,
            validity_seconds=validity_seconds
        )
        
        # 检查时间同步冲突
        if self._check_sync_conflict(source, timestamp):
            self.stats['sync_conflicts'] += 1
            self.logger.warning(f"时间同步冲突: {source.value} 数据时间戳异常")
        
        # 更新数据
        self._data_cache[source] = timestamped_data
        self.stats['total_updates'] += 1
        
        self.logger.debug(f"更新数据: {source.value} at {timestamp}")
        return True
    
    def get_data(self, source: DataSource, max_age_seconds: Optional[int] = None) -> Optional[Any]:
        """
        获取数据源的数据
        
        Args:
            source: 数据源类型
            max_age_seconds: 最大数据年龄（秒），超过则返回None
            
        Returns:
            数据内容，如果数据过期或不存在则返回None
        """
        if source not in self._data_cache:
            return None
        
        timestamped_data = self._data_cache[source]
        
        # 检查数据是否过期
        if not timestamped_data.is_valid:
            self.logger.debug(f"数据已过期: {source.value}")
            return None
        
        # 检查自定义年龄限制
        if max_age_seconds is not None:
            if timestamped_data.age_seconds > max_age_seconds:
                self.logger.debug(f"数据超过年龄限制: {source.value} ({timestamped_data.age_seconds:.1f}s > {max_age_seconds}s)")
                return None
        
        return timestamped_data.data
    
    def get_synchronized_data(self, sources: list[DataSource], 
                            sync_window_seconds: int = 60) -> Dict[DataSource, Any]:
        """
        获取时间同步的数据集合
        
        Args:
            sources: 需要同步的数据源列表
            sync_window_seconds: 同步时间窗口（秒）
            
        Returns:
            同步的数据字典，只包含在时间窗口内的数据
        """
        synchronized_data = {}
        reference_time = None
        
        # 找到最新的数据时间作为参考时间
        for source in sources:
            if source in self._data_cache:
                timestamped_data = self._data_cache[source]
                if timestamped_data.is_valid:
                    if reference_time is None or timestamped_data.timestamp > reference_time:
                        reference_time = timestamped_data.timestamp
        
        if reference_time is None:
            self.logger.warning("没有找到有效的参考时间")
            return {}
        
        # 收集在同步窗口内的数据
        for source in sources:
            if source in self._data_cache:
                timestamped_data = self._data_cache[source]
                if timestamped_data.is_valid:
                    time_diff = abs((timestamped_data.timestamp - reference_time).total_seconds())
                    if time_diff <= sync_window_seconds:
                        synchronized_data[source] = timestamped_data.data
                    else:
                        self.logger.debug(f"数据超出同步窗口: {source.value} ({time_diff:.1f}s > {sync_window_seconds}s)")
        
        if len(synchronized_data) == len(sources):
            self.stats['successful_syncs'] += 1
            self.logger.debug(f"成功同步{len(sources)}个数据源")
        else:
            self.logger.warning(f"部分数据源同步失败: {len(synchronized_data)}/{len(sources)}")
        
        return synchronized_data
    
    def get_data_freshness(self, source: DataSource) -> Optional[Dict[str, Any]]:
        """
        获取数据新鲜度信息
        
        Args:
            source: 数据源类型
            
        Returns:
            新鲜度信息字典
        """
        if source not in self._data_cache:
            return None
        
        timestamped_data = self._data_cache[source]
        age_seconds = timestamped_data.age_seconds
        validity_seconds = timestamped_data.validity_seconds
        
        return {
            'source': source.value,
            'timestamp': timestamped_data.timestamp,
            'age_seconds': age_seconds,
            'validity_seconds': validity_seconds,
            'is_valid': timestamped_data.is_valid,
            'freshness_ratio': max(0, (validity_seconds - age_seconds) / validity_seconds),
            'expires_in': max(0, validity_seconds - age_seconds)
        }
    
    def cleanup_expired_data(self) -> int:
        """
        清理过期数据
        
        Returns:
            清理的数据条数
        """
        expired_sources = []
        
        for source, timestamped_data in self._data_cache.items():
            if not timestamped_data.is_valid:
                expired_sources.append(source)
        
        for source in expired_sources:
            del self._data_cache[source]
            self.stats['expired_data_removed'] += 1
            self.logger.debug(f"清理过期数据: {source.value}")
        
        return len(expired_sources)
    
    def _check_sync_conflict(self, source: DataSource, timestamp: datetime) -> bool:
        """检查时间同步冲突"""
        now = datetime.now()
        tolerance = self.sync_tolerance.get(source, 60)
        
        # 检查时间戳是否在合理范围内
        time_diff = abs((timestamp - now).total_seconds())
        
        if time_diff > tolerance:
            return True
        
        # 检查与其他数据源的时间差异
        for other_source, other_data in self._data_cache.items():
            if other_source != source and other_data.is_valid:
                other_time_diff = abs((timestamp - other_data.timestamp).total_seconds())
                max_allowed_diff = max(tolerance, self.sync_tolerance.get(other_source, 60))
                
                if other_time_diff > max_allowed_diff:
                    self.logger.debug(f"时间差异过大: {source.value} vs {other_source.value} ({other_time_diff:.1f}s)")
        
        return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        active_sources = len(self._data_cache)
        valid_sources = sum(1 for data in self._data_cache.values() if data.is_valid)
        
        return {
            **self.stats,
            'active_sources': active_sources,
            'valid_sources': valid_sources,
            'cache_hit_rate': (self.stats['successful_syncs'] / max(1, self.stats['total_updates'])) * 100
        }
    
    def reset_statistics(self):
        """重置统计信息"""
        self.stats = {
            'total_updates': 0,
            'sync_conflicts': 0,
            'expired_data_removed': 0,
            'successful_syncs': 0
        }
    
    def log_status(self):
        """记录当前状态"""
        stats = self.get_statistics()
        
        self.logger.info("时间同步管理器状态:")
        self.logger.info(f"  活跃数据源: {stats['active_sources']}")
        self.logger.info(f"  有效数据源: {stats['valid_sources']}")
        self.logger.info(f"  总更新次数: {stats['total_updates']}")
        self.logger.info(f"  同步冲突: {stats['sync_conflicts']}")
        self.logger.info(f"  成功同步: {stats['successful_syncs']}")
        self.logger.info(f"  缓存命中率: {stats['cache_hit_rate']:.1f}%")
        
        # 显示各数据源的新鲜度
        for source in DataSource:
            freshness = self.get_data_freshness(source)
            if freshness:
                self.logger.info(f"  {source.value}: {freshness['age_seconds']:.1f}s old, "
                               f"{freshness['freshness_ratio']:.1%} fresh")

# 全局时间同步管理器实例
global_time_sync = TimeSyncManager()
