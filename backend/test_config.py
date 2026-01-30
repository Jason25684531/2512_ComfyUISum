"""
[TEMP] 测试脚本：验证 Veo3 测试模式配置是否正确加载
运行方式: python backend/test_config.py
"""
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.utils import load_env
load_env()

# 导入配置
sys.path.insert(0, str(Path(__file__).parent))
from src.config import VEO3_TEST_MODE, VEO3_TEST_VIDEO_PATH, PROJECT_ROOT

print("=" * 60)
print("Veo3 测试模式配置验证")
print("=" * 60)
print(f"VEO3_TEST_MODE: {VEO3_TEST_MODE} (type: {type(VEO3_TEST_MODE)})")
print(f"VEO3_TEST_VIDEO_PATH: {VEO3_TEST_VIDEO_PATH}")
print(f"PROJECT_ROOT: {PROJECT_ROOT}")
print()

# 检查测试视频文件是否存在
test_video_path = PROJECT_ROOT / VEO3_TEST_VIDEO_PATH
print(f"测试视频完整路径: {test_video_path}")
print(f"文件是否存在: {test_video_path.exists()}")

if test_video_path.exists():
    print(f"✅ 测试视频文件存在")
    print(f"   大小: {test_video_path.stat().st_size} bytes")
else:
    print(f"❌ 测试视频文件不存在！")

print()
print("触发条件: veo3_long_video 工作流 + 上传任意图片")
print("=" * 60)
