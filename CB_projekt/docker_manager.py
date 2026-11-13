"""Safe lifecycle management for allow-listed CTF Docker challenge images."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import models
from database import SessionLocal

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent
INSTANCE_TTL_MINUTES = int(os.getenv("CTF_INSTANCE_TTL_MINUTES", "30"))
MAX_ACTIVE_INSTANCES_PER_USER = int(os.getenv("CTF_MAX_ACTIVE_INSTANCES_PER_USER", "2"))
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CTF_INSTANCE_CLEANUP_INTERVAL", "30"))

# Only reviewed repository templates can be started. Never accept user-provided
# image names, build paths, commands, mounts, ports or Docker options.
SUPPORTED_TEMPLATES = {
    "web_sqli": {
        "title": "CyberShop – SQL Injection",
        "context": BASE_DIR / "docker_challanges" / "web_sqli",
        "image": "ctf-platform/web-sqli:stage2",
        "container_port": 7000,
    }
}
PROXY_CONTEXT = BASE_DIR / "docker_challanges" / "ingress_proxy"
PROXY_IMAGE = "ctf-platform/ingress-proxy:stage2-fix1"
PROXY_PORT = 8080


class DockerManagerError(RuntimeError):
    """A safe, user-displayable Docker lifecycle error."""


def utcnow() -> datetime:
    # Existing SQLite schema stores naive UTC timestamps.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_supported_template(template_key: Optional[str]) -> bool:
    return not template_key or template_key in SUPPORTED_TEMPLATES


def get_active_instance(db, user_id: int, challenge_id: int):
    return (
        db.query(models.ChallengeInstance)
        .filter(
            models.ChallengeInstance.user_id == user_id,
            models.ChallengeInstance.challenge_id == challenge_id,
            models.ChallengeInstance.status == "running",
            models.ChallengeInstance.expires_at > utcnow(),
        )
        .order_by(models.ChallengeInstance.created_at.desc())
        .first()
    )


def instance_url(instance: models.ChallengeInstance) -> Optional[str]:
    if not instance or not instance.host_port:
        return None
    host = os.getenv("CTF_PUBLIC_HOST", "127.0.0.1").strip()
    # Dynamic published ports do not terminate TLS. Use a reverse proxy for HTTPS.
    return f"http://{host}:{instance.host_port}"


def _is_image_not_found(exc: Exception) -> bool:
    """Check the Docker SDK's ImageNotFound type without leaking import scope."""
    try:
        from docker.errors import ImageNotFound
    except ImportError:
        return False
    return isinstance(exc, ImageNotFound)


def _docker_client():
    try:
        import docker
        from docker.errors import DockerException, ImageNotFound
    except ImportError as exc:
        raise DockerManagerError(
            "Brakuje biblioteki Docker SDK. Wykonaj: pip install -r requirements.txt."
        ) from exc
    try:
        # Image builds can take longer than a short request timeout, especially
        # on the first run when Docker must download base images.
        return docker.from_env(timeout=180)
    except DockerException as exc:
        raise DockerManagerError(
            "Nie można połączyć się z Dockerem. Uruchom Docker Desktop lub usługę Docker."
        ) from exc


def _remove_container_and_network(client, instance: models.ChallengeInstance) -> None:
    """Remove the trusted proxy first, then the lab container and both networks."""
    from docker.errors import NotFound

    for container_id in (instance.proxy_container_id, instance.container_id):
        if not container_id:
            continue
        try:
            container = client.containers.get(container_id)
            container.reload()
            if container.status == "running":
                container.stop(timeout=5)
            container.remove(force=True)
        except NotFound:
            pass

    for network_id in (instance.ingress_network_id, instance.network_id):
        if not network_id:
            continue
        try:
            client.networks.get(network_id).remove()
        except NotFound:
            pass


