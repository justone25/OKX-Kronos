"""
下载Kronos预训练模型
"""
import os
from pathlib import Path
from huggingface_hub import snapshot_download

def download_kronos_models(models_dir: str = None):
    """下载Kronos预训练模型"""
    if models_dir is None:
        # 获取项目根目录
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent  # src/models/download_models.py -> project_root
        models_dir = project_root / "models"
    else:
        models_dir = Path(models_dir)

    models_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 模型将下载到: {models_dir}")

    print("正在下载Kronos Tokenizer...")
    try:
        tokenizer_path = snapshot_download(
            repo_id="NeoQuasar/Kronos-Tokenizer-base",
            local_dir=str(models_dir / "tokenizer"),
            local_dir_use_symlinks=False
        )
        print(f"✅ Tokenizer下载完成: {tokenizer_path}")
    except Exception as e:
        print(f"❌ Tokenizer下载失败: {e}")
        return False

    print("正在下载Kronos模型...")
    try:
        model_path = snapshot_download(
            repo_id="NeoQuasar/Kronos-small",
            local_dir=str(models_dir / "kronos-small"),
            local_dir_use_symlinks=False
        )
        print(f"✅ 模型下载完成: {model_path}")
        return True
    except Exception as e:
        print(f"❌ 模型下载失败: {e}")
        return False

if __name__ == "__main__":
    print("开始下载Kronos预训练模型...")
    if download_kronos_models():
        print("🎉 所有模型下载完成！")
    else:
        print("💥 模型下载失败，请检查网络连接")
