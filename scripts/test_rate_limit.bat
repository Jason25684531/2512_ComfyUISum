@echo off
chcp 65001 >nul
echo ============================================
echo   Rate Limiting Test
echo ============================================
echo.
echo Testing /api/metrics endpoint...
echo Sending 20 requests in 5 seconds...
echo.

set success=0
set failed=0

for /L %%i in (1,1,20) do (
    curl -s -o nul -w "Request %%i: HTTP %%{http_code}\n" http://localhost:5000/api/metrics
    if !errorlevel! equ 0 (
        set /a success+=1
    ) else (
        set /a failed+=1
    )
    timeout /t 0 /nobreak >nul
)

echo.
echo ============================================
echo   Test Results
echo ============================================
echo   Total Requests: 20
echo   Successful: %success%
echo   Failed: %failed%
echo.
echo Expected Result:
echo   - All 20 requests should succeed (HTTP 200)
echo   - No 429 errors
echo.
echo Old Limit: 10 per minute (would fail)
echo New Limit: 2 per second = 120 per minute (should pass)
echo.
pause