def start_or_get_instance(db, user: models.User, challenge: models.Challenge):
    key = challenge.docker_template
    if not key or key not in SUPPORTED_TEMPLATES:
        raise DockerManagerError("To zadanie nie ma skonfigurowanego środowiska Docker.")

    existing = get_active_instance(db, user.id, challenge.id)
    if existing:
        return existing

    now = utcnow()
    active_count = (
        db.query(models.ChallengeInstance)
        .filter(
            models.ChallengeInstance.user_id == user.id,
            models.ChallengeInstance.status.in_(["starting", "running", "stop_failed"]),
            models.ChallengeInstance.expires_at > now,
        )
        .count()
    )
    if active_count >= MAX_ACTIVE_INSTANCES_PER_USER:
        raise DockerManagerError(
            f"Możesz mieć maksymalnie {MAX_ACTIVE_INSTANCES_PER_USER} aktywne środowiska jednocześnie."
        )

    config = SUPPORTED_TEMPLATES[key]
    context = Path(config["context"]).resolve()
    if not context.is_relative_to(BASE_DIR) or not context.is_dir():
        raise DockerManagerError("Brakuje katalogu z definicją środowiska Docker.")

    instance = models.ChallengeInstance(
        user_id=user.id,
        challenge_id=challenge.id,
        status="starting",
        created_at=now,
        expires_at=now + timedelta(minutes=INSTANCE_TTL_MINUTES),
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)

    client = network = container = None
    try:
        client = _docker_client()
        image_name = config["image"]
        logger.info("CTF instance %s: checking challenge image %s", instance.id, image_name)
        try:
            client.images.get(image_name)
        except Exception as image_error:
            if not _is_image_not_found(image_error):
                raise
            logger.info("CTF instance %s: building challenge image", instance.id)
            try:
                client.images.build(path=str(context), tag=image_name, rm=True)
            except Exception as exc:
                raise DockerManagerError(
                    "Nie udało się zbudować obrazu zadania. Sprawdź Dockerfile i połączenie z Dockerem."
                ) from exc
        logger.info("CTF instance %s: challenge image is ready", instance.id)

        if not PROXY_CONTEXT.is_dir():
            raise DockerManagerError("Brakuje katalogu z definicją bramy dostępowej Docker.")
        logger.info("CTF instance %s: checking ingress proxy image %s", instance.id, PROXY_IMAGE)
        try:
            client.images.get(PROXY_IMAGE)
        except Exception as image_error:
            if not _is_image_not_found(image_error):
                raise
            logger.info("CTF instance %s: building ingress proxy image", instance.id)
            try:
                client.images.build(path=str(PROXY_CONTEXT), tag=PROXY_IMAGE, rm=True)
            except Exception as exc:
                raise DockerManagerError(
                    "Nie udało się zbudować obrazu bramy dostępowej. Sprawdź Dockerfile proxy i połączenie z Dockerem."
                ) from exc
        logger.info("CTF instance %s: ingress proxy image is ready", instance.id)

        token = uuid.uuid4().hex[:12]
        labels = {
            "ctf.platform": "cb-projekt",
            "ctf.instance_id": str(instance.id),
            "ctf.user_id": str(user.id),
            "ctf.challenge_id": str(challenge.id),
        }
        # The vulnerable lab container stays on an internal-only network.
        # Docker does not publish ports for containers attached exclusively to
        # internal networks, so a small, trusted reverse proxy publishes ingress
        # from a separate bridge network.
        network = client.networks.create(
            name=f"ctf-private-{instance.id}-{token}",
            driver="bridge",
            internal=True,
            labels=labels,
        )
        instance.network_id = network.id
        db.commit()

        ingress_network = client.networks.create(
            name=f"ctf-ingress-{instance.id}-{token}",
            driver="bridge",
            internal=False,
            labels={**labels, "ctf.role": "ingress"},
        )
        instance.ingress_network_id = ingress_network.id
        db.commit()

        port = int(config["container_port"])
        bind_host = os.getenv("CTF_DOCKER_BIND_HOST", "127.0.0.1").strip()
        logger.info("CTF instance %s: creating private challenge container", instance.id)
        container = client.containers.create(
            image_name,
            name=f"ctf-lab-{instance.id}-{token}",
            mem_limit="256m",
            nano_cpus=500_000_000,
            pids_limit=64,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            read_only=True,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=32m,mode=1777"},
            user="10001:10001",
            restart_policy={"Name": "no"},
            labels={**labels, "ctf.role": "challenge"},
        )
        instance.container_id = container.id
        db.commit()
        # Attach exactly once, before start, with a stable DNS alias for Nginx.
        network.connect(container, aliases=["challenge"])
        container.start()
        container.reload()
        logger.info("CTF instance %s: private challenge container is running", instance.id)

        # Create the proxy on the non-internal ingress network so Docker can
        # publish its host port. Attach it to the private network before start,
        # allowing its fixed Nginx upstream to resolve the challenge alias.
        proxy = client.containers.create(
            PROXY_IMAGE,
            name=f"ctf-proxy-{instance.id}-{token}",
            network=ingress_network.name,
            ports={f"{PROXY_PORT}/tcp": (bind_host,)},
            mem_limit="64m",
            nano_cpus=250_000_000,
            pids_limit=32,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            read_only=True,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=16m,mode=1777"},
            user="101:101",
            restart_policy={"Name": "no"},
            labels={**labels, "ctf.role": "ingress"},
        )
        instance.proxy_container_id = proxy.id
        db.commit()
        network.connect(proxy, aliases=["ingress-proxy"])
        logger.info("CTF instance %s: starting ingress proxy", instance.id)
        proxy.start()
        proxy.reload()
        logger.info("CTF instance %s: ingress proxy state=%s", instance.id, proxy.status)

        if proxy.status != "running":
            try:
                proxy_output = proxy.logs(tail=80, stdout=True, stderr=True)
                if isinstance(proxy_output, bytes):
                    proxy_output = proxy_output.decode("utf-8", errors="replace")
            except Exception as log_exc:
                proxy_output = f"Nie udało się pobrać logów kontenera proxy: {log_exc}"
            logger.error(
                "CTF instance %s: ingress proxy exited before publishing its port. "
                "container_state=%r\nproxy_logs:\n%s",
                instance.id,
                proxy.attrs.get("State"),
                proxy_output,
            )
            raise DockerManagerError(
                "Kontener bramy Nginx zakończył pracę podczas uruchamiania. "
                "Dokładna przyczyna jest w terminalu serwera."
            )

        bindings = proxy.attrs.get("NetworkSettings", {}).get("Ports", {})
        host_bindings = bindings.get(f"{PROXY_PORT}/tcp") or []
        if not host_bindings or not host_bindings[0].get("HostPort"):
            # The ingress proxy is on a regular bridge network, not an internal one.
            # Keep details in the server log for diagnosis without exposing them to users.
            logger.error(
                "No host port for proxy instance %s: state=%r ports=%r",
                instance.id,
                proxy.attrs.get("State"),
                bindings,
            )
            raise DockerManagerError("Docker nie przydzielił portu dla bramy dostępowej środowiska.")

        instance.host_port = int(host_bindings[0]["HostPort"])
        logger.info(
            "CTF instance %s: proxy published at %s:%s",
            instance.id,
            bind_host,
            instance.host_port,
        )
        instance.status = "running"
        instance.error_message = None
        db.commit()
        db.refresh(instance)
        return instance

    except DockerManagerError as exc:
        cleanup_ok = True
        if client:
            try:
                _remove_container_and_network(client, instance)
            except Exception:
                cleanup_ok = False
                logger.exception("Nie udało się posprzątać nieudanej instancji Docker")
        instance.status = "error" if cleanup_ok else "stop_failed"
        if not cleanup_ok:
            instance.expires_at = utcnow()
        instance.stopped_at = utcnow() if cleanup_ok else None
        instance.error_message = str(exc)[:1000]
        db.commit()
        raise
    except Exception as exc:
        cleanup_ok = True
        if client:
            try:
                _remove_container_and_network(client, instance)
            except Exception:
                cleanup_ok = False
                logger.exception("Nie udało się posprzątać nieudanej instancji Docker")
        instance.status = "error" if cleanup_ok else "stop_failed"
        if not cleanup_ok:
            instance.expires_at = utcnow()
        instance.stopped_at = utcnow() if cleanup_ok else None
        instance.error_message = "Wystąpił błąd podczas uruchamiania kontenera. Sprawdź logi serwera."
        db.commit()
        logger.exception("Docker start failed for challenge instance %s", instance.id)
        raise DockerManagerError(instance.error_message) from exc
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass


