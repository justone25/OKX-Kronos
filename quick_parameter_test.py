#!/usr/bin/env python3
"""
快速参数测试 - 对比当前配置和推荐配置
"""
import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils.config import OKXConfig, TradingConfig
from src.trading.prediction_service import PredictionService


def test_current_vs_optimized():
    """对比当前配置和优化配置"""
    print("🎯 Kronos参数对比测试")
    print("="*50)
    
    # 配置
    okx_config = OKXConfig()
    trading_config = TradingConfig()
    
    # 测试配置
    configs = [
        {
            "name": "当前配置",
            "lookback_hours": 12,
            "pred_hours": 3,
            "temperature": 1.0,
            "top_p": 0.9,
            "sample_count": 1
        },
        {
            "name": "推荐配置1 (保守优化)",
            "lookback_hours": 24,
            "pred_hours": 2,
            "temperature": 0.8,
            "top_p": 0.9,
            "sample_count": 3
        },
        {
            "name": "推荐配置2 (高精度)",
            "lookback_hours": 24,
            "pred_hours": 1,
            "temperature": 0.6,
            "top_p": 0.85,
            "sample_count": 3
        }
    ]
    
    results = []
    
    for i, config in enumerate(configs, 1):
        print(f"\n🧪 测试 {i}/{len(configs)}: {config['name']}")
        print(f"   参数: 回看{config['lookback_hours']}h, 预测{config['pred_hours']}h")
        print(f"   采样: T={config['temperature']}, p={config['top_p']}, n={config['sample_count']}")
        
        try:
            # 创建预测服务
            service = PredictionService(okx_config, trading_config, device="auto")
            
            # 记录开始时间
            start_time = time.time()
            
            # 执行预测
            report = service.get_prediction(
                lookback_hours=config['lookback_hours'],
                pred_hours=config['pred_hours'],
                temperature=config['temperature'],
                top_p=config['top_p'],
                sample_count=config['sample_count'],
                seed=42  # 固定种子确保可比性
            )
            
            # 记录结束时间
            end_time = time.time()
            duration = end_time - start_time
            
            # 提取结果
            stats = report['statistics']
            result = {
                "name": config['name'],
                "duration": duration,
                "current_price": stats.get('current_price', 0),
                "predicted_price": stats.get('predicted_price_end', 0),
                "price_change_pct": stats.get('price_change_pct', 0),
                "volatility": stats.get('volatility', 0),
                "trend_direction": stats.get('trend_direction', 'unknown')
            }
            
            results.append(result)
            
            print(f"   ✅ 完成 - 耗时: {duration:.2f}秒")
            print(f"   📊 预测: ${result['current_price']:,.2f} → ${result['predicted_price']:,.2f}")
            print(f"   📈 变化: {result['price_change_pct']:+.2f}%, 趋势: {result['trend_direction']}")
            print(f"   🌊 波动率: {result['volatility']:.2f}")
            
        except Exception as e:
            print(f"   ❌ 失败: {e}")
            results.append({"name": config['name'], "error": str(e)})
        
        # 等待避免API限制
        if i < len(configs):
            print("   ⏳ 等待30秒...")
            time.sleep(30)
    
    # 分析结果
    print("\n" + "="*50)
    print("📊 测试结果对比")
    print("="*50)
    
    successful_results = [r for r in results if 'error' not in r]
    
    if len(successful_results) >= 2:
        print("\n🏆 性能对比:")
        for result in successful_results:
            print(f"   {result['name']}: {result['duration']:.2f}秒")
        
        print("\n📈 预测对比:")
        for result in successful_results:
            print(f"   {result['name']}: {result['price_change_pct']:+.2f}% ({result['trend_direction']})")
        
        print("\n🌊 波动率对比:")
        for result in successful_results:
            print(f"   {result['name']}: {result['volatility']:.2f}")
        
        # 推荐
        print("\n🎯 推荐:")
        if len(successful_results) > 1:
            # 简单的推荐逻辑
            best_performance = min(successful_results, key=lambda x: x['duration'])
            most_sensitive = max(successful_results, key=lambda x: abs(x['price_change_pct']))
            
            print(f"   ⚡ 最快配置: {best_performance['name']} ({best_performance['duration']:.2f}秒)")
            print(f"   📊 最敏感配置: {most_sensitive['name']} ({most_sensitive['price_change_pct']:+.2f}%)")
            
            if best_performance['name'] != "当前配置":
                print(f"\n🚀 建议切换到: {best_performance['name']}")
            else:
                print(f"\n✅ 当前配置已经是最优的")
    
    return results


def main():
    """主函数"""
    print("这将测试当前配置和2个推荐配置")
    print("⚠️  注意: 测试需要约2-3分钟")
    
    response = input("\n是否继续? (y/N): ").strip().lower()
    if response != 'y':
        print("已取消")
        return
    
    results = test_current_vs_optimized()
    print(f"\n✅ 测试完成! 共测试了 {len(results)} 种配置")


if __name__ == "__main__":
    main()
