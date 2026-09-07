"""Compatibility entry point using the canonical maintained server."""
from omega_stenographer_mcp import *
def cli():
 import asyncio
 asyncio.run(main())
if __name__=='__main__':cli()
