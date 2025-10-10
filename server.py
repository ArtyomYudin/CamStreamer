import asyncio
import logging
from aiohttp import web
from streamer import VideoStreamer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VideoServer")

# Настройка камер
CAMERAS = {
    9999: "rtsp://video:123456@172.20.58.23:7070",
    # 9996: "rtsp://video:123456@172.20.58.24:7070",
    # 9997: "rtsp://video:123456@172.20.58.28:7070",
    # 9998: "rtsp://video:123456@172.20.58.29:7070"",
}

NAMES = {
    9999: "MainCam",
    # 9996: "BackCam",
    # 9997: "ServerRoom1",
    # 9998: "ServerRoom2",
}

streamers = {}

async def websocket_handler(request):
    host = request.headers.get('Host', 'localhost:80')
    try:
        port = int(host.split(':')[-1])
    except:
        return web.Response(status=400, text="Invalid Host header")

    streamer = streamers.get(port)
    if not streamer:
        return web.Response(status=404, text="Stream not available")

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    streamer.add_client(ws)

    try:
        async for _ in ws:
            pass
    finally:
        streamer.remove_client(ws)

    return ws

async def start_streamers_background():
    await asyncio.sleep(1)
    for port, url in CAMERAS.items():
        streamer = VideoStreamer(name=NAMES[port], rtsp_url=url)
        streamers[port] = streamer
        await streamer.start()

def init_app():
    app = web.Application()
    app.router.add_get('/ws', websocket_handler)
    return app

if __name__ == "__main__":
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
        pass
    finally:
        async def cleanup():
            for s in streamers.values():
                s.stop()
            for r in runners:
                await r.cleanup()
        loop.run_until_complete(cleanup())
        loop.close()