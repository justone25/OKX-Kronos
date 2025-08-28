#!/usr/bin/env python3
"""
智谱AI预测模块
使用智谱AI GLM-4模型进行比特币价格预测
"""
import os
import logging
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from zai import ZaiClient
import zai

from ..common.signals import TradingSignal, SignalType


class PredictionDirection(Enum):
    """预测方向"""
    BULLISH = "bullish"    # 看涨
    BEARISH = "bearish"    # 看跌
    NEUTRAL = "neutral"    # 中性


@dataclass
class MarketData:
    """市场数据"""
    current_price: float
    price_24h_high: float
    price_24h_low: float
    volume_24h: float
    price_change_24h: float
    price_change_pct_24h: float
    timestamp: datetime


@dataclass
class AIPrediction:
    """AI预测结果"""
    direction: PredictionDirection
    confidence: float  # 0-1
    target_price: Optional[float]
    time_horizon: int  # 预测时间范围（分钟）
    reasoning: str
    generated_at: datetime
    model_version: str


class ZhipuAIPredictor:
    """智谱AI预测器"""
    
    def __init__(self, api_key: str = None):
        """
        初始化智谱AI预测器
        
        Args:
            api_key: 智谱AI API密钥，如果为空则从环境变量获取
        """
        self.logger = logging.getLogger(__name__)
        
        # 获取API密钥
        if api_key:
            self.api_key = api_key
        else:
            self.api_key = os.getenv('ZHIPU_API_KEY')
            
        if not self.api_key:
            raise ValueError("智谱AI API密钥未设置，请设置环境变量 ZHIPU_API_KEY 或传入api_key参数")
        
        # 初始化客户端
        try:
            self.client = ZaiClient(api_key=self.api_key)
            self.logger.info("智谱AI客户端初始化成功")
        except Exception as e:
            self.logger.error(f"智谱AI客户端初始化失败: {e}")
            raise
        
        # 预测配置
        self.model = "glm-4"
        self.temperature = 0.3  # 较低的温度以获得更一致的预测
        self.max_tokens = 1000
        
        # 预测缓存
        self.prediction_cache = {}
        self.cache_duration = 300  # 5分钟缓存
    
    def _build_market_context(self, market_data: MarketData, 
                            price_history: List[float] = None) -> str:
        """
        构建市场上下文信息
        
        Args:
            market_data: 当前市场数据
            price_history: 价格历史数据
            
        Returns:
            格式化的市场上下文字符串
        """
        context = f"""
当前比特币市场数据:
- 当前价格: ${market_data.current_price:,.2f}
- 24小时最高价: ${market_data.price_24h_high:,.2f}
- 24小时最低价: ${market_data.price_24h_low:,.2f}
- 24小时成交量: {market_data.volume_24h:,.0f}
- 24小时价格变化: ${market_data.price_change_24h:+,.2f} ({market_data.price_change_pct_24h:+.2%})
- 数据时间: {market_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        if price_history and len(price_history) > 0:
            recent_prices = price_history[-10:]  # 最近10个价格点
            price_trend = "上涨" if recent_prices[-1] > recent_prices[0] else "下跌"
            volatility = max(recent_prices) - min(recent_prices)
            
            context += f"""
最近价格趋势:
- 最近10个价格点: {[f'${p:,.0f}' for p in recent_prices]}
- 短期趋势: {price_trend}
- 短期波动幅度: ${volatility:,.2f}
"""
        
        return context
    
    def _build_prediction_prompt(self, market_data: MarketData, 
                               price_history: List[float] = None,
                               time_horizon: int = 240) -> str:
        """
        构建预测提示词
        
        Args:
            market_data: 市场数据
            price_history: 价格历史
            time_horizon: 预测时间范围（分钟）
            
        Returns:
            完整的提示词
        """
        market_context = self._build_market_context(market_data, price_history)
        
        prompt = f"""你是一个专业的加密货币分析师，专门分析比特币价格走势。请基于以下市场数据，对比特币在未来{time_horizon}分钟内的价格走势进行预测。

{market_context}

请注意以下分析要点:
1. 当前正处于白天交易时段（8:00-20:00），这个时段比特币波动通常较小
2. 重点关注短期技术指标和市场情绪
3. 考虑24小时价格变化和成交量的影响
4. 分析当前价格在24小时高低点中的位置

请严格按照以下JSON格式返回预测结果，不要添加任何其他文字:

