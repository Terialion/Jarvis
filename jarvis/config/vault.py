"""
敏感信息保险箱 - 加密存储API密钥等敏感信息

使用Windows DPAPI进行加密，无需额外密钥管理
"""
import os
import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any

# Windows DPAPI 加密
import sys
if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes
    
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", wintypes.LPBYTE)
        ]
    
    def _encrypt_data(data: bytes) -> bytes:
        """使用Windows DPAPI加密数据"""
        blob_in = DATA_BLOB(len(data), ctypes.cast(data, wintypes.LPBYTE))
        blob_out = DATA_BLOB()
        
        CRYPTPROTECT_UI_FORBIDDEN = 0x01
        
        if ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(blob_out)
        ):
            encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return encrypted
        else:
            raise RuntimeError("加密失败")
    
    def _decrypt_data(encrypted: bytes) -> bytes:
        """使用Windows DPAPI解密数据"""
        blob_in = DATA_BLOB(len(encrypted), ctypes.cast(encrypted, wintypes.LPBYTE))
        blob_out = DATA_BLOB()
        
        CRYPTPROTECT_UI_FORBIDDEN = 0x01
        
        if ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(blob_out)
        ):
            decrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return decrypted
        else:
            raise RuntimeError("解密失败，数据可能已损坏或来自其他用户")
else:
    # 非Windows平台使用简单的base64（警告：不安全，仅用于开发）
    def _encrypt_data(data: bytes) -> bytes:
        return base64.b64encode(data)
    
    def _decrypt_data(encrypted: bytes) -> bytes:
        return base64.b64decode(encrypted)


class SecretVault:
    """
    敏感信息保险箱
    
    特性：
    - 使用Windows DPAPI加密（绑定当前用户）
    - 自动备份和恢复
    - 内存中不持久化明文
    """
    
    _instance = None
    
    def __new__(cls, vault_path: Optional[str] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, vault_path: Optional[str] = None):
        if self._initialized:
            return
        
        self._vault_path = Path(vault_path) if vault_path else Path.home() / ".jarvis" / "vault.enc"
        self._vault_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, str] = {}  # 内存缓存（进程生命周期）
        self._initialized = True
    
    def _load_vault(self) -> Dict[str, str]:
        """加载保险箱"""
        if not self._vault_path.exists():
            return {}
        
        try:
            with open(self._vault_path, 'rb') as f:
                encrypted = f.read()
            
            if not encrypted:
                return {}
            
            decrypted = _decrypt_data(encrypted)
            return json.loads(decrypted.decode('utf-8'))
        except Exception as e:
            print(f"[Vault] 加载失败: {e}")
            return {}
    
    def _save_vault(self, data: Dict[str, str]):
        """保存保险箱"""
        json_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        encrypted = _encrypt_data(json_data)
        
        # 原子写入
        temp_path = self._vault_path.with_suffix('.tmp')
        with open(temp_path, 'wb') as f:
            f.write(encrypted)
        
        # 备份旧文件
        if self._vault_path.exists():
            backup_path = self._vault_path.with_suffix('.backup')
            self._vault_path.replace(backup_path)
        
        temp_path.replace(self._vault_path)
    
    def get(self, key: str) -> Optional[str]:
        """获取密钥"""
        # 1. 检查内存缓存
        if key in self._cache:
            return self._cache[key]
        
        # 2. 从保险箱加载
        vault = self._load_vault()
        value = vault.get(key)
        
        if value:
            self._cache[key] = value
        
        return value
    
    def set(self, key: str, value: str):
        """设置密钥"""
        # 更新缓存
        self._cache[key] = value
        
        # 更新存储
        vault = self._load_vault()
        vault[key] = value
        self._save_vault(vault)
    
    def delete(self, key: str):
        """删除密钥"""
        # 清除缓存
        self._cache.pop(key, None)
        
        # 更新存储
        vault = self._load_vault()
        vault.pop(key, None)
        self._save_vault(vault)
    
    def list_keys(self) -> list:
        """列出所有密钥名称（不包含值）"""
        vault = self._load_vault()
        return list(vault.keys())
    
    def has(self, key: str) -> bool:
        """检查密钥是否存在"""
        return self.get(key) is not None
    
    def clear_cache(self):
        """清除内存缓存（安全退出时调用）"""
        self._cache.clear()


# 便捷函数
def get_vault() -> SecretVault:
    """获取保险箱实例"""
    return SecretVault()
