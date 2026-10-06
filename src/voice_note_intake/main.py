from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import AsyncIterator

from aiohttp import web

from .api import CONFIG_KEY, STORE_KEY, WAKE_KEY, create_api
from .clients import ExternalClients
from .config import Config
from .store import JobStore
from .mounts import archive_available
from .spool import open_private_directory, private_directory_available
from .worker import Worker
from .writer import InboxWriter
from .vault_sync import VaultSync

CLIENTS_KEY = web.AppKey("clients", ExternalClients)
WORKER_KEY = web.AppKey("worker", Worker)


def _path_available(path) -> bool:
    return path.is_dir() and os.access(path, os.R_OK | os.W_OK | os.X_OK)


async def _health(request: web.Request) -> web.Response:
    config = request.app[CONFIG_KEY]
    database_ok = request.app[STORE_KEY].is_operable()
    archive_ok, archive_details = archive_available(config.archive_dir, config.require_nfs_mount)
    try:
        inbox = InboxWriter(config)._inbox()
        inbox_ok = _path_available(inbox)
        inbox_error = None
    except (OSError, ValueError) as error:
        inbox_ok = False
        inbox_error = str(error)
    task = getattr(request.app[WORKER_KEY], "_task", None)
    worker_alive = task is not None and not task.done()
    paths = {
        "state": {"usable": private_directory_available(config.state_dir)},
        "spool": {"usable": private_directory_available(config.state_dir / "spool")},
        "archive": archive_details,
        "vault": {"usable": _path_available(config.vault_dir)},
        "inbox": {"usable": inbox_ok, "path": config.inbox.as_posix(), "error": inbox_error},
    }
    ready = (
        paths["state"]["usable"] and paths["spool"]["usable"]
        and archive_ok and paths["vault"]["usable"]
        and inbox_ok and database_ok and worker_alive
    )
    return web.json_response(
        {
            "ready": ready,
            "database": {"operable": database_ok},
            "paths": paths,
            "worker": {"alive": worker_alive},
            "dependencies": {
                "asr": {"configured": bool(config.asr_url), "reachable": "not_probed"},
                "llm": {"configured": bool(config.llm_url), "reachable": "not_probed"},
                "ntfy": {"configured": bool(config.ntfy_url), "reachable": "not_probed"},
            },
        },
        status=200 if ready else 503,
    )


async def _lifecycle(app: web.Application) -> AsyncIterator[None]:
    clients = app[CLIENTS_KEY]
    worker = app[WORKER_KEY]
    await clients.__aenter__()
    worker._task = asyncio.create_task(worker.run(), name="voice-note-worker")
    worker.wake()
    try:
        yield
    finally:
        worker.stop()
        worker._task.cancel()
        try:
            try:
                await worker._task
            except asyncio.CancelledError:
                pass
        finally:
            await clients.close()


def create_app(config: Config | None = None) -> web.Application:
    config = config or Config.from_env()
    syncer = VaultSync(config.vault_dir, config.state_dir, config.vault_repo_dir,
                       config.vault_remote, config.vault_branch, config.vault_git_ssh_key) if config.vault_sync else None
    for path, label in ((config.state_dir, "state"), (config.state_dir / "spool", "spool")):
        os.close(open_private_directory(path, create=True, label=label))
    store = JobStore(config.state_dir / "jobs.sqlite3")
    app = create_api(config, store)
    clients = ExternalClients(config)
    worker = Worker(config, store, clients, InboxWriter(config), syncer)
    app[CLIENTS_KEY] = clients
    app[WORKER_KEY] = worker
    app[WAKE_KEY] = worker.wake
    app.router.add_get("/health", _health)
    app.cleanup_ctx.append(_lifecycle)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Durable voice-note intake service")
    parser.add_argument("--host", help="override configured bind host")
    parser.add_argument("--port", type=int, help="override configured bind port")
    args = parser.parse_args()
    try:
        config = Config.from_env()
    except ValueError as error:
        parser.error(str(error))
    web.run_app(create_app(config), host=args.host or config.bind_host, port=args.port or config.bind_port)


if __name__ == "__main__":
    main()
