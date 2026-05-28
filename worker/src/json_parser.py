"""
JSON Parser for ComfyUI Workflow
================================
動態解析並修改 ComfyUI workflow JSON 檔案。
支援 Aspect Ratio、Model、Prompt、Seed 等參數注入。
"""

import json
import os
import copy
import sys
import builtins
from pathlib import Path

from workflow_registry import WorkflowRegistry, find_workflow_node

PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_WORKFLOW_FALLBACK_DIR = PROJECT_ROOT / "ComfyUIworkflow_api"
DEFAULT_UNET_MODEL = os.getenv(
    "DEFAULT_UNET_MODEL",
    "z-image\\z-image-turbo-fp8-e4m3fn.safetensors",
)


def print(*args, **kwargs):
    file = kwargs.get("file", sys.stdout)
    encoding = getattr(file, "encoding", None) or "utf-8"
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    flush = kwargs.get("flush", False)
    message = sep.join(str(arg) for arg in args)
    safe_message = message.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")
    builtins.print(safe_message, end=end, file=file, flush=flush)

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
    "turbo_fp8": DEFAULT_UNET_MODEL,
    "z_image_turbo": DEFAULT_UNET_MODEL,
    
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
    "virtual_human": "InfiniteTalk_IndexTTS_2.json",
    "veo3_long_video": "Veo3_VideoConnection.json",
    "image_to_video": "Veo3_VideoConnection.json",  # 單段模式也使用 Veo3
    "t2v_veo3": "T2V.json",                         # 文字轉影片 (Veo3)
    "flf_veo3": "FLF.json",                         # 首尾禎動畫 (Veo3)
}

# ==========================================
# 圖片節點映射表 (Fallback / Deprecated)
# ==========================================
# ⚠️ DEPRECATED: 請優先使用 config.json 中的 image_map 欄位
# 此映射僅作為 config.json 未定義時的備用方案
# 新增 workflow 時應直接在 config.json 中定義 image_map
# 若重新匯出新版 ComfyUI API JSON，請優先更新 config.json 的 image_map / mapping，
# Parser 會先依該映射動態替換 image filename、prompt、text 等節點 ID。
# ==========================================
IMAGE_NODE_MAP = {
    "face_swap": {
        # ⚠️ 若重新匯出 face_swap API JSON，請先核對 501/502 是否仍是 source/target 的 LoadImage 節點
        # 節點 ID -> 前端欄位名稱
        "501": "source",   # 頭 (要換上去的臉)
        "502": "target",   # 身體 (目標圖片)
    },
    "multi_image_blend": {
        # 節點 ID 對應 multi_image_blend_qwen_2509_gguf_1222.json
        "78": "source",    # 模特圖 (對應前端 Image A)
        "436": "target",   # 行李箱圖 (對應前端 Image B)
        "437": "extra",    # 場景圖 (對應前端 Image C)
    },
    "sketch_to_image": {
        # ⚠️ 若重新匯出 sketch_to_image API JSON，請再次確認 120 是否仍是草稿圖的 LoadImage 節點
        "120": "input",    # 草稿圖
    },
    "single_image_edit": {
        "120": "input",    # 原圖
    },
    "text_to_image": {},   # 不需要圖片
    "virtual_human": {
        "284": "avatar",   # 虛擬人參考圖 (LoadImage)
    },
    "veo3_long_video": {
        # Veo3 Long Video: 5 個 LoadImage 節點對應 Shot 1-5
        "6": "shot_0",     # Shot 1 圖片
        "20": "shot_1",    # Shot 2 圖片
        "30": "shot_2",    # Shot 3 圖片
        "40": "shot_3",    # Shot 4 圖片
        "50": "shot_4",    # Shot 5 圖片
    },
    "image_to_video": {
        "6": "shot_0",     # 單段模式也使用 Shot 1
    },
    "t2v_veo3": {},        # 文字轉影片不需要圖片
    "flf_veo3": {
        # 首尾禎動畫：雙圖片注入 (從 config.json 的 image_map 讀取)
        "112": "first_frame",   # 首禎
        "113": "last_frame",    # 尾禎
    },
}

