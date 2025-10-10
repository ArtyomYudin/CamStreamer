import asyncio
import logging
import os
from aiohttp import web
from dotenv import load_dotenv
from streamer import VideoStreamer

load_dotenv()

logging.basicConfig(
    level=logging.INFO if not os.getenv("DEBUG") else logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("VideoServer")

# Настройка камер
CAMERAS = {
    9999: f"rtsp://{os.getenv('CAM_USER', 'video')}:{os.getenv('CAM_PASS', '123456')}@172.20.58.23:7070",
    # 9996: f"rtsp://{os.getenv('CAM_USER', 'video')}:{os.getenv('CAM_PASS', '123456')}@172.20.58.24:7070",
    # и т.д.
}

NAMES = {
    9999: "MainCam",
    # 9996: "BackCam",
}

MAX_CLIENTS_PER_CAMERA = 3

streamers = {}

async def websocket_handler(request):
    host = request.headers.get('Host', 'localhost:80')
    try:
        port = int(host.split(':')[-1])
    except ValueError:
        return web.Response(status=400, text="Invalid Host header")

    streamer = streamers.get(port)
    if not streamer:
        return web.Response(status=404, text="Stream not available")

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    if not streamer.add_client(ws):
        await ws.close(code=1008, message="Too many clients")
        return ws

    try:
        async for _ in ws:
            pass
    finally:
        streamer.remove_client(ws)

    return ws

async def stats_handler(request):
    stats = {}
    for port, streamer in streamers.items():
        stats[port] = {
            "name": NAMES[port],
            "clients": len(streamer.clients),
            "running": streamer._running,
            "url": streamer.rtsp_url.replace(os.getenv('CAM_PASS', ''), '***')  # скрыть пароль
        }
    return web.json_response(stats)

async def start_streamers_background():
    await asyncio.sleep(1)
    for port, url in CAMERAS.items():
        streamer = VideoStreamer(
            name=NAMES[port],
            rtsp_url=url,
            max_clients=MAX_CLIENTS_PER_CAMERA
        )
        streamers[port] = streamer
        await streamer.start()

def init_app():
    app = web.Application()
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/stats', stats_handler)
    return app

if __name__ == "__main__":
    import uvloop
    uvloop.install()

    app = init_app()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    runners = []
    try:
        for port in CAMERAS:
            runner = web.AppRunner(app)
            loop.run_until_complete(runner.setup())
            site = web.TCPSite(runner, "0.0.0.0", port)
            loop.run_until_complete(site.start())
            runners.append(runner)
            logger.info(f"🌐 WebSocket сервер слушает порт {port}")

        loop.create_task(start_streamers_background())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки...")
    finally:
        async def cleanup():
            for s in streamers.values():
                s.stop()
            for r in runners:
                await r.cleanup()
        loop.run_until_complete(cleanup())
        loop.close()