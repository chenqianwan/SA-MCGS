from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def setup_logger(config: dict) -> None:
    """根据配置初始化 loguru"""
    level = config.get("logging", {}).get("level", "INFO")
    save_path = config.get("logging", {}).get("save_path", "")

    logger.remove()
    logger.add(sys.stderr, level=level, format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    ))

    if save_path:
        log_dir = Path(save_path)
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "sa_mcgs_{time}.log",
            level=level,
            rotation="10 MB",
            retention="30 days",
        )
