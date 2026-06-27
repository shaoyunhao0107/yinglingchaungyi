"""RQ job entry points. Sync interface (RQ runs in its own worker process)."""
from __future__ import annotations

import asyncio
import json
import traceback
from datetime import datetime

from sqlmodel import Session, select

from app.database import session_scope
from app.models import Artifact, GenerationJob, ProviderCredential
from app.providers import get_provider
from app.providers.base import ProviderError
from app.services import (
    acquire_credential, sessionid_plain, mark_used, mark_exhausted,
    download_and_store, StorageError, debit, cost_for,
    publish_sync, CredentialExhausted,
)
from app.schemas.job import JobOut


def _set_status(session: Session, job: GenerationJob, status: str, **fields) -> None:
    job.status = status
    for k, v in fields.items():
        if hasattr(job, k):
            setattr(job, k, v)
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.flush()


def _publish(job: GenerationJob, session: Session) -> None:
    """SSE push current job state + artifact briefs."""
    arts = session.exec(
        select(Artifact).where(Artifact.job_id == job.id).where(Artifact.deleted_at.is_(None))
    ).all()
    publish_sync(job.user_id, "job.update", JobOut.from_job(job, arts).model_dump(mode="json"))


def run_image_job(job_id: int) -> None:
    """RQ entry: image generation. Reads job, calls provider, stores artifacts, debits."""
    with session_scope() as session:
        job = session.get(GenerationJob, job_id)
        if job is None:
            return
        if job.status in ("succeeded", "failed", "cancelled"):
            return

        _set_status(session, job, "running", started_at=datetime.utcnow())
        _publish(job, session)

        cost = cost_for(job.job_type)
        attempts = 0
        max_attempts = 3
        last_error = ""

        # image_api_* providers 不需要凭证池（凭证池是即梦专用），直接用 api_key
        if job.provider_name and job.provider_name.startswith("image_api_"):
            try:
                provider = get_provider(job.provider_name)
                params = json.loads(job.params_json) if job.params_json else {}
                results = asyncio.run(provider.generate_images(
                    prompt=job.prompt,
                    params=params,
                    sessionid="",
                    region="",
                ))
            except Exception as e:
                last_error = f'{type(e).__name__}: {e}'
                results = []
            if results:
                stored = []
                for gen in results:
                    try:
                        meta = download_and_store(gen.source_url, kind="image", user_id=job.user_id)
                        a = Artifact(
                            user_id=job.user_id, job_id=job.id, kind="image",
                            **meta,
                        )
                        session.add(a); stored.append(a)
                    except Exception as ex:
                        last_error = f'存储失败: {ex}'
                if stored:
                    debit(session, job.user_id, cost, job_id=job.id, job_type=job.job_type)
                    job.status = "succeeded"
                    job.completed_at = datetime.utcnow()
                    job.variation_count = len(stored)
                    _publish(job, session)
                    return
            _set_status(session, job, "failed", completed_at=datetime.utcnow(), error_message=last_error or "未知错误")
            _publish(job, session)
            return

        # 以下走即梦的凭证池模式
        while attempts < max_attempts:
            attempts += 1
            try:
                cred = acquire_credential(session, provider=job.provider_name)
            except CredentialExhausted as e:
                last_error = str(e)
                break

            try:
                plaintext = sessionid_plain(session, cred)
                provider = get_provider(job.provider_name)
                params = json.loads(job.params_json) if job.params_json else {}
                results = asyncio.run(provider.generate_images(
                    prompt=job.prompt,
                    params=params,
                    sessionid=plaintext,
                    region=cred.region,
                ))
                # Persist artifacts (download + re-encode).
                stored: list[Artifact] = []
                for gen in results:
                    try:
                        meta = download_and_store(
                            source_url=gen.source_url,
                            user_id=job.user_id,
                            kind="image",
                        )
                    except StorageError as e:
                        # Don't fail the whole job for one bad URL; record + continue.
                        last_error = str(e)
                        continue
                    art = Artifact(
                        job_id=job.id, user_id=job.user_id, kind="image",
                        storage_url=meta["storage_url"],
                        source_url=gen.source_url,
                        thumbnail_url=meta["thumbnail_url"],
                        width=meta["width"] or gen.width,
                        height=meta["height"] or gen.height,
                        bytes_size=meta["bytes_size"],
                        content_hash=meta["content_hash"],
                    )
                    session.add(art)
                    stored.append(art)
                session.flush()

                if not stored:
                    raise ProviderError("所有生成的图片都下载失败", kind="upstream")

                mark_used(session, cred)
                debit(session, job.user_id, cost, job_id=job.id, job_type=job.job_type)
                _set_status(session, job, "succeeded",
                            completed_at=datetime.utcnow(),
                            variation_count=len(stored),
                            credential_id_used=cred.id)
                _publish(job, session)
                return  # done

            except ProviderError as e:
                last_error = str(e)
                if e.kind == "auth":
                    mark_exhausted(session, cred, reason=str(e))
                    continue  # try another credential
                if e.kind == "rate_limit":
                    # 高峰期限流：等待 20s 再重试，避免立刻又撞限流
                    import time as _t
                    _t.sleep(20)
                    mark_used(session, cred)
                    continue
                # timeout / upstream / parse: retry on a different credential
                mark_used(session, cred)
                continue

            except Exception as e:  # noqa
                last_error = f"{type(e).__name__}: {e}"
                traceback.print_exc()
                break

        # All retries exhausted.
        _set_status(session, job, "failed",
                    completed_at=datetime.utcnow(),
                    error_message=last_error or "未知错误")
        _publish(job, session)


