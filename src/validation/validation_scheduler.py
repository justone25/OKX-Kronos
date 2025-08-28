#!/usr/bin/env python3
"""
Kronos预测验证调度器
定期验证到期的预测，生成准确性报告
"""
import time
import threading
import schedule
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from .prediction_validator import PredictionValidator
from ..utils.config import OKXConfig


class ValidationScheduler:
    """预测验证调度器"""
    
    def __init__(self, okx_config: OKXConfig, db_path: str = "./data/predictions.db",
                 validation_interval: int = 10):
        """
        初始化验证调度器
        
        Args:
            okx_config: OKX配置
            db_path: 数据库路径
            validation_interval: 验证间隔（分钟）
        """
        self.logger = logging.getLogger(__name__)
        self.okx_config = okx_config
        self.db_path = db_path
        self.validation_interval = validation_interval
        
        # 初始化验证器
        self.validator = PredictionValidator(okx_config, db_path)
        
        # 运行状态
        self.is_running = False
        self.scheduler_thread = None
        
        self.logger.info(f"验证调度器初始化完成，验证间隔: {validation_interval}分钟")
    
    def start(self):
        """启动验证调度器"""
        if self.is_running:
            self.logger.warning("⚠️ 验证调度器已在运行中")
            return
        
        self.logger.info("🚀 启动预测验证调度器")
        
        # 配置定时任务
        schedule.clear()
        schedule.every(self.validation_interval).minutes.do(self.run_validation_cycle)
        
        # 立即执行一次验证
        self.run_validation_cycle()
        
        # 启动调度器线程
        self.is_running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        self.logger.info(f"✅ 验证调度器已启动，每 {self.validation_interval} 分钟验证一次")
    
    def stop(self):
        """停止验证调度器"""
        if not self.is_running:
            self.logger.warning("⚠️ 验证调度器未在运行")
            return
        
        self.logger.info("🛑 停止预测验证调度器")
        self.is_running = False
        
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        
        schedule.clear()
        self.logger.info("✅ 验证调度器已停止")
    
    def _run_scheduler(self):
        """运行调度器主循环"""
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(1)
            except Exception as e:
                self.logger.error(f"❌ 验证调度器运行异常: {e}")
                time.sleep(10)  # 异常后等待10秒再继续
    
    def run_validation_cycle(self):
        """执行一次验证周期"""
        try:
            self.logger.info("🔍 开始预测验证周期")
            
            # 运行验证
            result = self.validator.run_validation_cycle()
            
            validated_count = result.get("validated_count", 0)
            
            if validated_count > 0:
                self.logger.info(f"✅ 验证周期完成，验证了 {validated_count} 个预测")
                
                # 生成简要报告
                self.print_validation_summary(result)
            else:
                self.logger.info("ℹ️ 验证周期完成，暂无待验证预测")
            
        except Exception as e:
            self.logger.error(f"❌ 验证周期执行失败: {e}")
    
    def print_validation_summary(self, validation_result: Dict[str, Any]):
        """打印验证摘要"""
        try:
            results = validation_result.get("results", [])
            if not results:
                return
            
            # 计算摘要统计
            total_count = len(results)
            correct_directions = sum(1 for r in results if r.direction_correct)
            direction_accuracy = (correct_directions / total_count) * 100
            
            avg_price_error = sum(abs(r.price_error_pct) for r in results) / total_count
            
            print(f"\n{'='*50}")
            print(f"🔍 预测验证摘要 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*50}")
            print(f"📊 验证数量: {total_count}")
            print(f"🎯 方向准确率: {direction_accuracy:.1f}% ({correct_directions}/{total_count})")
            print(f"💰 平均价格误差: {avg_price_error:.2f}%")
            
            # 显示最近几个验证结果
            print(f"\n最近验证结果:")
            for i, result in enumerate(results[-3:], 1):  # 显示最近3个
                direction_icon = "✅" if result.direction_correct else "❌"
                print(f"  {i}. {direction_icon} {result.predicted_direction} → {result.actual_direction} "
                      f"价格误差: {result.price_error_pct:+.2f}%")
            
            print(f"{'='*50}\n")
            
        except Exception as e:
            self.logger.error(f"打印验证摘要失败: {e}")
    
    def get_validation_status(self) -> Dict[str, Any]:
        """获取验证状态"""
        try:
            # 获取最近24小时的验证报告
            report = self.validator.get_validation_report(hours=24)
            
            # 获取性能趋势
            trend = self.validator.get_model_performance_trend(days=7)
            
            return {
                "scheduler_running": self.is_running,
                "validation_interval": self.validation_interval,
                "last_validation": datetime.now().isoformat(),
                "recent_report": report,
                "performance_trend": trend
            }
            
        except Exception as e:
            self.logger.error(f"获取验证状态失败: {e}")
            return {"error": str(e)}
    
    def generate_detailed_report(self, hours: int = 24) -> str:
        """生成详细的验证报告"""
        try:
            report = self.validator.get_validation_report(hours)
            
            if report.get("total_validations", 0) == 0:
                return f"过去{hours}小时内暂无验证数据"
            
            metrics = report["metrics"]
            
            report_text = f"""
📊 Kronos预测验证报告 ({hours}小时)
{'='*60}

📈 总体表现:
  • 验证数量: {report['total_validations']}
  • 方向准确率: {metrics['directional_accuracy']:.1f}%
  • 平均价格误差: {metrics['avg_mape']:.2f}%
  • 置信度校准: {metrics['confidence_calibration']:.2%}

📊 详细指标:
  • MAE (平均绝对误差): ${metrics['avg_mae']:.2f}
  • RMSE (均方根误差): ${metrics['avg_rmse']:.2f}
  • MAPE (平均绝对百分比误差): {metrics['avg_mape']:.2f}%

📋 误差分布:
  • 25%分位数: {report['error_distribution']['25%']:.2f}%
  • 50%分位数: {report['error_distribution']['50%']:.2f}%
  • 75%分位数: {report['error_distribution']['75%']:.2f}%
  • 最大误差: {report['error_distribution']['max']:.2f}%

💡 总结: {report['summary']}
"""
            
            return report_text
            
        except Exception as e:
            self.logger.error(f"生成详细报告失败: {e}")
            return f"报告生成失败: {str(e)}"
    
    def get_model_reliability_score(self) -> float:
        """获取模型可靠性评分"""
        try:
            report = self.validator.get_validation_report(hours=24)
            
            if report.get("total_validations", 0) == 0:
                return 0.5  # 默认评分
            
            metrics = report["metrics"]
            
            # 计算综合可靠性评分
            price_accuracy = max(0, 1 - (metrics["avg_mape"] / 100))  # 价格准确性
            direction_accuracy = metrics["directional_accuracy"] / 100  # 方向准确性
            confidence_calibration = metrics["confidence_calibration"]  # 置信度校准
            
            # 加权平均
            reliability_score = (
                price_accuracy * 0.4 +
                direction_accuracy * 0.4 +
                confidence_calibration * 0.2
            )
            
            return min(1.0, max(0.0, reliability_score))
            
        except Exception as e:
            self.logger.error(f"计算可靠性评分失败: {e}")
            return 0.5


def create_validation_scheduler(okx_config: OKXConfig, db_path: str = "./data/predictions.db",
                              validation_interval: int = 10) -> ValidationScheduler:
    """创建验证调度器实例"""
    return ValidationScheduler(okx_config, db_path, validation_interval)
