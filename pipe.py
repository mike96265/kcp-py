class Pipe:

    def __init__(self, reader, writer, size):
        self.reader = reader
        self.writer = writer
        self.size = size

    async def open(self):
        try:
            while not self.reader.at_eof():
                self.writer.write(await self.reader.read(self.size))
        finally:
            await self.writer.drain()
            self.writer.close()
