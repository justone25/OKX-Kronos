#!/usr/bin/env python3
"""
Kronos预测验证系统
基于时间序列预测评估标准，验证Kronos预测的准确性
"""
import os
import logging
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..data.okx_fetcher import OKXDataFetcher
from ..utils.config import OKXConfig


class ValidationStatus(Enum):
    """验证状态"""
    PENDING = "等待验证"        # 等待验证
    VALIDATED = "已验证"       # 已验证
    EXPIRED = "已过期"         # 已过期
    FAILED = "验证失败"        # 验证失败
    EXCELLENT = "优秀"         # 优秀预测
    GOOD = "良好"              # 良好预测
    FAIR = "一般"              # 一般预测
    POOR = "较差"              # 较差预测


@dataclass
class ValidationResult:
    """验证结果（增强版：支持高低价验证）"""
    prediction_id: int
    prediction_timestamp: datetime
    validation_timestamp: datetime
    predicted_price: float
    actual_price: float
    actual_high: float = None
    actual_low: float = None
    price_error: float = 0.0
    price_error_pct: float = 0.0
    predicted_direction: str = ""
    actual_direction: str = ""
    direction_correct: bool = False
    high_prediction_correct: bool = False
    low_prediction_correct: bool = False
    confidence_score: float = 0.0
    validation_status: ValidationStatus = ValidationStatus.PENDING

    # 评估指标
    mae: float = 0.0
    rmse: float = 0.0
    mape: float = 0.0
    directional_accuracy: float = 0.0
    confidence_calibration: float = 0.0


