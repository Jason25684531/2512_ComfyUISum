import json
import os
import glob

# 取得目前腳本路徑並推算根目錄
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_SRC = os.path.join(BASE_DIR, "ComfyUIworkflow")
# 注意：worker 的路徑解析邏輯（worker/src/workflow_registry.py、worker/src/workflow/loader.py）
# 不會讀取這個資料夾，此輸出僅供人工比對用，非執行期必要產物
WORKFLOW_OUT = os.path.join(WORKFLOW_SRC, "linux_fixed")

# 確保輸出資料夾存在
if not os.path.exists(WORKFLOW_OUT):
    os.makedirs(WORKFLOW_OUT)

def fix_content(data):
    if isinstance(data, dict):
        # 🌟 核心升級：把 GGUF 讀取器強制升級為原生 UNET 讀取器
        if data.get("class_type") == "UnetLoaderGGUF":
            data["class_type"] = "UNETLoader"
            # 原生 UNET 節點需要一個 weight_dtype 參數
            if "inputs" in data:
                data["inputs"]["weight_dtype"] = "default"
                
        return {k: fix_content(v) for k, v in data.items()}
        
    elif isinstance(data, list):
        return [fix_content(i) for i in data]
        
    elif isinstance(data, str):
        # 1. 統一斜線
        new_val = data.replace('\\\\', '/').replace('\\', '/')
        
        # 2. 精準對應字典 (將破檔的 GGUF 拋棄，全面擁抱 BF16)
        mapping = {
            # --- 拋棄 GGUF，全面指向你 SSD 裡的 2512 BF16 ---
            "Qwen/Qwen-Image-Edit-2512-Q4_K_M.gguf": "Qwen/split_files/diffusion_models/qwen_image_2512_bf16.safetensors",
            "Qwen/Qwen-Image-Edit-2509-Q4_K_M.gguf": "Qwen/split_files/diffusion_models/qwen_image_2512_bf16.safetensors",
            
            # --- 其餘修正保持不變 ---
            "Qwen/qwen_image_edit_2509_fp8_e4m3fn.safetensors": "Qwen/split_files/diffusion_models/qwen_image_2512_bf16.safetensors",
            "Qwen/qwen_image_edit_2512_fp8_e4m3fn.safetensors": "Qwen/split_files/diffusion_models/qwen_image_2512_bf16.safetensors",
            "Qwen/qwen_image_vae.safetensors": "Qwen_Image_Edit/split_files/vae/qwen_image_vae.safetensors",
            "z-image/ae.safetensors": "z-image/split_files/vae/ae.safetensors",
            "Qwen_Edit/Lightning/Qwen-Image-Edit-2512-Lightning-4steps-V1.0-bf16.safetensors": "Qwen_Image_Edit/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
            "Qwen_Edit/Lightning/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors": "Qwen_Image_Edit/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
            "z-image/qwen_3_4b.safetensors": "z-image/split_files/text_encoders/qwen_3_4b.safetensors",
            "Qwen/qwen_2.5_vl_7b_fp8_scaled.safetensors": "Qwen_Image_Edit/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"
        }
        
        for old_path, new_path in mapping.items():
            if old_path in new_val:
                return new_path
                
        return new_val
    return data
# 搜尋所有 1222 版本的工作流
target_files = glob.glob(os.path.join(WORKFLOW_SRC, "*_1222.json"))

print(f"📂 正在搜尋工作流於: {WORKFLOW_SRC}")

for file_path in target_files:
    file_name = os.path.basename(file_path)
    print(f"🛠️  正在修正: {file_name}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            workflow_data = json.load(f)
        
        # 執行遞迴修正
        fixed_workflow = fix_content(workflow_data)
        
        # 儲存到輸出目錄
        output_file = os.path.join(WORKFLOW_OUT, file_name)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(fixed_workflow, f, indent=2, ensure_ascii=False)
            
    except Exception as e:
        print(f"❌ 錯誤於 {file_name}: {e}")

print(f"\n✅ 修正完成！請查看：{WORKFLOW_OUT}")
print("⚠️  提醒：worker 執行期不會讀取此資料夾，僅供人工比對，請勿視為必要產物")