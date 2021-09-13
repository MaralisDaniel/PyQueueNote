import asyncio


class Default:
    __queue = None

    def __init__(self):
        self.__queue = asyncio.Queue()

    async def add_task(self, message):
        await self.__queue.put(message)

    async def get_task(self):
        return await self.__queue.get()

    def complete(self):
        self.__queue.task_done()
