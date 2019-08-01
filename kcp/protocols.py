import asyncio
import logging
from asyncio import streams, transports
from dataclasses import dataclass

from kcp.KCP import KCP

from kcp.updater import updater
from kcp.utils import KCPConfig


def get_conv(p, offset=0):
    l = p[3]
    l = (l << 8) + p[2]
    l = (l << 8) + p[1]
    l = (l << 8) + p[0]
    return l


class TunnelTransportWrapper:

    def __init__(self, transport, tunnel, kcp, remote_addr):
        self._transport = transport
        self._tunnel = tunnel
        self._remote_addr = remote_addr
        self._kcp = kcp
        self._is_closing = False

    def __getattr__(self, item):
        return getattr(self._transport, item)

    def write(self, data):
        kcp = self._kcp
        self._tunnel.active_sessions.add(kcp.conv)
        kcp.send(data, len(data))

    def writelines(self, list_of_data):
        data = b''.join(list_of_data)
        self.write(data)

    def write_eof(self):
        pass

    def can_write_eof(self):
        return False

    def is_reading(self):
        return True

    def pause_reading(self):
        pass

    def resume_reading(self):
        pass

    def close(self):
        self._is_closing = True
        self._kcp.state = -1

    def is_closing(self):
        return self._is_closing


@dataclass
class Session:
    protocol: streams.StreamReaderProtocol
    transport: transports.Transport
    conv: int
    kcp: 'KCP'
    next_update: int


class Tunnel:
    sessions: dict
    active_sessions = set()
    accept_dict = {}

    def __init__(self, is_local, remote_addr, local_addr, transport, client_connected_cb):
        self.is_local = is_local
        self.remote_addr = remote_addr
        self.local_addr = local_addr
        self._transport = transport
        self.client_connected_cb = client_connected_cb
        self.conv = 1
        self.sessions = {}

        def output_callback(buffer, buffer_len):
            self._transport.sendto(buffer, remote_addr)

        self.output_callback = output_callback

    def data_received(self, data: bytes):
        conv = get_conv(data)
        if conv in self.sessions:
            session = self.sessions[conv]
            session.kcp.input(data, len(data))
            self.active_sessions.add(conv)
        else:
            if not self.is_local and conv not in self.accept_dict:
                loop = asyncio.get_event_loop()

                def cb(fut):
                    reader, writer = fut.result()
                    s = self.sessions[conv]
                    s.kcp.input(data, len(data))
                    res = self.client_connected_cb(reader, writer)
                    if asyncio.iscoroutine(res):
                        loop.create_task(res)
                    del self.accept_dict[conv]

                task = loop.create_task(self.create_connection(conv))
                task.add_done_callback(cb)
                self.accept_dict[conv] = task

    def close(self, exc):
        sessions = self.sessions
        for session in sessions.values():
            session.protocol.eof_received()
            session.protocol.connection_lost(exc)
        sessions.clear()
        self.accept_dict.clear()
        del sessions
        self.sessions = None

    async def create_connection(self, conv=None):
        logging.info("in create connection")
        loop = asyncio.get_event_loop()
        if self.is_local:
            conv: int = self.conv
            self.conv += 1
        else:
            conv = conv
        config = KCPConfig()
        kcp = KCP(conv)
        kcp.set_output(self.output_callback)
        kcp.set_mtu(config.mtu)
        kcp.nodelay(config.nodelay, config.interval, config.resend, config.nc)
        kcp.wndsize(config.sndwnd, config.rcvwnd)
        reader = asyncio.StreamReader(limit=2 ** 16, loop=loop)
        protocol = streams.StreamReaderProtocol(reader, loop=loop)
        transport = TunnelTransportWrapper(self._transport, self, kcp, self.remote_addr)
        writer = streams.StreamWriter(transport, protocol, reader, loop)
        session = Session(protocol=protocol, transport=transport, kcp=kcp, conv=conv, next_update=0)
        self.active_sessions.add(conv)
        self.sessions[conv] = session
        return reader, writer

    def close_session(self, session):
        conv = session.conv
        del self.sessions[conv]
        if conv in self.active_sessions:
            self.active_sessions.remove(conv)


class LocalDataGramHandlerProtocol:
    tunnel = None

    def __init__(self):
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        local_addr = transport.get_extra_info('sockname')
        remote_addr = transport.get_extra_info('peername')
        self.tunnel = Tunnel(True, remote_addr, local_addr, transport, None)
        updater.register(self.tunnel)

    def datagram_received(self, data: bytes, addr):
        handler = self.tunnel
        handler.data_received(data)

    def connection_lost(self, exc):
        updater.unregister(self.tunnel)
        self.tunnel.close(exc)

    def error_received(self, exc):
        updater.unregister(self.tunnel)
        self.tunnel.close(exc)


class ServerDataGramHandlerProtocol:
    tunnels = {}

    def __init__(self, client_connected_cb):
        self.client_connected_cb = client_connected_cb
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if addr in self.tunnels:
            tunnel = self.tunnels.get(addr)
        else:
            transport = self.transport
            local_addr = transport.get_extra_info('sockname')
            remote_addr = addr
            tunnel = Tunnel(False, remote_addr, local_addr, transport, self.client_connected_cb)
            updater.register(tunnel)
            self.tunnels[addr] = tunnel
        tunnel.data_received(data)

    def connection_lost(self, exc):
        for tunnel in self.tunnels:
            updater.unregister(tunnel)
            tunnel.close(exc)

    def error_received(self, exc):
        for tunnel in self.tunnels:
            updater.unregister(tunnel)
            tunnel.close(exc)
        self.transport.close()
