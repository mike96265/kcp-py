import asyncio
import logging
from asyncio import streams, transports, protocols
from collections import defaultdict
from dataclasses import dataclass

from kcp.KCP import KCP, get_conv
from kcp.updater import updater
from kcp.utils import KCPConfig


def new_kcp(conv, output):
    config = KCPConfig()
    kcp = KCP(conv)
    kcp.set_output(output)
    kcp.set_mtu(config.mtu)
    kcp.nodelay(config.nodelay, config.interval, config.resend, config.nc)
    kcp.wndsize(config.sndwnd, config.rcvwnd)
    return kcp


class TunnelTransportWrapper(transports.Transport):

    def __init__(self, transport, conn, kcp):
        self._transport = transport
        self._conn = conn
        self._kcp = kcp
        self._is_closing = False

    def __getattr__(self, item):
        return getattr(self._transport, item)

    def write(self, data):
        kcp = self._kcp
        self._conn.active_sessions.add(kcp.conv)
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


class DataGramConnHandlerProtocol(protocols.DatagramProtocol):

    def __init__(self, is_local, client_connected_cb=None):
        self.is_local = is_local
        self.client_connected_cb = client_connected_cb
        self.conv = 1
        self.sessions = dict()
        self.active_sessions = set()
        self.accept_dict = defaultdict(bytearray)
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        updater.register(self)

    async def accept_connection(self, conv):
        reader, writer = await self.create_connection(conv)
        s = self.sessions[conv]
        accept_dict = self.accept_dict
        buffer = accept_dict[conv]
        s.kcp.input(buffer, len(buffer))
        res = self.client_connected_cb(reader, writer)
        loop = asyncio.get_event_loop()
        if asyncio.iscoroutine(res):
            loop.create_task(res)
        del accept_dict[conv]
        self.active_sessions.add(conv)

    async def create_connection(self, conv=None):
        loop = asyncio.get_event_loop()
        if self.is_local:
            conv = self.conv
            self.conv += 1
        else:
            assert conv
            conv = conv
        kcp = new_kcp(conv, self.transport.sendto)
        reader = asyncio.StreamReader(loop=loop)
        protocol = streams.StreamReaderProtocol(reader, loop=loop)
        transport = TunnelTransportWrapper(self.transport, self, kcp)
        writer = streams.StreamWriter(transport, protocol, reader, loop)
        session = Session(protocol=protocol, transport=transport, kcp=kcp, conv=conv, next_update=0)
        self.active_sessions.add(conv)
        self.sessions[conv] = session
        return reader, writer

    def datagram_received(self, data: bytes, addr):
        conv = get_conv(data)
        sessions = self.sessions
        if conv in sessions:
            session = sessions[conv]
            kcp = session.kcp
            kcp.input(data, len(data))
            peeksize = kcp.peeksize()
            if peeksize != 0 and peeksize != -1:
                data = bytes(peeksize)
                kcp.recv(data, peeksize)
                session.protocol.data_received(data)
            self.active_sessions.add(conv)
        else:
            if not self.is_local:
                if conv not in self.accept_dict:
                    loop = asyncio.get_event_loop()
                    loop.create_task(self.accept_connection(conv))
                    self.accept_dict[conv].extend(data)
                else:
                    data_len = len(data)
                    buffer = len(self.accept_dict[conv])
                    if buffer + data_len > 65536:
                        del self.accept_dict[conv]
                    else:
                        self.accept_dict[conv].extend(data)

    def connection_lost(self, exc):
        logging.info("connection lost for: %s", exc)
        updater.unregister(self)
        sessions = self.sessions
        for session in sessions.values():
            session.protocol.eof_received()
            session.protocol.connection_lost(exc)
        sessions.clear()
        self.accept_dict.clear()
        del sessions

    def close_session(self, session):
        conv = session.conv
        del self.sessions[conv]
        if conv in self.active_sessions:
            self.active_sessions.remove(conv)

    def error_received(self, exc):
        logging.warning("conn received error %s", exc)


class ServerDataGramHandlerProtocol(protocols.DatagramProtocol):
    conns = defaultdict(bytearray)

    def __init__(self, client_connected_cb):
        self.client_connected_cb = client_connected_cb
        self.transport = None

    def connection_made(self, transport: transports.DatagramTransport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        loop = asyncio.get_event_loop()
        conns = self.conns

        def connection_accepted_cb(result: asyncio.Future):
            if not result.exception():
                transport, protocol = result.result()
                buffer = conns[addr]
                protocol.datagram_received(buffer, addr)

        if addr not in conns:
            task = loop.create_task(loop.create_datagram_endpoint(
                lambda: DataGramConnHandlerProtocol(is_local=False, client_connected_cb=self.client_connected_cb),
                local_addr=self.transport.get_extra_info('sockname'),
                remote_addr=addr,
                reuse_address=True,
                reuse_port=True
            ))
            task.add_done_callback(connection_accepted_cb)
        self.conns[addr].extend(data)

    def connection_lost(self, exc):
        logging.info("server connection lost: %s", exc)

    def error_received(self, exc):
        logging.warning("server error: %s", exc)