```json
{{
    "direction": "bullish",
    "confidence": 0.75,
    "target_price": 65000.0,
    "reasoning": "详细的分析理由，包括技术面和基本面因素"
}}
```

格式要求:
- direction: 必须是 "bullish"(看涨)、"bearish"(看跌) 或 "neutral"(中性) 之一
- confidence: 置信度，0-1之间的数字，如 0.75
- target_price: 预测的目标价格数字，如果是neutral可以设为null
- reasoning: 分析理由的字符串，不超过200字

重要: 请只返回JSON格式的内容，不要包含任何解释文字或markdown标记。"""
        
        return prompt
    
    def _parse_ai_response(self, response_text: str, instrument: str = "Unknown") -> Dict:
        """
        解析AI响应

        Args:
            response_text: AI返回的文本

        Returns:
            解析后的预测数据
        """
        try:
            self.logger.info(f"[{instrument}] 原始AI响应: {response_text}")

            # 清理响应文本
            cleaned_text = response_text.strip()

            # 尝试直接解析JSON
            if cleaned_text.startswith('{') and cleaned_text.endswith('}'):
                return json.loads(cleaned_text)

            # 查找JSON代码块（可能被```包围）
            import re

            # 匹配 ```json 或 ``` 包围的JSON
            json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
            json_match = re.search(json_pattern, cleaned_text, re.DOTALL)

            if json_match:
                json_str = json_match.group(1).strip()
                self.logger.info(f"[{instrument}] 提取的JSON: {json_str}")
                return json.loads(json_str)

            # 查找第一个完整的JSON对象
            start_idx = cleaned_text.find('{')
            if start_idx != -1:
                # 找到匹配的右括号
                brace_count = 0
                end_idx = start_idx

                for i in range(start_idx, len(cleaned_text)):
                    if cleaned_text[i] == '{':
                        brace_count += 1
                    elif cleaned_text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break

                if brace_count == 0:
                    json_str = cleaned_text[start_idx:end_idx]
                    self.logger.info(f"提取的JSON对象: {json_str}")
                    return json.loads(json_str)

            # 尝试从文本中提取关键信息
            direction_match = re.search(r'"direction":\s*"(bullish|bearish|neutral)"', cleaned_text, re.IGNORECASE)
            confidence_match = re.search(r'"confidence":\s*(0?\.\d+|\d+\.?\d*)', cleaned_text)
            target_match = re.search(r'"target_price":\s*(\d+\.?\d*)', cleaned_text)
            reasoning_match = re.search(r'"reasoning":\s*"([^"]*)"', cleaned_text)

            if direction_match:
                result = {
                    "direction": direction_match.group(1).lower(),
                    "confidence": float(confidence_match.group(1)) if confidence_match else 0.5,
                    "target_price": float(target_match.group(1)) if target_match else None,
                    "reasoning": reasoning_match.group(1) if reasoning_match else "从文本中提取的预测"
                }
                self.logger.info(f"从文本提取的结果: {result}")
                return result

            # 如果无法解析JSON，返回默认结果
            self.logger.warning(f"无法解析AI响应为JSON: {response_text[:200]}...")
            return {
                "direction": "neutral",
                "confidence": 0.5,
                "target_price": None,
                "reasoning": "AI响应解析失败，返回中性预测"
            }

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析错误: {e}")
            self.logger.error(f"问题文本: {response_text[:500]}...")
            return {
                "direction": "neutral",
                "confidence": 0.5,
                "target_price": None,
                "reasoning": f"JSON解析错误: {str(e)}"
            }
        except Exception as e:
            self.logger.error(f"响应解析异常: {e}")
            return {
                "direction": "neutral",
                "confidence": 0.5,
                "target_price": None,
                "reasoning": f"响应解析异常: {str(e)}"
            }
    
    def predict(self, market_data: MarketData,
                price_history: List[float] = None,
                time_horizon: int = 240,
                instrument: str = "Unknown") -> AIPrediction:
        """
        进行价格预测

        Args:
            market_data: 当前市场数据
            price_history: 价格历史数据
            time_horizon: 预测时间范围（分钟，默认4小时）
            instrument: 交易品种标识

        Returns:
            AI预测结果
        """
        # 检查缓存
        cache_key = f"{market_data.current_price}_{time_horizon}_{int(market_data.timestamp.timestamp())}"
        if cache_key in self.prediction_cache:
            cached_prediction, cache_time = self.prediction_cache[cache_key]
            if datetime.now() - cache_time < timedelta(seconds=self.cache_duration):
                self.logger.info("使用缓存的预测结果")
                return cached_prediction
        
        try:
            # 构建提示词
            prompt = self._build_prediction_prompt(market_data, price_history, time_horizon)
            
            self.logger.info(f"[{instrument}] 正在调用智谱AI进行预测...")
            
            # 调用智谱AI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的加密货币分析师，擅长技术分析和市场预测。请基于提供的数据进行客观、理性的分析。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            # 获取响应内容
            ai_response = response.choices[0].message.content
            self.logger.info(f"[{instrument}] 智谱AI响应: {ai_response}")

            # 解析响应
            parsed_result = self._parse_ai_response(ai_response, instrument)
            
            # 创建预测结果
            prediction = AIPrediction(
                direction=PredictionDirection(parsed_result.get("direction", "neutral")),
                confidence=float(parsed_result.get("confidence", 0.5)),
                target_price=parsed_result.get("target_price"),
                time_horizon=time_horizon,
                reasoning=parsed_result.get("reasoning", ""),
                generated_at=datetime.now(),
                model_version=self.model
            )
            
            # 缓存结果
            self.prediction_cache[cache_key] = (prediction, datetime.now())
            
            self.logger.info(f"[{instrument}] 预测完成: {prediction.direction.value} (置信度: {prediction.confidence:.2f})")
            
            return prediction
            
        except Exception as api_error:
            # 处理各种API错误
            if "APIStatusError" in str(type(api_error)):
                self.logger.error(f"智谱AI API状态错误: {api_error}")
                return self._create_fallback_prediction(market_data, f"API状态错误: {str(api_error)}")
            elif "APITimeoutError" in str(type(api_error)):
                self.logger.error(f"智谱AI API超时: {api_error}")
                return self._create_fallback_prediction(market_data, f"API超时: {str(api_error)}")
            else:
                # 其他API相关错误
                self.logger.error(f"智谱AI API错误: {api_error}")
                return self._create_fallback_prediction(market_data, f"API错误: {str(api_error)}")
        
        except Exception as e:
            self.logger.error(f"预测过程中发生异常: {e}")
            return self._create_fallback_prediction(market_data, f"预测异常: {str(e)}")
    
    def _create_fallback_prediction(self, market_data: MarketData, 
                                  error_reason: str) -> AIPrediction:
        """
        创建备用预测结果（当AI调用失败时）
        
        Args:
            market_data: 市场数据
            error_reason: 错误原因
            
        Returns:
            备用预测结果
        """
        # 基于简单的技术分析创建备用预测
        price_position = (market_data.current_price - market_data.price_24h_low) / \
                        (market_data.price_24h_high - market_data.price_24h_low)
        
        if price_position < 0.3:
            direction = PredictionDirection.BULLISH
            confidence = 0.6
        elif price_position > 0.7:
            direction = PredictionDirection.BEARISH
            confidence = 0.6
        else:
            direction = PredictionDirection.NEUTRAL
            confidence = 0.5
        
        return AIPrediction(
            direction=direction,
            confidence=confidence,
            target_price=None,
            time_horizon=240,
            reasoning=f"备用预测 - {error_reason}。基于价格在24小时区间的位置({price_position:.1%})进行简单判断。",
            generated_at=datetime.now(),
            model_version="fallback"
        )
    
    def convert_to_trading_signal(self, prediction: AIPrediction, 
                                current_price: float) -> TradingSignal:
        """
        将AI预测转换为交易信号
        
        Args:
            prediction: AI预测结果
            current_price: 当前价格
            
        Returns:
            交易信号
        """
        # 转换预测方向到信号类型
        if prediction.direction == PredictionDirection.BULLISH:
            signal_type = SignalType.BUY
        elif prediction.direction == PredictionDirection.BEARISH:
            signal_type = SignalType.SELL
        else:
            signal_type = SignalType.HOLD
        
        # 计算止损止盈价格
        stop_loss = None
        take_profit = None
        
        if prediction.target_price:
            if signal_type == SignalType.BUY:
                stop_loss = current_price * 0.98  # 2%止损
                take_profit = prediction.target_price
            elif signal_type == SignalType.SELL:
                stop_loss = current_price * 1.02  # 2%止损
                take_profit = prediction.target_price
        
        return TradingSignal(
            signal_type=signal_type,
            strength=prediction.confidence,
            confidence=prediction.confidence,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=f"智谱AI预测: {prediction.reasoning[:100]}..."
        )
    
    def get_prediction_summary(self, prediction: AIPrediction) -> str:
        """
        获取预测摘要
        
        Args:
            prediction: 预测结果
            
        Returns:
            预测摘要字符串
        """
        direction_emoji = {
            PredictionDirection.BULLISH: "📈",
            PredictionDirection.BEARISH: "📉",
            PredictionDirection.NEUTRAL: "➡️"
        }
        
        emoji = direction_emoji.get(prediction.direction, "❓")
        target_str = f" → ${prediction.target_price:,.0f}" if prediction.target_price else ""
        
        return (f"{emoji} {prediction.direction.value.upper()} "
                f"(置信度: {prediction.confidence:.1%}){target_str} "
                f"[{prediction.time_horizon}分钟预测]")

    def get_trading_decision(self, analysis_data: Dict, instrument: str = "Unknown") -> Optional[Dict]:
        """
        基于技术指标和Kronos预测做最终交易决策

        Args:
            analysis_data: 包含技术分析和Kronos预测的综合数据
            instrument: 交易品种标识

        Returns:
            Dict: AI的最终交易决策
        """
        try:
            # 构建给AI的决策提示
            decision_prompt = self._build_decision_prompt(analysis_data)

            # 调用AI模型
            response = self.client.chat.completions.create(
                model="glm-4-plus",
                messages=[
                    {
                        "role": "system",
                        "content": """你是一个专业的量化交易决策AI。你需要基于技术指标分析和深度学习预测结果，做出最终的交易决策。

