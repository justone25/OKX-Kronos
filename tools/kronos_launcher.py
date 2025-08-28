#!/usr/bin/env python3
"""
Kronos统一启动器
整合所有启动功能到一个脚本中
"""
import sys
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.common import (
    setup_logging, setup_signal_handlers, create_base_parser,
    print_banner, print_status_info
)


class KronosLauncher:
    """Kronos统一启动器"""
    
    def __init__(self):
        self.logger = setup_logging()
        self.project_root = project_root
        
    def launch_daytime_strategy(self, args: List[str] = None):
        """启动白天震荡策略"""
        print_banner("🌅 白天震荡策略", "启动中...")
        
        cmd = [sys.executable, "tools/run_daytime_strategy.py"]
        if args:
            cmd.extend(args)
            
        return self._run_command(cmd)
    
    def launch_kronos_prediction(self, mode: str = "batch", **kwargs):
        """启动Kronos多币种预测与验证服务"""
        print_banner("🎯 Kronos多币种预测与验证", f"模式: {mode}")

        # 检查并下载模型
        if not self._check_and_download_models():
            self.logger.error("❌ 模型检查/下载失败，无法启动预测服务")
            return 1

        cmd = [sys.executable, "examples/kronos_multi_prediction.py", "--mode", mode]

        # 添加参数
        if "instruments" in kwargs:
            cmd.extend(["--instruments", str(kwargs["instruments"])])
        if "workers" in kwargs:
            cmd.extend(["--workers", str(kwargs["workers"])])
        if "interval" in kwargs:
            cmd.extend(["--interval", str(kwargs["interval"])])
        if "validation_interval" in kwargs:
            cmd.extend(["--validation-interval", str(kwargs["validation_interval"])])
        if "device" in kwargs:
            cmd.extend(["--device", kwargs["device"]])
        if "lookback" in kwargs:
            cmd.extend(["--lookback", str(kwargs["lookback"])])
        if "pred_hours" in kwargs:
            cmd.extend(["--pred-hours", str(kwargs["pred_hours"])])
        if kwargs.get("auto_validate"):
            cmd.append("--auto-validate")

        return self._run_command(cmd)

    def launch_integrated_service(self, **kwargs):
        """启动集成服务：预测服务 + Web面板"""
        print_banner("🚀 Kronos集成服务", "预测服务 + Web监控面板")

        import subprocess
        import time
        import signal
        import sys

        # 设置默认参数
        predict_kwargs = {
            "mode": kwargs.get("mode", "continuous"),
            "instruments": kwargs.get("instruments", 24),
            "workers": kwargs.get("workers", 4),
            "interval": kwargs.get("interval", 10),
            "validation_interval": kwargs.get("validation_interval", 5),
            "device": kwargs.get("device", "auto"),
            "auto_validate": kwargs.get("auto_validate", True)
        }

        dashboard_kwargs = {
            "host": kwargs.get("host", "127.0.0.1"),
            "port": kwargs.get("port", 8801),
            "debug": kwargs.get("debug", False)
        }

        # 构建预测服务命令
        predict_cmd = [sys.executable, "examples/kronos_multi_prediction.py"]
        predict_cmd.extend(["--mode", predict_kwargs["mode"]])
        predict_cmd.extend(["--instruments", str(predict_kwargs["instruments"])])
        predict_cmd.extend(["--workers", str(predict_kwargs["workers"])])
        predict_cmd.extend(["--interval", str(predict_kwargs["interval"])])
        predict_cmd.extend(["--validation-interval", str(predict_kwargs["validation_interval"])])
        predict_cmd.extend(["--device", predict_kwargs["device"]])
        if predict_kwargs["auto_validate"]:
            predict_cmd.append("--auto-validate")

        # 构建Web面板命令
        dashboard_cmd = [sys.executable, "examples/web_dashboard.py"]
        dashboard_cmd.extend(["--host", dashboard_kwargs["host"]])
        dashboard_cmd.extend(["--port", str(dashboard_kwargs["port"])])
        if dashboard_kwargs["debug"]:
            dashboard_cmd.append("--debug")

        processes = []

        try:
            # 启动Web面板
            self.logger.info("📊 启动Web监控面板...")
            dashboard_process = subprocess.Popen(dashboard_cmd, cwd=self.project_root)
            processes.append(dashboard_process)

            # 等待一下让Web面板启动
            time.sleep(3)

            print(f"\n✅ Web监控面板已启动")
            print(f"📊 访问地址: http://{dashboard_kwargs['host']}:{dashboard_kwargs['port']}")

            # 根据模式决定预测服务的启动方式
            if predict_kwargs['mode'] == 'batch':
                # batch模式：运行一次预测然后结束
                self.logger.info("🎯 运行批量预测...")
                predict_result = subprocess.run(predict_cmd, cwd=self.project_root)
                if predict_result.returncode == 0:
                    print(f"✅ 批量预测完成，{predict_kwargs['instruments']}个交易对")
                else:
                    print(f"❌ 批量预测失败")
            else:
                # continuous模式：持续运行
                self.logger.info("🎯 启动持续预测服务...")
                predict_process = subprocess.Popen(predict_cmd, cwd=self.project_root)
                processes.append(predict_process)
                print(f"🎯 持续预测服务: {predict_kwargs['mode']}模式，{predict_kwargs['instruments']}个交易对")

            print(f"\n按 Ctrl+C 停止服务")

            # 等待进程结束
            while True:
                time.sleep(5)
                # 检查Web面板进程状态
                if dashboard_process.poll() is not None:
                    self.logger.warning("Web面板进程已退出")
                    break

                # 如果是continuous模式且有持续预测进程，检查其状态
                if predict_kwargs['mode'] == 'continuous' and len(processes) > 1:
                    if processes[1].poll() is not None:
                        self.logger.error("❌ 预测服务进程意外退出，这不应该发生在continuous模式下")
                        self.logger.error("这可能表明预测服务存在严重问题，请检查日志")
                        break

        except KeyboardInterrupt:
            self.logger.info("收到中断信号，正在停止所有服务...")
        finally:
            # 停止所有进程
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()

            self.logger.info("✅ 所有服务已停止")
            return 0
    
    def launch_web_dashboard(self, host: str = "127.0.0.1", port: int = 8801, **kwargs):
        """启动Web监控面板"""
        print_banner("📊 Web监控面板", f"地址: http://{host}:{port}")
        
        cmd = [sys.executable, "examples/web_dashboard.py", "--host", host, "--port", str(port)]
        
        if "db_path" in kwargs:
            cmd.extend(["--db-path", kwargs["db_path"]])
        if kwargs.get("debug"):
            cmd.append("--debug")
            
        return self._run_command(cmd)
    
    def check_positions(self, query_type: str = "all", **kwargs):
        """检查持仓状态"""
        print_banner("📊 持仓查询", f"类型: {query_type}")
        
        cmd = [sys.executable, "tools/okx_positions_orders.py"]
        
        if query_type == "positions":
            cmd.append("--positions")
        elif query_type == "orders":
            cmd.append("--orders")
        elif query_type == "algo":
            cmd.append("--algo-orders")
        else:
            cmd.append("--all")
            
        if "inst_id" in kwargs:
            cmd.extend(["--inst-id", kwargs["inst_id"]])
        if "inst_type" in kwargs:
            cmd.extend(["--inst-type", kwargs["inst_type"]])
        if kwargs.get("json"):
            cmd.append("--json")
            
        return self._run_command(cmd)
    
    def run_benchmark(self):
        """运行设备基准测试"""
        print_banner("🏆 设备基准测试", "性能测试中...")
        
        cmd = [sys.executable, "tools/benchmark_devices.py"]
        return self._run_command(cmd)
    
    def show_prediction_status(self):
        """显示预测数据状态"""
        print_banner("📊 预测数据状态")
        
        try:
            import sqlite3
            import pandas as pd
            from datetime import datetime, timedelta
            
            db_path = self.project_root / "data" / "predictions.db"
            if not db_path.exists():
                print("❌ 预测数据库不存在")
                return False
                
            conn = sqlite3.connect(str(db_path))
            
            # 查询各交易对的预测数据
            query = '''
            SELECT instrument, 
                   COUNT(*) as total_predictions,
                   MIN(timestamp) as earliest,
                   MAX(timestamp) as latest,
                   AVG(price_change_pct) as avg_change_pct
            FROM predictions 
            GROUP BY instrument 
            ORDER BY total_predictions DESC
            '''
            
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            print('📊 各交易对Kronos预测数据统计:')
            print('=' * 80)
            for _, row in df.iterrows():
                print(f'{row["instrument"]:20} | 预测数: {row["total_predictions"]:4d} | '
                      f'最新: {row["latest"][:16]} | 平均变化: {row["avg_change_pct"]:+6.2f}%')
            
            print(f'\n总计: {len(df)}个交易对有预测数据')
            return True
            
        except Exception as e:
            print(f"❌ 查询预测状态失败: {e}")
            return False
    
    def _check_and_download_models(self) -> bool:
        """检查模型是否存在，不存在则下载"""
        try:
            models_dir = self.project_root / "models"
            kronos_model_path = models_dir / "kronos-small"
            tokenizer_path = models_dir / "tokenizer"

            # 检查模型是否存在
            model_exists = (kronos_model_path.exists() and
                          (kronos_model_path / "config.json").exists() and
                          (kronos_model_path / "model.safetensors").exists())

            tokenizer_exists = (tokenizer_path.exists() and
                              (tokenizer_path / "config.json").exists() and
                              (tokenizer_path / "model.safetensors").exists())

            if model_exists and tokenizer_exists:
                self.logger.info("✅ Kronos模型和Tokenizer已存在")
                return True

            # 需要下载模型
            self.logger.info("📥 Kronos模型不存在，开始下载...")
            print("📥 正在下载Kronos预训练模型，这可能需要几分钟...")

            # 导入下载模块
            sys.path.insert(0, str(self.project_root / "src" / "models"))
            from download_models import download_kronos_models

            # 执行下载
            success = download_kronos_models()
            if success:
                self.logger.info("✅ Kronos模型下载完成")
                print("✅ 模型下载完成！")
                return True
            else:
                self.logger.error("❌ Kronos模型下载失败")
                print("❌ 模型下载失败，请检查网络连接")
                return False

        except Exception as e:
            self.logger.error(f"❌ 模型检查/下载异常: {e}")
            print(f"❌ 模型检查/下载异常: {e}")
            return False

    def _run_command(self, cmd: List[str]) -> int:
        """运行命令"""
        try:
            # 切换到项目根目录
            os.chdir(self.project_root)

            # 运行命令
            result = subprocess.run(cmd, cwd=self.project_root)
            return result.returncode

        except KeyboardInterrupt:
            print("\n⚠️ 用户中断")
            return 1
        except Exception as e:
            print(f"❌ 命令执行失败: {e}")
            return 1


