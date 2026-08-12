"""Connected-instance discovery for local ComfyUI and Comfy Desktop.

The ComfyUI API exposes the process argv but not the process id, supervisor,
or Desktop installation metadata.  This module combines the API response with
read-only local process and Comfy Desktop registry inspection.  Every local
filesystem/process probe is optional and fails gracefully for remote hosts.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import Context

from comfy_mcp.server import mcp


def _client(ctx: Context):
    return ctx.request_context.lifespan_context["comfy_client"]


def _is_local_url(base_url: str) -> bool:
    """Return True only for loopback ComfyUI URLs."""
    try:
        host = (urlparse(base_url).hostname or "").strip().lower()
    except Exception:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _url_port(base_url: str) -> int | None:
    try:
        parsed = urlparse(base_url)
        if parsed.port is not None:
            return parsed.port
        return 443 if parsed.scheme == "https" else 80
    except (TypeError, ValueError):
        return None


def _argv_options(argv: list[Any]) -> tuple[dict[str, Any], list[str]]:
    """Parse ``--key value``/``--key=value`` options without argparse."""
    args = [str(value) for value in argv]
    options: dict[str, Any] = {}
    positional: list[str] = []
    index = 0
    while index < len(args):
        value = args[index]
        if not value.startswith("--"):
            positional.append(value)
            index += 1
            continue
        if "=" in value:
            key, option_value = value.split("=", 1)
            options[key] = option_value
            index += 1
            continue
        if index + 1 < len(args) and not args[index + 1].startswith("--"):
            options[value] = args[index + 1]
            index += 2
        else:
            options[value] = True
            index += 1
    return options, positional


def _normalise_path(value: Any) -> str | None:
    if value is None or value is True:
        return None
    text = str(value).strip().strip('"')
    if not text:
        return None
    return str(Path(text).expanduser())


def _path_record(value: str | None, source: str) -> dict[str, Any] | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return {"path": str(path), "source": source, "exists": path.exists()}


def _desktop_registry_path() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Comfy Desktop" / "installations.json"
    if sys.platform.startswith("win"):
        return Path.home() / "AppData" / "Roaming" / "Comfy Desktop" / "installations.json"
    return None


def _read_desktop_installations() -> tuple[list[dict[str, Any]], str | None]:
    path = _desktop_registry_path()
    if path is None or not path.is_file():
        return [], None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return [], str(path)
    if not isinstance(value, list):
        return [], str(path)
    return [item for item in value if isinstance(item, dict)], str(path)


def _same_path(left: Any, right: Any) -> bool:
    if not left or not right:
        return False
    try:
        return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
            os.path.abspath(str(right))
        )
    except Exception:
        return False


def _match_desktop_installation(
    installations: list[dict[str, Any]],
    *,
    options: dict[str, Any],
    port: int | None,
) -> dict[str, Any] | None:
    base_dir = options.get("--base-directory")
    input_dir = options.get("--input-directory")
    output_dir = options.get("--output-directory")
    best: tuple[int, dict[str, Any]] | None = None
    for item in installations:
        if item.get("sourceId") == "cloud" or not item.get("installPath"):
            continue
        score = 0
        if _same_path(base_dir, item.get("adoptedBaseDir")):
            score += 8
        if _same_path(input_dir, item.get("inputDir")):
            score += 3
        if _same_path(output_dir, item.get("outputDir")):
            score += 3
        launch_args = str(item.get("launchArgs", ""))
        if port and re.search(rf"(?:^|\s)--port(?:\s+|=){port}(?:\s|$)", launch_args):
            score += 2
        if score and (best is None or score > best[0]):
            best = (score, item)
    return best[1] if best else None


def _extract_model_roots(config_path: str | None) -> list[dict[str, Any]]:
    """Extract top-level ``base_path`` values from ComfyUI YAML safely.

    PyYAML is deliberately not a runtime dependency.  ComfyUI's extra model
    path format represents roots on ``base_path:`` lines, which is all the
    doctor needs to report.
    """
    if not config_path:
        return []
    path = Path(config_path)
    if not path.is_file():
        return []
    roots: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        match = re.match(r"^\s*base_path\s*:\s*(.*?)\s*$", line)
        if not match:
            continue
        value = match.group(1).strip().strip("'\"")
        if not value:
            continue
        record = _path_record(value, f"extra_model_paths:{path}")
        if record and not any(_same_path(record["path"], old["path"]) for old in roots):
            roots.append(record)
    return roots


def _powershell_json(script: str) -> Any:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=8.0,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _process_chain_psutil(port: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return [], []
    listeners: list[dict[str, Any]] = []
    try:
        connections = psutil.net_connections(kind="tcp")
    except Exception:
        return [], []
    for connection in connections:
        try:
            if not connection.laddr or int(connection.laddr.port) != port:
                continue
            if str(connection.status).upper() != "LISTEN":
                continue
            listeners.append({
                "address": str(connection.laddr.ip),
                "port": port,
                "pid": connection.pid,
            })
        except Exception:
            continue
    if not listeners or not listeners[0].get("pid"):
        return listeners, []
    chain: list[dict[str, Any]] = []
    try:
        process = psutil.Process(int(listeners[0]["pid"]))
        for _ in range(8):
            try:
                chain.append({
                    "pid": process.pid,
                    "parent_pid": process.ppid(),
                    "name": process.name(),
                    "executable": process.exe(),
                    "command_line": process.cmdline(),
                    "os_user": process.username(),
                })
                parent = process.parent()
            except Exception:
                break
            if parent is None or parent.pid == process.pid:
                break
            process = parent
    except Exception:
        pass
    return listeners, chain


def _process_chain_windows(port: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    listener_script = (
        f"$x=@(Get-NetTCPConnection -State Listen -LocalPort {int(port)} "
        "-ErrorAction SilentlyContinue | Select-Object "
        "@{n='address';e={$_.LocalAddress}},@{n='port';e={$_.LocalPort}},"
        "@{n='pid';e={$_.OwningProcess}}); $x | ConvertTo-Json -Compress"
    )
    raw_listeners = _powershell_json(listener_script)
    if isinstance(raw_listeners, dict):
        listeners = [raw_listeners]
    elif isinstance(raw_listeners, list):
        listeners = [item for item in raw_listeners if isinstance(item, dict)]
    else:
        listeners = []
    if not listeners or not listeners[0].get("pid"):
        return listeners, []
    pid = int(listeners[0]["pid"])
    process_script = (
        f"$items=@(); $next={pid}; for($i=0; $i -lt 8 -and $next -gt 0; $i++){{"
        "$p=Get-CimInstance Win32_Process -Filter \"ProcessId = $next\" "
        "-ErrorAction SilentlyContinue; if($null -eq $p){break}; "
        "$o=Invoke-CimMethod -InputObject $p -MethodName GetOwner -ErrorAction SilentlyContinue; "
        "$user=if($o.User){if($o.Domain){$o.Domain+'\\'+$o.User}else{$o.User}}else{$null}; "
        "$items += [pscustomobject]@{pid=[int]$p.ProcessId; parent_pid=[int]$p.ParentProcessId; "
        "name=$p.Name; executable=$p.ExecutablePath; command_line=$p.CommandLine; os_user=$user}; "
        "$next=[int]$p.ParentProcessId}; $items | ConvertTo-Json -Compress -Depth 4"
    )
    raw_chain = _powershell_json(process_script)
    if isinstance(raw_chain, dict):
        chain = [raw_chain]
    elif isinstance(raw_chain, list):
        chain = [item for item in raw_chain if isinstance(item, dict)]
    else:
        chain = []
    return listeners, chain


def _discover_process(port: int | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    if not port:
        return [], [], "unavailable"
    listeners, chain = _process_chain_psutil(port)
    if listeners:
        return listeners, chain, "psutil"
    if sys.platform.startswith("win"):
        listeners, chain = _process_chain_windows(port)
        return listeners, chain, "powershell"
    return [], [], "unavailable"


def _classify_supervisor(chain: list[dict[str, Any]], deploy_environment: Any) -> tuple[str, dict[str, Any] | None]:
    for process in chain:
        name = str(process.get("name", "")).lower()
        if "comfy desktop" in name:
            return "comfy_desktop", process
    for process in chain:
        name = str(process.get("name", "")).lower()
        if "docker" in name or "container" in name:
            return "container", process
    if "desktop" in str(deploy_environment or "").lower():
        return "comfy_desktop", None
    if chain:
        return "standalone", chain[0]
    return "unknown", None


async def _manager_details(client: Any) -> dict[str, Any]:
    try:
        value = await client.get_text("/v2/manager/version")
        version = str(value).strip()
        if not version:
            raise ValueError("empty Manager version response")
        return {
            "available": True,
            "version": version,
            "api_generation": "v2",
            "restart_route": "/v2/manager/reboot",
            "inventory_route": "/v2/customnode/installed",
        }
    except Exception as exc:
        return {
            "available": False,
            "version": None,
            "api_generation": None,
            "error": str(exc),
        }


async def inspect_instance(ctx: Context) -> dict[str, Any]:
    """Build a profile of the exact ComfyUI endpoint selected by ``ctx``."""
    client = _client(ctx)
    base_url = str(client.base_url)
    local = _is_local_url(base_url)
    port = _url_port(base_url)
    try:
        stats = await client.get_system_stats()
    except Exception as exc:
        return {
            "status": "offline",
            "base_url": base_url,
            "local": local,
            "port": port,
            "error": str(exc),
        }

    system = stats.get("system", {}) if isinstance(stats, dict) else {}
    if not isinstance(system, dict):
        system = {}
    argv = system.get("argv", [])
    if not isinstance(argv, list):
        argv = []
    options, positional = _argv_options(argv)
    api_port = options.get("--port")
    try:
        port = int(api_port) if api_port is not None else port
    except (TypeError, ValueError):
        pass

    installations, registry_path = _read_desktop_installations() if local else ([], None)
    desktop = _match_desktop_installation(installations, options=options, port=port)
    install_root = _normalise_path(desktop.get("installPath")) if desktop else None

    main_arg = positional[0] if positional else None
    code_root: str | None = None
    if main_arg:
        main_path = Path(main_arg)
        if main_path.is_absolute():
            code_root = str(main_path.parent)
        elif install_root:
            code_root = str((Path(install_root) / main_path).parent)

    base_directory = _normalise_path(options.get("--base-directory"))
    user_directory = _normalise_path(options.get("--user-directory"))
    input_directory = _normalise_path(options.get("--input-directory"))
    output_directory = _normalise_path(options.get("--output-directory"))
    if base_directory:
        user_directory = user_directory or str(Path(base_directory) / "user")
        input_directory = input_directory or str(Path(base_directory) / "input")
        output_directory = output_directory or str(Path(base_directory) / "output")

    model_roots: list[dict[str, Any]] = []
    if base_directory:
        record = _path_record(str(Path(base_directory) / "models"), "base_directory")
        if record:
            model_roots.append(record)
    extra_model_config = _normalise_path(options.get("--extra-model-paths-config"))
    for record in _extract_model_roots(extra_model_config):
        if not any(_same_path(record["path"], old["path"]) for old in model_roots):
            model_roots.append(record)

    if local:
        listeners, chain, process_source = await asyncio.to_thread(_discover_process, port)
    else:
        listeners, chain, process_source = [], [], "remote"
    owner_type, supervisor = _classify_supervisor(chain, system.get("deploy_environment"))
    manager = await _manager_details(client)

    database_url = options.get("--database-url")
    database_path = None
    if isinstance(database_url, str) and database_url.startswith("sqlite:///"):
        database_path = database_url[len("sqlite:///") :]

    paths = {
        "install_root": _path_record(install_root, "desktop_registry"),
        "code_root": _path_record(code_root, "argv+desktop_registry"),
        "data_root": _path_record(base_directory, "argv"),
        "user_root": _path_record(user_directory, "argv"),
        "input_root": _path_record(input_directory, "argv"),
        "output_root": _path_record(output_directory, "argv"),
        "custom_nodes_root": _path_record(
            str(Path(base_directory) / "custom_nodes") if base_directory else None,
            "base_directory",
        ),
        "database": _path_record(database_path, "argv"),
        "extra_model_paths_config": _path_record(extra_model_config, "argv"),
        "model_roots": model_roots,
    }

    warnings: list[str] = []
    listen = options.get("--listen")
    if listen in {"0.0.0.0", "::"} and not getattr(client, "api_key", ""):
        warnings.append("ComfyUI listens on all interfaces without ComfyPilot API authentication.")
    if local and not listeners:
        warnings.append(f"No local listening process could be resolved for port {port}.")
    if owner_type == "comfy_desktop" and desktop is None:
        warnings.append("Desktop supervision was detected, but no matching Desktop installation record was found.")

    return {
        "status": "ok",
        "base_url": base_url,
        "local": local,
        "port": port,
        "listen_address": listen,
        "instance_id": desktop.get("id") if desktop else None,
        "instance_name": desktop.get("name") if desktop else None,
        "owner_type": owner_type,
        "listener": listeners[0] if listeners else None,
        "listeners": listeners,
        "process": chain[0] if chain else None,
        "process_chain": chain,
        "process_probe": process_source,
        "supervisor": supervisor,
        "argv": argv,
        "paths": paths,
        "versions": {
            "comfyui": system.get("comfyui_version"),
            "frontend": system.get("comfyui_frontend_package")
            or system.get("required_frontend_version"),
            "templates": system.get("installed_templates_version"),
            "python": system.get("python_version"),
            "pytorch": system.get("pytorch_version"),
            "deploy_environment": system.get("deploy_environment"),
            "desktop_release": desktop.get("version") if desktop else None,
            "desktop_release_tag": desktop.get("releaseTag") if desktop else None,
            "desktop_comfy": desktop.get("comfyVersion") if desktop else None,
        },
        "manager": manager,
        "desktop_registry": registry_path,
        "desktop_installation": desktop,
        "warnings": warnings,
    }


@mcp.tool(
    annotations={
        "title": "Inspect Connected ComfyUI Instance",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def comfy_instance_doctor(ctx: Context) -> str:
    """Discover the connected instance, supervisor, paths, ports, and versions.

    For a local Comfy Desktop endpoint, this correlates API argv, the listening
    PID/process tree, and Desktop's installation registry.  It never starts,
    stops, or changes the instance.
    """
    return json.dumps(await inspect_instance(ctx), indent=2)
