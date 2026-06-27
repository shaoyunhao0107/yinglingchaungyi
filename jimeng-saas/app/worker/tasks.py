"""Enqueue helpers. Web process uses these; the RQ worker imports app.worker.jobs."""
from __future__ import annotations

from typing import Literal

from app.worker.connection import get_queue
from app.worker.jobs import run_image_job, run_video_job


def enqueue_job(job_id: int, job_type: Literal["image", "video"]) -> None:
    q = get_queue()
    fn = run_video_job if job_type == "video" else run_image_job
    q.enqueue(fn, job_id, job_timeout=600, result_ttl=3600)
