#! /usr/bin/env python3
from yaseeker import cli

def run():
    if sys.version_info >= (3, 7):
        asyncio.run(main())
    else:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(main())
        finally:
            loop.close()
