import asyncio
import logging
from asyncio import StreamReader, StreamWriter
from typing import Tuple


class DataPipeError(Exception):
    """DataPipe Error"""


async def open_pipe(us_reader: StreamReader, us_writer: StreamWriter, ds_factory=None):
    logging.info("pipe open")
    ds_reader, ds_writer = await ds_factory()
    pipe = DataPipe((us_reader, us_writer), (ds_reader, ds_writer))
    try:
        await pipe.flow(2048, 3000)
    finally:
        logging.info("pipe closed")
        us_writer.is_closing() or us_writer.close()
        ds_writer.is_closing() or ds_writer.close()


class DataPipe:

    def __init__(self, upstream: Tuple[StreamReader, StreamWriter], downstream: Tuple[StreamReader, StreamWriter]):
        self.upstream = upstream
        self.downstream = downstream

    async def flow(self, size, timeout):
        us_reader, us_writer = self.upstream
        ds_reader, ds_writer = self.downstream

        async def flowing(reader, writer):
            try:
                while not reader.at_eof() and not writer.is_closing():
                    writer.write(await asyncio.wait_for(reader.read(size), timeout))
            except TimeoutError:
                logging.info("timeout while reading data")
            except DataPipeError:
                logging.exception("pipe error")

        tasks = {flowing(us_reader, ds_writer), flowing(ds_reader, us_writer)}
        waiting = asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        try:
            done, tasks = await waiting
        finally:
            for task in tasks:
                task.cancel()
