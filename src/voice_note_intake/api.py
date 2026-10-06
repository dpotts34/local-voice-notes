from __future__ import annotations

import uuid
from dataclasses import asdict
from pathlib import PurePath

from aiohttp import web

from .config import Config
from .spool import EmptyUpload, UploadTooLarge, durable_unlink, spool_stream
from .store import Job, JobStore, SpoolIntegrityError

CONFIG_KEY = web.AppKey("config", Config)
STORE_KEY = web.AppKey("store", JobStore)
WAKE_KEY = web.AppKey("wake_worker", object)



def _uuid(value: str | None, *, generate: bool = False) -> str:
    if value is None and generate:
        return str(uuid.uuid4())
    if value is None:
        raise ValueError("missing UUID")
    parsed = uuid.UUID(value)
    if str(parsed) != value:
        raise ValueError("UUID must use canonical form")
    return value


def _job_json(job: Job, idempotent: bool = False) -> dict:
    data = asdict(job)
    data.pop("notification_nonce")
    data.pop("notification_summary")
    data.pop("note_sha256")
    data["idempotent"] = idempotent
    return data


def create_api(config: Config, store: JobStore) -> web.Application:
    app = web.Application(client_max_size=config.max_upload_bytes + 1024 * 1024)
    app[CONFIG_KEY] = config
    app[STORE_KEY] = store

    app.router.add_post("/v1/voice-notes", _upload)
    app.router.add_get("/v1/threads", _get_threads)
    app.router.add_get("/v1/jobs/{request_id}", _get_job)
    return app


async def _upload(request: web.Request) -> web.Response:
    if not request.content_type.startswith("multipart/"):
        raise web.HTTPBadRequest(text="multipart form required")
    config = request.app[CONFIG_KEY]
    store = request.app[STORE_KEY]
    reader = await request.multipart()
    request_id: str | None = None
    thread_id: str | None = None
    audio = None
    spooled = None
    supplied_filename = "recording"
    content_type = "application/octet-stream"
    try:
        while part := await reader.next():
            if part.name == "request_id":
                request_id = await part.text()
            elif part.name == "thread_id":
                thread_id = await part.text()
            elif part.name == "audio" and audio is None:
                audio = part
                supplied_filename = PurePath((part.filename or "recording").replace("\\", "/")).name[:255]
                content_type = part.headers.get("Content-Type", "application/octet-stream")[:255]

                async def chunks():
                    while chunk := await part.read_chunk(64 * 1024):
                        yield chunk

                try:
                    spooled = await spool_stream(
                        chunks(), config.state_dir / "spool", f".incoming-{uuid.uuid4()}.audio", config.max_upload_bytes
                    )
                except EmptyUpload:
                    raise web.HTTPBadRequest(text="audio is empty")
                except UploadTooLarge:
                    raise web.HTTPRequestEntityTooLarge(
                        max_size=config.max_upload_bytes, actual_size=config.max_upload_bytes + 1
                    )
    except BaseException:
        if spooled:
            durable_unlink(spooled.path)
        raise
    try:
        request_id = _uuid(request_id, generate=True)
        thread_id = _uuid(request_id if thread_id is None else thread_id)
    except (ValueError, AttributeError):
        if spooled:
            durable_unlink(spooled.path)
        raise web.HTTPBadRequest(text="request_id and thread_id must be canonical UUIDs")
    if audio is None or spooled is None:
        raise web.HTTPBadRequest(text="audio field required")
    final = config.state_dir / "spool" / f"{request_id}.audio"
    job = Job(
            request_id=request_id,
            thread_id=thread_id,
            sha256=spooled.sha256,
            original_filename=supplied_filename,
            stored_filename=final.name,
            content_type=content_type,
            byte_count=spooled.byte_count,
            spool_path=str(final),
    )
    try:
        try:
            saved, created = await __import__("asyncio").to_thread(
                store.install_spool_and_create, job, spooled.path, final
            )
        except SpoolIntegrityError as error:
            raise web.HTTPConflict(text=str(error))
    finally:
        durable_unlink(spooled.path)
    if created and (wake := request.app.get(WAKE_KEY)):
        wake()
    return web.json_response(_job_json(saved, not created), status=202)


async def _get_job(request: web.Request) -> web.Response:
    try:
        request_id = _uuid(request.match_info["request_id"])
    except ValueError:
        raise web.HTTPBadRequest(text="invalid request ID")
    job = request.app[STORE_KEY].get(request_id)
    if job is None:
        raise web.HTTPNotFound()
    return web.json_response(_job_json(job))


async def _get_threads(request: web.Request) -> web.Response:
    try:
        limit = int(request.query.get("limit", "10"))
    except ValueError:
        raise web.HTTPBadRequest(text="limit must be an integer from 1 to 20")
    if not 1 <= limit <= 20:
        raise web.HTTPBadRequest(text="limit must be an integer from 1 to 20")
    return web.json_response({"threads": request.app[STORE_KEY].recent_threads(limit)})
