"""
预测监控面板
提供实时监控和历史数据查看功能
"""
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pathlib import Path
import logging


class PredictionDashboard:
    """预测监控面板"""
    
    def __init__(self, db_path: str = "./data/predictions.db"):
        """
        初始化监控面板
        
        Args:
            db_path: 数据库路径
        """
        self.logger = logging.getLogger(__name__)
        self.db_path = Path(db_path)
        
        if not self.db_path.exists():
            raise FileNotFoundError(f"数据库文件不存在: {self.db_path}")
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统运行状态"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # 获取最新预测时间
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(timestamp) FROM predictions")
            last_prediction = cursor.fetchone()[0]
            
            # 获取预测总数
            cursor.execute("SELECT COUNT(*) FROM predictions")
            total_predictions = cursor.fetchone()[0]
            
            # 获取最近24小时的预测数量
            yesterday = (datetime.now() - timedelta(hours=24)).isoformat()
            cursor.execute("SELECT COUNT(*) FROM predictions WHERE timestamp > ?", (yesterday,))
            recent_predictions = cursor.fetchone()[0]
            
            # 获取最新的系统日志
            cursor.execute("""
                SELECT level, message, timestamp 
                FROM system_logs 
                ORDER BY timestamp DESC 
                LIMIT 5
            """)
            recent_logs = cursor.fetchall()
            
            conn.close()
            
            status = {
                "last_prediction": last_prediction,
                "total_predictions": total_predictions,
                "recent_predictions": recent_predictions,
                "recent_logs": recent_logs,
                "is_active": self._is_system_active(last_prediction)
            }
            
            return status
            
        except Exception as e:
            self.logger.error(f"❌ 获取系统状态失败: {e}")
            return {}
    
    def _is_system_active(self, last_prediction: str) -> bool:
        """判断系统是否活跃"""
        if not last_prediction:
            return False
        
        try:
            last_time = datetime.fromisoformat(last_prediction)
            time_diff = datetime.now() - last_time
            return time_diff.total_seconds() < 3600  # 1小时内有预测认为是活跃的
        except:
            return False
    
    def get_prediction_history(self, hours: int = 24) -> pd.DataFrame:
        """获取预测历史"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            query = '''
                SELECT timestamp, current_price, predicted_price, price_change_pct,
                       trend_direction, volatility, pred_hours
                FROM predictions 
                WHERE timestamp > ?
                ORDER BY timestamp ASC
            '''
            
            df = pd.read_sql_query(query, conn, params=(cutoff_time,))
            conn.close()
            
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            return df
            
        except Exception as e:
            self.logger.error(f"❌ 获取预测历史失败: {e}")
            return pd.DataFrame()
    
    def get_accuracy_metrics(self, hours: int = 24) -> Dict[str, float]:
        """获取预测准确性指标"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            # 获取有对应实际价格的预测
            query = '''
                SELECT p.timestamp, p.predicted_price, p.price_change_pct as pred_change,
                       p.current_price, a.price as actual_price
                FROM predictions p
                LEFT JOIN actual_prices a ON 
                    datetime(p.timestamp, '+' || p.pred_hours || ' hours') = a.timestamp
                WHERE p.timestamp > ?
                AND a.price IS NOT NULL
            '''
            
            df = pd.read_sql_query(query, conn, params=(cutoff_time,))
            conn.close()
            
            if df.empty:
                return {"samples": 0, "mae": 0, "direction_accuracy": 0}
            
            # 计算实际价格变化
            df['actual_change'] = (df['actual_price'] - df['current_price']) / df['current_price'] * 100
            df['price_error'] = abs(df['predicted_price'] - df['actual_price'])
            df['change_error'] = abs(df['pred_change'] - df['actual_change'])
            
            # 计算方向准确性
            df['pred_direction'] = df['pred_change'] > 0
            df['actual_direction'] = df['actual_change'] > 0
            direction_accuracy = (df['pred_direction'] == df['actual_direction']).mean() * 100
            
            metrics = {
                "samples": len(df),
                "mae": df['price_error'].mean(),  # 平均绝对误差（价格）
                "mape": (df['price_error'] / df['actual_price'] * 100).mean(),  # 平均绝对百分比误差
                "change_mae": df['change_error'].mean(),  # 变化率平均绝对误差
                "direction_accuracy": direction_accuracy,  # 方向预测准确率
                "rmse": (df['price_error'] ** 2).mean() ** 0.5  # 均方根误差
            }
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"❌ 计算准确性指标失败: {e}")
            return {"samples": 0, "mae": 0, "direction_accuracy": 0}
    
    def plot_prediction_trend(self, hours: int = 24, save_path: str = None):
        """绘制预测趋势图"""
        try:
            df = self.get_prediction_history(hours)
            
            if df.empty:
                self.logger.warning("⚠️ 没有预测数据可绘制")
                return
            
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
            
            # 绘制价格趋势
            ax1.plot(df['timestamp'], df['current_price'], 'b-', label='Current Price', linewidth=2)
            ax1.plot(df['timestamp'], df['predicted_price'], 'r--', label='Predicted Price', linewidth=2)
            ax1.set_ylabel('Price (USDT)')
            ax1.set_title('BTC-USDT Price Prediction Trend')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # 绘制价格变化预测
            ax2.bar(df['timestamp'], df['price_change_pct'], 
                   color=['green' if x > 0 else 'red' for x in df['price_change_pct']],
                   alpha=0.7, label='Predicted Change %')
            ax2.set_ylabel('Price Change (%)')
            ax2.set_xlabel('Time')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            # 格式化时间轴
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            ax2.xaxis.set_major_locator(mdates.HourLocator(interval=2))
            plt.xticks(rotation=45)
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                self.logger.info(f"预测趋势图已保存到: {save_path}")
            
            plt.show()
            
        except Exception as e:
            self.logger.error(f"❌ 绘制预测趋势失败: {e}")
    
    def print_status_report(self):
        """打印系统状态报告"""
        try:
            status = self.get_system_status()
            metrics = self.get_accuracy_metrics(24)
            
            print("\n" + "="*60)
            print("📊 KRONOS 预测系统状态报告")
            print("="*60)
            
            # 系统状态
            print(f"🔄 系统状态: {'🟢 运行中' if status.get('is_active', False) else '🔴 停止'}")
            print(f"📈 总预测次数: {status.get('total_predictions', 0)}")
            print(f"⏰ 最近24小时预测: {status.get('recent_predictions', 0)}")
            
            if status.get('last_prediction'):
                last_time = datetime.fromisoformat(status['last_prediction'])
                print(f"🕐 最后预测时间: {last_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 准确性指标
            print(f"\n📊 预测准确性 (最近24小时):")
            print(f"   样本数量: {metrics.get('samples', 0)}")
            if metrics.get('samples', 0) > 0:
                print(f"   方向准确率: {metrics.get('direction_accuracy', 0):.1f}%")
                print(f"   平均绝对误差: ${metrics.get('mae', 0):.2f}")
                print(f"   平均绝对百分比误差: {metrics.get('mape', 0):.2f}%")
            else:
                print("   暂无足够数据计算准确性")
            
            # 最近日志
            print(f"\n📝 最近系统日志:")
            for level, message, timestamp in status.get('recent_logs', [])[:3]:
                log_time = datetime.fromisoformat(timestamp)
                print(f"   [{log_time.strftime('%H:%M:%S')}] {level}: {message}")
            
            print("="*60 + "\n")
            
        except Exception as e:
            self.logger.error(f"❌ 打印状态报告失败: {e}")
    
    def export_data(self, output_path: str, hours: int = 24):
        """导出预测数据"""
        try:
            df = self.get_prediction_history(hours)
            
            if df.empty:
                self.logger.warning("⚠️ 没有数据可导出")
                return
            
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            if output_path.suffix.lower() == '.csv':
                df.to_csv(output_path, index=False)
            elif output_path.suffix.lower() == '.xlsx':
                df.to_excel(output_path, index=False)
            else:
                df.to_json(output_path, orient='records', date_format='iso')
            
            self.logger.info(f"✅ 数据已导出到: {output_path}")
            
        except Exception as e:
            self.logger.error(f"❌ 导出数据失败: {e}")


def create_dashboard(db_path: str = "./data/predictions.db") -> PredictionDashboard:
    """创建监控面板实例"""
    return PredictionDashboard(db_path)
