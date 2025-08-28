#!/usr/bin/env python3
"""
多币种并发虚拟交易测试
监控前24个交易对，AI决策驱动的三合一策略
"""
import sys
import os
import logging
import signal
import time
from datetime import datetime
from typing import Dict, List

# 添加项目根目录到路径
project_root = os.path.dirname(__file__)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

def setup_logging():
    """设置日志"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 控制台日志
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    
    # 文件日志
    file_handler = logging.FileHandler(
        f'multi_pair_trading_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))
    
    # 根日志配置
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # 减少第三方库的日志噪音
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)

class MultiPairTradingSystem:
    """多币种交易系统"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self.monitor = None
        
        # 信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        self.logger.info(f"收到信号 {signum}，正在优雅关闭...")
        self.is_running = False
    
    def initialize(self, pair_count: int = 24, max_workers: int = 8) -> bool:
        """初始化系统"""
        try:
            self.logger.info("🚀 初始化多币种并发交易系统")
            self.logger.info("=" * 80)
            
            # 导入必要的模块
            from src.utils.config import OKXConfig
            from src.trading.concurrent_monitor import ConcurrentMonitor
            from src.data.market_scanner import MarketScanner
            
            # 创建配置
            config = OKXConfig()
            
            # 测试OKX连接
            self.logger.info("🔗 测试OKX API连接...")
            scanner = MarketScanner(config)
            test_pairs = scanner.get_top_trading_pairs(1)  # 测试获取1个交易对
            
            if not test_pairs:
                self.logger.error("❌ OKX API连接失败或无法获取交易对")
                return False
            
            self.logger.info("✅ OKX API连接正常")
            
            # 创建并发监控器
            self.logger.info(f"📊 创建并发监控器 (最大工作线程: {max_workers})")
            self.monitor = ConcurrentMonitor(config, max_workers=max_workers)
            
            # 初始化监控
            self.logger.info(f"🎯 初始化{pair_count}个交易对的监控...")
            if not self.monitor.initialize_monitoring(pair_count):
                self.logger.error("❌ 监控系统初始化失败")
                return False
            
            self.logger.info("✅ 多币种交易系统初始化完成")
            self._print_system_info()
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 系统初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def start(self, update_interval: int = 60):
        """启动交易系统"""
        try:
            self.logger.info("🎯 启动多币种并发交易系统")
            self.logger.info(f"   更新间隔: {update_interval}秒")
            self.logger.info(f"   资金管理: 总资金 $100,000, 最大持仓比例 30%")
            self.logger.info("=" * 80)
            
            self.is_running = True
            start_time = time.time()
            
            # 状态报告计时器
            last_status_report = time.time()
            status_interval = 600  # 10分钟报告一次状态
            
            # 开始监控（在单独线程中）
            import threading
            monitor_thread = threading.Thread(
                target=self._run_monitoring,
                args=(update_interval,),
                daemon=True
            )
            monitor_thread.start()
            
            # 主循环 - 状态监控和报告
            while self.is_running:
                try:
                    current_time = time.time()
                    
                    # 定期状态报告
                    if current_time - last_status_report >= status_interval:
                        self._print_status_report()
                        last_status_report = current_time
                    
                    # 检查监控线程是否还在运行
                    if not monitor_thread.is_alive():
                        self.logger.error("监控线程已停止，重新启动...")
                        monitor_thread = threading.Thread(
                            target=self._run_monitoring,
                            args=(update_interval,),
                            daemon=True
                        )
                        monitor_thread.start()
                    
                    time.sleep(30)  # 主循环每30秒检查一次
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    self.logger.error(f"主循环异常: {e}")
                    time.sleep(10)
            
            # 计算运行时间
            total_runtime = time.time() - start_time
            self._print_final_report(total_runtime)
            
        except Exception as e:
            self.logger.error(f"❌ 系统运行异常: {e}")
            import traceback
            traceback.print_exc()
    
    def _run_monitoring(self, update_interval: int):
        """运行监控（在单独线程中）"""
        try:
            self.monitor.start_monitoring(update_interval)
        except Exception as e:
            self.logger.error(f"监控线程异常: {e}")
    
    def _print_system_info(self):
        """打印系统信息"""
        if not self.monitor:
            return
        
        status = self.monitor.get_monitoring_status()
        
        print(f"\n📊 系统配置信息:")
        print(f"   监控交易对数量: {status['total_pairs']}")
        print(f"   活跃监控任务: {status['active_pairs']}")
        print(f"   最大工作线程: {self.monitor.max_workers}")
        print(f"   AI并发限制: 3个")
        print(f"   总资金: ${self.monitor.total_capital:,.0f}")
        print(f"   最大持仓比例: {self.monitor.max_position_ratio:.0%}")
        
        print(f"\n🎯 策略配置:")
        print(f"   📊 技术指标: 震荡区间分析")
        print(f"   🤖 AI预测: 智谱AI市场分析")
        print(f"   🧠 Kronos预测: 深度学习趋势预测")
        print(f"   🎯 最终决策: AI综合决策")
    
    def _print_status_report(self):
        """打印状态报告"""
        if not self.monitor:
            return
        
        status = self.monitor.get_monitoring_status()
        stats = status['stats']
        
        print(f"\n" + "=" * 80)
        print(f"📊 系统状态报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"=" * 80)
        
        print(f"🎯 监控状态:")
        print(f"   总交易对: {status['total_pairs']}")
        print(f"   活跃监控: {status['active_pairs']}")
        print(f"   累计错误: {status['total_errors']}")
        print(f"   信号队列: {status['signal_queue_size']}")
        
        print(f"\n💰 资金状态:")
        print(f"   当前持仓比例: {status['position_ratio']:.1%}")
        print(f"   可用资金比例: {(1-status['position_ratio']):.1%}")
        
        print(f"\n📈 交易统计:")
        print(f"   总信号数: {stats['total_signals']}")
        print(f"   成功交易: {stats['successful_trades']}")
        print(f"   拒绝交易: {stats['rejected_trades']}")
        print(f"   AI调用次数: {stats['ai_calls']}")
        print(f"   系统错误: {stats['errors']}")
        
        if stats['total_signals'] > 0:
            success_rate = stats['successful_trades'] / stats['total_signals'] * 100
            print(f"   成功率: {success_rate:.1f}%")
    
    def _print_final_report(self, runtime: float):
        """打印最终报告"""
        print(f"\n" + "=" * 80)
        print(f"🏁 多币种交易系统运行结束")
        print(f"=" * 80)
        
        print(f"⏱️ 总运行时间: {runtime/3600:.1f} 小时")
        
        if self.monitor:
            status = self.monitor.get_monitoring_status()
            stats = status['stats']
            
            print(f"\n📊 最终统计:")
            print(f"   监控的交易对: {status['total_pairs']}")
            print(f"   生成的信号: {stats['total_signals']}")
            print(f"   执行的交易: {stats['successful_trades']}")
            print(f"   AI调用次数: {stats['ai_calls']}")
            print(f"   系统错误: {stats['errors']}")
            
            if runtime > 0:
                signals_per_hour = stats['total_signals'] / (runtime / 3600)
                print(f"   平均信号频率: {signals_per_hour:.1f} 信号/小时")
        
        print(f"\n💡 感谢使用 OKX-Kronos 多币种AI交易系统！")

def main():
    """主函数"""
    # 设置日志
    setup_logging()
    
    # 创建交易系统
    system = MultiPairTradingSystem()
    
    try:
        # 初始化系统
        if not system.initialize(pair_count=24, max_workers=8):
            print("❌ 系统初始化失败")
            return 1
        
        # 启动系统
        system.start(update_interval=60)
        
        return 0
        
    except KeyboardInterrupt:
        print("\n👋 用户中断，系统正在关闭...")
        return 0
    except Exception as e:
        print(f"❌ 系统异常: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
