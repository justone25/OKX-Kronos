"""
Kronos模型集成模块
基于shiyu-coder/Kronos项目的预测功能
"""
import os
import sys
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Tuple
from pathlib import Path

# 添加模型路径到系统路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

# 导入Kronos相关模块
try:
    from huggingface_hub import PyTorchModelHubMixin
    from tqdm import trange
    import math
    from einops import rearrange, reduce
    from torch.autograd import Function
except ImportError:
    print("请安装依赖: pip install huggingface_hub tqdm einops")
    raise


# 导入Kronos模块
from .kronos_modules import (
    TransformerBlock, HierarchicalEmbedding, DependencyAwareLayer,
    DualHead, TemporalEmbedding, RMSNorm
)
from .quantizer import BSQuantizer


class KronosTokenizer(nn.Module, PyTorchModelHubMixin):
    """Kronos Tokenizer模块"""

    def __init__(self, d_in, d_model, n_heads, ff_dim, n_enc_layers, n_dec_layers,
                 ffn_dropout_p, attn_dropout_p, resid_dropout_p, s1_bits, s2_bits,
                 beta, gamma0, gamma, zeta, group_size):
        super().__init__()
        self.d_in = d_in
        self.d_model = d_model
        self.n_heads = n_heads
        self.ff_dim = ff_dim
        self.enc_layers = n_enc_layers
        self.dec_layers = n_dec_layers
        self.ffn_dropout_p = ffn_dropout_p
        self.attn_dropout_p = attn_dropout_p
        self.resid_dropout_p = resid_dropout_p

        self.s1_bits = s1_bits
        self.s2_bits = s2_bits
        self.codebook_dim = s1_bits + s2_bits
        self.embed = nn.Linear(self.d_in, self.d_model)
        self.head = nn.Linear(self.d_model, self.d_in)

        # Encoder和Decoder Transformer Blocks
        self.encoder = nn.ModuleList([
            TransformerBlock(self.d_model, self.n_heads, self.ff_dim, self.ffn_dropout_p, self.attn_dropout_p, self.resid_dropout_p)
            for _ in range(self.enc_layers - 1)
        ])
        self.decoder = nn.ModuleList([
            TransformerBlock(self.d_model, self.n_heads, self.ff_dim, self.ffn_dropout_p, self.attn_dropout_p, self.resid_dropout_p)
            for _ in range(self.dec_layers - 1)
        ])
        self.quant_embed = nn.Linear(in_features=self.d_model, out_features=self.codebook_dim)
        self.post_quant_embed_pre = nn.Linear(in_features=self.s1_bits, out_features=self.d_model)
        self.post_quant_embed = nn.Linear(in_features=self.codebook_dim, out_features=self.d_model)
        self.tokenizer = BSQuantizer(self.s1_bits, self.s2_bits, beta, gamma0, gamma, zeta, group_size)

    def forward(self, x):
        z = self.embed(x)

        for layer in self.encoder:
            z = layer(z)

        z = self.quant_embed(z)
        bsq_loss, quantized, z_indices = self.tokenizer(z)

        quantized_pre = quantized[:, :, :self.s1_bits]
        z_pre = self.post_quant_embed_pre(quantized_pre)
        z = self.post_quant_embed(quantized)

        for layer in self.decoder:
            z_pre = layer(z_pre)
        z_pre = self.head(z_pre)

        for layer in self.decoder:
            z = layer(z)
        z = self.head(z)

        return (z_pre, z), bsq_loss, quantized, z_indices

    def indices_to_bits(self, x, half=False):
        if half:
            x1, x2 = x[0], x[1]
            mask = 2 ** torch.arange(self.codebook_dim//2, device=x1.device, dtype=torch.long)
            x1 = (x1.unsqueeze(-1) & mask) != 0
            x2 = (x2.unsqueeze(-1) & mask) != 0
            x = torch.cat([x1, x2], dim=-1)
        else:
            mask = 2 ** torch.arange(self.codebook_dim, device=x.device, dtype=torch.long)
            x = (x.unsqueeze(-1) & mask) != 0

        x = x.float() * 2 - 1
        q_scale = 1. / (self.codebook_dim ** 0.5)
        x = x * q_scale
        return x

    def encode(self, x, half=False):
        z = self.embed(x)
        for layer in self.encoder:
            z = layer(z)
        z = self.quant_embed(z)
        bsq_loss, quantized, z_indices = self.tokenizer(z, half)
        return z_indices

    def decode(self, x, half=False):
        quantized = self.indices_to_bits(x, half)
        z = self.post_quant_embed(quantized)
        for layer in self.decoder:
            z = layer(z)
        z = self.head(z)
        return z


class Kronos(nn.Module, PyTorchModelHubMixin):
    """Kronos主模型"""

    def __init__(self, s1_bits, s2_bits, n_layers, d_model, n_heads, ff_dim,
                 ffn_dropout_p, attn_dropout_p, resid_dropout_p, token_dropout_p, learn_te):
        super().__init__()
        self.s1_bits = s1_bits
        self.s2_bits = s2_bits
        self.n_layers = n_layers
        self.d_model = d_model
        self.n_heads = n_heads
        self.learn_te = learn_te
        self.ff_dim = ff_dim
        self.ffn_dropout_p = ffn_dropout_p
        self.attn_dropout_p = attn_dropout_p
        self.resid_dropout_p = resid_dropout_p
        self.token_dropout_p = token_dropout_p

        self.s1_vocab_size = 2 ** self.s1_bits
        self.token_drop = nn.Dropout(self.token_dropout_p)
        self.embedding = HierarchicalEmbedding(self.s1_bits, self.s2_bits, self.d_model)
        self.time_emb = TemporalEmbedding(self.d_model, self.learn_te)
        self.transformer = nn.ModuleList([
            TransformerBlock(self.d_model, self.n_heads, self.ff_dim, self.ffn_dropout_p, self.attn_dropout_p, self.resid_dropout_p)
            for _ in range(self.n_layers)
        ])
        self.norm = RMSNorm(self.d_model)
        self.dep_layer = DependencyAwareLayer(self.d_model)
        self.head = DualHead(self.s1_bits, self.s2_bits, self.d_model)
        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            nn.init.xavier_normal_(module.weight)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0, std=self.embedding.d_model ** -0.5)
        elif isinstance(module, nn.LayerNorm):
            nn.init.ones_(module.weight)
            nn.init.zeros_(module.bias)
        elif isinstance(module, RMSNorm):
            nn.init.ones_(module.weight)

    def decode_s1(self, s1_ids, s2_ids, stamp=None, padding_mask=None):
        x = self.embedding([s1_ids, s2_ids])
        if stamp is not None:
            time_embedding = self.time_emb(stamp)
            x = x + time_embedding
        x = self.token_drop(x)

        for layer in self.transformer:
            x = layer(x, key_padding_mask=padding_mask)

        x = self.norm(x)
        s1_logits = self.head(x)
        return s1_logits, x

    def decode_s2(self, context, s1_ids, padding_mask=None):
        sibling_embed = self.embedding.emb_s1(s1_ids)
        x2 = self.dep_layer(context, sibling_embed, key_padding_mask=padding_mask)
        return self.head.cond_forward(x2)


