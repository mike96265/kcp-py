from KCP import KCP
from socket import socket


class KCPSession:

    def __init__(self, conv, conn, ):
        def output(data, size):
            self.output(data, size)

        self.conv = conv
        self.kcp = KCP(conv, output)

    def input(self, data, size):
        self.kcp.input(data, size)

    def output(self, data, size):
        self.conn

    def send(self, data, size):
        self.kcp.send(data, size)

    def recv(self, data, size):
        self.kcp.recv(data, size)
