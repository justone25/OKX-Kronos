#!/usr/bin/env python3
"""
Kronos预测集成模块
从现有的Kronos预测系统中获取预测结果并转换为交易信号
"""
import os
import logging
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..common.signals import TradingSignal, SignalType


class KronosTrend(Enum):
    """Kronos趋势方向"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    UP = "up"           # 对应数据库中的"up"
    DOWN = "down"       # 对应数据库中的"down"
    SIDEWAYS = "sideways"  # 对应数据库中的"sideways"
    UNKNOWN = "unknown"


@dataclass
class KronosPrediction:
    """Kronos预测结果"""
    timestamp: datetime
    current_price: float
    predicted_price: float
    price_change: float
    price_change_pct: float
    trend_direction: KronosTrend
    volatility: float
    confidence: float
    pred_hours: int
    lookback_hours: int


class KronosPredictor:
    """Kronos预测器集成类"""
    
    def __init__(self, db_path: str = "./data/predictions.db"):
        """
        初始化Kronos预测器
        
        Args:
            db_path: 预测数据库路径
        """
        self.logger = logging.getLogger(__name__)
        self.db_path = db_path
        
        # 检查数据库是否存在
        if not os.path.exists(db_path):
            self.logger.warning(f"Kronos预测数据库不存在: {db_path}")
            self.logger.warning("请确保Kronos预测调度器正在运行")
        
        self.logger.info("Kronos预测器集成初始化完成")
    
    def get_latest_prediction(self, instrument: str = "BTC-USDT-SWAP", max_age_minutes: int = 30) -> Optional[KronosPrediction]:
        """
        获取最新的Kronos预测

        Args:
            instrument: 交易品种 (如 "BTC-USDT-SWAP", "ETH-USDT-SWAP")
            max_age_minutes: 预测的最大年龄（分钟），超过此时间的预测被认为过期

        Returns:
            最新的Kronos预测结果，如果没有或过期则返回None
        """
        try:
            if not os.path.exists(self.db_path):
                self.logger.warning("预测数据库不存在")
                return None
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 计算时间阈值
            cutoff_time = (datetime.now() - timedelta(minutes=max_age_minutes)).isoformat()
            
            # 查询指定品种的最新预测
            cursor.execute('''
                SELECT timestamp, current_price, predicted_price, price_change,
                       price_change_pct, trend_direction, volatility, pred_hours, lookback_hours
                FROM predictions
                WHERE timestamp > ? AND instrument = ?
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (cutoff_time, instrument))
            
            result = cursor.fetchone()
            conn.close()
            
            if not result:
                self.logger.warning(f"未找到{instrument}在{max_age_minutes}分钟内的Kronos预测")
                return None
            
            # 解析结果
            trend_direction_str = result[5]

            # 映射数据库中的趋势方向到枚举
            trend_mapping = {
                'up': KronosTrend.UP,
                'down': KronosTrend.DOWN,
                'sideways': KronosTrend.SIDEWAYS,
                'bullish': KronosTrend.BULLISH,
                'bearish': KronosTrend.BEARISH,
                'neutral': KronosTrend.NEUTRAL
            }

            trend_direction = trend_mapping.get(trend_direction_str, KronosTrend.UNKNOWN)

            prediction = KronosPrediction(
                timestamp=datetime.fromisoformat(result[0]),
                current_price=float(result[1]),
                predicted_price=float(result[2]),
                price_change=float(result[3]),
                price_change_pct=float(result[4]),
                trend_direction=trend_direction,
                volatility=float(result[6]),
                pred_hours=int(result[7]),
                lookback_hours=int(result[8]),
                confidence=self._calculate_confidence(result)
            )
            
            self.logger.info(f"获取到Kronos预测: {prediction.trend_direction.value} "
                           f"({prediction.price_change_pct:+.2%})")
            
            return prediction
            
        except Exception as e:
            self.logger.error(f"获取Kronos预测失败: {e}")
            return None
    
    def _calculate_confidence(self, prediction_data: tuple) -> float:
        """
        根据预测数据计算置信度

        Args:
            prediction_data: 数据库查询结果

        Returns:
            置信度 (0-1)
        """
        try:
            # 数据库中的price_change_pct已经是百分比形式（如-0.3269表示-0.3269%）
            price_change_pct = abs(float(prediction_data[4]))
            volatility = float(prediction_data[6])

            # 基础置信度
            base_confidence = 0.6

            # 根据价格变化幅度调整置信度
            # 变化越大，置信度越高（但有上限）
            # price_change_pct已经是百分比，如0.5表示0.5%
            change_factor = min(price_change_pct * 0.1, 0.2)  # 最多增加20%

            # 根据波动率调整置信度
            # 数据库中的波动率是绝对值，需要转换为百分比
            volatility_pct = volatility / 1000  # 假设波动率是以点为单位

            if 0.5 <= volatility_pct <= 2.0:  # 0.5%-2%波动率较合理
                volatility_factor = 0.1
            elif volatility_pct < 0.5:  # 波动率过低
                volatility_factor = -0.05
            else:  # 波动率过高
                volatility_factor = -0.1

            confidence = base_confidence + change_factor + volatility_factor

            # 限制在0.3-0.9之间
            return max(0.3, min(0.9, confidence))

        except Exception as e:
            self.logger.error(f"计算置信度失败: {e}")
            return 0.5
    
    def get_prediction_history(self, hours: int = 24) -> List[KronosPrediction]:
        """
        获取历史预测记录
        
        Args:
            hours: 获取多少小时内的预测
            
        Returns:
            预测历史列表
        """
        try:
            if not os.path.exists(self.db_path):
                return []
            
            conn = sqlite3.connect(self.db_path)
            
            cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            query = '''
                SELECT timestamp, current_price, predicted_price, price_change,
                       price_change_pct, trend_direction, volatility, pred_hours, lookback_hours
                FROM predictions 
                WHERE timestamp > ?
                ORDER BY timestamp DESC
            '''
            
            df = pd.read_sql_query(query, conn, params=(cutoff_time,))
            conn.close()
            
            predictions = []
            for _, row in df.iterrows():
                # 映射趋势方向
                trend_direction_str = row['trend_direction']
                trend_mapping = {
                    'up': KronosTrend.UP,
                    'down': KronosTrend.DOWN,
                    'sideways': KronosTrend.SIDEWAYS,
                    'bullish': KronosTrend.BULLISH,
                    'bearish': KronosTrend.BEARISH,
                    'neutral': KronosTrend.NEUTRAL
                }
                trend_direction = trend_mapping.get(trend_direction_str, KronosTrend.UNKNOWN)

                prediction = KronosPrediction(
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    current_price=float(row['current_price']),
                    predicted_price=float(row['predicted_price']),
                    price_change=float(row['price_change']),
                    price_change_pct=float(row['price_change_pct']),
                    trend_direction=trend_direction,
                    volatility=float(row['volatility']),
                    pred_hours=int(row['pred_hours']),
                    lookback_hours=int(row['lookback_hours']),
                    confidence=self._calculate_confidence((
                        row['timestamp'], row['current_price'], row['predicted_price'],
                        row['price_change'], row['price_change_pct'], row['trend_direction'],
                        row['volatility'], row['pred_hours'], row['lookback_hours']
                    ))
                )
                predictions.append(prediction)
            
            return predictions
            
        except Exception as e:
            self.logger.error(f"获取预测历史失败: {e}")
            return []
    
    def convert_to_trading_signal(self, prediction: KronosPrediction, 
                                current_price: float) -> TradingSignal:
        """
        将Kronos预测转换为交易信号
        
        Args:
            prediction: Kronos预测结果
            current_price: 当前价格
            
        Returns:
            交易信号
        """
        # 转换趋势方向到信号类型
        if prediction.trend_direction in [KronosTrend.BULLISH, KronosTrend.UP]:
            signal_type = SignalType.BUY
        elif prediction.trend_direction in [KronosTrend.BEARISH, KronosTrend.DOWN]:
            signal_type = SignalType.SELL
        else:
            signal_type = SignalType.HOLD
        
        # 计算止损止盈价格
        stop_loss = None
        take_profit = None
        
        if signal_type == SignalType.BUY:
            stop_loss = current_price * 0.98  # 2%止损
            take_profit = prediction.predicted_price
        elif signal_type == SignalType.SELL:
            stop_loss = current_price * 1.02  # 2%止损
            take_profit = prediction.predicted_price
        
        # 构建理由说明
        age_minutes = (datetime.now() - prediction.timestamp).total_seconds() / 60
        reason = (f"Kronos预测({prediction.pred_hours}小时): {prediction.trend_direction.value} "
                 f"目标${prediction.predicted_price:,.0f} ({prediction.price_change_pct:+.2f}%) "
                 f"波动率{prediction.volatility:.2f} [{age_minutes:.0f}分钟前]")
        
        return TradingSignal(
            signal_type=signal_type,
            strength=abs(prediction.price_change_pct) * 10,  # 将百分比转换为0-1强度
            confidence=prediction.confidence,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=reason
        )
    
    def get_prediction_summary(self, prediction: KronosPrediction) -> str:
        """
        获取预测摘要
        
        Args:
            prediction: 预测结果
            
        Returns:
            预测摘要字符串
        """
        trend_emoji = {
            KronosTrend.BULLISH: "📈",
            KronosTrend.BEARISH: "📉",
            KronosTrend.UP: "📈",
            KronosTrend.DOWN: "📉",
            KronosTrend.SIDEWAYS: "➡️",
            KronosTrend.NEUTRAL: "➡️",
            KronosTrend.UNKNOWN: "❓"
        }
        
        emoji = trend_emoji.get(prediction.trend_direction, "❓")
        age_minutes = (datetime.now() - prediction.timestamp).total_seconds() / 60
        
        return (f"{emoji} Kronos {prediction.trend_direction.value.upper()} "
                f"${prediction.current_price:,.0f} → ${prediction.predicted_price:,.0f} "
                f"({prediction.price_change_pct:+.2f}%) "
                f"置信度:{prediction.confidence:.1%} "
                f"[{age_minutes:.0f}分钟前]")
    
    def is_prediction_available(self, instrument: str = "BTC-USDT-SWAP", max_age_minutes: int = 30) -> bool:
        """
        检查是否有可用的预测

        Args:
            instrument: 交易品种
            max_age_minutes: 最大年龄限制

        Returns:
            是否有可用预测
        """
        prediction = self.get_latest_prediction(instrument, max_age_minutes)
        return prediction is not None
    
    def get_prediction_stats(self, hours: int = 24) -> Dict[str, any]:
        """
        获取预测统计信息
        
        Args:
            hours: 统计时间范围
            
        Returns:
            统计信息字典
        """
        try:
            predictions = self.get_prediction_history(hours)
            
            if not predictions:
                return {
                    "total_predictions": 0,
                    "avg_confidence": 0.0,
                    "trend_distribution": {},
                    "avg_volatility": 0.0
                }
            
            # 计算统计信息
            total = len(predictions)
            avg_confidence = sum(p.confidence for p in predictions) / total
            avg_volatility = sum(p.volatility for p in predictions) / total
            
            # 趋势分布
            trend_counts = {}
            for trend in KronosTrend:
                count = sum(1 for p in predictions if p.trend_direction == trend)
                if count > 0:
                    trend_counts[trend.value] = count
            
            return {
                "total_predictions": total,
                "avg_confidence": avg_confidence,
                "trend_distribution": trend_counts,
                "avg_volatility": avg_volatility,
                "latest_prediction": predictions[0] if predictions else None
            }
            
        except Exception as e:
            self.logger.error(f"获取预测统计失败: {e}")
            return {
                "total_predictions": 0,
                "avg_confidence": 0.0,
                "trend_distribution": {},
                "avg_volatility": 0.0
            }