# ==========================================
# 音訊節點映射表 (用於 virtual_human 等工作流)
# ==========================================
AUDIO_NODE_MAP = {
    "virtual_human": {
        "node_id": "311",    # LoadAudio 節點 ID
        "input_key": "audio" # 節點 inputs 中的參數名
    }
}


def _is_ui_workflow_data(workflow_data) -> bool:
    return isinstance(workflow_data, dict) and isinstance(workflow_data.get("nodes"), list)


def _load_json_file(path: Path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _safe_log_value(value) -> str:
    return ascii(value)


def get_workflow_node(workflow: dict, node_id: str):
    node = find_workflow_node(workflow, node_id)
    if not isinstance(node, dict):
        print(f"[Parser] ⚠️ Node {node_id} 不是 dict，而是 {type(node).__name__}")
        return None
    return node


def set_node_input_value(workflow: dict, node_id: str, input_key: str, value, label: str = "") -> bool:
    node = get_workflow_node(workflow, node_id)
    if not node:
        return False

    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        print(f"[Parser] ⚠️ Node {node_id} 沒有可用的 inputs dict")
        return False

    if input_key not in inputs:
        print(f"[Parser] ⚠️ Node {node_id} 不包含 inputs.{input_key}")
        return False

    old_value = inputs.get(input_key)
    inputs[input_key] = value

    if label:
        print(
            f"[Parser] {label}: Node {node_id}.{input_key} = "
            f"{_safe_log_value(old_value)} -> {_safe_log_value(value)}"
        )
    return True


def set_node_prompt_value(workflow: dict, node_id: str, prompt_value: str, label: str = "") -> bool:
    for input_key in ("text", "prompt", "string"):
        if set_node_input_value(workflow, node_id, input_key, prompt_value, label):
            return True

    node = get_workflow_node(workflow, node_id)
    if not node:
        return False

    widgets_values = node.get("widgets_values")
    if isinstance(widgets_values, list) and widgets_values:
        old_value = widgets_values[0]
        widgets_values[0] = prompt_value
        if label:
            print(
                f"[Parser] {label}: Node {node_id}.widgets_values[0] = "
                f"{_safe_log_value(old_value)} -> {_safe_log_value(prompt_value)}"
            )
        return True

    if isinstance(widgets_values, dict):
        for input_key in ("text", "prompt", "string"):
            if input_key in widgets_values:
                old_value = widgets_values[input_key]
                widgets_values[input_key] = prompt_value
                if label:
                    print(
                        f"[Parser] {label}: Node {node_id}.widgets_values[{input_key!r}] = "
                        f"{_safe_log_value(old_value)} -> {_safe_log_value(prompt_value)}"
                    )
                return True

    print(f"[Parser] ⚠️ Node {node_id} 找不到可寫入的 prompt/text/string 欄位")
    return False


def set_configured_prompt_value(workflow: dict, node_id: str, input_key: str, prompt_value: str, label: str = "") -> bool:
    node = get_workflow_node(workflow, node_id)
    if not node:
        return False

    inputs = node.get("inputs")
    if isinstance(inputs, dict) and input_key in inputs:
        old_value = inputs.get(input_key)
        inputs[input_key] = prompt_value
        if label:
            print(
                f"[Parser] {label}: Node {node_id}.{input_key} = "
                f"{_safe_log_value(old_value)} -> {_safe_log_value(prompt_value)}"
            )
        return True

    widgets_values = node.get("widgets_values")
    if isinstance(widgets_values, list) and widgets_values:
        old_value = widgets_values[0]
        widgets_values[0] = prompt_value
        if label:
            print(
                f"[Parser] {label}: Node {node_id}.widgets_values[0] = "
                f"{_safe_log_value(old_value)} -> {_safe_log_value(prompt_value)}"
            )
        return True

    if isinstance(widgets_values, dict):
        for widget_key in (input_key, "prompt", "text", "string"):
            if widget_key in widgets_values:
                old_value = widgets_values[widget_key]
                widgets_values[widget_key] = prompt_value
                if label:
                    print(
                        f"[Parser] {label}: Node {node_id}.widgets_values[{widget_key!r}] = "
                        f"{_safe_log_value(old_value)} -> {_safe_log_value(prompt_value)}"
                    )
                return True

    print(f"[Parser] ?? Config prompt target {node_id}.{input_key} cannot be injected")
    return False


def get_workflow_path(workflow_name: str) -> Path:
    """
    取得 workflow JSON 檔案路徑
    優先從 config.json 讀取，若不存在則使用 WORKFLOW_MAP
    """
    workflow_dir = WorkflowRegistry().workflow_dir

    try:
        entry = WorkflowRegistry(workflow_dir=workflow_dir).get(workflow_name)
        if entry.file and entry.path.exists():
            print(f"[Parser] 敺?config.json 霈??workflow ?辣: {entry.file}")
            return entry.path
    except Exception as e:
        print(f"[Parser] ?? 霈??config.json 憭望?: {e}")
        entry = None

    filename = WORKFLOW_MAP.get(workflow_name, f"{workflow_name}.json")
    return workflow_dir / filename
    
    # 嘗試從 config.json 讀取文件名
    if WORKFLOW_CONFIG_PATH.exists():
        try:
            with open(WORKFLOW_CONFIG_PATH, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            workflow_config = config_data.get(workflow_name, {})
            if 'file' in workflow_config:
                filename = workflow_config['file']
                print(f"[Parser] 從 config.json 讀取 workflow 文件: {filename}")
                return WORKFLOW_DIR / filename
        except Exception as e:
            print(f"[Parser] ⚠️ 讀取 config.json 失敗: {e}")
    
    # Fallback: 使用 WORKFLOW_MAP
    filename = WORKFLOW_MAP.get(workflow_name, f"{workflow_name}.json")
    return WORKFLOW_DIR / filename


def load_workflow(workflow_name: str) -> dict:
    """
    載入 workflow JSON 模板
    """
    workflow_path = get_workflow_path(workflow_name)
    
    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow 檔案不存在: {workflow_path}")
    
    workflow_data = _load_json_file(workflow_path)

    if _is_ui_workflow_data(workflow_data):
        fallback_path = API_WORKFLOW_FALLBACK_DIR / workflow_path.name
        if fallback_path.exists():
            print(f"[Parser] 偵測到 UI workflow，改用 API fallback: {fallback_path.name}")
            workflow_data = _load_json_file(fallback_path)
        else:
            raise ValueError(
                f"Workflow {workflow_path.name} 是 UI 匯出格式，但找不到 API fallback 檔案: {fallback_path}"
            )

    if not isinstance(workflow_data, dict):
        raise TypeError(f"Workflow 格式錯誤，預期 dict，實際為 {type(workflow_data).__name__}")

    return workflow_data


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


def trim_veo3_workflow(workflow: dict, image_files: dict) -> dict:
    """
    根據實際上傳的圖片數量，動態裁剪 Veo3 Long Video 工作流
    
    Veo3 工作流結構 (每個 Shot 的節點):
    - Shot 1: 節點 6 (LoadImage), 10 (VeoVideoGenerator), 11 (VHS_VideoCombine)
    - Shot 2: 節點 20 (LoadImage), 21 (VeoVideoGenerator), 22 (VHS_VideoCombine)
    - Shot 3: 節點 30 (LoadImage), 31 (VeoVideoGenerator), 32 (VHS_VideoCombine)
    - Shot 4: 節點 40 (LoadImage), 41 (VeoVideoGenerator), 42 (VHS_VideoCombine)
    - Shot 5: 節點 50 (LoadImage), 51 (VeoVideoGenerator), 52 (VHS_VideoCombine)
    - ImageBatch 鏈: 100 -> 101 -> 102 -> 103 -> 110 (最終輸出)
    
    Args:
        workflow: 原始工作流
        image_files: 圖片檔案映射 {"shot_0": "xxx.png", "shot_1": "yyy.png", ...}
    
    Returns:
        裁剪後的工作流
    """
    # 確定有哪些 shots
    valid_shots = []
    for i in range(5):
        shot_key = f"shot_{i}"
        if shot_key in image_files and image_files[shot_key]:
            valid_shots.append(i)
    
    shot_count = len(valid_shots)
    print(f"[Parser] Veo3 動態裁剪: 偵測到 {shot_count} 個有效 shots: {valid_shots}")
    
    if shot_count == 0:
        print("[Parser] ⚠️ 沒有有效的圖片，返回原始工作流")
        return workflow
    
    if shot_count == 5:
        print("[Parser] 所有 5 個 shots 都有圖片，不需要裁剪")
        return workflow
    
    # Shot 節點映射 (對應 Veo3_VideoConnection.json)
    # 注意：此 workflow 沒有獨立的 VHS_VideoCombine 節點，只有最終輸出節點 110
    shot_nodes = {
        0: {"load": "6", "gen": "10"},   # Shot 1
        1: {"load": "20", "gen": "21"},  # Shot 2
        2: {"load": "30", "gen": "31"},  # Shot 3
        3: {"load": "40", "gen": "41"},  # Shot 4
        4: {"load": "50", "gen": "51"},  # Shot 5
    }
    
    # 刪除沒有圖片的 Shot 節點
    nodes_to_remove = []
    for i in range(5):
        if i not in valid_shots:
            nodes = shot_nodes[i]
            nodes_to_remove.extend([nodes["load"], nodes["gen"]])
            print(f"[Parser] 移除 Shot {i+1} 節點: {nodes}")
    
    for node_id in nodes_to_remove:
        if node_id in workflow:
            del workflow[node_id]
    
    # 重建 ImageBatch 鏈 (只連接有效的 shots)
    # 原始鏈: 100(10+21) -> 101(100+31) -> 102(101+41) -> 103(102+51) -> 110
    
    # 移除原有的 ImageBatch 節點
    for node_id in ["100", "101", "102", "103"]:
        if node_id in workflow:
            del workflow[node_id]
    
    # 獲取有效 shots 的 generator 節點 ID (輸出影片幀)
    valid_gen_nodes = [shot_nodes[i]["gen"] for i in valid_shots]
    print(f"[Parser] 有效的 generator 節點: {valid_gen_nodes}")
    
    if shot_count == 1:
        # 只有一個 shot，直接連接到最終輸出
        if "110" in workflow:
            set_node_input_value(
                workflow,
                "110",
                "images",
                [valid_gen_nodes[0], 0],
                "單一 shot 輸出連接",
            )
            print(f"[Parser] 單一 shot 模式: 節點 110 直接連接到 {valid_gen_nodes[0]}")
    else:
        # 多個 shots，重建 ImageBatch 鏈
        # 使用節點 ID 100, 101, 102... 來建立鏈
        batch_node_id = 100
        
        # 第一個 batch: 連接前兩個 generator
        workflow[str(batch_node_id)] = {
            "inputs": {
                "image1": [valid_gen_nodes[0], 0],
                "image2": [valid_gen_nodes[1], 0]
            },
            "class_type": "ImageBatch",
            "_meta": {"title": "Batch Images (Dynamic)"}
        }
        print(f"[Parser] 建立 ImageBatch {batch_node_id}: {valid_gen_nodes[0]} + {valid_gen_nodes[1]}")
        
        # 後續的 batch: 連接前一個 batch 和下一個 generator
        for i in range(2, shot_count):
            prev_batch_id = str(batch_node_id)
            batch_node_id += 1
            
            workflow[str(batch_node_id)] = {
                "inputs": {
                    "image1": [prev_batch_id, 0],
                    "image2": [valid_gen_nodes[i], 0]
                },
                "class_type": "ImageBatch",
                "_meta": {"title": f"Batch Images (Dynamic {i})"}
            }
            print(f"[Parser] 建立 ImageBatch {batch_node_id}: {prev_batch_id} + {valid_gen_nodes[i]}")
        
        # 最終輸出節點連接到最後一個 batch
        if "110" in workflow:
            set_node_input_value(
                workflow,
                "110",
                "images",
                [str(batch_node_id), 0],
                "ImageBatch 最終輸出連接",
            )
            print(f"[Parser] 節點 110 連接到最後的 ImageBatch: {batch_node_id}")
    
    return workflow


def parse_workflow(
    workflow_name: str,
    prompt: str = "",
    prompts: list = None,  # Veo3 Long Video: 多段 prompts
    seed: int = -1,
    aspect_ratio: str = "1:1",
    model: str = "turbo_fp8",
    batch_size: int = 1,
    image_files: dict = None,
    audio_file: str = None,
    **kwargs
) -> dict:
    """
    解析並注入參數到 workflow
    優先從 config.json 讀取映射規則 (Config-Driven)
    """
    # ==========================================
    # 1. 初始化變數與引入 Config (優先定義)
    # ==========================================
    registry = WorkflowRegistry()
    workflow_entry = registry.get(workflow_name)
    config_path = registry.config_path
    
    if image_files is None:
        image_files = {}
    if prompts is None:
        prompts = []
    
    # 載入原始 workflow
    workflow = load_workflow(workflow_name)
    workflow = copy.deepcopy(workflow)  # 避免修改原始資料
    
    # ==========================================
    # 2. 載入 Config.json 配置 (Config-Driven)
    # ==========================================
    config_data = registry._config
    workflow_config = config_data.get(workflow_entry.name, {})
    image_map_config = workflow_entry.image_map
    prompt_map_config = workflow_entry.prompt_map
    
    try:
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            # 新版 ComfyUI API JSON 重新匯出後，只要更新這裡對應的 image_map / prompt_node_id / text_node_id，
            # Parser 就會優先使用新節點 ID，而不是回退到檔內常數映射。
            workflow_config = config_data.get(workflow_entry.name, {})
            image_map_config = workflow_entry.image_map
            print(f"[Parser] 成功載入 config.json for {workflow_name}")
            if image_map_config:
                print(f"[Parser] 偵測到 image_map 配置: {image_map_config}")
    except Exception as e:
        print(f"[Parser] ⚠️ 讀取 config.json 失敗，將使用 Fallback: {e}")
    
    # Veo3 Long Video 特殊處理：根據圖片數量動態裁剪工作流
    if workflow_name == "veo3_long_video":
        workflow = trim_veo3_workflow(workflow, image_files)
    
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
    # 特殊處理: virtual_human 台詞注入 (IndexTTS2BaseNode)
    # 從 config.json 讀取 text_node_id，注入到 inputs.text
    # ==========================================
    if workflow_name == "virtual_human" and prompt:
        text_node_id = workflow_config.get('mapping', {}).get('text_node_id')
        if text_node_id and text_node_id in workflow:
            if set_node_input_value(workflow, text_node_id, 'text', prompt, "virtual_human 台詞注入"):
                print(f"[Parser] 🎤 virtual_human: 注入台詞到 Node {text_node_id} (IndexTTS2BaseNode)")
                prompt_preview = prompt[:100] if len(prompt) > 100 else prompt
                print(f"[Parser] 📝 台詞內容: {_safe_log_value(prompt_preview)}...")
        else:
            # Fallback: 直接查找 IndexTTS2BaseNode
            tts_nodes = find_nodes_by_class(workflow, "IndexTTS2BaseNode")
            if tts_nodes:
                node_id, node = tts_nodes[0]
                if set_node_input_value(workflow, node_id, 'text', prompt, "virtual_human 台詞 fallback"):
                    print(f"[Parser] 🎤 virtual_human: 注入台詞到 IndexTTS2BaseNode 節點 {node_id} (fallback)")
    
    # ==========================================
    # 注入 Prompt (支援多種節點類型)
    # ==========================================
    prompt_injected = False

    if prompt and prompt_map_config:
        for prompt_name, target in prompt_map_config.items():
            node_id = target.get("node_id")
            input_key = target.get("input_key", "prompt")
            if node_id and set_configured_prompt_value(
                workflow,
                node_id,
                input_key,
                prompt,
                f"Config prompt_map.{prompt_name}",
            ):
                print(f"[Parser] Config prompt_map injected prompt into Node {node_id}.{input_key}")
                prompt_injected = True
                break
    
    # 1. 嘗試 CLIPTextEncode (標準 SDXL workflow)
    positive_nodes = [] if prompt_injected else find_nodes_by_class(workflow, "CLIPTextEncode")
    for node_id, node in positive_nodes:
        title = node.get("_meta", {}).get("title", "")
        if "Positive" in title or "positive" in title.lower():
            set_node_input_value(workflow, node_id, "text", prompt, "CLIPTextEncode Prompt 注入")
            print(f"[Parser] 注入 Prompt 到 CLIPTextEncode 節點 {node_id}")
            prompt_injected = True
            break
    else:
        # 如果沒找到標題，嘗試第一個 CLIPTextEncode
        if positive_nodes:
            first_node_id, _ = positive_nodes[0]
            if set_node_input_value(workflow, first_node_id, "text", prompt, "第一個 CLIPTextEncode Prompt 注入"):
                print(f"[Parser] 注入 Prompt 到第一個 CLIPTextEncode 節點")
                prompt_injected = True
    
    # 2. 嘗試 StringConstantMultiline (用於 face_swap 等需要用戶輸入的 workflow)
    # 注意：不要注入到 title 包含 "Trigger" 或 "trigger" 的節點，那些是預設內容
    if not prompt_injected:
        string_nodes = find_nodes_by_class(workflow, "StringConstantMultiline")
        for node_id, node in string_nodes:
            title = node.get("_meta", {}).get("title", "").lower()
            # 跳過包含 trigger 的節點（那是預設固定的 prompt）
            if "trigger" not in title:
                if set_node_input_value(workflow, node_id, "string", prompt, "StringConstantMultiline Prompt 注入"):
                    print(f"[Parser] 注入 Prompt 到 StringConstantMultiline 節點 {node_id} (title: {node.get('_meta', {}).get('title', '')})")
                    prompt_injected = True
                    break
    
    # 3. 嘗試 TextEncodeQwenImageEditPlus (Qwen Image Edit workflow)
    if not prompt_injected:
        qwen_nodes = find_nodes_by_class(workflow, "TextEncodeQwenImageEditPlus")
        for node_id, node in qwen_nodes:
            title = node.get("_meta", {}).get("title", "").lower()
            # 只注入到 Positive 節點 (通常 Negative 節點的 prompt 為空)
            if "negative" not in title:
                if set_node_input_value(workflow, node_id, "prompt", prompt, "Qwen Prompt 注入"):
                    print(f"[Parser] 注入 Prompt 到 TextEncodeQwenImageEditPlus 節點 {node_id}")
                    prompt_injected = True
                    break
        
        if not prompt_injected and qwen_nodes:
            # 如果找不到明確的 Positive，嘗試第一個有 prompt 輸入的節點
            for node_id, node in qwen_nodes:
                if isinstance(node.get("inputs"), dict) and "prompt" in node["inputs"]:
                    # 檢查這個節點的 prompt 是否不為空 (表示是 Positive)
                    if node["inputs"]["prompt"] or node["inputs"]["prompt"] == "":
                        set_node_input_value(workflow, node_id, "prompt", prompt, "Qwen Prompt fallback 注入")
                        print(f"[Parser] 注入 Prompt 到 TextEncodeQwenImageEditPlus 節點 {node_id} (fallback)")
                        prompt_injected = True
                        break
    
    # 4. 嘗試 VeoVideoGenerator / Veo3StartEndVideoGenerator (Veo3 Video workflows)
    if not prompt_injected:
        veo_classes = ["VeoVideoGenerator", "Veo3StartEndVideoGenerator"]
        for veo_class in veo_classes:
            veo_nodes = find_nodes_by_class(workflow, veo_class)
            for node_id, node in veo_nodes:
                if set_node_input_value(workflow, node_id, "prompt", prompt, f"{veo_class} Prompt 注入"):
                    print(f"[Parser] 注入 Prompt 到 {veo_class} 節點 {node_id}")
                    prompt_injected = True
                    break
            if prompt_injected:
                break
    
    # 5. 從 config.json 讀取 prompt_node_id 直接注入 (T2V/FLF 專用)
    if not prompt_injected and config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        workflow_config = config_data.get(workflow_name, {})
        mapping = workflow_config.get('mapping', {})
        prompt_node_id = mapping.get('prompt_node_id')
        
        if prompt_node_id and prompt_node_id in workflow:
            if set_node_input_value(workflow, prompt_node_id, 'prompt', prompt, "Config Prompt 注入"):
                print(f"[Parser] 從 config 注入 Prompt 到 Node {prompt_node_id}")
                prompt_injected = True
    
    if not prompt_injected:
        print(f"[Parser] ⚠️ 未找到可注入 Prompt 的節點")
    
    # ==========================================
    # Veo3 Long Video: 注入多段 Prompts (Strategy B)
    # 關鍵：迭代 Config 的 prompt_segments，而非用戶輸入
    # ==========================================
    # 檢查 workflow_name 是否有 prompt_segments 配置
    # from config import WORKFLOW_CONFIG_PATH
    # import json
    
    # config_path = WORKFLOW_CONFIG_PATH
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        workflow_config = config_data.get(workflow_name, {})
        mapping = workflow_config.get('mapping', {})
        prompt_segments_config = mapping.get('prompt_segments', {})
        
        if prompt_segments_config:
            print(f"[Parser] 檢測到 prompt_segments 配置，開始注入 {len(prompt_segments_config)} 個片段...")
            
            # Strategy B: 迭代 Config 定義的 segments
            injected_count = 0
            skipped_count = 0
            for segment_index_str, node_id_str in prompt_segments_config.items():
                segment_index = int(segment_index_str)
                
                # 優先檢查節點是否仍存在於工作流中（可能已被動態裁剪刪除）
                if node_id_str not in workflow:
                    print(f"[Parser] ⏭️ 跳過已刪除的節點 {node_id_str} (segment {segment_index})")
                    skipped_count += 1
                    continue
                
                # 檢查用戶是否提供了該 segment 的 prompt
                if segment_index < len(prompts) and prompts[segment_index]:
                    user_prompt = prompts[segment_index]
                else:
                    # 用戶未提供或留空，使用空字串
                    user_prompt = ""
                
                prompt_preview = user_prompt[:40] if user_prompt else '(empty)'
                print(f"[Parser] Segment {segment_index}: Node {node_id_str} = {_safe_log_value(prompt_preview)}...")
                
                # 注入到對應節點
                if set_node_prompt_value(workflow, node_id_str, user_prompt, f"Prompt Segment {segment_index}"):
                    print(f"[Parser] ✓ 已注入到 Node {node_id_str}")
                    injected_count += 1
            
            print(f"[Parser] ✅ 完成 prompt segments 注入: {injected_count} 個成功, {skipped_count} 個跳過")
    
    # ==========================================
    # 注入 Seed (KSampler)
    # ==========================================
    sampler_id, sampler_node = find_node_by_class(workflow, "KSampler")
    if sampler_node:
        if set_node_input_value(workflow, sampler_id, "seed", seed, "Seed 注入"):
            print(f"[Parser] 注入 Seed 到 KSampler 節點 {sampler_id}")
    
    # ==========================================
    # 注入 Resolution (EmptySD3LatentImage / EmptyLatentImage)
    # ==========================================
    latent_classes = ["EmptySD3LatentImage", "EmptyLatentImage"]
    for class_type in latent_classes:
        latent_id, latent_node = find_node_by_class(workflow, class_type)
        if latent_node:
            width_ok = set_node_input_value(workflow, latent_id, "width", width, f"{class_type} width 注入")
            height_ok = set_node_input_value(workflow, latent_id, "height", height, f"{class_type} height 注入")
            batch_ok = set_node_input_value(workflow, latent_id, "batch_size", batch_size, f"{class_type} batch_size 注入")
            if width_ok and height_ok and batch_ok:
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
            if set_node_input_value(workflow, unet_id, "unet_name", model_filename, "UNET 模型注入"):
                print(f"[Parser] 注入模型 {model_filename} 到 UNETLoader 節點 {unet_id}")
        
        # 嘗試 CheckpointLoaderSimple
        ckpt_id, ckpt_node = find_node_by_class(workflow, "CheckpointLoaderSimple")
        if ckpt_node:
            if set_node_input_value(workflow, ckpt_id, "ckpt_name", model_filename, "Checkpoint 模型注入"):
                print(f"[Parser] 注入模型 {model_filename} 到 CheckpointLoaderSimple 節點 {ckpt_id}")
    else:
        print(f"[Parser] ⚠️ 未知模型: {model}，使用 workflow 預設值")
    
    # ==========================================
    # 注入圖片 (LoadImage 節點) - Config-Driven 優先
    # ==========================================
    images_injected = False
    
    # 優先策略: 從 config.json 的 image_map 注入
    if image_map_config and image_files:
        print(f"[Parser] 使用 Config-Driven 圖片注入: {image_map_config}")
        for field_name, node_id in image_map_config.items():
            if field_name in image_files:
                filename = image_files[field_name]
                if set_node_input_value(workflow, node_id, "image", filename, f"Config 圖片注入 {field_name}"):
                    images_injected = True
            else:
                print(f"[Parser] ⚠️ Config 缺少圖片: {field_name}")
    
    # Fallback 策略: 使用 IMAGE_NODE_MAP (向後兼容)
    if not images_injected:
        node_map = IMAGE_NODE_MAP.get(workflow_name, {})
        if node_map and image_files:
            print(f"[Parser] 使用 Fallback 圖片注入 (IMAGE_NODE_MAP): {node_map}")
            for node_id, field_name in node_map.items():
                if field_name in image_files:
                    filename = image_files[field_name]
                    if set_node_input_value(workflow, node_id, "image", filename, f"Fallback 圖片注入 {field_name}"):
                        print(f"[Parser] ✅ Fallback 節點 {node_id}: {filename!r}")
                else:
                    print(f"[Parser] ⚠️ 缺少圖片欄位: {field_name}")
        elif node_map:
            print(f"[Parser] ⚠️ 此工作流需要圖片但未提供: {list(node_map.values())}")

    
    # ==========================================
    # 注入音訊 (LoadAudio 節點) - Phase 7 新增
    # 優先從 config.json 讀取 audio_node_id
    # ==========================================
    audio_injected = False
    
    # 優先策略: 從 config.json 讀取 audio_node_id
    audio_node_id = workflow_config.get('mapping', {}).get('audio_node_id')
    if audio_node_id and audio_file:
        if set_node_input_value(workflow, audio_node_id, "audio", audio_file, "Config 音訊注入"):
            print(f"[Parser] 🎵 Config: 音訊注入到 Node {audio_node_id}")
            audio_injected = True
    
    # Fallback 策略: 使用 AUDIO_NODE_MAP
    if not audio_injected:
        audio_config = AUDIO_NODE_MAP.get(workflow_name)
        
        if audio_config and audio_file:
            node_id = audio_config.get("node_id")
            input_key = audio_config.get("input_key", "audio")
            
            if node_id and set_node_input_value(workflow, node_id, input_key, audio_file, "Fallback 音訊注入"):
                print(f"[Parser] 🎵 Fallback: Injecting audio file: {audio_file} into node {node_id}")
            elif node_id:
                print(f"[Parser] ⚠️ 找不到音訊節點 {node_id}")
        elif audio_config and not audio_file:
            print(f"[Parser] ℹ️ 工作流 {workflow_name} 支援音訊注入，但未提供音訊檔案，使用預設值")
    
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