def main():
    """主函数"""
    parser = create_base_parser("Kronos统一启动器")
    
    # 添加启动器特有的参数
    parser.add_argument("command", nargs="?", default="start",
                       help="要执行的命令 (默认: start)")
    parser.add_argument("--mode", type=str, default="continuous",
                       help="预测运行模式 (默认: continuous)")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                       help="Web服务器地址")
    parser.add_argument("--port", type=int, default=8801,
                       help="Web服务器端口")
    parser.add_argument("--instruments", type=int, default=24,
                       help="交易对数量 (默认: 24)")
    parser.add_argument("--workers", type=int, default=4,
                       help="工作线程数")
    parser.add_argument("--interval", type=int, default=10,
                       help="预测间隔（分钟）(默认: 10)")
    parser.add_argument("--validation-interval", type=int, default=5,
                       help="验证间隔（分钟）")
    parser.add_argument("--device", type=str, default="auto",
                       choices=["cpu", "mps", "auto"],
                       help="计算设备")
    parser.add_argument("--auto-validate", action="store_true", default=True,
                       help="批量模式下自动验证 (默认: True)")
    parser.add_argument("--debug", action="store_true",
                       help="Web面板调试模式")
    
    args = parser.parse_args()
    
    # 创建启动器
    launcher = KronosLauncher()
    
    # 根据命令执行相应操作
    if args.command == "help":
        print_help()
        return 0
    elif args.command == "start":
        # 默认启动集成服务（预测 + 面板）
        return launcher.launch_integrated_service(
            mode=args.mode, instruments=args.instruments,
            workers=args.workers, interval=args.interval,
            validation_interval=args.validation_interval,
            device=args.device, auto_validate=args.auto_validate,
            host=args.host, port=args.port, debug=args.debug
        )
    elif args.command == "strategy":
        return launcher.launch_daytime_strategy()
    elif args.command == "predict":
        return launcher.launch_kronos_prediction(
            mode=args.mode, instruments=args.instruments,
            workers=args.workers, interval=args.interval,
            validation_interval=args.validation_interval,
            device=args.device, auto_validate=args.auto_validate
        )
    elif args.command == "dashboard":
        return launcher.launch_web_dashboard(
            host=args.host, port=args.port, debug=args.debug
        )
    elif args.command == "positions":
        return launcher.check_positions()
    elif args.command == "benchmark":
        return launcher.run_benchmark()
    elif args.command == "status":
        success = launcher.show_prediction_status()
        return 0 if success else 1
    else:
        print(f"❌ 未知命令: {args.command}")
        print_help()
        return 1


