import asyncio
import os
from aiohttp import web
from app.streamer import VideoStreamer
import yaml

from app.logger import logger


# Настройка камер

with open("app/cameras.yaml") as f:
    config = yaml.safe_load(f)

CAMERAS = {}
NAMES = {}

for cam_id, data in config["cameras"].items():
    if data.get("enabled", True):
        CAMERAS[cam_id] = data["rtsp_url"]
        NAMES[cam_id] = data["name"]


MAX_CLIENTS_PER_CAMERA = 3

streamers = {}


async def websocket_handler(request):
    try:
        camera_id = request.match_info["camera_id"]
    except (ValueError, KeyError):
        return web.Response(status=400, text="Invalid camera ID")

    if camera_id not in CAMERAS:
        return web.Response(status=404, text="Camera not found")

    streamer = streamers.get(camera_id)
    if not streamer:
        return web.Response(status=500, text="Streamer not initialized")

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    added = await streamer.add_client(ws)
    if not added:
        await ws.close(code=1008, message=b"Too many clients")
        return ws

    try:
        async for msg in ws:
            # принимаем, но не обрабатываем — соединение живое
            if msg.type == web.WSMsgType.PING:
                await ws.pong()
    finally:
        await streamer.remove_client(ws)

    return ws


async def stats_handler(request):
    stats = {}
    for cam_id, streamer in streamers.items():
        url_safe = streamer.rtsp_url
        password = os.getenv('CAM_PASS')
        if password:
            url_safe = url_safe.replace(password, '***')

        stats[cam_id] = {
            "name": NAMES.get(cam_id, f"Camera {cam_id}"),
            "clients": len(streamer.clients),
            "running": streamer._running,
            "url": url_safe
        }
    return web.json_response(stats)


async def start_streamers_background():
    """Создаёт стримеры, но не запускает ffmpeg сразу (ленивый старт)"""
    await asyncio.sleep(1)
    for cam_id, url in CAMERAS.items():
        streamer = VideoStreamer(
            name=NAMES.get(cam_id, f"Camera {cam_id}"),
            rtsp_url=url,
            max_clients=MAX_CLIENTS_PER_CAMERA
        )
        streamers[cam_id] = streamer
        logger.info(f"[{streamer.name}] Зарегистрирован (lazy start)")


def init_app():
    app = web.Application()
    app.router.add_get('/ws/{camera_id}', websocket_handler)
    app.router.add_get('/stats', stats_handler)
    return app


if __name__ == "__main__":
    import uvloop
    uvloop.install()

    app = init_app()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    SERVER_PORT = int(os.getenv("SERVER_PORT", "80"))
    SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")

    runner = web.AppRunner(app)
    try:
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, SERVER_HOST, SERVER_PORT)
        loop.run_until_complete(site.start())
        logger.info(f"🌐 WebSocket сервер слушает ПОРТ {SERVER_PORT}")

        loop.create_task(start_streamers_background())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("🛑 Остановка сервера...")
    finally:
        async def cleanup():
            for s in streamers.values():
                await s.stop()
            await runner.cleanup()
        loop.run_until_complete(cleanup())
        loop.close()