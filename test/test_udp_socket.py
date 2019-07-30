from socket import *


def send_to_closed_udp_socket():
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.bind(('127.0.0.1', 0))
    sock.sendto(b'hello world', ('127.0.0.1', 9999))


if __name__ == '__main__':
    send_to_closed_udp_socket()
