"""
JSON Parser for ComfyUI Workflow
================================
動態解析並修改 ComfyUI workflow JSON 檔案。
支援 Aspect Ratio、Model、Prompt、Seed 等參數注入。
"""

import json
import os
import copy
from pathlib import Path

# ==========================================
# Aspect Ratio 映射表 (SDXL 最佳解析度)
# ==========================================
ASPECT_RATIO_MAP = {
    "1:1":  {"width": 1024, "height": 1024},  # 方形
    "16:9": {"width": 1216, "height": 832},   # 電影寬銀幕
    "9:16": {"width": 832, "height": 1216},   # 手機直式
    "2:3":  {"width": 832, "height": 1248},   # 人像直式
}
DEFAULT_RESOLUTION = {"width": 1024, "height": 1024}

# ==========================================
# Model 映射表
# ⚠️ 請根據您的 ComfyUI models 資料夾內的實際檔名修改！
# 路徑格式：相對於 ComfyUI/models/checkpoints/ 或 unet/
# ==========================================
MODEL_MAP = {
    # UNET 模型 (用於 UNETLoader)
    "turbo_fp8": "z-image\\z-image-turbo-fp8-e4m3fn.safetensors",
    "z_image_turbo": "z-image\\z-image-turbo-fp8-e4m3fn.safetensors",
    
    # Checkpoint 模型 (用於 CheckpointLoaderSimple)
    # "sdxl_base": "sd_xl_base_1.0.safetensors",
    # "sdxl_turbo": "sd_xl_turbo_1.0.safetensors",
    # "dreamshaper": "dreamshaper_8.safetensors",
}

# Workflow 檔案映射
WORKFLOW_MAP = {
    "text_to_image": "text_to_image_z_image_turbo_fp8_1222.json",
    "face_swap": "face_swap_qwen_2509_gguf_1222.json",
    "multi_image_blend": "multi_image_blend_qwen_2509_gguf_1222.json",
    "single_image_edit": "single_image_edit_qwen_2509_gguf_1222.json",
    "sketch_to_image": "sketch_to_image_qwen_2509_gguf_1222.json",
}

# ==========================================
# 圖片節點映射表
# 定義每個工作流的 LoadImage 節點對應哪個前端上傳欄位
# ⚠️ 欄位名稱必須與前端 toolConfig 中的 uploads.id 一致！
# ==========================================
IMAGE_NODE_MAP = {
    "face_swap": {
        # 節點 ID -> 前端欄位名稱
        "501": "source",   # 頭 (要換上去的臉)
        "502": "target",   # 身體 (目標圖片)
    },
    "multi_image_blend": {
        "120": "source",   # 圖1 (對應前端 Image A)
        "121": "target",   # 圖2 (對應前端 Image B)
        "122": "extra",    # 圖3 (對應前端 Image C)
    },
    "sketch_to_image": {
        "120": "input",    # 草稿圖
    },
    "single_image_edit": {
        "120": "input",    # 原圖
    },
    "text_to_image": {},   # 不需要圖片
}


def get_workflow_path(workflow_name: str) -> Path:
    """
    取得 workflow JSON 檔案路徑
    """
    from config import WORKFLOW_DIR
    filename = WORKFLOW_MAP.get(workflow_name, f"{workflow_name}.json")
    return WORKFLOW_DIR / filename


