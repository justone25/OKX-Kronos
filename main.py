"""
OKX-Kronos集成系统主程序
"""
import logging
import time
import sys
import os

# 添加src目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.config import OKXConfig, TradingConfig, SystemConfig
from src.data.okx_fetcher import OKXDataFetcher
from src.trading.prediction_service import PredictionService

def setup_logging():
    """配置日志"""
    # 创建日志目录
    os.makedirs('./logs', exist_ok=True)

    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler('./logs/okx_kronos.log'),
            logging.StreamHandler()
        ]
    )

def test_okx_connection():
    """测试OKX连接"""
    logger = logging.getLogger(__name__)

    try:
        # 加载配置
        okx_config = OKXConfig()
        trading_config = TradingConfig()

        # 检查API配置
        if not okx_config.api_key:
            logger.error("❌ 请在 config/.env 文件中设置 OKX_API_KEY")
            return False

        if not okx_config.secret_key:
            logger.error("❌ 请在 config/.env 文件中设置 OKX_SECRET_KEY")
            return False

        if not okx_config.passphrase:
            logger.error("❌ 请在 config/.env 文件中设置 OKX_PASSPHRASE")
            return False

        # 创建数据获取器
        fetcher = OKXDataFetcher(okx_config)

        # 测试连接
        if not fetcher.test_connection():
            return False

        # 测试获取历史数据
        logger.info("正在测试历史数据获取...")
        df = fetcher.get_historical_klines(
            instrument=trading_config.instrument,
            bar=trading_config.bar_size,
            limit=10
        )

        if not df.empty:
            logger.info(f"✅ 数据获取成功！获取到 {len(df)} 条数据")
            logger.info(f"📊 最新价格: ${df['close'].iloc[-1]:,.2f}")
            logger.info(f"📈 最高价格: ${df['high'].max():,.2f}")
            logger.info(f"📉 最低价格: ${df['low'].min():,.2f}")
            # 格式化时间显示（北京时间）
            start_time = df['timestamps'].min().strftime('%Y-%m-%d %H:%M:%S')
            end_time = df['timestamps'].max().strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"⏰ 数据时间范围: {start_time} 到 {end_time} (北京时间)")
            return True
        else:
            logger.error("❌ 未获取到数据")
            return False

    except Exception as e:
        logger.error(f"❌ 连接测试失败: {e}")
        return False

def test_model_download():
    """检查模型是否已下载"""
    logger = logging.getLogger(__name__)

    tokenizer_path = "./models/tokenizer"
    model_path = "./models/kronos-small"

    if os.path.exists(tokenizer_path) and os.path.exists(model_path):
        logger.info("✅ Kronos模型已下载完成")
        return True
    else:
        logger.warning("⚠️ Kronos模型未找到，请先运行 src/models/download_models.py")
        return False

def run_prediction_demo():
    """运行预测演示"""
    logger = logging.getLogger(__name__)

    try:
        # 加载配置
        okx_config = OKXConfig()
        trading_config = TradingConfig()

        # 创建预测服务
        logger.info("🔮 正在初始化Kronos预测服务...")
        prediction_service = PredictionService(okx_config, trading_config, device="cpu")

        # 进行预测
        logger.info("📊 开始进行BTC-USDT永续合约预测...")
        report = prediction_service.get_prediction(
            lookback_hours=12,  # 回看12小时
            pred_hours=3,       # 预测3小时
            temperature=1.0,
            top_p=0.9,
            sample_count=1
        )

        # 显示预测报告
        prediction_service.print_prediction_report(report)

        # 可视化预测结果
        logger.info("📈 生成预测图表...")
        prediction_service.visualize_prediction(report, save_path="./logs/prediction_chart.png")

        return True

    except Exception as e:
        logger.error(f"❌ 预测演示失败: {e}")
        return False

def main():
    """主函数"""
    # 创建必要目录
    os.makedirs('src/data', exist_ok=True)
    os.makedirs('./logs', exist_ok=True)

    # 配置日志
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("🚀 OKX-Kronos集成系统启动")
    logger.info("=" * 60)

    # 检查模型下载状态
    model_ok = test_model_download()

    # 测试OKX连接
    okx_ok = test_okx_connection()

    # 总结测试结果
    logger.info("=" * 60)
    logger.info("📋 系统检查结果:")
    logger.info(f"   模型状态: {'✅ 正常' if model_ok else '❌ 需要下载'}")
    logger.info(f"   OKX连接: {'✅ 正常' if okx_ok else '❌ 连接失败'}")

    if model_ok and okx_ok:
        logger.info("🎉 系统初始化成功！开始运行Kronos预测演示")

        # 运行预测演示
        prediction_ok = run_prediction_demo()

        if prediction_ok:
            logger.info("✅ 预测演示完成！")
            logger.info("💡 您可以查看生成的预测图表: ./logs/prediction_chart.png")
        else:
            logger.error("❌ 预测演示失败")

        logger.info("按 Ctrl+C 退出程序")

        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            logger.info("👋 系统正在关闭...")
    else:
        logger.error("💥 系统初始化失败，请检查配置和网络")
        if not model_ok:
            logger.info("💡 请先运行: python src/models/download_models.py")
        if not okx_ok:
            logger.info("💡 请检查OKX API配置是否正确")

if __name__ == "__main__":
    main()
