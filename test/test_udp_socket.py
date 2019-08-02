from socket import *


def send_to_closed_udp_socket():
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.bind(('127.0.0.1', 0))
    sock.sendto(b'hello world', ('127.0.0.1', 9999))


def udp_connection():
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    sock.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1)
    sock.bind(('localhost', 1234))
    sock.connect(('localhost', 1235))
    sock.send(b'1234')
    while True:
        data, addr = sock.recvfrom(1024)
        print(f"recv data from {addr}")
        sock.send(data)


if __name__ == '__main__':
    udp_connection()
