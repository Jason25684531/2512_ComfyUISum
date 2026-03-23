import json
import os
import glob

# 取得目前腳本路徑並推算根目錄
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_SRC = os.path.join(BASE_DIR, "ComfyUIworkflow")
WORKFLOW_OUT = os.path.join(WORKFLOW_SRC, "linux_fixed")

# 確保輸出資料夾存在
if not os.path.exists(WORKFLOW_OUT):
    os.makedirs(WORKFLOW_OUT)

def fix_content(data):
    if isinstance(data, dict):
        return {k: fix_content(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [fix_content(i) for i in data]
    elif isinstance(data, str):
        # 1. 核心修正：將所有 Windows 反斜線 \\ 替換為 Linux 正斜線 /
        # 即使是 Qwen\\abc.safetensors 也會變成 Qwen/abc.safetensors
        new_val = data.replace('\\\\', '/').replace('\\', '/')
        
        # 2. 清理 Windows 的磁碟機代號 (例如 C:/...)
        if ":" in new_val and "/" in new_val:
            new_val = new_val.split('/')[-1]
            
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