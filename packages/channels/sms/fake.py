import logging

log = logging.getLogger("sms.fake")


class FakeSmsProvider:
    """Dev SMS: logs the body so OTPs can be read from the API log in local dev."""

    async def send(self, *, phone: str, body: str) -> None:
        log.warning("[FAKE SMS] to=%s body=%s", phone, body)
