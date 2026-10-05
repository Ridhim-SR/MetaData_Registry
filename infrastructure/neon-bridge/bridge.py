"""TCP -> WebSocket bridge for Neon Postgres.

Listens on 127.0.0.1:5433 and tunnels raw Postgres wire bytes to
wss://<NEON_HOST>/v2 over port 443 (outbound 5432 is blocked upstream).
SSLRequest / GSSENCRequest are answered with 'N' locally: the WebSocket is TLS.
"""
import asyncio
import logging
import os
import struct

import websockets

NEON_HOST = os.environ["NEON_HOST"]
LISTEN_HOST = os.environ.get("BRIDGE_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("BRIDGE_PORT", "5433"))
WS_URL = f"wss://{NEON_HOST}/v2"

SSL_REQUEST = 80877103
GSSENC_REQUEST = 80877104

log = logging.getLogger("neon-bridge")


async def read_startup(reader, writer):
    """Return the first real startup packet, refusing SSL/GSS negotiation."""
    while True:
        header = await reader.readexactly(4)
        (length,) = struct.unpack("!I", header)
        body = await reader.readexactly(length - 4)
        if length == 8 and struct.unpack("!I", body)[0] in (SSL_REQUEST, GSSENC_REQUEST):
            writer.write(b"N")
            await writer.drain()
            continue
        return header + body


async def handle(reader, writer):
    peer = writer.get_extra_info("peername")
    try:
        startup = await read_startup(reader, writer)
        async with websockets.connect(WS_URL, max_size=None, compression=None,
                                      ping_interval=20, open_timeout=15) as ws:
            await ws.send(startup)

            async def tcp_to_ws():
                while data := await reader.read(65536):
                    await ws.send(data)
                await ws.close()

            async def ws_to_tcp():
                async for msg in ws:
                    writer.write(msg if isinstance(msg, bytes) else msg.encode())
                    await writer.drain()

            tasks = [asyncio.create_task(tcp_to_ws()), asyncio.create_task(ws_to_tcp())]
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
    except (asyncio.IncompleteReadError, ConnectionError, websockets.ConnectionClosed):
        pass
    except Exception as exc:  # never log payloads: they can contain credentials
        log.warning("connection %s failed: %s", peer, type(exc).__name__)
    finally:
        writer.close()


async def main():
    server = await asyncio.start_server(handle, LISTEN_HOST, LISTEN_PORT)
    log.info("listening on %s:%s -> %s", LISTEN_HOST, LISTEN_PORT, WS_URL)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main())