def stop_instance(db, instance: models.ChallengeInstance, final_status: str = "stopped") -> None:
    if instance.status in {"stopped", "expired", "error"}:
        return
    client = _docker_client()
    try:
        try:
            _remove_container_and_network(client, instance)
        except Exception as exc:
            instance.status = "stop_failed"
            instance.error_message = "Nie udało się całkowicie zatrzymać kontenera. Spróbujemy ponownie."
            db.commit()
            raise DockerManagerError(instance.error_message) from exc
        instance.status = final_status
        instance.stopped_at = utcnow()
        instance.error_message = None
        db.commit()
    finally:
        try:
            client.close()
        except Exception:
            pass


def cleanup_expired_instances() -> int:
    """Stop expired instances; safe to call repeatedly from the background worker."""
    db = SessionLocal()
    stopped = 0
    try:
        expired = (
            db.query(models.ChallengeInstance)
            .filter(
                models.ChallengeInstance.status.in_(["running", "stop_failed", "starting"]),
                models.ChallengeInstance.expires_at <= utcnow(),
            )
            .all()
        )
        if not expired:
            return 0
        client = _docker_client()
        try:
            for instance in expired:
                try:
                    _remove_container_and_network(client, instance)
                    instance.status = "expired"
                    instance.stopped_at = utcnow()
                    instance.error_message = None
                    stopped += 1
                except Exception:
                    logger.exception("Could not stop expired instance %s", instance.id)
                    instance.status = "stop_failed"
                    instance.error_message = "Automatyczne zatrzymanie nie powiodło się; ponowienie nastąpi później."
            db.commit()
        finally:
            client.close()
    except DockerManagerError:
        logger.warning("Docker unavailable during expired-instance cleanup")
    except Exception:
        logger.exception("Unexpected error while cleaning expired Docker instances")
    finally:
        db.close()
    return stopped


