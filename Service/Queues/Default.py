import asyncio
from .AbstractQueue import AbstractQueue


class Default(AbstractQueue):
    __queue = None

    def __init__(self):
        self.__queue = asyncio.Queue()

    async def add_task(self, message: str) -> None:
        await self.__queue.put(message)

    async def get_task(self) -> str:
        return await self.__queue.get()

    def complete(self) -> None:
        self.__queue.task_done()
