"""Local-only Supabase/PostgreSQL and real-browser gate support (never skip)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
from threading import Thread
import time
from urllib.parse import urlparse
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
CLI_VERSION = "2.116.0"


def executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"Required executable is missing: {name}; gate cannot be skipped")
    return path


def redact(output: str) -> str:
    output = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[local JWT redacted]", output)
    output = re.sub(r"sb_secret_[A-Za-z0-9_-]+", "[local secret redacted]", output)
    output = re.sub(r"(postgres(?:ql)?://[^:\s]+:)[^@\s]+@", r"\1[redacted]@", output)
    return re.sub(
        r"((?:JWT_SECRET|SECRET_KEY|S3_PROTOCOL_ACCESS_KEY_SECRET|secret key)[\"']?\s*[:=]\s*[\"']?)[^\s,\"'}]+",
        r"\1[redacted]", output, flags=re.IGNORECASE,
    )


def run(
    command: Sequence[str], *, cwd: Path = ROOT,
    env: Mapping[str, str] | None = None, input_text: str | None = None,
    capture: bool = False,
) -> str:
    print(f"  $ {shlex.join(command)}", flush=True)
    result = subprocess.run(
        command, cwd=cwd, env=env, input=input_text,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.stderr.strip():
        print(redact(result.stderr.rstrip()), flush=True)
    if result.stdout.strip() and not capture:
        print(redact(result.stdout.rstrip()), flush=True)
    if result.returncode != 0:
        if capture:
            print(redact(result.stdout.rstrip()), flush=True)
        raise RuntimeError(f"Gate command exited with code {result.returncode}: {shlex.join(command)}")
    print("  EXIT CODE 0", flush=True)
    return result.stdout


def running_environment() -> dict[str, str]:
    supabase = executable("supabase")
    version = run([supabase, "--version"], capture=True).strip()
    if version != CLI_VERSION:
        raise RuntimeError(f"Supabase CLI must be {CLI_VERSION}; found {version}")
    status = json.loads(run([supabase, "status", "-o", "json"], capture=True))
    required = ("API_URL", "ANON_KEY", "SERVICE_ROLE_KEY", "DB_URL", "MAILPIT_URL")
    if any(not isinstance(status.get(key), str) or not status[key] for key in required):
        raise RuntimeError("Running Supabase stack did not report every required local endpoint/key")
    for key in ("API_URL", "DB_URL", "MAILPIT_URL"):
        if urlparse(status[key]).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError(f"Real gate fixtures may only target localhost: {key}")
    result = dict(os.environ)
    result.update({
        "PYTHONUTF8": "1",
        "SUPABASE_URL": status["API_URL"],
        "SUPABASE_ANON_KEY": status["ANON_KEY"],
        "SUPABASE_SERVICE_ROLE_KEY": status["SERVICE_ROLE_KEY"],
        "DATABASE_URL": status["DB_URL"],
        "MAILPIT_URL": status["MAILPIT_URL"],
        "SUPABASE_JWT_VERIFY_MODE": "auth_server",
        "CORS_ALLOWED_ORIGINS": "http://127.0.0.1:5173",
        "DJANGO_URL": "http://127.0.0.1:8000",
        "VITE_SUPABASE_URL": status["API_URL"],
        "VITE_SUPABASE_ANON_KEY": status["ANON_KEY"],
    })
    # Real auth gates never send telemetry to an external account.
    result.pop("VITE_POSTHOG_KEY", None)
    result.pop("VITE_POSTHOG_HOST", None)
    result.pop("NO_COLOR", None)
    result["FORCE_COLOR"] = "0"
    if os.name == "nt":
        dlls = Path("C:/msys64/ucrt64/bin")
        if dlls.is_dir():
            result.setdefault("WEASYPRINT_DLL_DIRECTORIES", str(dlls))
    return result


def start_clean_stack() -> dict[str, str]:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    docker = executable("docker")
    supabase = executable("supabase")
    run([docker, "info", "--format", "{{.ServerVersion}} {{.OSType}}"])
    version = run([supabase, "--version"], capture=True).strip()
    if version != CLI_VERSION:
        raise RuntimeError(f"Supabase CLI must be exactly {CLI_VERSION}; found {version}")
    started = False
    try:
        run([supabase, "start"])
        started = True
        run([supabase, "db", "reset", "--local"])
        return running_environment()
    except BaseException:
        if started:
            try:
                stop_stack()
            except Exception as error:  # never mask the original startup failure
                print(f"  warning: could not stop partially started stack: {error}", flush=True)
        raise


def stop_stack() -> None:
    run([executable("supabase"), "stop", "--no-backup"])


def require_mailpit(env: Mapping[str, str]) -> None:
    response = httpx.get(f"{env['MAILPIT_URL']}/readyz", timeout=10)
    if response.status_code != 200:
        raise RuntimeError(f"Mailpit /readyz failed: HTTP {response.status_code}")
    print("  Mailpit GET /readyz: HTTP 200", flush=True)


def _free_port(port: int) -> None:
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"Port {port} is occupied; gate will not reuse an unknown server")


def _wait_for_server(process: subprocess.Popen[str], url: str) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Gate server exited before readiness: {url}")
        try:
            response = httpx.get(url, timeout=2)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Gate server readiness timed out: {url}")


def run_auth_e2e(env: Mapping[str, str], *test_args: str) -> None:
    require_mailpit(env)
    _free_port(8000)
    _free_port(5173)
    node = executable("node")
    backend_env = dict(env)
    # Proveedor Flow simulado: el portal de cotización ejerce el cobro
    # completo (CTA → checkout simulado → retorno) sin red real. El
    # retorno del pagador apunta al mismo origen que sirve Vite.
    backend_env["FLOW_WS_MOCK"] = "1"
    backend_env.setdefault("FRONTEND_ORIGIN", "http://127.0.0.1:5173")
    backend_env.setdefault("BILLING_FRONTEND_ORIGIN", "http://127.0.0.1:5173")
    frontend_env = {
        key: value for key, value in env.items()
        if key not in {"DATABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SECRET_KEY", "JWT_SECRET"}
    }
    commands = [
        ([sys.executable, "backend/manage.py", "runserver", "127.0.0.1:8000", "--noreload"], ROOT, backend_env),
        ([node, "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--strictPort"], FRONTEND, frontend_env),
        # Durable-job worker — app flows that enqueue jobs (document
        # generation, optimization) deadlock in e2e without it.
        ([sys.executable, "backend/manage.py", "runjobs", "--poll", "0.5"], ROOT, backend_env),
    ]
    processes: list[subprocess.Popen[str]] = []
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    logs: list[list[str]] = []
    readers: list[Thread] = []
    try:
        for command, cwd, process_env in commands:
            process = subprocess.Popen(
                command, cwd=cwd, env=process_env, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                creationflags=flags,
            )
            processes.append(process)
            assert process.stdout is not None
            lines: list[str] = []
            logs.append(lines)
            reader = Thread(target=lines.extend, args=(process.stdout,), daemon=True)
            reader.start()
            readers.append(reader)
        _wait_for_server(processes[0], "http://127.0.0.1:8000/api/schema/")
        _wait_for_server(processes[1], "http://127.0.0.1:5173/login")
        run(
            [node, "node_modules/@playwright/test/cli.js", "test", *test_args],
            cwd=FRONTEND, env=env,
        )
    except BaseException:
        for lines in logs:
            print(redact("".join(lines)), flush=True)
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        for reader in readers:
            reader.join(timeout=10)
            if reader.is_alive():
                raise RuntimeError("Gate server output did not close during teardown")
        for process in processes:
            if process.stdout is not None:
                process.stdout.close()
        _free_port(8000)
        _free_port(5173)
        print("  E2E teardown: backend/frontend stopped, logs closed, ports 8000/5173 free", flush=True)


def verify_postgres16() -> None:
    docker = executable("docker")
    container = os.environ.get("POSTGRES16_CONTAINER")
    owned = container is None
    if owned:
        container = f"dekopen-pg16-{uuid4().hex}"
        run([
            docker, "run", "--detach", "--name", container,
            "--env", "POSTGRES_PASSWORD=postgres", "postgres:16-alpine",
        ])
    assert container is not None
    try:
        deadline = time.monotonic() + 60
        while True:
            server_ready = True
            if owned:
                server = subprocess.run(
                    [docker, "exec", container, "cat", "/proc/1/comm"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
                    text=True,
                )
                server_ready = server.returncode == 0 and server.stdout.strip() == "postgres"
            result = subprocess.run(
                [docker, "exec", container, "pg_isready", "-U", "postgres", "-d", "postgres"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            if server_ready and result.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Independent PostgreSQL 16 container did not become ready")
            time.sleep(0.5)
        paths = [
            ROOT / "supabase/compat/postgres16_bootstrap.sql",
            *sorted((ROOT / "supabase/migrations").glob("*.sql")),
            ROOT / "supabase/seed.sql",
            ROOT / "supabase/compat/postgres16_verify.sql",
        ]
        for path in paths:
            print(f"  PostgreSQL 16 applies {path.relative_to(ROOT).as_posix()}", flush=True)
            run(
                [docker, "exec", "-i", container, "psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "postgres"],
                input_text=path.read_text(encoding="utf-8"),
            )
        import check_documentary_upgrade
        import check_migration_upgrades
        import check_pricing_upgrade

        check_migration_upgrades.verify(container)
        check_pricing_upgrade.verify(container)
        check_documentary_upgrade.verify(container)
    finally:
        if owned:
            run([docker, "rm", "--force", container])
