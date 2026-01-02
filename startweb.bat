@echo off
echo Starting Web Server on port 8000...
cd frontend
python -m http.server 8000
pause