def calculate_cpu_percent(stats: dict) -> Optional[float]:
    """Calculate a container CPU percentage from a one-shot Docker stats payload."""
    cpu = stats.get("cpu_stats") or {}
    previous = stats.get("precpu_stats") or {}
    cpu_usage = cpu.get("cpu_usage") or {}
    previous_usage = previous.get("cpu_usage") or {}

    current_total = cpu_usage.get("total_usage")
    previous_total = previous_usage.get("total_usage")
    current_system = cpu.get("system_cpu_usage")
    previous_system = previous.get("system_cpu_usage")
    if None in (current_total, previous_total, current_system, previous_system):
        return None

    cpu_delta = current_total - previous_total
    system_delta = current_system - previous_system
    if cpu_delta < 0 or system_delta <= 0:
        return None

    online_cpus = cpu.get("online_cpus")
    if not online_cpus:
        online_cpus = len(cpu_usage.get("percpu_usage") or []) or 1
    return round((cpu_delta / system_delta) * online_cpus * 100.0, 1)


def calculate_memory_usage(stats: dict) -> dict:
    """Return memory usage, limit and percentage from a Docker stats payload."""
    memory_stats = stats.get("memory_stats") or {}
    usage = memory_stats.get("usage")
    limit = memory_stats.get("limit")
    memory_details = memory_stats.get("stats") or {}
    cache = memory_details.get("total_inactive_file")
    if cache is None:
        cache = memory_details.get("inactive_file", 0)
    if usage is not None:
        usage = max(0, usage - (cache or 0))
    percentage = None
    if usage is not None and limit:
        percentage = round((usage / limit) * 100.0, 1)
    return {"usage_bytes": usage, "limit_bytes": limit, "percent": percentage}


def format_bytes(value: Optional[int]) -> str:
    if value is None:
        return "—"
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} TB"


def _read_container_metrics(client, container_id: Optional[str]) -> dict:
    """Inspect a known container and read live resource metrics."""
    if not container_id:
        return {
            "status": "brak",
            "cpu_percent": None,
            "memory": {"usage_bytes": None, "limit_bytes": None, "percent": None},
            "error": None,
        }

    try:
        container = client.containers.get(container_id)
        container.reload()
        state = container.status
        cpu_percent = None
        memory = {"usage_bytes": None, "limit_bytes": None, "percent": None}

        if state == "running":
            try:
                payload = container.stats(stream=False)
                cpu_percent = calculate_cpu_percent(payload)
                memory = calculate_memory_usage(payload)
            except Exception:
                logger.exception("Could not read Docker stats for container %s", container_id)

        return {"status": state, "cpu_percent": cpu_percent, "memory": memory, "error": None}
    except Exception as exc:
        try:
            from docker.errors import NotFound
            if isinstance(exc, NotFound):
                return {
                    "status": "brak",
                    "cpu_percent": None,
                    "memory": {"usage_bytes": None, "limit_bytes": None, "percent": None},
                    "error": "Kontener nie istnieje w Docker Engine.",
                }
        except ImportError:
            pass
        logger.exception("Could not inspect Docker container %s", container_id)
        return {
            "status": "niedostępny",
            "cpu_percent": None,
            "memory": {"usage_bytes": None, "limit_bytes": None, "percent": None},
            "error": "Nie udało się pobrać stanu kontenera.",
        }


