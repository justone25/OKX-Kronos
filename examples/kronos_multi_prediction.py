#!/usr/bin/env python3
"""
Kronos多币种预测与验证服务
整合预测生成、持续监控和结果验证的完整解决方案
"""
import os
import sys
import time
import signal
import logging
import argparse
import threading
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config import OKXConfig, TradingConfig
from src.trading.prediction_service import PredictionService
from src.scheduler.prediction_scheduler import PredictionScheduler
from src.validation.prediction_validator import PredictionValidator
from src.data.market_scanner import MarketScanner
from src.utils.common import setup_logging, setup_signal_handlers, print_banner, print_status_info


class KronosMultiPairPredictionService:
    """Kronos多币种预测与验证服务"""
    
    def __init__(self, args):
        """初始化服务"""
        self.logger = setup_logging(args.log_level)
        self.args = args
        
        # 基础配置
        self.instruments = []
        self.device = args.device
        self.max_workers = args.workers
        self.db_path = str(project_root / "data" / "predictions.db")
        
        # 预测配置
        self.prediction_interval = args.interval  # 分钟
        self.lookback_hours = args.lookback
        self.pred_hours = args.pred_hours
        
        # 验证配置
        self.validation_interval = args.validation_interval  # 分钟
        
        # 服务组件
        self.okx_config = OKXConfig()
        self.prediction_services = {}
        self.schedulers = {}
        self.validator = None
        
        # 运行状态
        self.is_running = False
        self.prediction_thread = None
        self.validation_thread = None
        
        # 统计信息
        self.stats = {
            'predictions_generated': 0,
            'validations_completed': 0,
            'start_time': None,
            'last_prediction_time': None,
            'last_validation_time': None
        }
        
        # 设置信号处理
        setup_signal_handlers(self.stop)
        
    def initialize(self) -> bool:
        """初始化服务组件"""
        try:
            print_banner("🚀 Kronos多币种预测与验证服务", "初始化中...")
            
            # 获取交易对列表
            self.instruments = self._get_top_instruments(self.args.instruments)
            self.logger.info(f"选择了{len(self.instruments)}个交易对进行预测")
            
            # 创建数据目录
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            
            # 初始化预测服务
            self._initialize_prediction_services()
            
            # 初始化验证器
            self._initialize_validator()
            
            self.logger.info("✅ 服务初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 服务初始化失败: {e}")
            return False
    
    def _get_top_instruments(self, count: int) -> List[str]:
        """获取前N个交易对"""
        try:
            # 优先使用BTC-USDT-SWAP，然后获取其他热门交易对
            default_pairs = ['BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP']

            if count <= len(default_pairs):
                return default_pairs[:count]

            # 如果需要更多交易对，从市场扫描器获取
            scanner = MarketScanner(self.okx_config)
            top_pairs = scanner.get_top_trading_pairs(count, inst_type='SWAP')
            pair_symbols = [pair.symbol for pair in top_pairs]

            # 确保BTC-USDT-SWAP在第一位
            if 'BTC-USDT-SWAP' in pair_symbols:
                pair_symbols.remove('BTC-USDT-SWAP')
            pair_symbols.insert(0, 'BTC-USDT-SWAP')

            return pair_symbols[:count]
        except Exception as e:
            self.logger.error(f"获取交易对失败: {e}")
            # 返回默认列表
            return ['BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP'][:count]
    
    def _initialize_prediction_services(self):
        """初始化预测服务"""
        self.logger.info("初始化预测服务...")
        
        for instrument in self.instruments:
            # 创建交易配置
            trading_config = TradingConfig()
            trading_config.instrument = instrument
            
            # 创建预测服务
            prediction_service = PredictionService(
                self.okx_config, 
                trading_config, 
                device=self.device
            )
            
            # 创建调度器
            scheduler = PredictionScheduler(
                okx_config=self.okx_config,
                trading_config=trading_config,
                db_path=self.db_path,
                device=self.device
            )
            
            # 配置调度器参数
            scheduler.prediction_interval = self.prediction_interval
            scheduler.lookback_hours = self.lookback_hours
            scheduler.pred_hours = self.pred_hours
            scheduler.temperature = 0.8
            scheduler.top_p = 0.9
            scheduler.sample_count = 1
            
            self.prediction_services[instrument] = prediction_service
            self.schedulers[instrument] = scheduler
            
            self.logger.info(f"✅ {instrument} 预测服务初始化完成")
    
    def _initialize_validator(self):
        """初始化验证器"""
        try:
            self.logger.info("初始化预测验证器...")

            self.validator = PredictionValidator(
                okx_config=self.okx_config,
                db_path=self.db_path
            )

            self.logger.info("✅ 预测验证器初始化完成")
            return True
        except Exception as e:
            self.logger.error(f"验证器初始化失败: {e}")
            return False
    
    def run_batch_prediction(self) -> Dict[str, Any]:
        """运行批量预测"""
        print_banner("🎯 批量预测模式", f"{len(self.instruments)}个交易对")
        
        start_time = time.time()
        results = []
        
        # 并发预测
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_instrument = {
                executor.submit(self._predict_single_instrument, instrument): instrument
                for instrument in self.instruments
            }
            
            for future in as_completed(future_to_instrument):
                instrument = future_to_instrument[future]
                try:
                    result = future.result()
                    results.append(result)
                    self.stats['predictions_generated'] += 1
                    self.logger.info(f"✅ {instrument} 预测完成")
                except Exception as e:
                    self.logger.error(f"❌ {instrument} 预测失败: {e}")
        
        # 运行一次验证
        if self.args.auto_validate:
            self.logger.info("🔍 运行预测验证...")
            validation_result = self.validator.run_validation_cycle()
            self.stats['validations_completed'] += validation_result.get('validated_count', 0)
        
        elapsed_time = time.time() - start_time
        
        # 显示结果
        summary = {
            "预测交易对数量": len(self.instruments),
            "成功预测数量": len(results),
            "总耗时": f"{elapsed_time:.1f}秒",
            "平均耗时": f"{elapsed_time/len(self.instruments):.1f}秒/交易对"
        }
        
        if self.args.auto_validate:
            summary["验证预测数量"] = self.stats['validations_completed']
        
        print_status_info(summary, "批量预测结果")
        
        return {
            'success': True,
            'results': results,
            'stats': summary
        }
    
    def start_continuous_prediction(self):
        """启动持续预测模式"""
        print_banner("🔄 持续预测模式", f"{len(self.instruments)}个交易对，{self.prediction_interval}分钟间隔")

        self.is_running = True
        self.stats['start_time'] = datetime.now()

        # 启动预测线程（非daemon，确保主进程不会意外退出）
        self.prediction_thread = threading.Thread(target=self._prediction_loop, daemon=False)
        self.prediction_thread.start()

        # 启动验证线程（非daemon）
        self.validation_thread = threading.Thread(target=self._validation_loop, daemon=False)
        self.validation_thread.start()

        self.logger.info("✅ 持续预测服务已启动")

        try:
            # 主线程持续监控和状态显示
            while self.is_running:
                time.sleep(10)
                self._print_running_status()

                # 检查线程健康状态
                if not self.prediction_thread.is_alive():
                    self.logger.error("❌ 预测线程意外停止")
                    break

                if not self.validation_thread.is_alive():
                    self.logger.error("❌ 验证线程意外停止")
                    break

        except KeyboardInterrupt:
            self.logger.info("收到中断信号，正在停止服务...")
            self.stop()

        # 等待线程正常结束
        if hasattr(self, 'prediction_thread') and self.prediction_thread.is_alive():
            self.prediction_thread.join(timeout=30)
        if hasattr(self, 'validation_thread') and self.validation_thread.is_alive():
            self.validation_thread.join(timeout=30)
    
    def _predict_single_instrument(self, instrument: str) -> Dict[str, Any]:
        """为单个交易对生成预测"""
        try:
            service = self.prediction_services[instrument]

            # 生成预测
            report = service.get_prediction(
                lookback_hours=self.lookback_hours,
                pred_hours=self.pred_hours,
                temperature=0.8,
                top_p=0.9,
                sample_count=1
            )

            # 保存预测结果到数据库
            try:
                scheduler = self.schedulers[instrument]
                scheduler.save_prediction(report)
                self.logger.info(f"✅ [{instrument}] 预测结果已保存到数据库")
            except Exception as save_error:
                self.logger.error(f"❌ [{instrument}] 保存预测结果失败: {save_error}")

            return {
                'instrument': instrument,
                'success': True,
                'prediction': report
            }

        except Exception as e:
            self.logger.error(f"[{instrument}] 预测失败: {e}")
            return {
                'instrument': instrument,
                'success': False,
                'error': str(e)
            }
    
    def _prediction_loop(self):
        """预测循环"""
        self.logger.info("🎯 预测循环线程已启动")

        while self.is_running:
            try:
                # 在循环开始时检查是否仍在运行
                if not self.is_running:
                    break

                self.logger.info("🎯 开始新一轮预测...")

                # 并发预测所有交易对
                executor = None
                try:
                    executor = ThreadPoolExecutor(max_workers=self.max_workers)
                    futures = []

                    # 只有在服务运行时才提交任务
                    if self.is_running:
                        futures = [
                            executor.submit(self._predict_single_instrument, instrument)
                            for instrument in self.instruments
                        ]

                    successful_predictions = 0
                    for future in as_completed(futures):
                        # 在处理结果前再次检查运行状态
                        if not self.is_running:
                            break
                        result = future.result()
                        if result['success']:
                            successful_predictions += 1

                    if self.is_running:  # 只有在服务运行时才更新统计
                        self.stats['predictions_generated'] += successful_predictions
                        self.stats['last_prediction_time'] = datetime.now()
                        self.logger.info(f"✅ 本轮预测完成，成功{successful_predictions}/{len(self.instruments)}个")

                finally:
                    # 确保executor被正确关闭
                    if executor:
                        executor.shutdown(wait=True)

                # 等待下一轮（分段等待，便于响应停止信号）
                wait_time = self.prediction_interval * 60
                while wait_time > 0 and self.is_running:
                    sleep_duration = min(30, wait_time)  # 每30秒检查一次停止信号
                    time.sleep(sleep_duration)
                    wait_time -= sleep_duration

            except Exception as e:
                self.logger.error(f"❌ 预测循环异常: {e}")
                if self.is_running:  # 只有在服务运行时才重试
                    self.logger.info("⏳ 等待60秒后重试...")
                    # 分段等待，便于响应停止信号
                    for _ in range(60):
                        if not self.is_running:
                            break
                        time.sleep(1)

        self.logger.info("🎯 预测循环线程已停止")
    
    def _validation_loop(self):
        """验证循环"""
        self.logger.info("🔍 验证循环线程已启动")

        while self.is_running:
            try:
                self.logger.info("🔍 开始预测验证...")

                validation_result = self.validator.run_validation_cycle()
                validated_count = validation_result.get('validated_count', 0)

                if validated_count > 0:
                    self.stats['validations_completed'] += validated_count
                    self.stats['last_validation_time'] = datetime.now()
                    self.logger.info(f"✅ 验证完成，处理了{validated_count}个预测")

                # 等待下一轮验证（分段等待，便于响应停止信号）
                wait_time = self.validation_interval * 60
                while wait_time > 0 and self.is_running:
                    sleep_duration = min(30, wait_time)  # 每30秒检查一次停止信号
                    time.sleep(sleep_duration)
                    wait_time -= sleep_duration

            except Exception as e:
                self.logger.error(f"❌ 验证循环异常: {e}")
                if self.is_running:  # 只有在服务运行时才重试
                    self.logger.info("⏳ 等待300秒后重试...")
                    time.sleep(300)  # 出错后等待5分钟再重试

        self.logger.info("🔍 验证循环线程已停止")
    
    def _print_running_status(self):
        """打印运行状态"""
        if self.stats['start_time']:
            uptime = datetime.now() - self.stats['start_time']
            uptime_str = str(uptime).split('.')[0]  # 去掉微秒

            # 获取当前会话的验证数量（今天的验证数）
            try:
                import sqlite3
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                # 获取今天的验证数量
                today = datetime.now().strftime('%Y-%m-%d')
                cursor.execute('''
                    SELECT COUNT(*) FROM prediction_validations
                    WHERE DATE(validation_timestamp) = ?
                ''', (today,))
                today_validations = cursor.fetchone()[0]

                # 获取当前运行会话的预测数量（用于对比）
                cursor.execute('''
                    SELECT COUNT(*) FROM predictions
                    WHERE DATE(timestamp) = ? AND timestamp >= ?
                ''', (today, self.stats['start_time'].isoformat()))
                session_predictions = cursor.fetchone()[0]

                conn.close()

                # 显示今天的验证数量，但不超过当前会话的预测数量
                current_validations = min(today_validations, session_predictions + self.stats['validations_completed'])

            except Exception as e:
                current_validations = self.stats['validations_completed']  # 备用方案

            status = {
                "运行时间": uptime_str,
                "预测交易对": len(self.instruments),
                "生成预测数": self.stats['predictions_generated'],
                "完成验证数": current_validations,
                "最后预测": self.stats['last_prediction_time'].strftime('%H:%M:%S') if self.stats['last_prediction_time'] else "未开始",
                "最后验证": self.stats['last_validation_time'].strftime('%H:%M:%S') if self.stats['last_validation_time'] else "未开始"
            }

            print_status_info(status, "服务运行状态")
    
    def stop(self):
        """停止服务"""
        self.logger.info("正在停止服务...")
        self.is_running = False
        
        # 等待线程结束
        if self.prediction_thread and self.prediction_thread.is_alive():
            self.prediction_thread.join(timeout=5)
        
        if self.validation_thread and self.validation_thread.is_alive():
            self.validation_thread.join(timeout=5)
        
        self.logger.info("✅ 服务已停止")

    def show_status(self):
        """显示预测数据状态"""
        try:
            import sqlite3
            import pandas as pd

            if not Path(self.db_path).exists():
                print("❌ 预测数据库不存在")
                return

            conn = sqlite3.connect(self.db_path)

            # 查询预测统计
            prediction_query = '''
            SELECT instrument,
                   COUNT(*) as total_predictions,
                   MIN(timestamp) as earliest,
                   MAX(timestamp) as latest,
                   AVG(price_change_pct) as avg_change_pct
            FROM predictions
            GROUP BY instrument
            ORDER BY total_predictions DESC
            '''

            pred_df = pd.read_sql_query(prediction_query, conn)

            # 查询验证统计
            validation_query = '''
            SELECT COUNT(*) as total_validations,
                   AVG(directional_accuracy) * 100 as avg_accuracy,
                   AVG(mape) as avg_mape,
                   AVG(mae) as avg_mae
            FROM prediction_validations
            '''

            val_result = conn.execute(validation_query).fetchone()
            conn.close()

            # 显示预测统计
            print_banner("📊 预测数据统计")
            if not pred_df.empty:
                print('各交易对预测数据:')
                print('=' * 80)
                for _, row in pred_df.iterrows():
                    print(f'{row["instrument"]:20} | 预测数: {row["total_predictions"]:4d} | '
                          f'最新: {row["latest"][:16]} | 平均变化: {row["avg_change_pct"]:+6.2f}%')
                print(f'\n总计: {len(pred_df)}个交易对有预测数据')
            else:
                print("暂无预测数据")

            # 显示验证统计
            print_banner("🔍 验证结果统计")
            if val_result and val_result[0] > 0:
                validation_stats = {
                    "总验证数量": val_result[0],
                    "平均方向准确率": f"{val_result[1]:.1f}%" if val_result[1] else "N/A",
                    "平均价格误差率": f"{val_result[2]:.2f}%" if val_result[2] else "N/A",
                    "平均绝对误差": f"${val_result[3]:.2f}" if val_result[3] else "N/A"
                }
                print_status_info(validation_stats)
            else:
                print("暂无验证数据")

        except Exception as e:
            self.logger.error(f"显示状态失败: {e}")

    def run_validation_only(self):
        """仅运行验证模式"""
        print_banner("🔍 预测验证模式", "验证历史预测结果")

        if not self._initialize_validator():
            return False

        try:
            validation_result = self.validator.run_validation_cycle()
            validated_count = validation_result.get('validated_count', 0)

            if validated_count > 0:
                print(f"✅ 验证完成，处理了{validated_count}个预测")

                # 显示验证统计
                self.show_status()
            else:
                print("暂无待验证的预测")

            return True

        except Exception as e:
            self.logger.error(f"验证失败: {e}")
            return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Kronos多币种预测与验证服务')

    # 运行模式
    parser.add_argument('--mode', choices=['batch', 'continuous', 'validate-only', 'status'],
                       default='batch', help='运行模式')

    # 预测参数
    parser.add_argument('--instruments', type=int, default=24,
                       help='预测的交易对数量 (默认: 24)')
    parser.add_argument('--workers', type=int, default=4,
                       help='并发工作线程数 (默认: 4)')
    parser.add_argument('--device', choices=['cpu', 'mps', 'auto'], default='auto',
                       help='计算设备 (默认: auto)')

    # 时间参数
    parser.add_argument('--interval', type=int, default=30,
                       help='预测间隔(分钟) (默认: 30)')
    parser.add_argument('--validation-interval', type=int, default=10,
                       help='验证间隔(分钟) (默认: 10)')
    parser.add_argument('--lookback', type=int, default=24,
                       help='历史数据回看小时数 (默认: 24)')
    parser.add_argument('--pred-hours', type=int, default=2,
                       help='预测时长(小时) (默认: 2)')

    # 其他选项
    parser.add_argument('--auto-validate', action='store_true',
                       help='批量模式下自动运行验证')
    parser.add_argument('--log-level', type=str, default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='日志级别')

    args = parser.parse_args()

    # 创建服务实例
    service = KronosMultiPairPredictionService(args)

    # 根据模式执行不同操作
    if args.mode == 'status':
        # 仅显示状态，不需要完整初始化
        service.show_status()
        return 0

    # 初始化服务
    if not service.initialize():
        print("❌ 服务初始化失败")
        return 1

    # 执行相应模式
    try:
        if args.mode == 'batch':
            result = service.run_batch_prediction()
            return 0 if result['success'] else 1
        elif args.mode == 'continuous':
            service.start_continuous_prediction()
            return 0
        elif args.mode == 'validate-only':
            success = service.run_validation_only()
            return 0 if success else 1
        else:
            print(f"❌ 未知模式: {args.mode}")
            return 1

    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
        service.stop()
        return 0
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
