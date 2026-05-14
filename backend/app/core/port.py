import socket


def select_port(port_range: list[int]) -> int:
    """在 [port_range[0], port_range[1]] 闭区间内挑第一个能绑定的端口。
    整段都被占用则抛 RuntimeError。"""
    start, end = port_range[0], port_range[1]
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"端口段 {start}-{end} 全部被占用")
