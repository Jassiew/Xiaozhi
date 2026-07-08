import asyncio
from aiomysql import create_pool

async def test():
    pool = await create_pool(host='localhost', port=3306, user='root', password='root', db='student_monitor')
    pool.close()
    print('aiomysql连接成功')

asyncio.run(test())
