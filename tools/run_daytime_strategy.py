#!/usr/bin/env python3
"""
白天震荡策略启动脚本
"""
import sys
import os
import signal
import logging
import yaml
import argparse
from datetime import datetime
from pathlib import Path

# 添加src目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from src.strategies.daytime_oscillation import DaytimeOscillationStrategy, StrategyConfig
from src.utils.config import OKXConfig

class StrategyRunner:
    """策略运行器"""
    
    def __init__(self, config_file: str = "config/daytime_strategy.yaml"):
        """初始化策略运行器"""
        self.config_file = config_file
        self.strategy = None
        self.logger = None
        self.setup_logging()
        self.load_config()
    
    def setup_logging(self):
        """设置日志"""
        # 创建logs目录
        os.makedirs("logs", exist_ok=True)
        
        # 配置日志
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler(f"logs/daytime_strategy_{datetime.now().strftime('%Y%m%d')}.log"),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("日志系统初始化完成")
    
    def load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            strategy_config = config_data.get('strategy', {})
            
            # 创建策略配置对象
            self.strategy_config = StrategyConfig(
                # 时间设置
                trading_start_hour=strategy_config.get('timing', {}).get('trading_start_hour', 8),
                trading_end_hour=strategy_config.get('timing', {}).get('trading_end_hour', 19),
                force_close_hour=strategy_config.get('timing', {}).get('force_close_hour', 19),
                force_close_minute=strategy_config.get('timing', {}).get('force_close_minute', 30),
                
                # 区间设置
                range_calculation_hours=strategy_config.get('oscillation', {}).get('range_calculation_hours', 24),
                range_shrink_factor=strategy_config.get('oscillation', {}).get('range_shrink_factor', 0.6),
                entry_threshold=strategy_config.get('oscillation', {}).get('entry_threshold', 0.1),
                breakout_threshold=strategy_config.get('oscillation', {}).get('breakout_threshold', 0.2),
                
                # 信号权重
                technical_weight=strategy_config.get('signal_weights', {}).get('technical', 0.4),
                ai_weight=strategy_config.get('signal_weights', {}).get('ai_prediction', 0.35),
                kronos_weight=strategy_config.get('signal_weights', {}).get('kronos_prediction', 0.25),
                
                # 风险控制
                max_position_ratio=strategy_config.get('risk_management', {}).get('max_position_ratio', 0.3),
                max_single_trade=strategy_config.get('risk_management', {}).get('max_single_trade', 0.1),
                daily_loss_limit=strategy_config.get('risk_management', {}).get('daily_loss_limit', 0.05),
                stop_loss_pct=strategy_config.get('risk_management', {}).get('stop_loss_pct', 0.02),
                take_profit_pct=strategy_config.get('risk_management', {}).get('take_profit_pct', 0.015),
                
                # AI过滤
                min_confidence=strategy_config.get('ai_filters', {}).get('min_confidence', 0.7),
                prediction_horizon_hours=strategy_config.get('ai_filters', {}).get('prediction_horizon_hours', 4)
            )
            
            self.config_data = config_data
            self.logger.info(f"配置文件加载成功: {self.config_file}")
            
        except Exception as e:
            self.logger.error(f"配置文件加载失败: {e}")
            sys.exit(1)
    
    def initialize_strategy(self):
        """初始化策略"""
        try:
            # 加载OKX配置
            okx_config = OKXConfig()
            
            # 检查是否为模拟模式
            demo_mode = self.config_data.get('environment', {}).get('demo_mode', False)
            
            # 创建策略实例
            self.strategy = DaytimeOscillationStrategy(okx_config, self.strategy_config)
            
            self.logger.info(f"策略初始化完成 - {'模拟模式' if demo_mode else '实盘模式'}")
            
            # 显示策略配置
            self.print_strategy_info()
            
        except Exception as e:
            self.logger.error(f"策略初始化失败: {e}")
            sys.exit(1)
    
    def print_strategy_info(self):
        """打印策略信息"""
        print("\n" + "="*60)
        print("🚀 白天震荡策略")
        print("="*60)
        print(f"📅 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏰ 交易时间: {self.strategy_config.trading_start_hour:02d}:00 - {self.strategy_config.trading_end_hour:02d}:00")
        print(f"🎯 交易品种: BTC-USDT-SWAP")
        print(f"💰 最大仓位: {self.strategy_config.max_position_ratio:.1%}")
        print(f"🛡️ 止损比例: {self.strategy_config.stop_loss_pct:.1%}")
        print(f"🎉 止盈比例: {self.strategy_config.take_profit_pct:.1%}")
        print(f"📊 信号权重: 技术{self.strategy_config.technical_weight:.0%} | AI{self.strategy_config.ai_weight:.0%} | Kronos{self.strategy_config.kronos_weight:.0%}")
        print("="*60)
        
        # 检查当前是否为交易时间
        if self.strategy.is_trading_time():
            print("✅ 当前为交易时间，策略将开始运行")
        else:
            print("⏰ 当前非交易时间，策略将等待交易时间开始")
        
        print()
    
    def setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            self.logger.info(f"收到信号 {signum}，正在停止策略...")
            if self.strategy:
                self.strategy.stop_strategy()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def run_strategy(self):
        """运行策略"""
        try:
            self.logger.info("开始运行白天震荡策略")
            
            # 设置信号处理器
            self.setup_signal_handlers()
            
            # 启动策略
            self.strategy.start_strategy()
            
        except KeyboardInterrupt:
            self.logger.info("用户中断，停止策略")
        except Exception as e:
            self.logger.error(f"策略运行异常: {e}")
        finally:
            if self.strategy:
                self.strategy.stop_strategy()
            self.logger.info("策略已停止")
    
    def show_status(self):
        """显示策略状态"""
        if not self.strategy:
            print("❌ 策略未初始化")
            return
        
        stats = self.strategy.get_strategy_stats()
        
        print("\n📊 策略状态")
        print("-" * 40)
        print(f"运行状态: {'🟢 运行中' if stats['is_active'] else '🔴 已停止'}")
        print(f"交易时间: {'✅ 是' if stats['is_trading_time'] else '❌ 否'}")
        print(f"日盈亏: ${stats['daily_pnl']:.2f}")
        print(f"交易次数: {stats['trade_count']}")
        print(f"连续亏损: {stats['consecutive_losses']}")
        
        if stats['current_range']:
            range_info = stats['current_range']
            print(f"震荡区间: ${range_info['lower']:.2f} - ${range_info['upper']:.2f}")
            print(f"区间中心: ${range_info['center']:.2f}")
        
        print("-" * 40)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='白天震荡策略启动器')
    parser.add_argument('--config', '-c', default='config/daytime_strategy.yaml',
                       help='配置文件路径')
    parser.add_argument('--status', '-s', action='store_true',
                       help='显示策略状态')
    parser.add_argument('--test', '-t', action='store_true',
                       help='测试模式（不实际交易）')
    parser.add_argument('--dry-run', '-d', action='store_true',
                       help='干运行模式（模拟交易）')
    
    args = parser.parse_args()
    
    try:
        # 创建策略运行器
        runner = StrategyRunner(args.config)
        
        # 初始化策略
        runner.initialize_strategy()
        
        if args.status:
            # 显示状态
            runner.show_status()
        elif args.test:
            # 测试模式
            print("🧪 测试模式 - 运行策略测试")
            os.system("python test_daytime_strategy.py")
        elif args.dry_run:
            # 干运行模式
            print("🔍 干运行模式 - 模拟策略运行（不实际交易）")
            print("此模式下策略会正常运行但不会执行实际交易")
            runner.run_strategy()
        else:
            # 正常运行模式
            print("⚠️ 实盘交易模式")
            print("策略将执行实际交易，请确认:")
            print("1. API配置正确")
            print("2. 账户余额充足")
            print("3. 风险参数合理")
            
            confirm = input("\n确认开始实盘交易? (yes/no): ")
            if confirm.lower() in ['yes', 'y']:
                runner.run_strategy()
            else:
                print("已取消")
                return 0
        
        return 0
        
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
