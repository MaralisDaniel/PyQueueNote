class AbstractQueue:
    async def add_task(self, message: str) -> None:
        raise NotImplemented

    async def get_task(self) -> str:
        raise NotImplemented

    def complete(self) -> None:
        raise NotImplemented
