import asyncio
from app.logger import logger


class VideoStreamer:
    def __init__(self, name: str, rtsp_url: str, max_clients: int = 3):
        self.name = name
        self.rtsp_url = rtsp_url
        self.max_clients = max_clients
        self.clients = set()

        # Параметры перекодирования по умолчанию
        self.default_width = 1280
        self.default_height = 960
        self.default_fps = 25
        self.bitrate = '1000k'

        # Процесс и задачи
        self._proc = None
        self._stderr_task = None
        self._stdout_task = None
        self._monitor_task = None
        self._running = False
        self._start_lock = asyncio.Lock()

        # Перезапуски
        self._restart_count = 0
        self._max_restarts = 3

    # ===========================
    # Формируем команду ffmpeg (всегда перекодируем)
    # ===========================

    def _build_ffmpeg_cmd(self):
        return [
            "ffmpeg",
            "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-timeout", "30000000",          # 30 сек в микросекундах
            "-probesize", "32768",
            "-analyzeduration", "500000",
            "-fflags", "+nobuffer+flush_packets",
            "-i", self.rtsp_url,
            "-an",                           # без аудио
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            # "-profile:v", "baseline",        # совместимость с браузерами
            # "-level", "3.1",
            "-pix_fmt", "yuv420p",
            "-r", str(self.default_fps),     # всегда используем default_fps
            "-s", f"{self.default_width}x{self.default_height}",
            "-b:v", self.bitrate,
            "-g", str(self.default_fps * 2), # ключевые кадры каждые 2 сек
            "-bf", "0",                      # без B-кадров
            "-f", "mpegts",
            "-fflags", "+genpts",
            "-mpegts_copyts", "1",
            "-"
        ]


    async def _read_stdout_and_send(self):
        if not self._proc or not self._proc.stdout:
            return
        try:
            while self._running:
                # Читаем порциями (MPEG-TS пакет = 188 байт, но можно брать больше для эффективности)
                chunk = await self._proc.stdout.read(1024 * 8)  # 8 КБ
                if not chunk:
                    break
                # Отправляем всем клиентам
                disconnected = set()
                for ws in self.clients:
                    try:
                        await ws.send_bytes(chunk)
                    except Exception:
                        disconnected.add(ws)
                # Удаляем отвалившихся клиентов
                for ws in disconnected:
                    self.clients.discard(ws)
                    logger.info(f"[{self.name}] Клиент отключён при отправке ({len(self.clients)})")
        except Exception as e:
            logger.debug(f"[{self.name}] _read_stdout_and_send завершён: {e}")


    # ===========================
    # Чтение stderr для логов
    # ===========================

    async def _read_stderr(self):
        if not self._proc or not self._proc.stderr:
            return
        try:
            while self._running:
                try:
                    line = await asyncio.wait_for(self._proc.stderr.readline(), timeout=1.0)
                    if not line:
                        break
                    decoded = line.decode(errors='ignore').strip()
                    if not decoded:
                        continue
                    if 'error' in decoded.lower():
                        logger.error(f"[{self.name}] FFmpeg error: {decoded}")
                    elif 'warning' in decoded.lower():
                        logger.warning(f"[{self.name}] FFmpeg warning: {decoded}")
                    else:
                        logger.debug(f"[{self.name}] FFmpeg: {decoded}")
                except asyncio.TimeoutError:
                    continue
        except Exception as e:
            logger.debug(f"[{self.name}] _read_stderr завершён: {e}")

    # ===========================
    # Мониторинг процесса
    # ===========================

    async def _monitor_process(self):
        try:
            retcode = await self._proc.wait()
            if retcode != 0 and self._running:
                # Прочитаем остаток stderr для диагностики
                remaining = await self._proc.stderr.read()
                if remaining:
                    err_msg = remaining.decode(errors='ignore').strip()
                    logger.error(f"[{self.name}] FFmpeg stderr после падения:\n{err_msg}")

                self._restart_count += 1
                if self._restart_count <= self._max_restarts:
                    logger.warning(f"[{self.name}] ffmpeg завершился с кодом {retcode}, перезапуск ({self._restart_count}/{self._max_restarts})...")
                    self._proc = None
                    await asyncio.sleep(3)
                    await self.start()
                else:
                    logger.error(f"[{self.name}] Достигнут лимит перезапусков ({self._max_restarts}). Остановка стримера.")
                    await self.stop()
            else:
                logger.info(f"[{self.name}] ffmpeg завершился корректно")
                self._proc = None
                self._running = False
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка при мониторинге ffmpeg: {e}")
            await self.stop()

    # ===========================
    # Запуск ffmpeg
    # ===========================

    async def start(self):
        async with self._start_lock:
            if self._running or not self.clients:
                return

            self._running = True
            cmd = self._build_ffmpeg_cmd()
            logger.info(f"[{self.name}] ▶️ Запуск ffmpeg")

            try:
                self._proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                self._stderr_task = asyncio.create_task(self._read_stderr())
                self._monitor_task = asyncio.create_task(self._monitor_process())
                self._stdout_task = asyncio.create_task(self._read_stdout_and_send())
            except Exception as e:
                logger.error(f"[{self.name}] Не удалось запустить ffmpeg: {e}")
                self._running = False
                self._proc = None

    # ===========================
    # Остановка ffmpeg
    # ===========================

    async def stop(self):
        self._running = False
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        self._proc = None

        # Отменяем задачи
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
        if self._stdout_task and not self._stdout_task.done():
            self._stdout_task.cancel()

        self.clients.clear()
        self._restart_count = 0  # сброс счётчика при остановке
        logger.info(f"[{self.name}] Стример остановлен")

    # ===========================
    # Добавление/удаление клиента
    # ===========================

    async def add_client(self, ws):
        if len(self.clients) >= self.max_clients:
            return False
        self.clients.add(ws)
        logger.info(f"[{self.name}] Новый клиент ({len(self.clients)})")
        await self.start()
        return True

    async def remove_client(self, ws):
        self.clients.discard(ws)
        logger.info(f"[{self.name}] Клиент отключён ({len(self.clients)})")
        if not self.clients:
            await self.stop()