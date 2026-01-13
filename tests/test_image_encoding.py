#!/usr/bin/env python3
"""
測試圖片 Base64 編碼和解碼
驗證前端發送的 base64 圖片是否能正確解碼
"""
import base64
import io
from PIL import Image
from pathlib import Path

# 生成測試圖片
def create_test_image():
    """建立一個簡單的測試圖片 (100x100 藍色方塊)"""
    img = Image.new('RGB', (100, 100), color='blue')
    return img

# 測試 1: 圖片轉 base64
def test_image_to_base64():
    print("\n[TEST 1] 圖片轉 Base64")
    img = create_test_image()
    
    # 轉成 PNG 二進制
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_bytes = img_buffer.getvalue()
    
    # 轉成 base64
    b64_str = base64.b64encode(img_bytes).decode('utf-8')
    print(f"  Base64 長度: {len(b64_str)} 字元")
    print(f"  前 100 字元: {b64_str[:100]}...")
    
    # 測試帶前綴的格式
    b64_with_prefix = f"data:image/png;base64,{b64_str}"
    print(f"  帶前綴長度: {len(b64_with_prefix)} 字元")
    
    return b64_str, b64_with_prefix

# 測試 2: Base64 解碼為圖片
def test_base64_to_image(b64_str):
    print("\n[TEST 2] Base64 解碼為圖片")
    
    # 解碼
    try:
        img_bytes = base64.b64decode(b64_str)
        print(f"  ✅ Base64 解碼成功，大小: {len(img_bytes)} bytes")
        
        # 驗證圖片
        img = Image.open(io.BytesIO(img_bytes))
        img.verify()
        print(f"  ✅ 圖片驗證成功: {img.format} {img.size}")
        
        return True
    except Exception as e:
        print(f"  ❌ 解碼失敗: {e}")
        return False

# 測試 3: 帶前綴的 base64 解碼
def test_base64_with_prefix(b64_with_prefix):
    print("\n[TEST 3] 帶前綴的 Base64 解碼")
    
    # 移除前綴
    if "," in b64_with_prefix:
        b64_only = b64_with_prefix.split(",", 1)[1].strip()
        print(f"  ✅ 前綴移除成功")
        print(f"  移除後長度: {len(b64_only)} 字元")
        
        # 驗證
        try:
            img_bytes = base64.b64decode(b64_only)
            img = Image.open(io.BytesIO(img_bytes))
            img.verify()
            print(f"  ✅ 帶前綴圖片驗證成功")
            return True
        except Exception as e:
            print(f"  ❌ 帶前綴圖片驗證失敗: {e}")
            return False
    else:
        print(f"  ⚠️ 沒有找到前綴")
        return False

# 測試 4: 圖片重新編碼
def test_image_reencoding(b64_str):
    print("\n[TEST 4] 圖片重新編碼為 PNG")
    
    try:
        # 解碼原圖
        img_bytes = base64.b64decode(b64_str)
        img = Image.open(io.BytesIO(img_bytes))
        
        # 重新編碼為 PNG
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        reencoded_bytes = img_buffer.getvalue()
        
        print(f"  原始大小: {len(img_bytes)} bytes")
        print(f"  重新編碼後: {len(reencoded_bytes)} bytes")
        
        # 驗證重新編碼的圖片
        reencoded_img = Image.open(io.BytesIO(reencoded_bytes))
        reencoded_img.verify()
        print(f"  ✅ 重新編碼成功，格式: {reencoded_img.format}")
        
        return True
    except Exception as e:
        print(f"  ❌ 重新編碼失敗: {e}")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("圖片 Base64 編碼/解碼測試")
    print("=" * 60)
    
    # 執行測試
    b64_str, b64_with_prefix = test_image_to_base64()
    
    result1 = test_base64_to_image(b64_str)
    result2 = test_base64_with_prefix(b64_with_prefix)
    result3 = test_image_reencoding(b64_str)
    
    print("\n" + "=" * 60)
    if result1 and result2 and result3:
        print("[OK] 所有測試通過！")
    else:
        print("[FAIL] 某些測試失敗")
    print("=" * 60)
