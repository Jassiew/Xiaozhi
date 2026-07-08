import asyncio
import webbrowser
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import uvicorn
from config import API_PORT


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 表已在MySQL中建好，跳过init_db
    from ws_handler import frame_queue
    import ws_handler
    from analyzer import run_analyzer

    # 创建分析结果输出队列，用于推送 learning_status 到设备
    ws_handler.output_queue = asyncio.Queue(maxsize=100)
    broadcast_task = asyncio.create_task(ws_handler._broadcast_results())

    analyzer_task = asyncio.create_task(
        run_analyzer(frame_queue, ws_handler.output_queue)
    )

    webbrowser.open(f"http://localhost:{API_PORT}")
    yield

    analyzer_task.cancel()
    broadcast_task.cancel()
    try:
        await analyzer_task
    except asyncio.CancelledError:
        pass
    try:
        await broadcast_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="小智伴学 · 学生状态监测系统", lifespan=lifespan)

# 静态文件（管理端页面）
app.mount("/static", StaticFiles(directory="static"), name="static")

from ws_handler import router as ws_router
app.include_router(ws_router)

from api_router import router as api_router
app.include_router(api_router)

@app.get("/")
async def root():
    return RedirectResponse("/static/login.html")




if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
