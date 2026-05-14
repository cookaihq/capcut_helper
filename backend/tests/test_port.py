import socket

import pytest

from app.core.port import select_port


def test_select_port_returns_port_in_range():
    port = select_port([19527, 19536])
    assert 19527 <= port <= 19536


def test_select_port_skips_occupied_port():
    # 先占住端口段里的第一个端口
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupied.bind(("127.0.0.1", 19600))
    occupied.listen(1)
    try:
        port = select_port([19600, 19601])
        assert port == 19601
    finally:
        occupied.close()


def test_select_port_raises_when_whole_range_occupied():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 19700))
    s.listen(1)
    try:
        with pytest.raises(RuntimeError):
            select_port([19700, 19700])
    finally:
        s.close()
