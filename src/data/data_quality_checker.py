#!/usr/bin/env python3
"""
数据质量检查器
检查和验证从OKX API获取的数据质量
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
from dataclasses import dataclass

@dataclass
class DataQualityReport:
    """数据质量报告"""
    is_valid: bool
    issues: List[str]
    warnings: List[str]
    data_points: int
    time_range: Tuple[datetime, datetime]
    quality_score: float  # 0-100分

class DataQualityChecker:
    """数据质量检查器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 质量检查阈值
        self.price_change_threshold = 0.10  # 10%价格变化阈值
        self.volume_change_threshold = 5.0   # 5倍成交量变化阈值
        self.missing_data_threshold = 0.05   # 5%缺失数据阈值
        self.time_gap_threshold = 300        # 5分钟时间间隔阈值(秒)
    
    def validate_kline_data(self, klines: List[List]) -> DataQualityReport:
        """
        验证K线数据质量
        
        Args:
            klines: K线数据列表 [[timestamp, open, high, low, close, volume], ...]
            
        Returns:
            数据质量报告
        """
        issues = []
        warnings = []
        quality_score = 100.0
        
        if not klines:
            return DataQualityReport(
                is_valid=False,
                issues=["数据为空"],
                warnings=[],
                data_points=0,
                time_range=(datetime.now(), datetime.now()),
                quality_score=0.0
            )
        
        # 转换数据格式
        try:
            data = []
            for kline in klines:
                if len(kline) < 6:
                    issues.append(f"K线数据格式不完整: {len(kline)} < 6")
                    continue
                
                timestamp = int(kline[0])
                open_price = float(kline[1])
                high_price = float(kline[2])
                low_price = float(kline[3])
                close_price = float(kline[4])
                volume = float(kline[5])
                
                data.append({
                    'timestamp': timestamp,
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'volume': volume,
                    'datetime': datetime.fromtimestamp(timestamp / 1000)
                })
        except (ValueError, TypeError) as e:
            issues.append(f"数据类型转换错误: {e}")
            quality_score -= 30
        
        if not data:
            return DataQualityReport(
                is_valid=False,
                issues=issues + ["没有有效的数据点"],
                warnings=warnings,
                data_points=0,
                time_range=(datetime.now(), datetime.now()),
                quality_score=0.0
            )
        
        # 按时间排序
        data.sort(key=lambda x: x['timestamp'])
        
        # 时间范围
        time_range = (data[0]['datetime'], data[-1]['datetime'])
        
        # 1. 检查价格逻辑性
        price_issues = self._check_price_logic(data)
        issues.extend(price_issues)
        if price_issues:
            quality_score -= len(price_issues) * 5
        
        # 2. 检查价格异常波动
        volatility_issues = self._check_price_volatility(data)
        if volatility_issues:
            warnings.extend(volatility_issues)
            quality_score -= len(volatility_issues) * 3
        
        # 3. 检查成交量异常
        volume_issues = self._check_volume_anomalies(data)
        if volume_issues:
            warnings.extend(volume_issues)
            quality_score -= len(volume_issues) * 2
        
        # 4. 检查时间连续性
        time_issues = self._check_time_continuity(data)
        if time_issues:
            warnings.extend(time_issues)
            quality_score -= len(time_issues) * 4
        
        # 5. 检查数据完整性
        completeness_issues = self._check_data_completeness(data)
        issues.extend(completeness_issues)
        if completeness_issues:
            quality_score -= len(completeness_issues) * 10
        
        # 确保质量分数不低于0
        quality_score = max(0.0, quality_score)
        
        # 判断数据是否有效
        is_valid = len(issues) == 0 and quality_score >= 60.0
        
        return DataQualityReport(
            is_valid=is_valid,
            issues=issues,
            warnings=warnings,
            data_points=len(data),
            time_range=time_range,
            quality_score=quality_score
        )
    
    def _check_price_logic(self, data: List[Dict]) -> List[str]:
        """检查价格逻辑性"""
        issues = []
        
        for i, kline in enumerate(data):
            open_price = kline['open']
            high_price = kline['high']
            low_price = kline['low']
            close_price = kline['close']
            
            # 检查OHLC逻辑
            if high_price < max(open_price, close_price):
                issues.append(f"第{i+1}根K线: 最高价({high_price})低于开盘价或收盘价")
            
            if low_price > min(open_price, close_price):
                issues.append(f"第{i+1}根K线: 最低价({low_price})高于开盘价或收盘价")
            
            if high_price < low_price:
                issues.append(f"第{i+1}根K线: 最高价({high_price})低于最低价({low_price})")
            
            # 检查价格为零或负数
            if any(price <= 0 for price in [open_price, high_price, low_price, close_price]):
                issues.append(f"第{i+1}根K线: 存在零或负价格")
        
        return issues
    
    def _check_price_volatility(self, data: List[Dict]) -> List[str]:
        """检查价格异常波动"""
        warnings = []
        
        if len(data) < 2:
            return warnings
        
        for i in range(1, len(data)):
            prev_close = data[i-1]['close']
            curr_open = data[i]['open']
            curr_close = data[i]['close']
            
            # 检查开盘价跳空
            if prev_close > 0:  # 避免除零错误
                gap_ratio = abs(curr_open - prev_close) / prev_close
                if gap_ratio > self.price_change_threshold:
                    warnings.append(f"第{i+1}根K线: 开盘价跳空{gap_ratio:.2%}")
            else:
                warnings.append(f"第{i}根K线: 前收盘价为零，无法计算跳空")
            
            # 检查单根K线涨跌幅
            if curr_open > 0:  # 避免除零错误
                change_ratio = abs(curr_close - curr_open) / curr_open
                if change_ratio > self.price_change_threshold:
                    warnings.append(f"第{i+1}根K线: 单根涨跌幅{change_ratio:.2%}")
            else:
                warnings.append(f"第{i+1}根K线: 开盘价为零，无法计算涨跌幅")
        
        return warnings
    
    def _check_volume_anomalies(self, data: List[Dict]) -> List[str]:
        """检查成交量异常"""
        warnings = []
        
        if len(data) < 2:
            return warnings
        
        volumes = [kline['volume'] for kline in data]
        avg_volume = np.mean(volumes)
        
        for i, kline in enumerate(data):
            volume = kline['volume']
            
            # 检查零成交量
            if volume == 0:
                warnings.append(f"第{i+1}根K线: 成交量为零")
            
            # 检查异常大成交量
            elif volume > avg_volume * self.volume_change_threshold:
                ratio = volume / avg_volume
                warnings.append(f"第{i+1}根K线: 成交量异常({ratio:.1f}倍平均值)")
        
        return warnings
    
    def _check_time_continuity(self, data: List[Dict]) -> List[str]:
        """检查时间连续性"""
        warnings = []
        
        if len(data) < 2:
            return warnings
        
        for i in range(1, len(data)):
            prev_time = data[i-1]['timestamp']
            curr_time = data[i]['timestamp']
            
            time_gap = (curr_time - prev_time) / 1000  # 转换为秒
            
            if time_gap > self.time_gap_threshold:
                gap_minutes = time_gap / 60
                warnings.append(f"第{i}到{i+1}根K线: 时间间隔过大({gap_minutes:.1f}分钟)")
            
            if time_gap <= 0:
                warnings.append(f"第{i}到{i+1}根K线: 时间顺序错误")
        
        return warnings
    
    def _check_data_completeness(self, data: List[Dict]) -> List[str]:
        """检查数据完整性"""
        issues = []
        
        # 检查必需字段
        required_fields = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        
        for i, kline in enumerate(data):
            for field in required_fields:
                if field not in kline or kline[field] is None:
                    issues.append(f"第{i+1}根K线: 缺少{field}字段")
        
        return issues
    
    def validate_price_data(self, price: float, symbol: str = "BTC-USDT") -> bool:
        """
        验证单个价格数据

        Args:
            price: 价格
            symbol: 交易对

        Returns:
            是否有效
        """
        if price <= 0:
            self.logger.warning(f"{symbol} 价格无效: {price}")
            return False

        # 基本价格合理性检查 - 更宽松的范围
        if price > 1000000:  # 价格不应超过100万
            self.logger.warning(f"{symbol} 价格异常过高: {price}")
            return False

        # 对于极小价格的检查 - 允许小数点后很多位
        if price < 1e-12:  # 价格不应小于1e-12
            self.logger.warning(f"{symbol} 价格异常过小: {price}")
            return False

        # 特定币种的价格范围检查
        if symbol.startswith("BTC") and (price < 1000 or price > 500000):
            self.logger.warning(f"{symbol} BTC价格异常: {price}")
            return False
        elif symbol.startswith("ETH") and (price < 100 or price > 50000):
            self.logger.warning(f"{symbol} ETH价格异常: {price}")
            return False

        return True
    
    def log_quality_report(self, report: DataQualityReport, symbol: str = ""):
        """记录质量报告"""
        prefix = f"[{symbol}] " if symbol else ""
        
        self.logger.info(f"{prefix}数据质量报告:")
        self.logger.info(f"  有效性: {'✅' if report.is_valid else '❌'}")
        self.logger.info(f"  数据点: {report.data_points}")
        self.logger.info(f"  质量分数: {report.quality_score:.1f}/100")
        self.logger.info(f"  时间范围: {report.time_range[0]} - {report.time_range[1]}")
        
        if report.issues:
            self.logger.warning(f"  问题 ({len(report.issues)}):")
            for issue in report.issues:
                self.logger.warning(f"    - {issue}")
        
        if report.warnings:
            self.logger.info(f"  警告 ({len(report.warnings)}):")
            for warning in report.warnings[:5]:  # 只显示前5个警告
                self.logger.info(f"    - {warning}")
            if len(report.warnings) > 5:
                self.logger.info(f"    ... 还有{len(report.warnings)-5}个警告")
