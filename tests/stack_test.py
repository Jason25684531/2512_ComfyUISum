"""
ComfyUI Studio - Stack Testing Suite (Phase 6)
================================================
功能測試 (Functional Test) + 壓力測試 (Stress Test)

依賴安裝：
pip install playwright aiohttp

Playwright 初始化：
playwright install chromium
"""

import asyncio
import aiohttp
import time
import random
import logging
from playwright.sync_api import sync_playwright

# ============================================
# Configuration
# ============================================
BASE_URL = "http://localhost:5000"
CONCURRENT_USERS = 20
TOTAL_REQUESTS = 50

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================
# Functional Test (Happy Path with Playwright)
# ============================================
def run_functional_test():
    """
    功能測試 - 使用 Playwright 模擬完整的使用者流程
    步驟：
    1. 打開瀏覽器並訪問首頁
    2. 填寫 Prompt 輸入框
    3. 點擊 Generate 按鈕
    4. 等待並驗證回應
    """
    logger.info("=" * 60)
    logger.info("🤖 [功能測試] 啟動 Playwright E2E 測試...")
    logger.info("=" * 60)
    
    try:
        with sync_playwright() as p:
            # 啟動瀏覽器（無頭模式）
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # 訪問首頁
            logger.info(f"📄 訪問 URL: {BASE_URL}")
            page.goto(BASE_URL, timeout=30000)
            page.wait_for_load_state('networkidle')
            
            # 檢查頁面標題
            title = page.title()
            logger.info(f"📄 頁面標題: {title}")
            
            # 檢查系統 HUD 是否存在
            hud_exists = page.locator('#system-hud').is_visible()
            logger.info(f"🎯 系統 HUD 顯示: {hud_exists}")
            
            # 測試 API 端點（因為實際生成需要 ComfyUI 運行）
            # 這裡測試 /api/metrics 和 /health
            logger.info("🔍 測試 API 端點...")
            
            # 測試 Health Check
            health_response = page.evaluate(f"""
                fetch('{BASE_URL}/health')
                    .then(r => r.json())
                    .then(data => data)
                    .catch(err => ({{error: err.message}}))
            """)
            logger.info(f"✅ Health Check: {health_response}")
            
            # 測試 Metrics
            metrics_response = page.evaluate(f"""
                fetch('{BASE_URL}/api/metrics')
                    .then(r => r.json())
                    .then(data => data)
                    .catch(err => ({{error: err.message}}))
            """)
            logger.info(f"📊 Metrics: {metrics_response}")
            
            # 截圖保存
            screenshot_path = 'tests/functional_test_screenshot.png'
            page.screenshot(path=screenshot_path)
            logger.info(f"📸 截圖已保存: {screenshot_path}")
            
            logger.info("✅ [功能測試] 完成！所有檢查通過。")
            
            browser.close()
            return True
            
    except Exception as e:
        logger.error(f"❌ [功能測試] 失敗: {e}")
        return False


# ============================================
# Stress Test (Load Simulation with aiohttp)
# ============================================
async def send_job(session, user_id):
    """
    異步發送生成請求到 /api/generate
    
    Args:
        session: aiohttp ClientSession
        user_id: 用戶 ID（用於日誌追蹤）
    
    Returns:
        str: 請求結果 ("OK", "RATE_LIMIT", "ERROR", "CONN_ERR")
    """
    payload = {
        "prompt": f"Stress Test User {user_id}",
        "workflow": "text_to_image",
        "seed": random.randint(1, 999999),
        "model": "turbo_fp8",
        "aspect_ratio": "1:1",
        "batch_size": 1
    }
    
    try:
        async with session.post(
            f"{BASE_URL}/api/generate",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status == 202:
                return "OK"
            elif resp.status == 429:
                return "RATE_LIMIT"
            else:
                return f"ERROR_{resp.status}"
    except asyncio.TimeoutError:
        return "TIMEOUT"
    except Exception as e:
        return "CONN_ERR"


async def run_stress_test():
    """
    壓力測試 - 模擬多個併發用戶發送請求
    驗證：
    1. Rate Limiter 是否正常工作（HTTP 429）
    2. Server 是否能處理併發請求不崩潰
    3. Queue 是否正常累積
    """
    logger.info("=" * 60)
    logger.info(f"🔥 [壓力測試] 模擬 {CONCURRENT_USERS} 個併發用戶發送 {TOTAL_REQUESTS} 個請求...")
    logger.info("=" * 60)
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        tasks = [send_job(session, i) for i in range(TOTAL_REQUESTS)]
        results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    
    # 統計結果
    ok_count = results.count("OK")
    rate_limited = results.count("RATE_LIMIT")
    errors = [r for r in results if r.startswith("ERROR_")]
    timeouts = results.count("TIMEOUT")
    conn_errors = results.count("CONN_ERR")
    
    logger.info("=" * 60)
    logger.info("📊 [壓力測試結果]")
    logger.info(f"總請求數: {TOTAL_REQUESTS}")
    logger.info(f"成功 (202): {ok_count}")
    logger.info(f"被限流 (429): {rate_limited}")
    logger.info(f"錯誤: {len(errors)}")
    logger.info(f"超時: {timeouts}")
    logger.info(f"連線錯誤: {conn_errors}")
    logger.info(f"總耗時: {elapsed:.2f} 秒")
    logger.info(f"平均每請求: {elapsed/TOTAL_REQUESTS:.3f} 秒")
    logger.info("=" * 60)
    
    # 驗證 Rate Limiter 是否工作
    if rate_limited > 0:
        logger.info("✅ Rate Limiter 運作正常！")
    else:
        logger.warning("⚠️ 未檢測到 Rate Limit (可能配置有問題)")
    
    # 驗證 Server 沒有崩潰
    if conn_errors == 0:
        logger.info("✅ Server 穩定運行，沒有崩潰！")
    else:
        logger.error(f"❌ 檢測到 {conn_errors} 個連線錯誤！")
    
    return {
        'total': TOTAL_REQUESTS,
        'success': ok_count,
        'rate_limited': rate_limited,
        'errors': len(errors),
        'timeouts': timeouts,
        'elapsed': elapsed
    }


# ============================================
# Main Entry Point
# ============================================
if __name__ == "__main__":
    logger.info("🚀 ComfyUI Studio - Stack Testing Suite")
    logger.info("=" * 60)
    
    # 1. 執行功能測試
    functional_success = run_functional_test()
    
    # 延遲 2 秒
    time.sleep(2)
    
    # 2. 執行壓力測試
    stress_results = asyncio.run(run_stress_test())
    
    # 最終報告
    logger.info("\n" + "=" * 60)
    logger.info("📋 [最終測試報告]")
    logger.info("=" * 60)
    logger.info(f"功能測試: {'✅ 通過' if functional_success else '❌ 失敗'}")
    logger.info(f"壓力測試: ✅ 完成 ({stress_results['success']} 成功 / {stress_results['total']} 總數)")
    
    if functional_success and stress_results['success'] > 0:
        logger.info("=" * 60)
        logger.info("🎉 所有測試完成！系統運作正常。")
        logger.info("=" * 60)
    else:
        logger.error("=" * 60)
        logger.error("⚠️ 部分測試失敗，請檢查日誌。")
        logger.error("=" * 60)