def run_video_job(job_id: int) -> None:
    """RQ entry: video generation. Same shape as image, longer timeout budget."""
    with session_scope() as session:
        job = session.get(GenerationJob, job_id)
        if job is None:
            return
        if job.status in ("succeeded", "failed", "cancelled"):
            return

        _set_status(session, job, "running", started_at=datetime.utcnow())
        _publish(job, session)

        cost = cost_for(job.job_type)
        attempts = 0
        max_attempts = 3
        last_error = ""

        while attempts < max_attempts:
            attempts += 1
            try:
                cred = acquire_credential(session, provider=job.provider_name)
            except CredentialExhausted as e:
                last_error = str(e)
                break

            try:
                plaintext = sessionid_plain(session, cred)
                provider = get_provider(job.provider_name)
                params = json.loads(job.params_json) if job.params_json else {}
                results = asyncio.run(provider.generate_videos(
                    prompt=job.prompt,
                    params=params,
                    sessionid=plaintext,
                    region=cred.region,
                ))
                stored: list[Artifact] = []
                for gen in results:
                    try:
                        meta = download_and_store(
                            source_url=gen.source_url,
                            user_id=job.user_id,
                            kind="video",
                        )
                    except StorageError as e:
                        last_error = str(e)
                        continue
                    art = Artifact(
                        job_id=job.id, user_id=job.user_id, kind="video",
                        storage_url=meta["storage_url"],
                        source_url=gen.source_url,
                        duration_secs=gen.duration_secs,
                        bytes_size=meta["bytes_size"],
                        content_hash=meta["content_hash"],
                    )
                    session.add(art)
                    stored.append(art)
                session.flush()

                if not stored:
                    raise ProviderError("所有生成的视频都下载失败", kind="upstream")

                mark_used(session, cred)
                debit(session, job.user_id, cost, job_id=job.id, job_type=job.job_type)
                _set_status(session, job, "succeeded",
                            completed_at=datetime.utcnow(),
                            variation_count=len(stored),
                            credential_id_used=cred.id)
                _publish(job, session)
                return

            except ProviderError as e:
                last_error = str(e)
                if e.kind == "auth":
                    mark_exhausted(session, cred, reason=str(e))
                    continue
                if e.kind == "rate_limit":
                    import time as _t
                    _t.sleep(30)  # 视频高峰期等待更久
                    mark_used(session, cred)
                    continue
                mark_used(session, cred)
                continue

            except Exception as e:  # noqa
                last_error = f"{type(e).__name__}: {e}"
                traceback.print_exc()
                break

        _set_status(session, job, "failed",
                    completed_at=datetime.utcnow(),
                    error_message=last_error or "未知错误")
        _publish(job, session)