你的任务：
1. 综合分析技术指标信号和Kronos深度学习预测
2. 考虑当前市场环境和风险因素
3. 做出买入(buy)、卖出(sell)或持有(hold)的决策
4. 给出决策的置信度(0-1)和信号强度(0-1)
5. 提供清晰的决策理由

请以JSON格式回复，包含：
{
    "action": "buy/sell/hold",
    "confidence": 0.0-1.0,
    "strength": 0.0-1.0,
    "reasoning": "详细的决策理由"
}"""
                    },
                    {
                        "role": "user",
                        "content": decision_prompt
                    }
                ],
                temperature=0.3,
                max_tokens=500
            )

            # 解析响应
            response_text = response.choices[0].message.content.strip()
            self.logger.debug(f"AI决策响应: {response_text}")

            # 使用robust的JSON提取逻辑
            try:
                decision = self._extract_decision_from_response(response_text)

                if not decision:
                    self.logger.warning("无法从AI响应中提取有效决策")
                    return None

                # 验证决策格式
                if not all(key in decision for key in ['action', 'confidence', 'strength', 'reasoning']):
                    self.logger.warning("AI决策响应格式不完整")
                    return None

                # 验证action值
                if decision['action'] not in ['buy', 'sell', 'hold']:
                    self.logger.warning(f"无效的action值: {decision['action']}")
                    return None

                # 限制数值范围
                decision['confidence'] = max(0.0, min(1.0, float(decision['confidence'])))
                decision['strength'] = max(0.0, min(1.0, float(decision['strength'])))

                self.logger.info(f"[{instrument}] 🤖 AI最终决策: {decision['action'].upper()} "
                               f"(置信度:{decision['confidence']:.2f}, 强度:{decision['strength']:.2f})")

                return decision

            except Exception as e:
                self.logger.error(f"AI决策响应解析失败: {e}")
                self.logger.error(f"原始响应: {response_text[:500]}...")
                return None

        except Exception as e:
            self.logger.error(f"AI交易决策失败: {e}")
            return None

    def _extract_decision_from_response(self, response_text: str) -> Optional[Dict]:
        """从AI响应中提取交易决策JSON"""
        try:
            # 清理响应文本
            cleaned_text = response_text.strip()

            # 移除markdown代码块标记
            if '```json' in cleaned_text:
                json_match = re.search(r'```json\s*\n?(.*?)\n?```', cleaned_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1).strip()
                    self.logger.debug(f"提取的决策JSON: {json_str}")
                    return json.loads(json_str)

            # 查找第一个完整的JSON对象
            start_idx = cleaned_text.find('{')
            if start_idx != -1:
                # 找到匹配的右括号
                brace_count = 0
                end_idx = start_idx

                for i in range(start_idx, len(cleaned_text)):
                    if cleaned_text[i] == '{':
                        brace_count += 1
                    elif cleaned_text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break

                if brace_count == 0:
                    json_str = cleaned_text[start_idx:end_idx]
                    self.logger.debug(f"提取的决策JSON对象: {json_str}")
                    return json.loads(json_str)

            # 尝试从文本中提取关键信息
            action_match = re.search(r'"action":\s*"(buy|sell|hold)"', cleaned_text, re.IGNORECASE)
            confidence_match = re.search(r'"confidence":\s*(0?\.\d+|\d+\.?\d*)', cleaned_text)
            strength_match = re.search(r'"strength":\s*(0?\.\d+|\d+\.?\d*)', cleaned_text)
            reasoning_match = re.search(r'"reasoning":\s*"([^"]*)"', cleaned_text)

            if action_match:
                result = {
                    "action": action_match.group(1).lower(),
                    "confidence": float(confidence_match.group(1)) if confidence_match else 0.6,
                    "strength": float(strength_match.group(1)) if strength_match else 0.7,
                    "reasoning": reasoning_match.group(1) if reasoning_match else "从文本中提取的决策"
                }
                self.logger.info(f"从文本提取的决策: {result}")
                return result

            # 如果无法解析，返回None
            self.logger.warning(f"无法解析AI决策响应: {response_text[:200]}...")
            return None

        except json.JSONDecodeError as e:
            self.logger.error(f"决策JSON解析错误: {e}")
            self.logger.error(f"问题文本: {response_text[:500]}...")
            return None
        except Exception as e:
            self.logger.error(f"决策响应解析异常: {e}")
            return None

    def _build_decision_prompt(self, analysis_data: Dict) -> str:
        """构建AI决策提示"""
        current_price = analysis_data.get('current_price', 0)
        technical_analysis = analysis_data.get('technical_analysis', {})
        kronos_prediction = analysis_data.get('kronos_prediction', {})
        oscillation_range = analysis_data.get('oscillation_range', {})
        price_history_summary = analysis_data.get('price_history_summary', {})

        prompt = f"""请基于以下信息做出交易决策：

