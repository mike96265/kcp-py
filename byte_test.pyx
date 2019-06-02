cdef extern from "strings.h":
    void *memcpy(void *str1, const void *str2, size_t n)

cdef extern from 'stdlib.h':
    void *malloc(size_t size);
    void free(void *ptr)

def byte_test(char* a, int size):
    cdef int i
    for i in range(size):
        print(a[i])
    a[1] = 97