class KronosPredictor:
    """Kronos预测器，用于BTC-USDT永续合约价格预测"""

    def __init__(self, model_path: str = None, tokenizer_path: str = None, device: str = "auto", auto_download: bool = True):
        """
        初始化Kronos预测器

        Args:
            model_path: 模型路径，默认使用项目中的kronos-small
            tokenizer_path: tokenizer路径，默认使用项目中的tokenizer
            device: 计算设备，auto/cpu/cuda/mps
            auto_download: 是否自动下载缺失的模型
        """
        self.logger = logging.getLogger(__name__)
        self.device = self._get_optimal_device(device)

        # 设置默认路径
        if model_path is None:
            model_path = project_root / "models" / "kronos-small"
        if tokenizer_path is None:
            tokenizer_path = project_root / "models" / "tokenizer"

        self.model_path = Path(model_path)
        self.tokenizer_path = Path(tokenizer_path)

        # 检查模型文件是否存在，如果不存在且允许自动下载，则下载
        if not self._check_models_exist():
            if auto_download:
                self.logger.info("📥 模型文件不存在，开始自动下载...")
                if not self._download_models():
                    raise FileNotFoundError(f"模型下载失败，请检查网络连接")
            else:
                raise FileNotFoundError(f"模型路径不存在: {self.model_path}, Tokenizer路径不存在: {self.tokenizer_path}")

        self.logger.info(f"使用模型路径: {self.model_path}")
        self.logger.info(f"使用tokenizer路径: {self.tokenizer_path}")

        # 初始化模型和tokenizer
        self._load_models()

        # 预测相关参数
        self.max_context = 512
        self.clip = 5
        self.price_cols = ['open', 'high', 'low', 'close']
        self.vol_col = 'volume'
        self.amt_col = 'amount'
        self.time_cols = ['minute', 'hour', 'weekday', 'day', 'month']

        self.logger.info(f"🖥️ 使用计算设备: {self.device}")

    def _check_models_exist(self) -> bool:
        """检查模型文件是否存在"""
        model_exists = (self.model_path.exists() and
                       (self.model_path / "config.json").exists() and
                       (self.model_path / "model.safetensors").exists())

        tokenizer_exists = (self.tokenizer_path.exists() and
                           (self.tokenizer_path / "config.json").exists() and
                           (self.tokenizer_path / "model.safetensors").exists())

        return model_exists and tokenizer_exists

    def _download_models(self) -> bool:
        """下载模型文件"""
        try:
            # 导入下载函数
            from .download_models import download_kronos_models

            # 执行下载，传入models目录路径
            models_dir = self.model_path.parent
            success = download_kronos_models(str(models_dir))

            if success:
                self.logger.info("✅ 模型下载完成")
                return True
            else:
                self.logger.error("❌ 模型下载失败")
                return False

        except Exception as e:
            self.logger.error(f"❌ 模型下载异常: {e}")
            return False

    def _get_optimal_device(self, device: str) -> str:
        """获取最优计算设备"""
        if device == "auto":
            # 自动选择最优设备
            if torch.backends.mps.is_available():
                return "mps"  # M1/M2 Mac GPU
            elif torch.cuda.is_available():
                return "cuda"  # NVIDIA GPU
            else:
                return "cpu"
        elif device == "mps":
            if torch.backends.mps.is_available():
                return "mps"
            else:
                self.logger.warning("⚠️ MPS不可用，回退到CPU")
                return "cpu"
        elif device == "cuda":
            if torch.cuda.is_available():
                return "cuda"
            else:
                self.logger.warning("⚠️ CUDA不可用，回退到CPU")
                return "cpu"
        else:
            return "cpu"

    def _load_models(self):
        """加载模型和tokenizer"""
        try:
            self.logger.info("正在加载Kronos模型...")

            # 加载tokenizer配置和权重
            tokenizer_config_path = self.tokenizer_path / "config.json"
            with open(tokenizer_config_path, 'r') as f:
                tokenizer_config = json.load(f)

            # 创建tokenizer
            self.tokenizer = KronosTokenizer(
                d_in=tokenizer_config['d_in'],
                d_model=tokenizer_config['d_model'],
                n_heads=tokenizer_config['n_heads'],
                ff_dim=tokenizer_config['ff_dim'],
                n_enc_layers=tokenizer_config['n_enc_layers'],
                n_dec_layers=tokenizer_config['n_dec_layers'],
                ffn_dropout_p=tokenizer_config['ffn_dropout_p'],
                attn_dropout_p=tokenizer_config['attn_dropout_p'],
                resid_dropout_p=tokenizer_config['resid_dropout_p'],
                s1_bits=tokenizer_config['s1_bits'],
                s2_bits=tokenizer_config['s2_bits'],
                beta=tokenizer_config['beta'],
                gamma0=tokenizer_config['gamma0'],
                gamma=tokenizer_config['gamma'],
                zeta=tokenizer_config['zeta'],
                group_size=tokenizer_config['group_size']
            )

            # 加载tokenizer权重
            tokenizer_weights_path = self.tokenizer_path / "model.safetensors"
            if tokenizer_weights_path.exists():
                from safetensors.torch import load_file
                tokenizer_state_dict = load_file(tokenizer_weights_path)
                self.tokenizer.load_state_dict(tokenizer_state_dict)

            # 加载模型配置和权重
            model_config_path = self.model_path / "config.json"
            with open(model_config_path, 'r') as f:
                model_config = json.load(f)

            # 创建模型
            self.model = Kronos(
                s1_bits=model_config['s1_bits'],
                s2_bits=model_config['s2_bits'],
                n_layers=model_config['n_layers'],
                d_model=model_config['d_model'],
                n_heads=model_config['n_heads'],
                ff_dim=model_config['ff_dim'],
                ffn_dropout_p=model_config['ffn_dropout_p'],
                attn_dropout_p=model_config['attn_dropout_p'],
                resid_dropout_p=model_config['resid_dropout_p'],
                token_dropout_p=model_config['token_dropout_p'],
                learn_te=model_config['learn_te']
            )

            # 加载模型权重
            model_weights_path = self.model_path / "model.safetensors"
            if model_weights_path.exists():
                from safetensors.torch import load_file
                model_state_dict = load_file(model_weights_path)
                self.model.load_state_dict(model_state_dict)

            # 移动到指定设备
            self.tokenizer = self.tokenizer.to(self.device)
            self.model = self.model.to(self.device)

            # 设置为评估模式
            self.tokenizer.eval()
            self.model.eval()

            self.logger.info("✅ Kronos模型加载成功")

        except Exception as e:
            self.logger.error(f"❌ 模型加载失败: {e}")
            raise
    
    def _calc_time_stamps(self, timestamp_series: pd.Series) -> pd.DataFrame:
        """计算时间戳特征"""
        time_df = pd.DataFrame()
        time_df['minute'] = timestamp_series.dt.minute
        time_df['hour'] = timestamp_series.dt.hour
        time_df['weekday'] = timestamp_series.dt.weekday
        time_df['day'] = timestamp_series.dt.day
        time_df['month'] = timestamp_series.dt.month
        return time_df
    
    def _prepare_data(self, df: pd.DataFrame, timestamp_series: pd.Series) -> Tuple[np.ndarray, np.ndarray]:
        """准备输入数据"""
        # 检查必要的列
        if not all(col in df.columns for col in self.price_cols):
            raise ValueError(f"数据缺少必要的价格列: {self.price_cols}")
        
        # 处理缺失的volume和amount列
        df = df.copy()
        if self.vol_col not in df.columns:
            df[self.vol_col] = 0.0
        if self.amt_col not in df.columns:
            df[self.amt_col] = df[self.vol_col] * df[self.price_cols].mean(axis=1)
        
        # 检查NaN值
        if df[self.price_cols + [self.vol_col, self.amt_col]].isnull().values.any():
            raise ValueError("输入数据包含NaN值")
        
        # 准备价格和成交量数据
        x = df[self.price_cols + [self.vol_col, self.amt_col]].values.astype(np.float32)
        
        # 准备时间特征
        time_df = self._calc_time_stamps(timestamp_series)
        x_stamp = time_df.values.astype(np.float32)
        
        return x, x_stamp
    
    def predict(self, df: pd.DataFrame, x_timestamp: pd.Series, y_timestamp: pd.Series,
                pred_len: int = 24, temperature: float = 1.0, top_p: float = 0.9,
                sample_count: int = 1, verbose: bool = True, seed: Optional[int] = None,
                deterministic: bool = False) -> pd.DataFrame:
        """
        进行价格预测

        Args:
            df: 历史K线数据，包含['open', 'high', 'low', 'close']列
            x_timestamp: 历史数据对应的时间戳
            y_timestamp: 预测时间戳
            pred_len: 预测长度
            temperature: 采样温度（越低越确定性，越高越随机）
            top_p: nucleus采样参数（0.9表示只考虑累积概率90%的token）
            sample_count: 采样次数（多次采样取平均）
            verbose: 是否显示详细信息
            seed: 随机种子（设置后结果可重现）
            deterministic: 是否使用确定性模式（减少随机性）

        Returns:
            预测结果DataFrame
        """
        try:
            # 设置随机种子（如果指定）
            if seed is not None:
                torch.manual_seed(seed)
                np.random.seed(seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed(seed)
                if torch.backends.mps.is_available():
                    torch.mps.manual_seed(seed)
                self.logger.info(f"🎲 设置随机种子: {seed}")

            # 确定性模式设置
            if deterministic:
                temperature = 0.1  # 降低温度增加确定性
                top_p = 0.5       # 减少采样范围
                self.logger.info("🔒 使用确定性模式（低温度采样）")

            self.logger.info(f"开始进行Kronos预测，预测长度: {pred_len}")
            self.logger.info(f"🌡️ 采样参数 - 温度: {temperature}, Top-p: {top_p}, 采样次数: {sample_count}")

            # 检查必要的列
            if not all(col in df.columns for col in self.price_cols):
                raise ValueError(f"数据缺少必要的价格列: {self.price_cols}")

            # 处理缺失的volume和amount列
            df = df.copy()
            if self.vol_col not in df.columns:
                df[self.vol_col] = 0.0
            if self.amt_col not in df.columns:
                df[self.amt_col] = df[self.vol_col] * df[self.price_cols].mean(axis=1)

            # 检查NaN值
            if df[self.price_cols + [self.vol_col, self.amt_col]].isnull().values.any():
                raise ValueError("输入数据包含NaN值")

            # 准备时间特征
            x_time_df = self._calc_time_stamps(x_timestamp)
            y_time_df = self._calc_time_stamps(y_timestamp)

            # 准备数据
            x = df[self.price_cols + [self.vol_col, self.amt_col]].values.astype(np.float32)
            x_stamp = x_time_df.values.astype(np.float32)
            y_stamp = y_time_df.values.astype(np.float32)

            # 数据标准化
            x_mean, x_std = np.mean(x, axis=0), np.std(x, axis=0)
            x_normalized = (x - x_mean) / (x_std + 1e-5)
            x_normalized = np.clip(x_normalized, -self.clip, self.clip)

            # 转换为tensor并添加batch维度
            x_tensor = torch.from_numpy(x_normalized[np.newaxis, :]).to(self.device)
            x_stamp_tensor = torch.from_numpy(x_stamp[np.newaxis, :]).to(self.device)
            y_stamp_tensor = torch.from_numpy(y_stamp[np.newaxis, :]).to(self.device)

            # 使用真正的Kronos模型进行预测
            preds = self._auto_regressive_inference(
                x_tensor, x_stamp_tensor, y_stamp_tensor,
                pred_len, temperature, 0, top_p, sample_count, verbose
            )

            # 移除batch维度并转换为numpy
            preds = preds.squeeze(0)

            # 反标准化
            preds = preds * (x_std + 1e-5) + x_mean

            # 创建预测结果DataFrame
            pred_df = pd.DataFrame(
                preds,
                columns=self.price_cols + [self.vol_col, self.amt_col],
                index=y_timestamp
            )

            self.logger.info("✅ Kronos预测完成")
            return pred_df

        except Exception as e:
            self.logger.error(f"❌ 预测失败: {e}")
            raise
    
    def _top_k_top_p_filtering(self, logits, top_k: int = 0, top_p: float = 1.0,
                              filter_value: float = -float("Inf"), min_tokens_to_keep: int = 1):
        """Top-k和nucleus (top-p)过滤"""
        if top_k > 0:
            top_k = min(max(top_k, min_tokens_to_keep), logits.size(-1))
            indices_to_remove = logits < torch.topk(logits, top_k)[0][..., -1, None]
            logits[indices_to_remove] = filter_value
            return logits

        if top_p < 1.0:
            sorted_logits, sorted_indices = torch.sort(logits, descending=True)
            cumulative_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)

            sorted_indices_to_remove = cumulative_probs > top_p
            if min_tokens_to_keep > 1:
                sorted_indices_to_remove[..., :min_tokens_to_keep] = 0
            sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
            sorted_indices_to_remove[..., 0] = 0

            indices_to_remove = sorted_indices_to_remove.scatter(1, sorted_indices, sorted_indices_to_remove)
            logits[indices_to_remove] = filter_value
            return logits

    def _sample_from_logits(self, logits, temperature=1.0, top_k=None, top_p=None, sample_logits=True):
        """从logits中采样"""
        logits = logits / temperature
        if top_k is not None or top_p is not None:
            if top_k > 0 or top_p < 1.0:
                logits = self._top_k_top_p_filtering(logits, top_k=top_k, top_p=top_p)

        probs = F.softmax(logits, dim=-1)

        if not sample_logits:
            _, x = torch.topk(probs, k=1, dim=-1)
        else:
            x = torch.multinomial(probs, num_samples=1)

        return x

    def _auto_regressive_inference(self, x, x_stamp, y_stamp, pred_len, temperature=1.0,
                                  top_k=0, top_p=0.99, sample_count=1, verbose=False):
        """自回归推理"""
        with torch.no_grad():
            batch_size = x.size(0)
            initial_seq_len = x.size(1)
            x = torch.clip(x, -self.clip, self.clip)

            device = x.device
            x = x.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, x.size(1), x.size(2)).to(device)
            x_stamp = x_stamp.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, x_stamp.size(1), x_stamp.size(2)).to(device)
            y_stamp = y_stamp.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, y_stamp.size(1), y_stamp.size(2)).to(device)

            # 编码输入数据
            x_token = self.tokenizer.encode(x, half=True)

            def get_dynamic_stamp(x_stamp, y_stamp, current_seq_len, pred_step):
                if current_seq_len <= self.max_context - pred_step:
                    return torch.cat([x_stamp, y_stamp[:, :pred_step, :]], dim=1)
                else:
                    start_idx = self.max_context - pred_step
                    return torch.cat([x_stamp[:, -start_idx:, :], y_stamp[:, :pred_step, :]], dim=1)

            if verbose:
                try:
                    from tqdm import trange
                    ran = trange
                except ImportError:
                    ran = range
            else:
                ran = range

            for i in ran(pred_len):
                current_seq_len = initial_seq_len + i

                if current_seq_len <= self.max_context:
                    input_tokens = x_token
                else:
                    input_tokens = [t[:, -self.max_context:].contiguous() for t in x_token]

                current_stamp = get_dynamic_stamp(x_stamp, y_stamp, current_seq_len, i)

                # 解码s1
                s1_logits, context = self.model.decode_s1(input_tokens[0], input_tokens[1], current_stamp)
                s1_logits = s1_logits[:, -1, :]
                sample_pre = self._sample_from_logits(s1_logits, temperature=temperature, top_k=top_k, top_p=top_p, sample_logits=True)

                # 解码s2
                s2_logits = self.model.decode_s2(context, sample_pre)
                s2_logits = s2_logits[:, -1, :]
                sample_post = self._sample_from_logits(s2_logits, temperature=temperature, top_k=top_k, top_p=top_p, sample_logits=True)

                # 更新token序列
                x_token[0] = torch.cat([x_token[0], sample_pre], dim=1)
                x_token[1] = torch.cat([x_token[1], sample_post], dim=1)

            # 解码最终结果
            input_tokens = [t[:, -self.max_context:].contiguous() for t in x_token]
            z = self.tokenizer.decode(input_tokens, half=True)
            z = z.reshape(batch_size, sample_count, z.size(1), z.size(2))
            preds = z.cpu().numpy()
            preds = np.mean(preds, axis=1)

            return preds[:, -pred_len:, :]


def create_kronos_predictor(device: str = "cpu") -> KronosPredictor:
    """创建Kronos预测器实例"""
    return KronosPredictor(device=device)
