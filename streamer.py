import asyncio
import subprocess
import logging
import os

logger = logging.getLogger(__name__)

class VideoStreamer:
    def __init__(self, name: str, rtsp_url: str, max_clients: int = 3):
        self.bitrate = '1000k'
        self.height = '480'
        self.width = '640'
        self.fps = '25'
        self.name = name
        self.rtsp_url = rtsp_url
        self.max_clients = max_clients
        self.clients = set()
        self._proc = None
        self._task = None
        self._running = False

    def _build_ffmpeg_cmd(self):
        return [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-i", self.rtsp_url,
            "-an",  # без аудио
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
            "-s", f"{self.width}x{self.height}",
            "-b:v", self.bitrate,
            "-bf", "0",
            "-f", "mpegts",
            "-fflags", "+genpts",
            "-mpegts_copyts", "1",  # для синхронизации
            "-"
        ]

    async def _read_stderr(self):
        if not self._proc or not self._proc.stderr:
            return
        while self._running and not self._proc.stderr.at_eof():
            try:
                line = await self._proc.stderr.readline()
                if not line:
                    break
                decoded = line.decode(errors='ignore').strip()
                if 'error' in decoded.lower():
                    logger.error(f"[{self.name}] FFmpeg error: {decoded}")
                elif 'warning' in decoded.lower():
                    logger.warning(f"[{self.name}] FFmpeg warning: {decoded}")
                else:
                    logger.debug(f"[{self.name}] FFmpeg: {decoded}")
            except Exception:
                break

    async def _broadcast(self, data: bytes):
        if not self.clients:
            return
        disconnected = set()
        for ws in self.clients:
            try:
                await ws.send_bytes(data)
            except Exception as e:
                logger.warning(f"Failed to send data to client: {e}")
                disconnected.add(ws)
        self.clients -= disconnected

    async def _run_ffmpeg(self):
        restart_delay = 3
        while self._running:
            if not self.clients:
                await self._stop_ffmpeg()
                while not self.clients and self._running:
                    await asyncio.sleep(0.5)
                if not self._running:
                    break

            try:
                cmd = self._build_ffmpeg_cmd()
                logger.info(f"[{self.name}] Запуск ffmpeg...")
                self._proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.DEVNULL
                )
                asyncio.create_task(self._read_stderr())

                while self._running and self.clients:
                    chunk = await self._proc.stdout.read(8192)
                    if not chunk:
                        break
                    await self._broadcast(chunk)

                returncode = await self._proc.wait()
                logger.warning(f"[{self.name}] ffmpeg завершился с кодом {returncode}")

            except Exception as e:
                logger.error(f"[{self.name}] Ошибка ffmpeg: {e}", exc_info=True)

            finally:
                await self._stop_ffmpeg()

            if self._running:
                logger.info(f"[{self.name}] Перезапуск через {restart_delay} сек...")
                await asyncio.sleep(restart_delay)

    async def _stop_ffmpeg(self):
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
            logger.info(f"[{self.name}] FFmpeg остановлен")

    async def start(self):
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._run_ffmpeg())
        logger.info(f"[{self.name}] Стример запущен")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        self.clients.clear()
        logger.info(f"[{self.name}] Стример остановлен")

    def add_client(self, ws):
        if len(self.clients) >= self.max_clients:
            logger.warning(f"[{self.name}] Достигнуто максимальное количество клиентов: {self.max_clients}")
            return False
        self.clients.add(ws)
        logger.info(f"[{self.name}] Новый клиент ({len(self.clients)})")
        return True

    def remove_client(self, ws):
        self.clients.discard(ws)
        logger.info(f"[{self.name}] Клиент отключён ({len(self.clients)})")