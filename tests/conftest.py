import socket
from datetime import datetime, timezone
import pytest
from memory_engine import MemoryService, Repository

NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)


@pytest.fixture
def engine(tmp_path):
    clock = [NOW]
    service = MemoryService(Repository(tmp_path / "memory.db"), clock=lambda: clock[0])
    service.test_clock = clock
    return service


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    original = socket.socket.connect

    def guarded(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("Network disabled in default tests")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
