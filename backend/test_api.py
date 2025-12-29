"""
API 测试脚本
用于测试 Backend API 的各个端点
使用方法: python test_api.py
"""
import requests
import json
import time

# 配置
API_BASE_URL = "http://localhost:5000"

def print_section(title):
    """打印分隔线"""
    print("\n" + "="*60)
    print(f" {title}")
    print("="*60)

def test_health():
    """测试健康检查端点"""
    print_section("1. 测试健康检查端点")
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        print(f"状态码: {response.status_code}")
        print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

def test_generate():
    """测试生成任务端点"""
    print_section("2. 测试 POST /api/generate")
    
    test_data = {
        "prompt": "a cyberpunk cat in neon city",
        "seed": 12345,
        "workflow": "sdxl"
    }
    
    try:
        print(f"请求数据: {json.dumps(test_data, indent=2, ensure_ascii=False)}")
        response = requests.post(
            f"{API_BASE_URL}/api/generate",
            json=test_data,
            headers={"Content-Type": "application/json"}
        )
        print(f"\n状态码: {response.status_code}")
        result = response.json()
        print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if response.status_code == 202 and 'job_id' in result:
            print(f"✓ 任务创建成功! job_id: {result['job_id']}")
            return result['job_id']
        else:
            print("❌ 任务创建失败")
            return None
    except Exception as e:
        print(f"❌ 错误: {e}")
        return None

def test_status(job_id):
    """测试状态查询端点"""
    print_section(f"3. 测试 GET /api/status/{job_id}")
    
    try:
        response = requests.get(f"{API_BASE_URL}/api/status/{job_id}")
        print(f"状态码: {response.status_code}")
        result = response.json()
        print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if response.status_code == 200:
            print(f"✓ 状态查询成功")
            print(f"  - 状态: {result.get('status')}")
            print(f"  - 进度: {result.get('progress')}%")
            return True
        else:
            print("❌ 状态查询失败")
            return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

def test_invalid_generate():
    """测试无效的生成请求"""
    print_section("4. 测试无效请求（空 prompt）")
    
    test_data = {
        "prompt": "",
        "seed": 12345
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/generate",
            json=test_data,
            headers={"Content-Type": "application/json"}
        )
        print(f"状态码: {response.status_code}")
        print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code == 400:
            print("✓ 验证逻辑正常工作")
            return True
        else:
            print("❌ 应该返回 400 错误")
            return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

def test_nonexistent_job():
    """测试查询不存在的任务"""
    print_section("5. 测试查询不存在的任务")
    
    fake_job_id = "00000000-0000-0000-0000-000000000000"
    
    try:
        response = requests.get(f"{API_BASE_URL}/api/status/{fake_job_id}")
        print(f"状态码: {response.status_code}")
        print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code == 404:
            print("✓ 正确返回 404")
            return True
        else:
            print("❌ 应该返回 404")
            return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

def main():
    """主测试流程"""
    print("\n")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║          Studio Core Backend API 测试套件                 ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    
    results = []
    
    # 1. 健康检查
    if not test_health():
        print("\n❌ API 服务未运行或 Redis 不可用")
        print("请确保已启动:")
        print("  1. Redis: docker run -d -p 6379:6379 redis")
        print("  2. Backend: python backend/src/app.py")
        return
    
    # 2. 测试生成任务
    job_id = test_generate()
    if job_id:
        results.append(("生成任务", True))
        
        # 3. 等待一下再查询状态
        time.sleep(0.5)
        
        # 4. 测试状态查询
        status_ok = test_status(job_id)
        results.append(("状态查询", status_ok))
    else:
        results.append(("生成任务", False))
        results.append(("状态查询", False))
    
    # 5. 测试无效请求
    invalid_ok = test_invalid_generate()
    results.append(("输入验证", invalid_ok))
    
    # 6. 测试不存在的任务
    notfound_ok = test_nonexistent_job()
    results.append(("404 处理", notfound_ok))
    
    # 总结
    print_section("测试总结")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    
    for test_name, ok in results:
        status = "✓ 通过" if ok else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！Backend API 工作正常。")
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，请检查日志。")

if __name__ == "__main__":
    main()
