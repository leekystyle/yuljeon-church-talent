import os
import uvicorn
from app.main import app

# Cloudtype 기본 실행 명령(uvicorn main:app) 호환 진입점
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
