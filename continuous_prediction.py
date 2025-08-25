#!/usr/bin/env python3
"""
Kronos持续预测系统
支持定时采样、实时更新和监控
"""
import os
import sys
import time
import signal
import logging
import argparse
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils.config import OKXConfig, TradingConfig, SystemConfig
from src.scheduler.prediction_scheduler import create_prediction_scheduler
from src.monitor.dashboard import create_dashboard


def setup_logging():
    """配置日志系统"""
    log_dir = Path("./logs")
    log_dir.mkdir(exist_ok=True)
    
    # 配置日志格式
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 文件日志
    file_handler = logging.FileHandler(log_dir / f"continuous_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format))
    
    # 控制台日志
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    
    # 根日志配置
    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, console_handler]
    )


class ContinuousPredictionSystem:
    """持续预测系统"""
    
    def __init__(self, config_args):
        """初始化系统"""
        self.logger = logging.getLogger(__name__)
        
        # 加载配置
        self.okx_config = OKXConfig()
        self.trading_config = TradingConfig()
        self.system_config = SystemConfig()
        
        # 应用命令行参数
        self._apply_config(config_args)
        
        # 初始化组件
        self.scheduler = None
        self.dashboard = None
        self.is_running = False
        
        # 信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _apply_config(self, args):
        """应用命令行配置"""
        if args.interval:
            self.prediction_interval = args.interval
        else:
            self.prediction_interval = 30  # 默认30分钟
        
        if args.lookback:
            self.lookback_hours = args.lookback
        else:
            self.lookback_hours = 12  # 默认12小时
        
        if args.pred_hours:
            self.pred_hours = args.pred_hours
        else:
            self.pred_hours = 6  # 默认预测6小时
        
        self.device = args.device if args.device else "auto"
        self.db_path = args.db_path if args.db_path else "./data/predictions.db"
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        self.logger.info(f"收到信号 {signum}，正在优雅关闭系统...")
        self.stop()
        sys.exit(0)
    
    def initialize(self):
        """初始化系统组件"""
        try:
            self.logger.info("🚀 初始化Kronos持续预测系统")
            
            # 创建数据目录
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            
            # 初始化调度器
            self.scheduler = create_prediction_scheduler(
                self.okx_config, 
                self.trading_config, 
                self.db_path, 
                self.device
            )
            
            # 配置调度器参数
            self.scheduler.prediction_interval = self.prediction_interval
            self.scheduler.lookback_hours = self.lookback_hours
            self.scheduler.pred_hours = self.pred_hours
            
            # 初始化监控面板
            self.dashboard = create_dashboard(self.db_path)
            
            self.logger.info("✅ 系统初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 系统初始化失败: {e}")
            return False
    
    def start(self):
        """启动持续预测系统"""
        if not self.initialize():
            return False
        
        try:
            self.logger.info("🎯 启动持续预测系统")
            
            # 显示系统配置
            self._print_system_config()
            
            # 启动调度器
            self.scheduler.start()
            self.is_running = True
            
            self.logger.info("✅ 系统启动成功，开始持续预测")
            
            # 主循环
            self._main_loop()
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 系统启动失败: {e}")
            return False
    
    def _print_system_config(self):
        """打印系统配置"""
        print("\n" + "="*60)
        print("🔧 KRONOS 持续预测系统配置")
        print("="*60)
        print(f"📊 交易对: {self.trading_config.instrument}")
        print(f"⏰ 预测间隔: {self.prediction_interval} 分钟")
        print(f"📈 回看时长: {self.lookback_hours} 小时")
        print(f"🔮 预测时长: {self.pred_hours} 小时")
        print(f"💻 计算设备: {self.device}")
        print(f"💾 数据库路径: {self.db_path}")
        print("="*60 + "\n")
    
    def _main_loop(self):
        """主循环"""
        try:
            while self.is_running:
                time.sleep(10)  # 每10秒检查一次
                
                # 可以在这里添加其他监控逻辑
                # 例如检查系统健康状态、内存使用等
                
        except KeyboardInterrupt:
            self.logger.info("收到中断信号，正在停止系统...")
        except Exception as e:
            self.logger.error(f"主循环异常: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """停止系统"""
        if not self.is_running:
            return
        
        self.logger.info("🛑 正在停止持续预测系统")
        self.is_running = False
        
        if self.scheduler:
            self.scheduler.stop()
        
        self.logger.info("✅ 系统已停止")
    
    def show_status(self):
        """显示系统状态"""
        if self.dashboard:
            self.dashboard.print_status_report()
        else:
            print("❌ 监控面板未初始化")
    
    def show_trends(self, hours: int = 24):
        """显示预测趋势"""
        if self.dashboard:
            self.dashboard.plot_prediction_trend(hours, f"./logs/trend_{datetime.now().strftime('%Y%m%d_%H%M')}.png")
        else:
            print("❌ 监控面板未初始化")
    
    def export_data(self, output_path: str, hours: int = 24):
        """导出数据"""
        if self.dashboard:
            self.dashboard.export_data(output_path, hours)
        else:
            print("❌ 监控面板未初始化")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Kronos持续预测系统")
    
    # 系统配置参数
    parser.add_argument("--interval", type=int, help="预测间隔（分钟），默认30")
    parser.add_argument("--lookback", type=int, help="回看时长（小时），默认12")
    parser.add_argument("--pred-hours", type=int, help="预测时长（小时），默认6")
    parser.add_argument("--device", type=str, choices=["auto", "cpu", "cuda", "mps"], help="计算设备，默认auto（自动选择最优）")
    parser.add_argument("--db-path", type=str, help="数据库路径，默认./data/predictions.db")
    
    # 操作模式
    parser.add_argument("--mode", type=str, choices=["run", "status", "trends", "export"], 
                       default="run", help="运行模式：run(持续运行), status(显示状态), trends(显示趋势), export(导出数据)")
    parser.add_argument("--hours", type=int, default=24, help="查看或导出的时间范围（小时）")
    parser.add_argument("--output", type=str, help="导出文件路径")
    
    args = parser.parse_args()
    
    # 配置日志
    setup_logging()
    
    # 创建系统实例
    system = ContinuousPredictionSystem(args)
    
    # 根据模式执行不同操作
    if args.mode == "run":
        # 持续运行模式
        system.start()
    elif args.mode == "status":
        # 状态查看模式
        system.initialize()
        system.show_status()
    elif args.mode == "trends":
        # 趋势查看模式
        system.initialize()
        system.show_trends(args.hours)
    elif args.mode == "export":
        # 数据导出模式
        if not args.output:
            print("❌ 导出模式需要指定 --output 参数")
            return
        system.initialize()
        system.export_data(args.output, args.hours)


if __name__ == "__main__":
    main()
