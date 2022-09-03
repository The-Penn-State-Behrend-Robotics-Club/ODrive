from can import Bus, Notifier
from odrive_can.async_reader import AsyncResponseReader
import asyncio

__all__ = ["test_async_reader"]


def test_async_reader() -> None:
    async def main() -> None:
        reader = AsyncResponseReader()
        notifier = Notifier(bus, [reader], loop=asyncio.get_running_loop())

        print("ODrive heartbeat:")
        print(await reader.get_message(axisID << 5 | 0x01))
        for i in range(2):
            encoder_monitor = asyncio.create_task(reader.get_message(axisID << 5 | 0x09))
            while not encoder_monitor.done():
                print("ODrive heartbeat:")
                print(await reader.get_message(axisID << 5 | 0x01))
            print("ODrive encoder:")
            print(encoder_monitor.result())

        notifier.stop()

    bus = Bus("can0", bustype="socketcan")
    axisID = 0x04

    asyncio.run(main())


if __name__ == "__main__":
    test_async_reader()
