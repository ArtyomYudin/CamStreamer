import logging, os
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logger = logging.getLogger('cam-streamer')
if not logger.handlers:
    handler = logging.StreamHandler()
    fmt = '[%(asctime)s] %(levelname)s: %(message)s'
    handler.setFormatter(logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(handler)
    logger.setLevel(LOG_LEVEL)