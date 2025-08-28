#!/usr/bin/env python3
"""
智能信号融合器
解决信号冲突和动态权重调整问题
"""
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from .signals import TradingSignal, SignalType

class SignalSource(Enum):
    """信号源类型"""
    TECHNICAL = "technical"
    AI_PREDICTION = "ai_prediction"
    KRONOS_PREDICTION = "kronos_prediction"

class MarketCondition(Enum):
    """市场状态"""
    NORMAL = "normal"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    TRENDING = "trending"
    SIDEWAYS = "sideways"

@dataclass
class SignalPerformance:
    """信号性能记录"""
    source: SignalSource
    total_signals: int = 0
    correct_predictions: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    avg_confidence: float = 0.0
    recent_accuracy: float = 0.5  # 最近准确率
    
    @property
    def accuracy(self) -> float:
        """计算准确率"""
        if self.total_signals == 0:
            return 0.5  # 默认50%
        return self.correct_predictions / self.total_signals
    
    @property
    def precision(self) -> float:
        """计算精确率"""
        true_positives = self.correct_predictions
        if true_positives + self.false_positives == 0:
            return 0.5
        return true_positives / (true_positives + self.false_positives)
    
    @property
    def recall(self) -> float:
        """计算召回率"""
        true_positives = self.correct_predictions
        if true_positives + self.false_negatives == 0:
            return 0.5
        return true_positives / (true_positives + self.false_negatives)