class PredictionValidator:
    """Kronos预测验证器"""
    
    def __init__(self, okx_config: OKXConfig, db_path: str = "./data/predictions.db"):
        """
        初始化预测验证器
        
        Args:
            okx_config: OKX配置
            db_path: 预测数据库路径
        """
        self.logger = logging.getLogger(__name__)
        self.config = okx_config  # 保持向后兼容
        self.okx_config = okx_config
        self.db_path = db_path

        # 初始化数据获取器
        self.data_fetcher = OKXDataFetcher(okx_config)
        
        # 初始化验证数据库
        self._init_validation_database()
        
        self.logger.info("Kronos预测验证器初始化完成")
    
    def _init_validation_database(self):
        """初始化验证数据库表"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 创建验证结果表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prediction_validations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prediction_id INTEGER,
                    prediction_timestamp DATETIME,
                    validation_timestamp DATETIME,
                    predicted_price REAL,
                    actual_price REAL,
                    price_error REAL,
                    price_error_pct REAL,
                    predicted_direction TEXT,
                    actual_direction TEXT,
                    direction_correct BOOLEAN,
                    confidence_score REAL,
                    validation_status TEXT,
                    mae REAL,
                    rmse REAL,
                    mape REAL,
                    directional_accuracy REAL,
                    confidence_calibration REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (prediction_id) REFERENCES predictions (id)
                )
            ''')
            
            # 创建验证统计表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS validation_statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period_start DATETIME,
                    period_end DATETIME,
                    total_predictions INTEGER,
                    validated_predictions INTEGER,
                    avg_mae REAL,
                    avg_rmse REAL,
                    avg_mape REAL,
                    directional_accuracy REAL,
                    confidence_calibration REAL,
                    reliability_score REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            
            self.logger.info("验证数据库表初始化完成")
            
        except Exception as e:
            self.logger.error(f"初始化验证数据库失败: {e}")
            raise
    
    def get_pending_validations(self) -> List[Dict]:
        """获取待验证的预测"""
        try:
            conn = sqlite3.connect(self.db_path)

            # 查询需要验证的预测（预测时间已到期且未验证）
            current_time = datetime.now()

            query = '''
                SELECT p.id, p.instrument, p.timestamp, p.current_price, p.predicted_price,
                       p.price_change_pct, p.trend_direction, p.pred_hours,
                       p.volatility,
                       datetime(p.timestamp, '+' || p.pred_hours || ' hours') as target_time
                FROM predictions p
                LEFT JOIN prediction_validations pv ON p.id = pv.prediction_id
                WHERE pv.prediction_id IS NULL
                AND datetime(p.timestamp, '+' || p.pred_hours || ' hours') <= datetime(?)
                AND datetime(p.timestamp, '+' || p.pred_hours || ' hours') >= datetime(?)
                ORDER BY p.timestamp ASC
            '''

            # 验证窗口：预测到期时间到预测到期后30分钟
            # 查找目标时间在 [当前时间-30分钟, 当前时间] 范围内的预测
            validation_window_start = (current_time - timedelta(minutes=30)).isoformat()
            validation_window_end = current_time.isoformat()

            df = pd.read_sql_query(query, conn, params=(validation_window_end, validation_window_start))

            # 同时处理过期的预测（目标时间+30分钟 < 当前时间的预测标记为过期）
            expired_query = '''
                SELECT p.id
                FROM predictions p
                LEFT JOIN prediction_validations pv ON p.id = pv.prediction_id
                WHERE pv.prediction_id IS NULL
                AND datetime(p.timestamp, '+' || p.pred_hours || ' hours', '+30 minutes') < datetime(?)
            '''

            # 过期时间：当前时间（目标时间+30分钟 < 当前时间）
            expired_cutoff = current_time.isoformat()
            expired_df = pd.read_sql_query(expired_query, conn, params=(expired_cutoff,))

            # 将过期的预测标记为EXPIRED
            if not expired_df.empty:
                expired_ids = expired_df['id'].tolist()
                self.logger.info(f"标记 {len(expired_ids)} 个过期预测")

                # 批量插入过期记录
                cursor = conn.cursor()
                for pred_id in expired_ids:
                    cursor.execute('''
                        INSERT INTO prediction_validations (
                            prediction_id, validation_timestamp, validation_status
                        ) VALUES (?, ?, ?)
                    ''', (pred_id, current_time.isoformat(), 'EXPIRED'))

                conn.commit()

            conn.close()

            return df.to_dict('records')

        except Exception as e:
            self.logger.error(f"获取待验证预测失败: {e}")
            return []
    
    def validate_prediction(self, prediction: Dict) -> Optional[ValidationResult]:
        """
        验证单个预测
        
        Args:
            prediction: 预测数据
            
        Returns:
            验证结果
        """
        try:
            prediction_id = prediction['id']
            prediction_timestamp = datetime.fromisoformat(prediction['timestamp'])
            pred_hours = prediction['pred_hours']
            predicted_price = float(prediction['predicted_price'])
            predicted_direction = prediction['trend_direction']
            current_price = float(prediction['current_price'])
            
            # 计算验证时间点
            validation_time = prediction_timestamp + timedelta(hours=pred_hours)
            
            # 获取验证时间点的实际K线数据
            instrument = prediction.get('instrument', 'BTC-USDT-SWAP')
            kline_data = self._get_actual_kline_at_time(instrument, validation_time)

            if kline_data is None:
                self.logger.warning(f"无法获取验证时间点的K线数据: {validation_time}")
                return None

            actual_price = kline_data['close']
            actual_high = kline_data['high']
            actual_low = kline_data['low']
            
            # 计算价格误差
            price_error = actual_price - predicted_price
            price_error_pct = (price_error / predicted_price) * 100
            
            # 计算实际方向
            actual_direction = self._calculate_actual_direction(current_price, actual_price)
            
            # 判断方向预测是否正确
            direction_correct = self._is_direction_correct(predicted_direction, actual_direction)
            
            # 计算评估指标
            mae = abs(price_error)
            rmse = price_error ** 2  # 单个预测的RMSE就是误差的平方
            mape = abs(price_error_pct)
            directional_accuracy = 1.0 if direction_correct else 0.0
            
            # 计算置信度校准（简化版本）
            confidence_calibration = self._calculate_confidence_calibration(
                predicted_price, actual_price, prediction.get('volatility', 0)
            )
            
            # 验证高低价预测（如果有的话）
            predicted_high = prediction.get('predicted_high')
            predicted_low = prediction.get('predicted_low')

            high_prediction_correct = False
            low_prediction_correct = False

            if predicted_high is not None:
                high_error_pct = abs((actual_high - predicted_high) / predicted_high) * 100
                high_prediction_correct = high_error_pct <= 5.0  # 5%容差

            if predicted_low is not None:
                low_error_pct = abs((actual_low - predicted_low) / predicted_low) * 100
                low_prediction_correct = low_error_pct <= 5.0  # 5%容差

            # 确定验证状态（综合考虑价格、方向、高低价）
            price_accuracy = abs(price_error_pct)
            high_low_bonus = 0.0

            if predicted_high is not None and high_prediction_correct:
                high_low_bonus += 0.5
            if predicted_low is not None and low_prediction_correct:
                high_low_bonus += 0.5

            if price_accuracy <= 1.0 and direction_correct:
                validation_status = ValidationStatus.EXCELLENT
            elif price_accuracy <= 2.0 and (direction_correct or high_low_bonus > 0):
                validation_status = ValidationStatus.EXCELLENT
            elif price_accuracy <= 3.0 and direction_correct:
                validation_status = ValidationStatus.GOOD
            elif price_accuracy <= 5.0 and (direction_correct or high_low_bonus > 0):
                validation_status = ValidationStatus.GOOD
            elif price_accuracy <= 8.0 and direction_correct:
                validation_status = ValidationStatus.FAIR
            elif price_accuracy <= 10.0:
                validation_status = ValidationStatus.FAIR
            else:
                validation_status = ValidationStatus.POOR

            # 创建验证结果
            validation_result = ValidationResult(
                prediction_id=prediction_id,
                prediction_timestamp=prediction_timestamp,
                validation_timestamp=datetime.now(),
                predicted_price=predicted_price,
                actual_price=actual_price,
                actual_high=actual_high,
                actual_low=actual_low,
                price_error=price_error,
                price_error_pct=price_error_pct,
                predicted_direction=predicted_direction,
                actual_direction=actual_direction,
                direction_correct=direction_correct,
                high_prediction_correct=high_prediction_correct,
                low_prediction_correct=low_prediction_correct,
                confidence_score=prediction.get('volatility', 0),
                validation_status=validation_status,
                mae=mae,
                rmse=rmse,
                mape=mape,
                directional_accuracy=directional_accuracy,
                confidence_calibration=confidence_calibration + high_low_bonus * 0.1
            )
            
            # 保存验证结果
            self._save_validation_result(validation_result)
            
            self.logger.info(f"预测验证完成 - ID:{prediction_id}, "
                           f"价格误差:{price_error:+.2f}({price_error_pct:+.2f}%), "
                           f"方向{'正确' if direction_correct else '错误'}")
            
            return validation_result
            
        except Exception as e:
            self.logger.error(f"验证预测失败: {e}")
            return None
    
    def _get_actual_kline_at_time(self, instrument: str, target_time: datetime) -> Optional[Dict]:
        """获取指定时间点的实际K线数据（包含高低价）"""
        try:
            from src.data.kline_storage import KlineStorageService

            # 使用K线存储服务获取历史数据
            kline_service = KlineStorageService(self.config, self.db_path)

            # 首先尝试从数据库获取
            kline_data = kline_service.get_historical_kline_at_time(
                instrument=instrument,
                target_time=target_time,
                bar_size="1m",
                tolerance_minutes=10
            )

            if kline_data:
                self.logger.info(f"从数据库获取到K线数据: {target_time.strftime('%H:%M:%S')}")
                return kline_data

            # 如果数据库中没有，尝试从API获取并存储
            self.logger.info(f"数据库中无K线数据，尝试从API获取: {target_time.strftime('%H:%M:%S')}")

            # 获取目标时间前后的K线数据
            current_time = datetime.now()
            start_time = target_time - timedelta(minutes=30)
            end_time = min(target_time + timedelta(minutes=30), current_time)

            df = self.data_fetcher.get_historical_klines(
                instrument=instrument,
                bar="1m",
                start_time=start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                end_time=end_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                limit=60,
                validate_quality=False
            )

            if df.empty:
                self.logger.warning(f"无法获取历史K线数据: {instrument}")
                return None

            # 存储获取到的数据
            kline_service._store_klines_to_db(df, instrument, "1m")

            # 找到最接近目标时间的K线
            df['time_diff'] = abs((df['timestamps'] - target_time).dt.total_seconds())
            closest_row = df.loc[df['time_diff'].idxmin()]

            time_diff_seconds = closest_row['time_diff']
            self.logger.info(f"找到最接近K线: {closest_row['timestamps']} (时间差: {time_diff_seconds:.0f}秒)")

            return {
                'timestamp': closest_row['timestamps'].isoformat(),
                'open': float(closest_row['open']),
                'high': float(closest_row['high']),
                'low': float(closest_row['low']),
                'close': float(closest_row['close']),
                'volume': float(closest_row['volume']),
                'amount': float(closest_row['amount'])
            }

        except Exception as e:
            self.logger.error(f"获取实际K线数据失败: {e}")
            return None
    
    def _calculate_actual_direction(self, start_price: float, end_price: float) -> str:
        """计算实际价格方向"""
        price_change_pct = (end_price - start_price) / start_price * 100
        
        if price_change_pct > 0.1:  # 上涨超过0.1%
            return "up"
        elif price_change_pct < -0.1:  # 下跌超过0.1%
            return "down"
        else:  # 横盘
            return "sideways"
    
    def _is_direction_correct(self, predicted: str, actual: str) -> bool:
        """判断方向预测是否正确"""
        # 方向映射
        up_directions = ['up', 'bullish']
        down_directions = ['down', 'bearish']
        neutral_directions = ['sideways', 'neutral']
        
        if predicted in up_directions and actual in up_directions:
            return True
        elif predicted in down_directions and actual in down_directions:
            return True
        elif predicted in neutral_directions and actual in neutral_directions:
            return True
        else:
            return False
    
    def _calculate_confidence_calibration(self, predicted: float, actual: float, volatility: float) -> float:
        """计算置信度校准分数"""
        try:
            # 基于波动率的期望误差范围
            expected_error_range = volatility * 2  # 2倍波动率作为期望误差范围
            actual_error = abs(actual - predicted)
            
            if expected_error_range == 0:
                return 0.5  # 默认值
            
            # 校准分数：实际误差在期望范围内得分较高
            calibration = max(0, 1 - (actual_error / expected_error_range))
            return min(1.0, calibration)
            
        except Exception as e:
            self.logger.error(f"计算置信度校准失败: {e}")
            return 0.5
    
    def _save_validation_result(self, result: ValidationResult):
        """保存验证结果到数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO prediction_validations (
                    prediction_id, validation_timestamp,
                    predicted_price, actual_price, actual_high, actual_low,
                    price_error, price_error_pct,
                    predicted_direction, actual_direction, direction_correct,
                    high_prediction_correct, low_prediction_correct,
                    validation_status, mae, rmse, mape,
                    directional_accuracy, confidence_calibration
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result.prediction_id,
                result.validation_timestamp.isoformat(),
                result.predicted_price,
                result.actual_price,
                result.actual_high,
                result.actual_low,
                result.price_error,
                result.price_error_pct,
                result.predicted_direction,
                result.actual_direction,
                result.direction_correct,
                result.high_prediction_correct,
                result.low_prediction_correct,
                result.validation_status.value,
                result.mae,
                result.rmse,
                result.mape,
                result.directional_accuracy,
                result.confidence_calibration
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"保存验证结果失败: {e}")
            raise

    def _log_next_validation_time(self):
        """记录下次验证时间"""
        try:
            conn = sqlite3.connect(self.db_path)

            # 查询最近24小时内的未验证预测
            cutoff_time = (datetime.now() - timedelta(hours=24)).isoformat()

            query = '''
                SELECT p.id, p.instrument, p.timestamp, p.pred_hours,
                       datetime(p.timestamp, '+' || p.pred_hours || ' hours') as target_time
                FROM predictions p
                LEFT JOIN prediction_validations pv ON p.id = pv.prediction_id
                WHERE pv.prediction_id IS NULL
                AND p.timestamp > ?
                ORDER BY p.timestamp ASC
                LIMIT 3
            '''

            df = pd.read_sql_query(query, conn, params=(cutoff_time,))
            conn.close()

            if not df.empty:
                current_time = datetime.now()
                found_next = False

                for _, row in df.iterrows():
                    target_time = datetime.fromisoformat(row['target_time'])
                    validation_start = target_time  # 验证窗口开始时间

                    if validation_start > current_time:
                        wait_minutes = (validation_start - current_time).total_seconds() / 60
                        instrument_short = row['instrument'].replace('-USDT-SWAP', '')
                        self.logger.info(f"📅 下个验证: {instrument_short} (ID {row['id']}) "
                                       f"在 {validation_start.strftime('%H:%M:%S')} "
                                       f"(还需等待 {wait_minutes:.0f} 分钟)")
                        found_next = True
                        break

                if not found_next:
                    self.logger.info("📅 最近的预测都已过验证窗口")
            else:
                self.logger.info("📅 暂无最近的待验证预测")

        except Exception as e:
            self.logger.debug(f"记录下次验证时间失败: {e}")

    def run_validation_cycle(self) -> Dict[str, any]:
        """运行一次验证周期"""
        try:
            self.logger.info("🔍 开始预测验证周期")

            # 获取待验证的预测
            pending_predictions = self.get_pending_validations()

            if not pending_predictions:
                # 检查最近的预测何时可以验证
                self._log_next_validation_time()
                self.logger.info("暂无待验证的预测")
                return {"validated_count": 0, "results": []}

            self.logger.info(f"发现 {len(pending_predictions)} 个待验证预测")

            # 验证每个预测
            validation_results = []
            successful_validations = 0

            for prediction in pending_predictions:
                result = self.validate_prediction(prediction)
                if result:
                    validation_results.append(result)
                    successful_validations += 1

            # 更新统计信息
            if validation_results:
                self._update_validation_statistics(validation_results)

            self.logger.info(f"✅ 验证周期完成，成功验证 {successful_validations} 个预测")

            return {
                "validated_count": successful_validations,
                "results": validation_results
            }

        except Exception as e:
            self.logger.error(f"❌ 验证周期执行失败: {e}")
            return {"validated_count": 0, "results": []}

    def _update_validation_statistics(self, results: List[ValidationResult]):
        """更新验证统计信息"""
        try:
            if not results:
                return

            # 计算统计指标
            total_predictions = len(results)
            avg_mae = np.mean([r.mae for r in results])
            avg_rmse = np.sqrt(np.mean([r.rmse for r in results]))
            avg_mape = np.mean([r.mape for r in results])
            directional_accuracy = np.mean([r.directional_accuracy for r in results]) * 100
            confidence_calibration = np.mean([r.confidence_calibration for r in results])

            # 计算可靠性评分（综合指标）
            reliability_score = (
                (1 - min(avg_mape / 100, 1.0)) * 0.4 +  # 价格准确性权重40%
                (directional_accuracy / 100) * 0.4 +      # 方向准确性权重40%
                confidence_calibration * 0.2              # 置信度校准权重20%
            )

            # 保存统计信息
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            period_start = min(r.prediction_timestamp for r in results)
            period_end = max(r.prediction_timestamp for r in results)

            cursor.execute('''
                INSERT INTO validation_statistics (
                    period_start, period_end, total_predictions, validated_predictions,
                    avg_mae, avg_rmse, avg_mape, directional_accuracy,
                    confidence_calibration, reliability_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                period_start.isoformat(),
                period_end.isoformat(),
                total_predictions,
                total_predictions,
                avg_mae,
                avg_rmse,
                avg_mape,
                directional_accuracy,
                confidence_calibration,
                reliability_score
            ))

            conn.commit()
            conn.close()

            self.logger.info(f"统计信息更新完成 - 可靠性评分: {reliability_score:.2%}")

        except Exception as e:
            self.logger.error(f"更新验证统计失败: {e}")

    def get_validation_report(self, hours: int = 24) -> Dict[str, any]:
        """获取验证报告"""
        try:
            conn = sqlite3.connect(self.db_path)

            cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()

            # 获取验证结果
            query = '''
                SELECT * FROM prediction_validations
                WHERE validation_timestamp > ?
                ORDER BY validation_timestamp DESC
            '''

            df = pd.read_sql_query(query, conn, params=(cutoff_time,))

            if df.empty:
                conn.close()
                return {
                    "period_hours": hours,
                    "total_validations": 0,
                    "metrics": {},
                    "summary": "暂无验证数据"
                }

            # 计算报告指标
            total_validations = len(df)
            avg_mae = df['mae'].mean()
            avg_rmse = np.sqrt(df['rmse'].mean())
            avg_mape = df['mape'].mean()
            directional_accuracy = df['directional_accuracy'].mean() * 100
            confidence_calibration = df['confidence_calibration'].mean()

            # 方向预测分布
            direction_stats = df.groupby(['predicted_direction', 'direction_correct']).size().unstack(fill_value=0)

            # 误差分布
            error_percentiles = df['price_error_pct'].describe()

            conn.close()

            return {
                "period_hours": hours,
                "total_validations": total_validations,
                "metrics": {
                    "avg_mae": avg_mae,
                    "avg_rmse": avg_rmse,
                    "avg_mape": avg_mape,
                    "directional_accuracy": directional_accuracy,
                    "confidence_calibration": confidence_calibration
                },
                "direction_stats": direction_stats.to_dict() if not direction_stats.empty else {},
                "error_distribution": error_percentiles.to_dict(),
                "summary": f"过去{hours}小时验证了{total_validations}个预测，"
                          f"方向准确率{directional_accuracy:.1f}%，"
                          f"平均价格误差{avg_mape:.2f}%"
            }

        except Exception as e:
            self.logger.error(f"获取验证报告失败: {e}")
            return {"error": str(e)}

    def get_model_performance_trend(self, days: int = 7) -> Dict[str, any]:
        """获取模型性能趋势"""
        try:
            conn = sqlite3.connect(self.db_path)

            cutoff_time = (datetime.now() - timedelta(days=days)).isoformat()

            query = '''
                SELECT DATE(validation_timestamp) as date,
                       AVG(mae) as avg_mae,
                       AVG(mape) as avg_mape,
                       AVG(directional_accuracy) * 100 as directional_accuracy,
                       COUNT(*) as validation_count
                FROM prediction_validations
                WHERE validation_timestamp > ?
                GROUP BY DATE(validation_timestamp)
                ORDER BY date ASC
            '''

            df = pd.read_sql_query(query, conn, params=(cutoff_time,))
            conn.close()

            if df.empty:
                return {"trend_data": [], "summary": "暂无趋势数据"}

            trend_data = df.to_dict('records')

            # 计算趋势
            if len(df) > 1:
                mae_trend = "改善" if df['avg_mae'].iloc[-1] < df['avg_mae'].iloc[0] else "恶化"
                accuracy_trend = "提升" if df['directional_accuracy'].iloc[-1] > df['directional_accuracy'].iloc[0] else "下降"
            else:
                mae_trend = "稳定"
                accuracy_trend = "稳定"

            return {
                "trend_data": trend_data,
                "summary": f"过去{days}天模型性能趋势：价格预测{mae_trend}，方向预测{accuracy_trend}"
            }

        except Exception as e:
            self.logger.error(f"获取性能趋势失败: {e}")
            return {"error": str(e)}