当前价格: ${current_price:,.2f}

技术指标分析:
- 信号: {technical_analysis.get('signal', '无')}
- 强度: {technical_analysis.get('strength', 0):.2f}
- 置信度: {technical_analysis.get('confidence', 0):.2f}
- 分析理由: {technical_analysis.get('reasoning', '无')}
- 震荡区间位置: {technical_analysis.get('oscillation_position', '未知')}

Kronos深度学习预测:
- 预测信号: {kronos_prediction.get('signal', '无')}
- 预测强度: {kronos_prediction.get('strength', 0):.2f}
- 预测置信度: {kronos_prediction.get('confidence', 0):.2f}
- 预测理由: {kronos_prediction.get('reasoning', '无')}

震荡区间信息:
"""

        if oscillation_range:
            # oscillation_range是OscillationRange对象，不是字典
            try:
                prompt += f"""- 区间下限: ${oscillation_range.lower_bound:,.2f}
- 区间上限: ${oscillation_range.upper_bound:,.2f}
- 区间中位数: ${oscillation_range.center_price:,.2f}
- 区间宽度: ${oscillation_range.range_size:,.2f}
"""
            except AttributeError:
                # 如果是字典格式的旧数据
                prompt += f"""- 区间下限: ${oscillation_range.get('lower', 0):,.2f}
- 区间上限: ${oscillation_range.get('upper', 0):,.2f}
- 区间中位数: ${oscillation_range.get('mid', 0):,.2f}
- 区间宽度: ${oscillation_range.get('width', 0):,.2f}
"""
        else:
            prompt += "- 暂无震荡区间数据\n"

        prompt += "\n价格历史摘要:\n"
        if price_history_summary:
            prompt += f"""- 近期趋势: {price_history_summary.get('recent_trend', '未知')}
- 波动率: {price_history_summary.get('volatility', 0):.3f}
- 1小时价格变化: {price_history_summary.get('price_change_1h', 0):.3%}
- 平均成交量: {price_history_summary.get('avg_volume', 0):,.0f}
"""
        else:
            prompt += "- 暂无价格历史摘要\n"

        prompt += """
请综合考虑以上所有信息，特别注意：
1. 技术指标和深度学习预测的一致性
2. 当前价格在震荡区间中的位置
3. 市场趋势和波动率
4. 信号的强度和置信度

做出你的最终交易决策。"""

        return prompt
