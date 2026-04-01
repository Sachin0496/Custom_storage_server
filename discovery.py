import socket
import threading
from zeroconf import ServiceInfo, Zeroconf
import json


def get_lan_ip() -> str:
    """Get the primary LAN IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_all_ips() -> list[str]:
    """Get all non-loopback IPv4 addresses."""
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ":" not in ip and not ip.startswith("127."):
                if ip not in ips:
                    ips.append(ip)
    except Exception:
        pass
    primary = get_lan_ip()
    if primary not in ips and primary != "127.0.0.1":
        ips.insert(0, primary)
    return ips or ["127.0.0.1"]


_zeroconf: Zeroconf | None = None
_service_info: ServiceInfo | None = None


def start_mdns(port: int, app_name: str):
    """Advertise the server on mDNS so clients can discover it automatically."""
    global _zeroconf, _service_info

    def _run():
        global _zeroconf, _service_info
        try:
            ip = get_lan_ip()
            ip_bytes = socket.inet_aton(ip)
            _service_info = ServiceInfo(
                "_lanstore._tcp.local.",
                f"{app_name}._lanstore._tcp.local.",
                addresses=[ip_bytes],
                port=port,
                properties={"path": "/", "name": app_name},
                server=f"{socket.gethostname()}.local.",
            )
            _zeroconf = Zeroconf()
            _zeroconf.register_service(_service_info)
        except Exception as e:
            print(f"[mDNS] Warning: could not advertise service: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def stop_mdns():
    global _zeroconf, _service_info
    if _zeroconf and _service_info:
        try:
            _zeroconf.unregister_service(_service_info)
            _zeroconf.close()
        except Exception:
            pass
