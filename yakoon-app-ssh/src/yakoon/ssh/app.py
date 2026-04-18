import asyncio

import asyncssh

from yakoon.client.runtime import Client, create_runtime
from yakoon.client.terminal import SSHTerminal
from yakoon.platform.transport import LocalTransport


class SSHSession(asyncssh.SSHServerSession):

    def __init__(self, host):
        self.host = host

    def connection_made(self, chan):

        reader = chan
        writer = chan

        self.terminal = SSHTerminal(reader, writer)

    def shell_requested(self):
        return True

    def session_started(self):
        asyncio.create_task(self.run())

    # SSH liefert Input hier rein
    def data_received(self, data, datatype):
        self.terminal.data_received(data, datatype)

    async def run(self):
        transport = LocalTransport(self.host)
        client = Client(transport)

        await client.run(self.terminal)


class SSHServer(asyncssh.SSHServer):

    def __init__(self, host):
        self.host = host

    def begin_auth(self, username):
        return False  #  keine Auth nötig

    def session_requested(self):
        return SSHSession(self.host)


async def run():

    host = await create_runtime()

    from pathlib import Path

    BASE_DIR = Path(__file__).resolve().parent
    KEY_PATH = BASE_DIR / "ssh_keys/ssh_host_key"

    # build ssh key
    # ssh-keygen -t rsa -f ssh_host_key -N ""
    # .

    await asyncssh.create_server(
        lambda: SSHServer(host),
        "",
        8022,
        server_host_keys=[str(KEY_PATH)],
    )

    # test on :
    # ssh -p 8022 localhost
    # .

    print("SSH server running on port 8022")

    await asyncio.Future()