def get_infrastructure_overview(db, limit: int = 100) -> dict:
    """Return recent instance records enriched with live Docker container metrics."""
    instances = (
        db.query(models.ChallengeInstance)
        .order_by(models.ChallengeInstance.created_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    try:
        client = _docker_client()
        docker_available = True
        docker_error = None
    except DockerManagerError as exc:
        client = None
        docker_available = False
        docker_error = str(exc)

    try:
        for instance in instances:
            unavailable = {
                "status": "niedostępny",
                "cpu_percent": None,
                "memory": {"usage_bytes": None, "limit_bytes": None, "percent": None},
                "error": docker_error,
            }
            lab = _read_container_metrics(client, instance.container_id) if client else dict(unavailable)
            proxy = _read_container_metrics(client, instance.proxy_container_id) if client else dict(unavailable)

            result.append({
                "id": instance.id,
                "username": instance.user.username if instance.user else "—",
                "challenge_title": instance.challenge.title if instance.challenge else "—",
                "db_status": instance.status,
                "created_at": instance.created_at,
                "expires_at": instance.expires_at,
                "stopped_at": instance.stopped_at,
                "host_port": instance.host_port,
                "lab": lab,
                "proxy": proxy,
                "can_manage": bool(instance.container_id and instance.proxy_container_id),
                "last_error": instance.error_message,
            })
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass

    active_statuses = {"starting", "running", "stop_failed"}
    return {
        "docker_available": docker_available,
        "docker_error": docker_error,
        "instances": result,
        "total_instances": len(result),
        "active_instances": sum(1 for item in result if item["db_status"] in active_statuses),
        "running_labs": sum(1 for item in result if item["lab"]["status"] == "running"),
        "failed_instances": sum(1 for item in result if item["db_status"] in {"error", "stop_failed"}),
    }


def restart_instance(db, instance: models.ChallengeInstance) -> None:
    """Restart the existing lab and ingress containers without changing ownership."""
    if not instance.container_id or not instance.proxy_container_id:
        raise DockerManagerError(
            "Ta instancja nie ma już kompletu kontenerów. Uruchom zadanie ponownie z jego strony."
        )
    if instance.status in {"stopped", "expired", "error"}:
        raise DockerManagerError(
            "Ta instancja jest zatrzymana lub wygasła. Uruchom nowe środowisko ze strony zadania."
        )

    client = _docker_client()
    try:
        try:
            lab = client.containers.get(instance.container_id)
            proxy = client.containers.get(instance.proxy_container_id)
        except Exception as exc:
            raise DockerManagerError(
                "Nie znaleziono kontenera laboratorium lub proxy. Uruchom nowe środowisko ze strony zadania."
            ) from exc

        for container, label in ((lab, "laboratorium"), (proxy, "proxy")):
            container.reload()
            if container.status == "running":
                container.restart(timeout=10)
            else:
                container.start()
            container.reload()
            if container.status != "running":
                try:
                    logs = container.logs(tail=60, stdout=True, stderr=True)
                    if isinstance(logs, bytes):
                        logs = logs.decode("utf-8", errors="replace")
                except Exception:
                    logs = "Nie udało się odczytać logów kontenera."
                logger.error(
                    "Restart failed for %s container of instance %s: %s",
                    label, instance.id, logs
                )
                raise DockerManagerError(
                    f"Nie udało się ponownie uruchomić kontenera: {label}. Sprawdź terminal serwera."
                )

        bindings = proxy.attrs.get("NetworkSettings", {}).get("Ports", {})
        host_bindings = bindings.get(f"{PROXY_PORT}/tcp") or []
        if not host_bindings or not host_bindings[0].get("HostPort"):
            raise DockerManagerError("Po restarcie proxy nie ma przypisanego portu hosta.")

        instance.host_port = int(host_bindings[0]["HostPort"])
        instance.status = "running"
        instance.error_message = None
        instance.stopped_at = None
        db.commit()
    except DockerManagerError:
        raise
    except Exception as exc:
        logger.exception("Could not restart Docker instance %s", instance.id)
        instance.status = "error"
        instance.error_message = "Restart środowiska nie powiódł się. Sprawdź logi serwera."
        db.commit()
        raise DockerManagerError(instance.error_message) from exc
    finally:
        try:
            client.close()
        except Exception:
            pass
