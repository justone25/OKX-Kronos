#!/usr/bin/env python3
"""
设备性能基准测试
对比CPU vs MPS (M1 GPU)的预测性能
"""
import time
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config import OKXConfig, TradingConfig
from src.trading.prediction_service import PredictionService


def benchmark_device(device: str, runs: int = 3):
    """基准测试指定设备"""
    print(f"\n🔧 测试设备: {device.upper()}")
    print("="*50)
    
    try:
        # 初始化服务
        okx_config = OKXConfig()
        trading_config = TradingConfig()
        service = PredictionService(okx_config, trading_config, device=device)
        
        times = []
        
        for i in range(runs):
            print(f"运行 {i+1}/{runs}...")
            
            start_time = time.time()
            
            # 执行预测
            report = service.get_prediction(
                lookback_hours=6,
                pred_hours=1,
                temperature=1.0,
                top_p=0.9,
                sample_count=1,
                seed=42  # 固定种子确保公平比较
            )
            
            end_time = time.time()
            duration = end_time - start_time
            times.append(duration)
            
            print(f"  耗时: {duration:.2f}秒")
            print(f"  预测: ${report['statistics']['current_price']:,.2f} → ${report['statistics']['predicted_price_end']:,.2f}")
        
        # 计算统计信息
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        print(f"\n📊 {device.upper()} 性能统计:")
        print(f"  平均耗时: {avg_time:.2f}秒")
        print(f"  最快耗时: {min_time:.2f}秒")
        print(f"  最慢耗时: {max_time:.2f}秒")
        
        return avg_time, min_time, max_time
        
    except Exception as e:
        print(f"❌ {device.upper()} 测试失败: {e}")
        return None, None, None


def main():
    """主函数"""
    print("🚀 Kronos设备性能基准测试")
    print("="*60)
    print("测试配置:")
    print("  - 回看时长: 6小时")
    print("  - 预测时长: 1小时")
    print("  - 预测长度: 12个时间点")
    print("  - 运行次数: 3次")
    print("  - 固定随机种子: 42")
    
    # 测试CPU
    cpu_avg, cpu_min, cpu_max = benchmark_device("cpu", runs=3)
    
    # 测试MPS (M1 GPU)
    mps_avg, mps_min, mps_max = benchmark_device("mps", runs=3)
    
    # 性能对比
    if cpu_avg and mps_avg:
        print("\n" + "="*60)
        print("🏆 性能对比结果")
        print("="*60)
        
        speedup = cpu_avg / mps_avg
        
        print(f"CPU平均耗时:  {cpu_avg:.2f}秒")
        print(f"MPS平均耗时:  {mps_avg:.2f}秒")
        print(f"加速比:      {speedup:.2f}x")
        
        if speedup > 1:
            print(f"🚀 MPS比CPU快 {speedup:.1f}倍！")
            print("💡 建议使用MPS设备进行预测")
        elif speedup < 0.8:
            print(f"⚠️ MPS比CPU慢 {1/speedup:.1f}倍")
            print("💡 建议使用CPU设备进行预测")
        else:
            print("📊 两种设备性能相近")
            print("💡 可以使用任意设备")
        
        # 推荐配置
        print(f"\n🎯 推荐配置:")
        if speedup > 1.2:
            print("  ./start_continuous.sh gpu     # 使用MPS加速")
        else:
            print("  ./start_continuous.sh         # 使用默认配置")
    
    print("\n✅ 基准测试完成")


if __name__ == "__main__":
    main()
