# app/jobs/arq_worker.py
from __future__ import annotations

import os
import sys
import logging
from arq.connections import RedisSettings

from app.jobs.epmc_tasks import build_epmc_cursors
from app.jobs.export_tasks import run_export_job

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
LOG_LEVEL = (os.getenv("LOG_LEVEL") or "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    stream=sys.stdout,
    format="%(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("litsearch.arq_worker")
logger.info("ARQ worker logging initialized level=%s redis=%s", LOG_LEVEL, REDIS_URL)


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(REDIS_URL)

    functions = [
        build_epmc_cursors,
        run_export_job,
    ]

    max_jobs = int(os.getenv("ARQ_MAX_JOBS", "8"))
    job_timeout = int(os.getenv("ARQ_JOB_TIMEOUT", "900"))