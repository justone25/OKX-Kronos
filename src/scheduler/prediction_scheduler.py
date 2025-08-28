"""
持续预测调度器
支持定时采样、预测更新和结果存储
支持SQLite和PostgreSQL数据库
"""
import time
import logging
import threading
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pathlib import Path
import pandas as pd
import schedule

from ..trading.prediction_service import PredictionService
from ..utils.config import OKXConfig, TradingConfig
from ..utils.database import db_config, get_db_connection, execute_query, init_database


class PredictionScheduler:
    """持续预测调度器"""
    
    def __init__(self, okx_config: OKXConfig, trading_config: TradingConfig,
                 db_path: str = None, device: str = "cpu"):
        """
        初始化调度器

        Args:
            okx_config: OKX API配置
            trading_config: 交易配置
            db_path: 数据库路径 (可选，优先使用DATABASE_URL环境变量)
            device: 计算设备
        """
        self.logger = logging.getLogger(__name__)
        self.okx_config = okx_config
        self.trading_config = trading_config
        self.device = device

        # 数据库配置
        if db_path and not os.getenv('DATABASE_URL'):
            # 如果提供了db_path且没有DATABASE_URL，设置SQLite路径
            os.environ['SQLITE_DB_PATH'] = str(Path(db_path).absolute())
            # 创建数据目录
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # 初始化预测服务
        self.prediction_service = PredictionService(okx_config, trading_config, device)

        # 初始化数据库
        self._init_database()

        # 运行状态
        self.is_running = False
        self.scheduler_thread = None
        
        # 配置参数
        self.prediction_interval = 10  # 预测间隔（分钟）
        self.lookback_hours = 48      # 回看小时数
        self.pred_hours = 2           # 预测小时数
        self.temperature = 0.8        # 采样温度
        self.top_p = 0.9             # nucleus采样参数
        self.sample_count = 3        # 采样次数
        
        
        self.logger.info("✅ 预测调度器初始化完成")
    
    def _init_database(self):
        """初始化数据库"""
        try:
            init_database()
            self.logger.info("✅ 数据库初始化完成")
        except Exception as e:
            self.logger.error(f"❌ 数据库初始化失败: {e}")
            raise
    
    def save_prediction(self, report: Dict[str, Any]):
        """保存预测结果到数据库"""
        try:
            stats = report['statistics']
            params = report['parameters']

            # 获取预测数据
            prediction_df = report.get('prediction_data', None)

            # 计算预测的高低价
            predicted_high = stats.get('predicted_price_end', 0)
            predicted_low = stats.get('predicted_price_end', 0)

            if prediction_df is not None and not prediction_df.empty:
                predicted_high = float(prediction_df['high'].max())
                predicted_low = float(prediction_df['low'].min())

            # 将预测数据转换为JSON字符串
            prediction_data_json = ""
            if prediction_df is not None and not prediction_df.empty:
                try:
                    prediction_data_json = prediction_df.to_json(orient='records')
                except:
                    prediction_data_json = "{}"
            else:
                prediction_data_json = "{}"

            # 构建插入SQL（兼容PostgreSQL和SQLite）
            if db_config.db_type == 'postgresql':
                query = '''
                    INSERT INTO predictions (
                        timestamp, instrument, current_price, predicted_price,
                        price_change, price_change_pct, predicted_high, predicted_low,
                        volatility, trend_direction, lookback_hours, pred_hours,
                        temperature, top_p, sample_count, prediction_data
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                '''
            else:
                query = '''
                    INSERT INTO predictions (
                        timestamp, instrument, current_price, predicted_price,
                        price_change, price_change_pct, predicted_high, predicted_low,
                        volatility, trend_direction, lookback_hours, pred_hours,
                        temperature, top_p, sample_count, prediction_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                '''

            params_tuple = (
                report['timestamp'].isoformat(),
                report['instrument'],
                stats.get('current_price', 0),
                stats.get('predicted_price_end', 0),
                stats.get('price_change', 0),
                stats.get('price_change_pct', 0),
                predicted_high,
                predicted_low,
                stats.get('volatility', 0),
                stats.get('trend_direction', 'unknown'),
                report['lookback_hours'],
                report['pred_hours'],
                params.get('temperature', 1.0),
                params.get('top_p', 0.9),
                params.get('sample_count', 1),
                prediction_data_json
            )

            execute_query(query, params_tuple)
            self.logger.info(f"✅ 预测结果已保存到数据库")

        except Exception as e:
            self.logger.error(f"❌ 保存预测结果失败: {e}")
    
    def save_actual_price(self, timestamp: datetime, instrument: str, price: float, volume: float):
        """保存实际价格数据"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO actual_prices (timestamp, instrument, price, volume)
                VALUES (?, ?, ?, ?)
            ''', (timestamp.isoformat(), instrument, price, volume))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"❌ 保存实际价格失败: {e}")
    
    def log_system_event(self, level: str, message: str, details: str = None):
        """记录系统事件"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO system_logs (timestamp, level, message, details)
                VALUES (?, ?, ?, ?)
            ''', (datetime.now().isoformat(), level, message, details))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"❌ 记录系统事件失败: {e}")
    
    def run_prediction_cycle(self):
        """执行一次预测周期"""
        try:
            self.logger.info("🔄 开始新的预测周期")
            
            # 获取预测
            report = self.prediction_service.get_prediction(
                lookback_hours=self.lookback_hours,
                pred_hours=self.pred_hours,
                temperature=self.temperature,
                top_p=self.top_p,
                sample_count=self.sample_count
            )
            
            # 保存预测结果
            self.save_prediction(report)
            
            # 保存当前实际价格
            current_data = report['historical_data'].iloc[-1]
            self.save_actual_price(
                current_data['timestamps'],
                report['instrument'],
                current_data['close'],
                current_data['volume']
            )
            
            # 打印简化的预测报告
            self.print_brief_report(report)
            
            # 记录系统事件
            self.log_system_event(
                "INFO", 
                f"预测周期完成 - 当前价格: ${report['statistics']['current_price']:,.2f}, "
                f"预测价格: ${report['statistics']['predicted_price_end']:,.2f}"
            )
            
        except Exception as e:
            self.logger.error(f"❌ 预测周期执行失败: {e}")
            self.log_system_event("ERROR", f"预测周期失败: {str(e)}")
    
    def print_brief_report(self, report: Dict[str, Any]):
        """打印简化的预测报告"""
        stats = report['statistics']
        timestamp = report['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"\n{'='*50}")
        print(f"🔮 Kronos预测更新 - {timestamp}")
        print(f"{'='*50}")
        print(f"💰 当前价格: ${stats.get('current_price', 0):,.2f}")
        print(f"🔮 预测价格: ${stats.get('predicted_price_end', 0):,.2f}")
        print(f"📈 价格变化: {stats.get('price_change_pct', 0):+.2f}%")
        print(f"📊 趋势方向: {stats.get('trend_direction', 'unknown').upper()}")
        print(f"⏰ 下次更新: {(datetime.now() + timedelta(minutes=self.prediction_interval)).strftime('%H:%M:%S')}")
        print(f"{'='*50}\n")
    
    def start(self):
        """启动持续预测"""
        if self.is_running:
            self.logger.warning("⚠️ 调度器已在运行中")
            return
        
        self.logger.info("🚀 启动持续预测调度器")
        
        # 配置定时任务
        schedule.clear()
        schedule.every(self.prediction_interval).minutes.do(self.run_prediction_cycle)
        
        # 立即执行一次预测
        self.run_prediction_cycle()
        
        # 启动调度器线程
        self.is_running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        self.logger.info(f"✅ 调度器已启动，每 {self.prediction_interval} 分钟更新一次预测")
    
    def _run_scheduler(self):
        """运行调度器主循环"""
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(1)
            except Exception as e:
                self.logger.error(f"❌ 调度器运行异常: {e}")
                self.log_system_event("ERROR", f"调度器异常: {str(e)}")
                time.sleep(10)  # 异常后等待10秒再继续
    
    def stop(self):
        """停止持续预测"""
        if not self.is_running:
            self.logger.warning("⚠️ 调度器未在运行")
            return
        
        self.logger.info("🛑 停止持续预测调度器")
        self.is_running = False
        
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        
        schedule.clear()
        self.logger.info("✅ 调度器已停止")
    
    def get_recent_predictions(self, limit: int = 10) -> pd.DataFrame:
        """获取最近的预测结果"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            query = '''
                SELECT timestamp, current_price, predicted_price, price_change_pct, 
                       trend_direction, volatility
                FROM predictions 
                ORDER BY timestamp DESC 
                LIMIT ?
            '''
            
            df = pd.read_sql_query(query, conn, params=(limit,))
            conn.close()
            
            return df
            
        except Exception as e:
            self.logger.error(f"❌ 获取预测历史失败: {e}")
            return pd.DataFrame()
    
    def get_prediction_accuracy(self, hours_back: int = 24) -> Dict[str, float]:
        """计算预测准确性"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # 获取指定时间范围内的预测和实际价格
            cutoff_time = (datetime.now() - timedelta(hours=hours_back)).isoformat()
            
            query = '''
                SELECT p.timestamp, p.predicted_price, p.price_change_pct as pred_change,
                       a.price as actual_price
                FROM predictions p
                LEFT JOIN actual_prices a ON 
                    datetime(p.timestamp, '+' || p.pred_hours || ' hours') = a.timestamp
                WHERE p.timestamp > ?
                AND a.price IS NOT NULL
            '''
            
            df = pd.read_sql_query(query, conn, params=(cutoff_time,))
            conn.close()
            
            if df.empty:
                return {"accuracy": 0.0, "mae": 0.0, "samples": 0}
            
            # 计算准确性指标
            df['actual_change'] = (df['actual_price'] - df['predicted_price']) / df['predicted_price'] * 100
            df['error'] = abs(df['pred_change'] - df['actual_change'])
            
            accuracy = {
                "mae": df['error'].mean(),  # 平均绝对误差
                "rmse": (df['error'] ** 2).mean() ** 0.5,  # 均方根误差
                "samples": len(df),
                "direction_accuracy": (
                    (df['pred_change'] > 0) == (df['actual_change'] > 0)
                ).mean() * 100  # 方向预测准确率
            }
            
            return accuracy
            
        except Exception as e:
            self.logger.error(f"❌ 计算预测准确性失败: {e}")
            return {"accuracy": 0.0, "mae": 0.0, "samples": 0}


def create_prediction_scheduler(okx_config: OKXConfig, trading_config: TradingConfig, 
                              db_path: str = "./data/predictions.db", device: str = "cpu") -> PredictionScheduler:
    """创建预测调度器实例"""
    return PredictionScheduler(okx_config, trading_config, db_path, device)
