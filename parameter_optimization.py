#!/usr/bin/env python3
"""
Kronos参数优化测试脚本
测试不同参数组合对预测准确性的影响
"""
import sys
import time
import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils.config import OKXConfig, TradingConfig
from src.trading.prediction_service import PredictionService


class ParameterOptimizer:
    """参数优化器"""
    
    def __init__(self, device: str = "cpu"):
        """初始化优化器"""
        self.okx_config = OKXConfig()
        self.trading_config = TradingConfig()
        self.device = device
        
        # 测试参数组合
        self.test_configs = [
            # 基准配置 (当前)
            {
                "name": "baseline",
                "lookback_hours": 12,
                "pred_hours": 3,
                "temperature": 1.0,
                "top_p": 0.9,
                "sample_count": 1
            },
            # 扩展数据窗口
            {
                "name": "extended_lookback_24h",
                "lookback_hours": 24,
                "pred_hours": 3,
                "temperature": 1.0,
                "top_p": 0.9,
                "sample_count": 1
            },
            {
                "name": "extended_lookback_48h",
                "lookback_hours": 48,
                "pred_hours": 3,
                "temperature": 1.0,
                "top_p": 0.9,
                "sample_count": 1
            },
            # 优化采样参数
            {
                "name": "lower_temperature",
                "lookback_hours": 24,
                "pred_hours": 3,
                "temperature": 0.7,
                "top_p": 0.9,
                "sample_count": 1
            },
            {
                "name": "higher_top_p",
                "lookback_hours": 24,
                "pred_hours": 3,
                "temperature": 0.8,
                "top_p": 0.95,
                "sample_count": 1
            },
            # 多样本采样
            {
                "name": "multi_sample_3",
                "lookback_hours": 24,
                "pred_hours": 3,
                "temperature": 0.8,
                "top_p": 0.9,
                "sample_count": 3
            },
            {
                "name": "multi_sample_5",
                "lookback_hours": 24,
                "pred_hours": 3,
                "temperature": 0.8,
                "top_p": 0.9,
                "sample_count": 5
            },
            # 短期预测优化
            {
                "name": "short_pred_1h",
                "lookback_hours": 24,
                "pred_hours": 1,
                "temperature": 0.6,
                "top_p": 0.85,
                "sample_count": 3
            },
            {
                "name": "short_pred_2h",
                "lookback_hours": 24,
                "pred_hours": 2,
                "temperature": 0.7,
                "top_p": 0.9,
                "sample_count": 3
            },
            # 确定性模式
            {
                "name": "deterministic",
                "lookback_hours": 24,
                "pred_hours": 3,
                "temperature": 0.1,
                "top_p": 0.5,
                "sample_count": 1
            }
        ]
        
        self.results = []
    
    def test_configuration(self, config: Dict) -> Dict:
        """测试单个配置"""
        print(f"\n🧪 测试配置: {config['name']}")
        print(f"   回看: {config['lookback_hours']}h, 预测: {config['pred_hours']}h")
        print(f"   温度: {config['temperature']}, Top-p: {config['top_p']}, 采样: {config['sample_count']}")
        
        try:
            # 创建预测服务
            service = PredictionService(self.okx_config, self.trading_config, self.device)
            
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
            
            # 提取关键指标
            stats = report['statistics']
            result = {
                "config_name": config['name'],
                "config": config,
                "duration": duration,
                "current_price": stats.get('current_price', 0),
                "predicted_price": stats.get('predicted_price_end', 0),
                "price_change": stats.get('price_change', 0),
                "price_change_pct": stats.get('price_change_pct', 0),
                "volatility": stats.get('volatility', 0),
                "trend_direction": stats.get('trend_direction', 'unknown'),
                "predicted_high": stats.get('predicted_high', 0),
                "predicted_low": stats.get('predicted_low', 0),
                "price_range": stats.get('predicted_high', 0) - stats.get('predicted_low', 0),
                "timestamp": datetime.now().isoformat()
            }
            
            print(f"   ✅ 完成 - 耗时: {duration:.2f}s")
            print(f"   📊 预测: ${result['current_price']:,.2f} → ${result['predicted_price']:,.2f} ({result['price_change_pct']:+.2f}%)")
            print(f"   📈 趋势: {result['trend_direction']}, 波动率: {result['volatility']:.2f}")
            
            return result
            
        except Exception as e:
            print(f"   ❌ 失败: {e}")
            return {
                "config_name": config['name'],
                "config": config,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def run_optimization(self, save_results: bool = True) -> List[Dict]:
        """运行参数优化测试"""
        print("🚀 开始Kronos参数优化测试")
        print(f"📋 测试配置数量: {len(self.test_configs)}")
        print("="*60)
        
        for i, config in enumerate(self.test_configs, 1):
            print(f"\n进度: {i}/{len(self.test_configs)}")
            result = self.test_configuration(config)
            self.results.append(result)
            
            # 短暂休息避免API限制
            if i < len(self.test_configs):
                print("⏳ 等待30秒避免API限制...")
                time.sleep(30)
        
        # 保存结果
        if save_results:
            self.save_results()
        
        # 分析结果
        self.analyze_results()
        
        return self.results
    
    def save_results(self):
        """保存测试结果"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"parameter_optimization_{timestamp}.json"
        filepath = Path("./logs") / filename
        
        # 确保目录存在
        filepath.parent.mkdir(exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 结果已保存到: {filepath}")
    
    def analyze_results(self):
        """分析测试结果"""
        print("\n" + "="*60)
        print("📊 参数优化结果分析")
        print("="*60)
        
        # 过滤成功的结果
        successful_results = [r for r in self.results if 'error' not in r]
        
        if not successful_results:
            print("❌ 没有成功的测试结果")
            return
        
        # 按不同指标排序
        print("\n🏆 最佳配置排名:")
        
        # 1. 按执行时间排序 (性能)
        print("\n⚡ 执行速度排名:")
        speed_ranking = sorted(successful_results, key=lambda x: x['duration'])
        for i, result in enumerate(speed_ranking[:5], 1):
            print(f"   {i}. {result['config_name']}: {result['duration']:.2f}秒")
        
        # 2. 按价格变化幅度排序 (预测敏感性)
        print("\n📈 预测敏感性排名 (价格变化幅度):")
        sensitivity_ranking = sorted(successful_results, key=lambda x: abs(x['price_change_pct']), reverse=True)
        for i, result in enumerate(sensitivity_ranking[:5], 1):
            print(f"   {i}. {result['config_name']}: {result['price_change_pct']:+.2f}%")
        
        # 3. 按波动率排序 (市场理解)
        print("\n🌊 市场波动理解排名:")
        volatility_ranking = sorted(successful_results, key=lambda x: x['volatility'], reverse=True)
        for i, result in enumerate(volatility_ranking[:5], 1):
            print(f"   {i}. {result['config_name']}: {result['volatility']:.2f}")
        
        # 4. 按预测范围排序 (不确定性量化)
        print("\n📊 预测范围排名 (不确定性量化):")
        range_ranking = sorted(successful_results, key=lambda x: x['price_range'], reverse=True)
        for i, result in enumerate(range_ranking[:5], 1):
            print(f"   {i}. {result['config_name']}: ${result['price_range']:,.2f}")
        
        # 综合推荐
        print("\n🎯 综合推荐:")
        self.recommend_best_config(successful_results)
    
    def recommend_best_config(self, results: List[Dict]):
        """推荐最佳配置"""
        # 综合评分算法
        for result in results:
            score = 0
            
            # 性能分 (执行时间越短越好)
            max_duration = max(r['duration'] for r in results)
            performance_score = (max_duration - result['duration']) / max_duration * 25
            
            # 敏感性分 (适度的价格变化)
            sensitivity_score = min(abs(result['price_change_pct']) * 5, 25)
            
            # 波动率分 (能够捕捉市场波动)
            volatility_score = min(result['volatility'] / 10, 25)
            
            # 稳定性分 (合理的预测范围)
            stability_score = min(result['price_range'] / 1000, 25)
            
            result['composite_score'] = performance_score + sensitivity_score + volatility_score + stability_score
        
        # 按综合分排序
        best_configs = sorted(results, key=lambda x: x['composite_score'], reverse=True)
        
        print("\n🥇 综合评分排名:")
        for i, result in enumerate(best_configs[:3], 1):
            print(f"   {i}. {result['config_name']}: {result['composite_score']:.1f}分")
            config = result['config']
            print(f"      回看: {config['lookback_hours']}h, 预测: {config['pred_hours']}h")
            print(f"      温度: {config['temperature']}, Top-p: {config['top_p']}, 采样: {config['sample_count']}")
            print(f"      预测: {result['price_change_pct']:+.2f}%, 耗时: {result['duration']:.2f}s")
        
        # 输出推荐命令
        best_config = best_configs[0]['config']
        print(f"\n🚀 推荐启动命令:")
        print(f"python continuous_prediction.py \\")
        print(f"  --interval 15 \\")
        print(f"  --lookback {best_config['lookback_hours']} \\")
        print(f"  --pred-hours {best_config['pred_hours']} \\")
        print(f"  --device auto")
        
        print(f"\n🔧 推荐调度器参数修改:")
        print(f"# 在 src/scheduler/prediction_scheduler.py 中修改:")
        print(f"self.temperature = {best_config['temperature']}")
        print(f"self.top_p = {best_config['top_p']}")
        print(f"self.sample_count = {best_config['sample_count']}")


def main():
    """主函数"""
    print("🎯 Kronos参数优化工具")
    print("这将测试多种参数组合以找到最佳配置")
    print("⚠️  注意: 完整测试需要约10-15分钟")
    
    response = input("\n是否继续? (y/N): ").strip().lower()
    if response != 'y':
        print("已取消")
        return
    
    optimizer = ParameterOptimizer(device="auto")
    results = optimizer.run_optimization()
    
    print(f"\n✅ 参数优化完成! 测试了 {len(results)} 种配置")


if __name__ == "__main__":
    main()
