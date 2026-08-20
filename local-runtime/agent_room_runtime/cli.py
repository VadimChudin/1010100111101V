from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .config import RuntimeConfig
from .runtime import LocalRuntime
from .serena import SerenaLaunchSpec


def load_runtime(config_path: str) -> LocalRuntime:
    return LocalRuntime(RuntimeConfig.load(config_path))


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent-room-runtime", description="Local-first Agent Room runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a local runtime configuration")
    init.add_argument("--cloud-url", required=True)
    init.add_argument("--project-id", required=True)
    init.add_argument("--workspace-root", required=True)
    init.add_argument("--state-dir", required=True)
    init.add_argument("--device-name", default="Local Agent Room Runtime")

    register = subparsers.add_parser("register", help="Consume a one-time pairing token")
    register.add_argument("--config", required=True)
    register.add_argument("--pairing-token", required=True)

    sync = subparsers.add_parser("sync-once", help="Synchronize the durable local outbox with cloud")
    sync.add_argument("--config", required=True)

    serve = subparsers.add_parser("serve", help="Run automatic outbox synchronization with reconnect backoff")
    serve.add_argument("--config", required=True)
    serve.add_argument("--interval-seconds", type=float, default=10.0)

    serena = subparsers.add_parser("serena-command", help="Print hardened local-only Serena launch command")
    serena.add_argument("--config", required=True)
    serena.add_argument("--port", type=int, default=9121)

    arguments = parser.parse_args()
    if arguments.command == "init":
        config = RuntimeConfig(
            cloud_url=arguments.cloud_url,
            project_id=arguments.project_id,
            workspace_root=str(Path(arguments.workspace_root).resolve()),
            state_dir=str(Path(arguments.state_dir).resolve()),
            device_name=arguments.device_name,
        )
        config.save()
        print(config.config_path)
        return
    if arguments.command == "register":
        print(json.dumps(asyncio.run(load_runtime(arguments.config).register(arguments.pairing_token)), indent=2))
        return
    if arguments.command == "sync-once":
        print(json.dumps(asyncio.run(load_runtime(arguments.config).sync_once()), indent=2))
        return
    if arguments.command == "serve":
        asyncio.run(load_runtime(arguments.config).sync_forever(arguments.interval_seconds))
        return
    if arguments.command == "serena-command":
        config = RuntimeConfig.load(arguments.config)
        print(" ".join(SerenaLaunchSpec(config.workspace_root, arguments.port).command()))


if __name__ == "__main__":
    main()
