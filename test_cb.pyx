cdef extern from 'stdio.h':
    int printf(char *format, ...);

cdef extern from 'stdlib.h':
    void *malloc(size_t size);
    void free(void *ptr)

cdef extern from "string.h":
    void *memcpy(void *str1, const void *str2, size_t n)


cdef class A:
    cdef char* buffer
    cdef object cb

    def __cinit__(self, cb):
        self.cb = cb
        self.buffer = <char*> malloc(sizeof(char) * 10)
        if self.buffer == NULL:
            raise MemoryError()

        memcpy(self.buffer, "1234567890", 10)

    def __dealloc__(self):
        free(self.buffer)

    cpdef out(self):
        self.test(self.buffer, 10)

    cdef test(self, char *buffer, int size):
        cdef char* o
        o = <char*> malloc(sizeof(char) * 10)
        memcpy(o, buffer, 10)
        self.cb(o)
        free(o)