def print_help():
    """打印帮助信息"""
    print_banner("🚀 Kronos统一启动器", "使用说明")
    
    commands = {
        "start": "启动集成服务（预测+面板）【默认】",
        "strategy": "启动白天震荡策略",
        "predict": "仅启动Kronos预测服务",
        "dashboard": "仅启动Web监控面板",
        "positions": "查询持仓状态",
        "benchmark": "运行设备基准测试",
        "status": "显示预测数据状态"
    }
    
    print("📖 可用命令:")
    for cmd, desc in commands.items():
        print(f"  {cmd:12} - {desc}")
    
    print("\n💡 使用示例:")
    print("  python tools/kronos_launcher.py                    # 默认启动集成服务")
    print("  python tools/kronos_launcher.py start              # 启动集成服务（预测+面板）")
    print("  python tools/kronos_launcher.py start --port 8080  # 自定义端口")
    print("  python tools/kronos_launcher.py predict --mode continuous  # 仅预测服务")
    print("  python tools/kronos_launcher.py dashboard          # 仅Web面板")
    print("  python tools/kronos_launcher.py status             # 查看状态")

    print("\n🎯 默认参数:")
    print("  交易对数量: 24")
    print("  预测模式: continuous")
    print("  预测间隔: 10分钟")
    print("  验证间隔: 5分钟")
    print("  自动验证: 开启")
    print("  Web端口: 8801")


if __name__ == "__main__":
    sys.exit(main())
