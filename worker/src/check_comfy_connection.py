"""
ComfyUI 連接檢查工具
====================
驗證 ComfyUI 是否正確啟動並接受 API 請求。
"""

import os
import sys
import requests
from pathlib import Path

# 從 config 統一讀取 ComfyUI 配置（避免重複定義）
try:
    from config import COMFY_HOST, COMFY_PORT
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    try:
        from config import COMFY_HOST, COMFY_PORT
    except ImportError:
        COMFY_HOST = os.getenv("COMFYUI_HOST", os.getenv("COMFY_HOST", "127.0.0.1"))
        COMFY_PORT = int(os.getenv("COMFYUI_PORT", os.getenv("COMFY_PORT", "8188")))

COMFY_URL = f"http://{COMFY_HOST}:{COMFY_PORT}"


def check_comfyui():
    """
    檢查 ComfyUI 連接狀態
    """
    print("="*50)
    print("🔍 ComfyUI 連接檢查")
    print("="*50)
    
    # 1. 檢查系統狀態
    print(f"\n[1] 測試連接: {COMFY_URL}/system_stats")
    
    try:
        response = requests.get(f"{COMFY_URL}/system_stats", timeout=5)
        
        if response.status_code == 200:
            print("    ✅ 連接成功！")
            
            # 顯示系統資訊
            stats = response.json()
            system = stats.get("system", {})
            
            print(f"\n[系統資訊]")
            print(f"    Python: {system.get('python_version', 'N/A')}")
            print(f"    OS: {system.get('os', 'N/A')}")
            
            # 顯示 GPU 資訊
            devices = stats.get("devices", [])
            if devices:
                print(f"\n[GPU 資訊]")
                for i, device in enumerate(devices):
                    name = device.get("name", "Unknown")
                    vram_total = device.get("vram_total", 0) / (1024**3)
                    vram_free = device.get("vram_free", 0) / (1024**3)
                    print(f"    GPU {i}: {name}")
                    print(f"           VRAM: {vram_free:.1f} GB / {vram_total:.1f} GB")
            
            return True
        else:
            print(f"    ❌ 回應錯誤: HTTP {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("    ❌ 無法連接！")
        print("\n[可能原因]")
        print("    1. ComfyUI 尚未啟動")
        print("    2. ComfyUI 未使用 --listen 參數啟動")
        print("    3. 防火牆阻擋了 8188 端口")
        print("\n[解決方法]")
        print("    請使用以下指令啟動 ComfyUI:")
        print("    python main.py --listen --enable-cors-header *")
        return False
        
    except requests.exceptions.Timeout:
        print("    ❌ 連接超時")
        return False
        
    except Exception as e:
        print(f"    ❌ 錯誤: {e}")
        return False


def check_models():
    """
    列出可用的模型
    """
    print("\n[2] 檢查可用模型")
    
    try:
        # 取得 object_info
        response = requests.get(f"{COMFY_URL}/object_info", timeout=10)
        
        if response.status_code == 200:
            info = response.json()
            
            # 嘗試找 CheckpointLoaderSimple 來列出 checkpoint
            ckpt_loader = info.get("CheckpointLoaderSimple", {})
            ckpt_input = ckpt_loader.get("input", {}).get("required", {})
            ckpt_names = ckpt_input.get("ckpt_name", [[]])[0]
            
            if ckpt_names:
                print(f"\n    [Checkpoints] 找到 {len(ckpt_names)} 個模型:")
                for name in ckpt_names[:10]:  # 只顯示前 10 個
                    print(f"        - {name}")
                if len(ckpt_names) > 10:
                    print(f"        ... 還有 {len(ckpt_names) - 10} 個")
            
            # 嘗試找 UNETLoader
            unet_loader = info.get("UNETLoader", {})
            unet_input = unet_loader.get("input", {}).get("required", {})
            unet_names = unet_input.get("unet_name", [[]])[0]
            
            if unet_names:
                print(f"\n    [UNET Models] 找到 {len(unet_names)} 個模型:")
                for name in unet_names[:10]:
                    print(f"        - {name}")
                if len(unet_names) > 10:
                    print(f"        ... 還有 {len(unet_names) - 10} 個")
                    
            return True
        else:
            print(f"    ⚠️ 無法取得模型列表")
            return True
            
    except Exception as e:
        print(f"    ⚠️ 取得模型列表失敗: {e}")
        return True


def main():
    """
    主函數
    """
    success = check_comfyui()
    
    if success:
        check_models()
        print("\n" + "="*50)
        print("✅ ComfyUI 已就緒，可以開始使用！")
        print("="*50)
        sys.exit(0)
    else:
        print("\n" + "="*50)
        print("❌ 請先啟動 ComfyUI")
        print("="*50)
        sys.exit(1)


if __name__ == "__main__":
    main()
