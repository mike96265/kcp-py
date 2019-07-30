from cpython.bytes cimport PyBytes_FromStringAndSize
from cpython.pycapsule cimport *
from libc.stdint cimport uint32_t, int32_t

cdef extern from 'stdio.h':
    int printf(char *format, ...);


cdef extern from "../ikcp/ikcp.h":
    ctypedef uint32_t ISTDUINT32;  #for linux
    ctypedef int32_t ISTDINT32;  #for linux
    ctypedef ISTDINT32 IINT32;
    ctypedef ISTDUINT32 IUINT32;

    struct IQUEUEHEAD:
        IQUEUEHEAD *next, *prev

    struct IKCPCB:
        IUINT32 conv, mtu, mss, state;
        IUINT32 snd_una, snd_nxt, rcv_nxt;
        IUINT32 ts_recent, ts_lastack, ssthresh;
        IINT32 rx_rttval, rx_srtt, rx_rto, rx_minrto;
        IUINT32 snd_wnd, rcv_wnd, rmt_wnd, cwnd, probe;
        IUINT32 current, interval, ts_flush, xmit;
        IUINT32 nrcv_buf, nsnd_buf;
        IUINT32 nrcv_que, nsnd_que;
        IUINT32 nodelay, updated;
        IUINT32 ts_probe, probe_wait;
        IUINT32 dead_link, incr;
        IQUEUEHEAD snd_queue;
        IQUEUEHEAD rcv_queue;
        IQUEUEHEAD snd_buf;
        IQUEUEHEAD rcv_buf;
        IUINT32 *acklist;
        IUINT32 ackcount;
        IUINT32 ackblock;
        void *user;
        char *buffer;
        int fastresend;
        int nocwnd;
        int logmask;
        int (*output)(const char *buf, int len, IKCPCB *kcp, void *user);
        void (*writelog)(const char *log, IKCPCB *kcp, void *user);

    ctypedef IKCPCB ikcpcb;
    ikcpcb *ikcp_create(IUINT32 conv, void *user);
    void ikcp_release(ikcpcb *kcp);
    int ikcp_recv(ikcpcb *kcp, char *buffer, int length);
    int ikcp_send(ikcpcb *kcp, const char *buffer, int length);
    void ikcp_update(ikcpcb *kcp, IUINT32 current);
    IUINT32 ikcp_check(const ikcpcb *kcp, IUINT32 current);
    int ikcp_input(ikcpcb *kcp, const char *data, long size);
    void ikcp_flush(ikcpcb *kcp);
    int ikcp_wndsize(ikcpcb *kcp, int sndwnd, int rcvwnd);
    int ikcp_nodelay(ikcpcb *kcp, int nodelay, int interval, int resend, int nc);
    int ikcp_peeksize(const ikcpcb *kcp);
    void ikcp_setoutput(ikcpcb *kcp, int (*output)(const char *buf, int len, ikcpcb *kcp, void *user));
    IUINT32 ikcp_getconv(const void *ptr);



cdef int output_wrapper(const char *buf, int length, ikcpcb *ikcp, void *user):
    cdef object kcp = <object> user
    cdef bytes o = PyBytes_FromStringAndSize(buf, length)
    kcp.output(o, length)
    return 1

cpdef get_conv(const char *ptr):
    return ikcp_getconv(ptr)

cdef class KCP:
    cdef ikcpcb *ckcp
    cdef public object output

    @property
    def conv(self):
        return self.ckcp.conv

    @property
    def state(self):
        return self.ckcp.state

    def __cinit__(self, conv):
        self.ckcp = ikcp_create(conv, <void*> self)

    def __dealloc__(self):
        ikcp_release(self.ckcp)

    cpdef int recv(self, char *buffer, int length):
        return ikcp_recv(self.ckcp, buffer, length)

    cpdef int send(self, char *buffer, int length):
        return ikcp_send(self.ckcp, buffer, length)

    cpdef void update(self, IUINT32 current):
        ikcp_update(self.ckcp, current)

    cpdef IUINT32 check(self, IUINT32 current):
        return ikcp_check(self.ckcp, current)

    cpdef int input(self, char *buffer, int length):
        return ikcp_input(self.ckcp, buffer, length)

    cpdef int wndsize(self, int sndwnd, int rcvwnd):
        return ikcp_wndsize(self.ckcp, sndwnd, rcvwnd)

    cpdef int nodelay(self, int nodelay, int interval, int resend, int nc):
        return ikcp_nodelay(self.ckcp, nodelay, interval, resend, nc)

    cpdef int peeksize(self):
        return ikcp_peeksize(self.ckcp)

    def set_output(self, output):
        self.output = output
        ikcp_setoutput(self.ckcp, output_wrapper)
