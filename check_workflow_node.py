import json
from pathlib import Path

path = Path("ComfyUIworkflow/multi_image_blend_qwen_2509_gguf_1222.json")
data = json.loads(path.read_text(encoding="utf-8"))

nodes = data["nodes"]
target = next((n for n in nodes if str(n.get("id")) == "433:111"), None)

assert target is not None, "node 433:111 not found"
assert target.get("type") == "TextEncodeQwenImageEditPlus"
assert target.get("widgets_values"), "widgets_values missing"
assert target["widgets_values"][0] == "圖1的女生拖著圖2的行李箱，站在圖3的地鐵站入口，逼真的光影"

print("OK: node 433:111 exists and widgets_values[0] is the expected default prompt")
