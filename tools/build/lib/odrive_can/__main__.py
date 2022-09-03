from . import CANODrive
import can

import IPython
import asyncio

bus = can.Bus("can0", bustype="socketcan")
axisID = 0x4

raise NotImplementedError("Neither the builtin repl or IPython supported a background asyncio loop when this file was written")

# This currently doesn't work since the library is asyncio based,
# but IPython does not handle being part of an asyncio event loop well.
# IPython's prompt-toolkit was recently updated to use asyncio, so it
# is possible that IPython will soon be updated to do the same.


async def main():
    async with CANODrive.at(axisID, bus) as odrive:
        IPython.start_ipython(user_ns={
            "asyncio": asyncio,
            "CANODrive": CANODrive,
            "can": can,
            "bus": bus,
            "odrive": odrive
        }, using="asyncio")

asyncio.run(main())