class SmartSignalFusion:
    """智能信号融合器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 基础权重配置
        self.base_weights = {
            SignalSource.TECHNICAL: 0.40,
            SignalSource.AI_PREDICTION: 0.35,
            SignalSource.KRONOS_PREDICTION: 0.25
        }
        
        # 性能跟踪
        self.performance_history: Dict[SignalSource, SignalPerformance] = {
            source: SignalPerformance(source) for source in SignalSource
        }
        
        # 市场状态适应权重
        self.market_adaptive_weights = {
            MarketCondition.NORMAL: {
                SignalSource.TECHNICAL: 0.40,
                SignalSource.AI_PREDICTION: 0.35,
                SignalSource.KRONOS_PREDICTION: 0.25
            },
            MarketCondition.HIGH_VOLATILITY: {
                SignalSource.TECHNICAL: 0.50,  # 技术指标在高波动时更重要
                SignalSource.AI_PREDICTION: 0.30,
                SignalSource.KRONOS_PREDICTION: 0.20
            },
            MarketCondition.LOW_VOLATILITY: {
                SignalSource.TECHNICAL: 0.30,
                SignalSource.AI_PREDICTION: 0.40,  # AI在低波动时更准确
                SignalSource.KRONOS_PREDICTION: 0.30
            },
            MarketCondition.TRENDING: {
                SignalSource.TECHNICAL: 0.35,
                SignalSource.AI_PREDICTION: 0.40,  # AI善于识别趋势
                SignalSource.KRONOS_PREDICTION: 0.25
            },
            MarketCondition.SIDEWAYS: {
                SignalSource.TECHNICAL: 0.45,  # 震荡市技术指标更有效
                SignalSource.AI_PREDICTION: 0.30,
                SignalSource.KRONOS_PREDICTION: 0.25
            }
        }
        
        # 冲突解决策略
        self.conflict_resolution_enabled = True
        self.min_confidence_threshold = 0.6
        self.consensus_threshold = 0.7  # 需要70%的信号一致才认为有共识
        
        # 统计信息
        self.stats = {
            'total_fusions': 0,
            'conflicts_detected': 0,
            'consensus_achieved': 0,
            'performance_adjustments': 0
        }
    
    def fuse_signals(self, signals: Dict[SignalSource, TradingSignal], 
                    market_condition: MarketCondition = MarketCondition.NORMAL) -> TradingSignal:
        """
        融合多个信号源的信号
        
        Args:
            signals: 各信号源的信号字典
            market_condition: 当前市场状态
            
        Returns:
            融合后的交易信号
        """
        self.stats['total_fusions'] += 1
        
        if not signals:
            return TradingSignal(SignalType.HOLD, 0.0, 0.0, 0.0, reason="无信号输入")
        
        # 1. 检测信号冲突
        conflict_detected = self._detect_signal_conflicts(signals)
        if conflict_detected:
            self.stats['conflicts_detected'] += 1
            self.logger.warning("检测到信号冲突，启用冲突解决机制")
        
        # 2. 计算动态权重
        dynamic_weights = self._calculate_dynamic_weights(signals, market_condition)
        
        # 3. 执行信号融合
        fused_signal = self._perform_fusion(signals, dynamic_weights)
        
        # 4. 检查共识度
        consensus_score = self._calculate_consensus_score(signals)
        if consensus_score >= self.consensus_threshold:
            self.stats['consensus_achieved'] += 1
            fused_signal.confidence *= 1.1  # 提升共识信号的置信度
        
        # 5. 应用最终过滤
        final_signal = self._apply_final_filters(fused_signal, consensus_score)
        
        self.logger.debug(f"信号融合完成: {final_signal.signal_type.value} "
                         f"(强度:{final_signal.strength:.2f}, 置信度:{final_signal.confidence:.2f})")
        
        return final_signal
    
    def _detect_signal_conflicts(self, signals: Dict[SignalSource, TradingSignal]) -> bool:
        """检测信号冲突"""
        signal_types = [signal.signal_type for signal in signals.values()]
        
        # 检查是否有相反的信号
        has_buy = SignalType.BUY in signal_types
        has_sell = SignalType.SELL in signal_types
        
        return has_buy and has_sell
    
    def _calculate_dynamic_weights(self, signals: Dict[SignalSource, TradingSignal], 
                                 market_condition: MarketCondition) -> Dict[SignalSource, float]:
        """计算动态权重"""
        # 1. 获取市场适应权重
        market_weights = self.market_adaptive_weights.get(market_condition, self.base_weights)
        
        # 2. 基于历史性能调整权重
        performance_weights = {}
        total_performance_score = 0
        
        for source in signals.keys():
            if source in self.performance_history:
                perf = self.performance_history[source]
                # 综合考虑准确率、精确率和最近表现
                performance_score = (perf.accuracy * 0.4 + 
                                   perf.precision * 0.3 + 
                                   perf.recent_accuracy * 0.3)
                performance_weights[source] = performance_score
                total_performance_score += performance_score
        
        # 3. 基于信号置信度调整权重
        confidence_weights = {}
        for source, signal in signals.items():
            confidence_weights[source] = signal.confidence
        
        # 4. 综合计算最终权重
        final_weights = {}
        for source in signals.keys():
            market_weight = market_weights.get(source, self.base_weights.get(source, 0.33))
            
            # 性能权重归一化
            perf_weight = performance_weights.get(source, 0.5)
            if total_performance_score > 0:
                perf_weight = perf_weight / total_performance_score * len(signals)
            
            # 置信度权重
            conf_weight = confidence_weights.get(source, 0.5)
            
            # 加权平均
            final_weight = (market_weight * 0.5 + 
                          perf_weight * 0.3 + 
                          conf_weight * 0.2)
            
            final_weights[source] = final_weight
        
        # 归一化权重
        total_weight = sum(final_weights.values())
        if total_weight > 0:
            final_weights = {k: v/total_weight for k, v in final_weights.items()}
        
        self.logger.debug(f"动态权重: {final_weights}")
        return final_weights
    
    def _perform_fusion(self, signals: Dict[SignalSource, TradingSignal], 
                       weights: Dict[SignalSource, float]) -> TradingSignal:
        """执行信号融合"""
        # 信号类型投票
        signal_votes = {SignalType.BUY: 0, SignalType.SELL: 0, SignalType.HOLD: 0}
        
        # 加权投票和属性计算
        weighted_strength = 0
        weighted_confidence = 0
        weighted_entry_price = 0
        total_weight = 0
        
        for source, signal in signals.items():
            weight = weights.get(source, 0)
            
            # 投票
            signal_votes[signal.signal_type] += weight
            
            # 加权属性
            weighted_strength += signal.strength * weight
            weighted_confidence += signal.confidence * weight
            weighted_entry_price += signal.entry_price * weight
            total_weight += weight
        
        # 确定最终信号类型
        final_signal_type = max(signal_votes, key=signal_votes.get)
        
        # 归一化属性
        if total_weight > 0:
            final_strength = weighted_strength / total_weight
            final_confidence = weighted_confidence / total_weight
            final_entry_price = weighted_entry_price / total_weight
        else:
            final_strength = 0
            final_confidence = 0
            final_entry_price = 0
        
        # 生成融合原因
        reason_parts = []
        for source, signal in signals.items():
            weight = weights.get(source, 0)
            reason_parts.append(f"{source.value}({weight:.1%}):{signal.signal_type.value}")
        
        fusion_reason = f"融合信号: {', '.join(reason_parts)}"
        
        return TradingSignal(
            signal_type=final_signal_type,
            strength=final_strength,
            confidence=final_confidence,
            entry_price=final_entry_price,
            reason=fusion_reason
        )
    
    def _calculate_consensus_score(self, signals: Dict[SignalSource, TradingSignal]) -> float:
        """计算信号共识度"""
        if len(signals) <= 1:
            return 1.0
        
        signal_types = [signal.signal_type for signal in signals.values()]
        
        # 计算最多的信号类型占比
        from collections import Counter
        type_counts = Counter(signal_types)
        max_count = max(type_counts.values())
        
        consensus_score = max_count / len(signals)
        return consensus_score
    
    def _apply_final_filters(self, signal: TradingSignal, consensus_score: float) -> TradingSignal:
        """应用最终过滤器"""
        # 1. 置信度过滤
        if signal.confidence < self.min_confidence_threshold:
            return TradingSignal(
                SignalType.HOLD, 
                signal.strength, 
                signal.confidence,
                signal.entry_price,
                reason=f"置信度不足({signal.confidence:.2f} < {self.min_confidence_threshold})"
            )
        
        # 2. 共识度调整
        if consensus_score < 0.5:  # 共识度过低
            signal.confidence *= 0.8  # 降低置信度
            signal.reason += f" (低共识度:{consensus_score:.1%})"
        
        return signal
    
    def update_performance(self, source: SignalSource, was_correct: bool, 
                         confidence: float, signal_type: SignalType, actual_outcome: SignalType):
        """更新信号源性能"""
        if source not in self.performance_history:
            self.performance_history[source] = SignalPerformance(source)
        
        perf = self.performance_history[source]
        perf.total_signals += 1
        
        if was_correct:
            perf.correct_predictions += 1
        else:
            # 分析错误类型
            if signal_type != SignalType.HOLD and actual_outcome == SignalType.HOLD:
                perf.false_positives += 1
            elif signal_type == SignalType.HOLD and actual_outcome != SignalType.HOLD:
                perf.false_negatives += 1
        
        # 更新平均置信度
        perf.avg_confidence = ((perf.avg_confidence * (perf.total_signals - 1) + confidence) / 
                              perf.total_signals)
        
        # 更新最近准确率（使用指数移动平均）
        alpha = 0.1  # 学习率
        perf.recent_accuracy = (1 - alpha) * perf.recent_accuracy + alpha * (1 if was_correct else 0)
        
        self.stats['performance_adjustments'] += 1
        self.logger.debug(f"更新{source.value}性能: 准确率{perf.accuracy:.1%}, 最近准确率{perf.recent_accuracy:.1%}")
    
    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        report = {
            'statistics': self.stats.copy(),
            'signal_sources': {}
        }
        
        for source, perf in self.performance_history.items():
            report['signal_sources'][source.value] = {
                'accuracy': perf.accuracy,
                'precision': perf.precision,
                'recall': perf.recall,
                'recent_accuracy': perf.recent_accuracy,
                'total_signals': perf.total_signals,
                'avg_confidence': perf.avg_confidence
            }
        
        return report
    
    def reset_performance_history(self):
        """重置性能历史"""
        self.performance_history = {
            source: SignalPerformance(source) for source in SignalSource
        }
        self.stats = {
            'total_fusions': 0,
            'conflicts_detected': 0,
            'consensus_achieved': 0,
            'performance_adjustments': 0
        }

# 全局智能信号融合器实例
global_signal_fusion = SmartSignalFusion()