def load_workflow(workflow_name: str) -> dict:
    """
    載入 workflow JSON 模板
    """
    workflow_path = get_workflow_path(workflow_name)
    
    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow 檔案不存在: {workflow_path}")
    
    with open(workflow_path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_node_by_class(workflow: dict, class_type: str) -> tuple:
    """
    根據 class_type 找到節點
    Returns: (node_id, node_data) or (None, None)
    """
    for node_id, node_data in workflow.items():
        if isinstance(node_data, dict) and node_data.get("class_type") == class_type:
            return node_id, node_data
    return None, None


def find_nodes_by_class(workflow: dict, class_type: str) -> list:
    """
    找到所有符合 class_type 的節點
    Returns: [(node_id, node_data), ...]
    """
    nodes = []
    for node_id, node_data in workflow.items():
        if isinstance(node_data, dict) and node_data.get("class_type") == class_type:
            nodes.append((node_id, node_data))
    return nodes


def parse_workflow(
    workflow_name: str,
    prompt: str = "",
    seed: int = -1,
    aspect_ratio: str = "1:1",
    model: str = "turbo_fp8",
    batch_size: int = 1,
    image_files: dict = None,
    **kwargs
) -> dict:
    """
    解析並注入參數到 workflow
    
    Args:
        workflow_name: workflow 名稱 (如 "text_to_image")
        prompt: 正向提示詞
        seed: 隨機種子 (-1 為隨機)
        aspect_ratio: 畫面比例 ("1:1", "16:9", "9:16", "2:3")
        model: 模型名稱
        batch_size: 批次數量
        image_files: 圖片檔名映射 {"source": "xxx.png", "target": "yyy.png"}
    
    Returns:
        修改後的 workflow dict
    """
    if image_files is None:
        image_files = {}
    # 載入原始 workflow
    workflow = load_workflow(workflow_name)
    workflow = copy.deepcopy(workflow)  # 避免修改原始資料
    
    # 取得解析度
    resolution = ASPECT_RATIO_MAP.get(aspect_ratio, DEFAULT_RESOLUTION)
    width = resolution["width"]
    height = resolution["height"]
    
    # 處理 seed (-1 表示隨機)
    if seed == -1:
        import random
        seed = random.randint(0, 2**32 - 1)
    
    print(f"[Parser] 解析度: {width}x{height}, Seed: {seed}, Model: {model}")
    
    # ==========================================
    # 注入 Prompt (支援多種節點類型)
    # ==========================================
    prompt_injected = False
    
    # 1. 嘗試 CLIPTextEncode (標準 SDXL workflow)
    positive_nodes = find_nodes_by_class(workflow, "CLIPTextEncode")
    for node_id, node in positive_nodes:
        title = node.get("_meta", {}).get("title", "")
        if "Positive" in title or "positive" in title.lower():
            node["inputs"]["text"] = prompt
            print(f"[Parser] 注入 Prompt 到 CLIPTextEncode 節點 {node_id}")
            prompt_injected = True
            break
    else:
        # 如果沒找到標題，嘗試第一個 CLIPTextEncode
        if positive_nodes:
            positive_nodes[0][1]["inputs"]["text"] = prompt
            print(f"[Parser] 注入 Prompt 到第一個 CLIPTextEncode 節點")
            prompt_injected = True
    
    # 2. 嘗試 TextEncodeQwenImageEditPlus (Qwen Image Edit workflow)
    if not prompt_injected:
        qwen_nodes = find_nodes_by_class(workflow, "TextEncodeQwenImageEditPlus")
        for node_id, node in qwen_nodes:
            title = node.get("_meta", {}).get("title", "").lower()
            # 只注入到 Positive 節點 (通常 Negative 節點的 prompt 為空)
            if "negative" not in title:
                if "inputs" in node and "prompt" in node["inputs"]:
                    node["inputs"]["prompt"] = prompt
                    print(f"[Parser] 注入 Prompt 到 TextEncodeQwenImageEditPlus 節點 {node_id}")
                    prompt_injected = True
                    break
        
        if not prompt_injected and qwen_nodes:
            # 如果找不到明確的 Positive，嘗試第一個有 prompt 輸入的節點
            for node_id, node in qwen_nodes:
                if "inputs" in node and "prompt" in node["inputs"]:
                    # 檢查這個節點的 prompt 是否不為空 (表示是 Positive)
                    if node["inputs"]["prompt"] or node["inputs"]["prompt"] == "":
                        node["inputs"]["prompt"] = prompt
                        print(f"[Parser] 注入 Prompt 到 TextEncodeQwenImageEditPlus 節點 {node_id} (fallback)")
                        prompt_injected = True
                        break
    
    if not prompt_injected:
        print(f"[Parser] ⚠️ 未找到可注入 Prompt 的節點")
    
    # ==========================================
    # 注入 Seed (KSampler)
    # ==========================================
    sampler_id, sampler_node = find_node_by_class(workflow, "KSampler")
    if sampler_node:
        sampler_node["inputs"]["seed"] = seed
        print(f"[Parser] 注入 Seed 到 KSampler 節點 {sampler_id}")
    
    # ==========================================
    # 注入 Resolution (EmptySD3LatentImage / EmptyLatentImage)
    # ==========================================
    latent_classes = ["EmptySD3LatentImage", "EmptyLatentImage"]
    for class_type in latent_classes:
        latent_id, latent_node = find_node_by_class(workflow, class_type)
        if latent_node:
            latent_node["inputs"]["width"] = width
            latent_node["inputs"]["height"] = height
            latent_node["inputs"]["batch_size"] = batch_size
            print(f"[Parser] 注入解析度 {width}x{height} 到 {class_type} 節點 {latent_id}")
            break
    
    # ==========================================
    # 注入 Model (UNETLoader / CheckpointLoaderSimple)
    # ==========================================
    model_filename = MODEL_MAP.get(model)
    
    if model_filename:
        # 嘗試 UNETLoader
        unet_id, unet_node = find_node_by_class(workflow, "UNETLoader")
        if unet_node:
            unet_node["inputs"]["unet_name"] = model_filename
            print(f"[Parser] 注入模型 {model_filename} 到 UNETLoader 節點 {unet_id}")
        
        # 嘗試 CheckpointLoaderSimple
        ckpt_id, ckpt_node = find_node_by_class(workflow, "CheckpointLoaderSimple")
        if ckpt_node:
            ckpt_node["inputs"]["ckpt_name"] = model_filename
            print(f"[Parser] 注入模型 {model_filename} 到 CheckpointLoaderSimple 節點 {ckpt_id}")
    else:
        print(f"[Parser] ⚠️ 未知模型: {model}，使用 workflow 預設值")
    
    # ==========================================
    # 注入圖片 (LoadImage 節點)
    # ==========================================
    node_map = IMAGE_NODE_MAP.get(workflow_name, {})
    
    if node_map and image_files:
        print(f"[Parser] 準備注入圖片，映射表: {node_map}")
        print(f"[Parser] 收到的圖片檔案: {image_files}")
        
        for node_id, field_name in node_map.items():
            if field_name in image_files:
                filename = image_files[field_name]
                
                # 找到對應的 LoadImage 節點
                if node_id in workflow:
                    node = workflow[node_id]
                    if "inputs" in node:
                        old_image = node["inputs"].get("image", "")
                        node["inputs"]["image"] = filename
                        print(f"[Parser] ✅ 節點 {node_id}: {old_image!r} -> {filename!r}")
                    else:
                        print(f"[Parser] ⚠️ 節點 {node_id} 沒有 inputs")
                else:
                    print(f"[Parser] ⚠️ 找不到節點 {node_id}")
            else:
                print(f"[Parser] ⚠️ 缺少圖片欄位: {field_name}")
    elif node_map:
        print(f"[Parser] ⚠️ 此工作流需要圖片但未提供: {list(node_map.values())}")
    
    return workflow


# ==========================================
# 測試用
# ==========================================
if __name__ == "__main__":
    # 測試 parse_workflow
    try:
        workflow = parse_workflow(
            workflow_name="text_to_image",
            prompt="A beautiful sunset over mountains",
            seed=12345,
            aspect_ratio="16:9",
            model="turbo_fp8",
            batch_size=1
        )
        print("\n[Test] Workflow 解析成功！")
        print(json.dumps(workflow, indent=2, ensure_ascii=False)[:500] + "...")
    except Exception as e:
        print(f"[Test] 錯誤: {e}")
