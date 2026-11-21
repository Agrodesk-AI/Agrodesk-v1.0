from typing import Protocol


class SmsProvider(Protocol):
    async def send(self, *, phone: str, body: str) -> None: ...
