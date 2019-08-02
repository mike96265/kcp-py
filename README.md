# KCP-PY


### description
- python binding for kcp
- simple tunnel implementation based asyncio module
- [KCP: A Fast and Reliable ARQ Protocol](https://github.com/skywind3000/kcp)

### platform
- python3.7
- arch linux

### install
```shell script
git clone https://github.com/yukityan/kcp-py.git
cd kcp-py
python3 -m pip install cython
python3 kcp/ikcp_setup.py build_ext --build-lib=kcp/
python3 setup.py install
```

### uninstall
```shell script
pip uninstall kcp_py
```

### usage

#### console_scripts
- kcp_local
```console
foo@bar:~$ kcp_local -h
usage: kcp_local [-h] [-s SERVER] [-p SERVER_PORT] [-l LOCAL] [-t LOCAL_PORT]
                 [-c CONFIG] [--sndwnd SNDWND] [--rcvwnd RCVWND] [--mtu MTU]
                 [--interval {30,40,50}] [--nodelay {0,1}] [--resend {0,1,2}]
                 [--nc {0,1}]

Python binding KCP tunnel Local.

optional arguments:
  -h, --help            show this help message and exit
  -s SERVER, --server SERVER
                        Host name or IP address of your remote server.
  -p SERVER_PORT, --server_port SERVER_PORT
                        Port number of your remote server.
  -l LOCAL, --local LOCAL
                        Host name or IP address your local server
  -t LOCAL_PORT, --local_port LOCAL_PORT
                        Port number of your local server.
  -c CONFIG, --config CONFIG
                        config file path
  --sndwnd SNDWND       send window size. (default 128)
  --rcvwnd RCVWND       receive window size (default 512)
  --mtu MTU             Maximum Transmission Unit for UDP packets (default:
                        1350)
  --interval {30,40,50}
                        Interval of KCP update (ms)
  --nodelay {0,1}       KCP ack nodelay or delay (default: 0 nodelay)
  --resend {0,1,2}      Fast resend
  --nc {0,1}            net control disable or enable (default: 0 enable)
```
- kcp_server
```console
foo@bar:~$ kcp_server -h
usage: kcp_server [-h] [-s SERVER] [-p SERVER_PORT] [-l LOCAL] [-t LOCAL_PORT]
                  [-c CONFIG] [--sndwnd SNDWND] [--rcvwnd RCVWND] [--mtu MTU]
                  [--interval {30,40,50}] [--nodelay {0,1}] [--resend {0,1,2}]
                  [--nc {0,1}]

Python binding KCP tunnel Server.

optional arguments:
  -h, --help            show this help message and exit
  -s SERVER, --server SERVER
                        Host name or IP address of your remote server.
  -p SERVER_PORT, --server_port SERVER_PORT
                        Port number of your remote server.
  -l LOCAL, --local LOCAL
                        Host name or IP address your local server
  -t LOCAL_PORT, --local_port LOCAL_PORT
                        Port number of your local server.
  -c CONFIG, --config CONFIG
                        config file path
  --sndwnd SNDWND       send window size. (default 128)
  --rcvwnd RCVWND       receive window size (default 512)
  --mtu MTU             Maximum Transmission Unit for UDP packets (default:
                        1350)
  --interval {30,40,50}
                        Interval of KCP update (ms)
  --nodelay {0,1}       KCP ack nodelay or delay (default: 0 nodelay)
  --resend {0,1,2}      Fast resend
  --nc {0,1}            net control disable or enable (default: 0 enable)
```
 
 #### config example
 ```json
{
    "server": "kcp_test.com",
    "server_port": 8002,
    "local": "localhost",
    "local_port": 8002,
    "sndwnd": 128,
    "rcvwnd": 1024,
    "mtu": 1300,
    "interval": 30,
    "resend": 2,
    "nc": 1,
    "nodelay": 0
}
```

