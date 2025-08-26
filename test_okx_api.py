#!/usr/bin/env python3
"""
OKX API配置测试脚本
"""
import sys
import os

# 添加src目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from okx.api import Public
from src.utils.config import OKXConfig

def test_public_api():
    """测试公共API（不需要认证）"""
    try:
        public_api = Public()
        
        # 获取系统时间
        response = public_api.get_time()
        print(f"📅 系统时间API测试: {response}")
        
        if response.get('code') == '0':
            print("✅ 公共API连接正常")
            return True
        else:
            print(f"❌ 公共API失败: {response.get('msg')}")
            return False
            
    except Exception as e:
        print(f"❌ 公共API异常: {e}")
        return False

def test_private_api():
    """测试私有API（需要认证）"""
    try:
        config = OKXConfig()
        
        print(f"🔑 API Key: {config.api_key[:8]}...{config.api_key[-8:]}")
        print(f"🔐 Secret Key: {config.secret_key[:8]}...{config.secret_key[-8:]}")
        print(f"🔒 Passphrase: {config.passphrase}")
        
        from okx.api import Account
        
        account_api = Account(
            key=config.api_key,
            secret=config.secret_key,
            passphrase=config.passphrase,
            flag='0'  # 0: 实盘, 1: 模拟盘
        )
        
        # 测试获取账户配置（最简单的私有API）
        response = account_api.get_config()
        print(f"📊 账户配置API测试: {response}")
        
        if response.get('code') == '0':
            print("✅ 私有API认证成功")
            return True
        else:
            print(f"❌ 私有API失败: {response.get('msg')}")
            print("💡 可能的原因:")
            print("   1. API Key、Secret Key 或 Passphrase 不正确")
            print("   2. API权限设置不正确（需要'读取'权限）")
            print("   3. IP白名单限制")
            print("   4. API Key已过期或被禁用")
            return False
            
    except Exception as e:
        print(f"❌ 私有API异常: {e}")
        return False

def main():
    print("🚀 OKX API配置测试")
    print("=" * 50)
    
    # 测试公共API
    print("\n1️⃣ 测试公共API...")
    public_ok = test_public_api()
    
    # 测试私有API
    print("\n2️⃣ 测试私有API...")
    private_ok = test_private_api()
    
    print("\n" + "=" * 50)
    print("📋 测试结果:")
    print(f"   公共API: {'✅ 正常' if public_ok else '❌ 失败'}")
    print(f"   私有API: {'✅ 正常' if private_ok else '❌ 失败'}")
    
    if not public_ok:
        print("\n💡 网络连接可能有问题，请检查网络设置")
    
    if public_ok and not private_ok:
        print("\n💡 请检查以下配置:")
        print("   1. 登录OKX官网 -> API管理")
        print("   2. 确认API Key状态为'启用'")
        print("   3. 确认API权限包含'读取'权限")
        print("   4. 确认IP白名单设置正确")
        print("   5. 确认Passphrase与创建时设置的一致")
    
    if public_ok and private_ok:
        print("\n🎉 API配置正确！可以使用持仓查询工具了")

if __name__ == "__main__":
    main()
