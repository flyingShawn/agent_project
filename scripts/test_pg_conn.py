import asyncio
import asyncpg
import socket

def test_raw_tcp():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(('192.168.1.212', 5432))
        s.send(b'\x00\x00\x00\x08\x04\xd2\x16\x2f')
        data = s.recv(1024)
        print(f'Raw TCP response ({len(data)} bytes): {data[:50]}')
        s.close()
    except Exception as e:
        print(f'Raw TCP failed: {e}')

async def test_with_connect_params():
    try:
        conn = await asyncpg.connect(
            host='192.168.1.212',
            port=5432,
            user='agent',
            password='agent123',
            database='agent_chat',
            ssl=None,
            timeout=10,
        )
        print('Connected with explicit params!')
        await conn.close()
    except Exception as e:
        print(f'Explicit params failed: {type(e).__name__}: {e}')

async def test_with_statement_cache_size():
    try:
        conn = await asyncpg.connect(
            host='192.168.1.212',
            port=5432,
            user='agent',
            password='agent123',
            database='agent_chat',
            ssl=False,
            statement_cache_size=0,
            timeout=10,
        )
        print('Connected with statement_cache_size=0!')
        await conn.close()
    except Exception as e:
        print(f'statement_cache_size=0 failed: {type(e).__name__}: {e}')

test_raw_tcp()
asyncio.run(test_with_connect_params())
asyncio.run(test_with_statement_cache_size())
