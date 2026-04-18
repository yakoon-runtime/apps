class FastAPIWebSocketAdapter:

    def __init__(self, ws):
        self.ws = ws

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.ws.receive_text()
        except Exception:
            raise StopAsyncIteration from Exception

    async def send(self, data):
        await self.ws.send_text(data)

    async def recv(self):
        return await self.ws.receive_text()
