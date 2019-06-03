class A:
    _a = 0

    @property
    def a(self):
        return A._a

    @a.setter
    def a(self, a):
        A.a = a
