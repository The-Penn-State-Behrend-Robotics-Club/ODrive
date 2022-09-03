from typing import Optional, Union, Any

from .enums import CanProtocol, AxisState
from .database import db, streamed_messages, format_name, unformat_name
from .async_reader import AsyncResponseReader

import asyncio
import contextlib
import functools
import sys
import can
import cantools
from collections.abc import Iterable
from itertools import repeat, zip_longest

# Extra type imports, since python 3.9 adds typing to builtin types instead of using the ones from typing
if sys.version_info < (3, 9):
    from typing import Generator, AsyncGenerator, List, Dict
else:
    from collections.abc import Generator, AsyncGenerator
    List = list
    Dict = dict

# _canopen_error_message = "CANOpen was not suppored by ODrive the last time this module was updated"


class CANODrive:
    @classmethod
    @contextlib.asynccontextmanager
    async def on(
        cls,
        bus: can.Bus,
        mode: Optional[Union[int, CanProtocol]] = CanProtocol.SIMPLE,
        *args,
        return_to_idle: bool = True,
        **kwargs
    ) -> AsyncGenerator["CANODrive", None]:
        reader = AsyncResponseReader()
        notifier = can.Notifier(bus, [reader], loop=asyncio.get_running_loop())
        try:
            # Scan the bus for ODrives
            if mode == CanProtocol.SIMPLE:
                validation_queue = asyncio.Queue()

                async for message in reader.get_messages(
                    lambda id: id & 0x1F == db.get_message_by_name("Heartbeat").frame_id
                ):
                    validation_queue.put(asyncio.create_task())
            # elif mode == CanProtocol.CANOPEN:
            #     raise NotImplementedError(_canopen_error_message)
            else:
                raise ValueError("Unrecognized mode for ODrive CAN protocol")
        finally:
            notifier.stop()

    @classmethod
    @contextlib.asynccontextmanager
    async def allOn(
        cls,
        bus: can.Bus,
        mode: Optional[Union[int, CanProtocol]] = CanProtocol.SIMPLE,
        *args,
        return_to_idle: bool = True,
        **kwargs
    ) -> AsyncGenerator[List["CANODrive"], None]:
        # Scan the bus for ODrives
        raise NotImplementedError()

    @classmethod
    @contextlib.asynccontextmanager
    async def at(
        cls,
        id: int, bus: can.Bus,
        *args,
        return_to_idle: bool = True,
        **kwargs
    ) -> Generator["CANODrive", None, None]:
        reader = AsyncResponseReader()
        notifier = can.Notifier(bus, [reader], loop=asyncio.get_running_loop())
        try:
            async with cls(id, bus, reader, *args, **kwargs) as odrive:
                try:
                    yield odrive
                finally:
                    if return_to_idle:
                        try:
                            await odrive.set_axis_state(AxisState.IDLE)
                        except can.CanError:
                            pass
        finally:
            notifier.stop()

    @classmethod
    @contextlib.asynccontextmanager
    async def allAt(
        cls,
        ids: List[int], bus: can.Bus,
        *args,
        return_to_idle: bool = True,
        **kwargs
    ) -> Generator[List["CANODrive"], None, None]:
        reader = AsyncResponseReader()
        notifier = can.Notifier(bus, [reader], loop=asyncio.get_running_loop())
        try:
            if any(isinstance(arg, Iterable) for arg in args):
                # Different properties depending on the ODrive
                zippedArgs = zip_longest(
                    ids, repeat(bus), repeat(reader),
                    *(
                        arg if isinstance(arg, Iterable) else repeat(arg)
                        for arg
                        in args
                    )
                )
                zippedKwargs = [
                    {key: value for key, value in pairs[1:]}  # Slice removes ids, which was used to set the length
                    for pairs
                    in zip_longest(
                        ids,
                        *(
                            zip(repeat(key), value if isinstance(value, Iterable) else repeat(value))
                            for key, value
                            in kwargs.items()
                        )
                    )
                ]
                async with contextlib.AsyncExitStack() as stack:
                    odrives = [
                        await stack.enter_async_context(cls(*args, **kwargs))
                        for args, kwargs
                        in zip(zippedArgs, zippedKwargs)
                    ]
                    try:
                        print(odrives)
                        yield odrives
                    finally:
                        if return_to_idle:
                            for odrive in odrives:
                                try:
                                    await odrive.set_axis_state(AxisState.IDLE)
                                except can.CanError:
                                    pass
            else:
                # Same extra properties for all ODrives
                async with contextlib.AsyncExitStack() as stack:
                    odrives = [
                        await stack.enter_async_context(cls(id, bus, reader, *args, **kwargs))
                        for id
                        in ids
                    ]
                    try:
                        print(odrives)
                        yield odrives
                    finally:
                        if return_to_idle:
                            for odrive in odrives:
                                try:
                                    await odrive.set_axis_state(AxisState.IDLE)
                                except can.CanError:
                                    pass
        finally:
            notifier.stop()

    def __init__(
        self,
        id: int,
        bus: can.Bus,
        reader: AsyncResponseReader,
        mode: Optional[Union[int, CanProtocol]] = CanProtocol.SIMPLE,
        heartbeat_timeout: float = 500,
    ):
        # Connect to the CAN Bus
        self.bus = bus
        self.reader = reader

        # Set up mode and CAN Id
        self.mode = mode
        if mode == CanProtocol.SIMPLE:
            self.id = id
        else:
            raise ValueError("Unrecognized mode for ODrive CAN protocol")

        # Timeout before the ODrive is considered disconnected
        self.connected = False
        self.heartbeat_timeout = heartbeat_timeout
        self.heartbeat_timer = asyncio.create_task(asyncio.sleep(0))

        # Add remote methods, event handlers, and remote properties
        for message in db.messages:
            if message.name in streamed_messages:
                setattr(
                    self,
                    "update_" + format_name(message.name, True),
                    functools.partial(self.wait_for_update, message)
                )
                setattr(self, "_" + format_name(message.name, True) + "_event", asyncio.Event())
                for signal in message.signals:
                    setattr(self, format_name(signal.name), None)
            else:
                setattr(self, format_name(message.name), functools.partial(self.send_command, message))

    async def __aenter__(self):
        # Start monitoring the heartbeat and encoder
        for message in (db.get_message_by_name(name) for name in streamed_messages):
            setattr(
                self,
                "_" + format_name(message.name, True) + "_monitor",
                asyncio.create_task(self.update_stream(message))
            )

        await asyncio.wait_for(self.update_heartbeat(), timeout=5.0)

        return self

    async def __aexit__(self, exc_type, exc, tb):
        # Stop monitoring the heartbeat and encoder
        for message in (db.get_message_by_name(name) for name in streamed_messages):
            monitor = getattr(self, "_" + format_name(message.name, True) + "_monitor")
            monitor.cancel()
            try:
                await monitor
            except asyncio.CancelledError:
                pass

        self.heartbeat_timer.cancel()
        try:
            await self.heartbeat_timer
        except asyncio.CancelledError:
            pass
        self.connected = False

    def _make_id(self, msg_id: int) -> int:
        if self.mode == CanProtocol.SIMPLE:
            return self.id << 5 | msg_id
        else:
            raise ValueError("Unrecognized mode for ODrive CAN protocol")

    def _break_id(self, msg_id: int) -> int:
        if self.mode == CanProtocol.SIMPLE:
            return msg_id & 0x1F
        else:
            raise ValueError("Unrecognized mode for ODrive CAN protocol")

    async def send_command(
        self,
        message: cantools.db.Message,
        *args: List[Any],
        **kwargs: Dict[str, Any]
    ) -> Optional[dict]:
        if not self.connected:
            raise can.CanError(f"The ODrive at id {self.id} is not reachable")

        sending = len(message.signals) > 0 and message.name.startswith("Set_")

        if sending:
            formatted_args = {key.name: value for (key, value) in zip(message.signals, args)}
            formatted_kwargs = {unformat_name(key): value for (key, value) in kwargs.items()}
            print(formatted_args, formatted_kwargs)
            data = message.encode({**formatted_args, **formatted_kwargs})
        else:
            data = message.encode({})

        arbitration_id = self._make_id(message.frame_id)

        self.bus.send(can.Message(arbitration_id=arbitration_id, is_extended_id=False, data=data))

        if not sending:
            data = await self.reader.get_message(arbitration_id)
            msg = message.decode(data)
            return {format_name(key): value for (key, value) in msg.items()}

    async def wait_for_update(self, message: cantools.db.Message, ignore_timeout: bool = False):
        # Once using Python 3.10, this might be changed to a generator (since anext is added then)
        await getattr(self, "_" + format_name(message.name, True) + "_event").wait()
        if ignore_timeout:
            while not self.connected:
                await getattr(self, "_" + format_name(message.name, True) + "_event").wait()
        return self.connected

    async def update_stream(self, message: cantools.db.Message):
        async for stream_item in self.reader.get_messages(self._make_id(message.frame_id)):
            parsed_item = message.decode(stream_item.data)
            for signal in parsed_item:
                setattr(self, format_name(signal), parsed_item[signal])

            # Reset heartbeat timeout, if the stream is the heartbeat stream
            if (message.frame_id == db.get_message_by_name("Heartbeat").frame_id):
                self.connected = True

                self.heartbeat_timer.cancel()
                try:
                    await self.heartbeat_timer
                except asyncio.CancelledError:
                    pass
                self.heartbeat_timer = asyncio.create_task(self.timeout_heartbeat())

            getattr(self, "_" + format_name(message.name, True) + "_event").set()
            setattr(self, "_" + format_name(message.name, True) + "_event", asyncio.Event())

    async def timeout_heartbeat(self):
        await asyncio.sleep(self.heartbeat_timeout)
        self.connected = False

        for message in (db.get_message_by_name(name) for name in streamed_messages):
            # Notify all event listeners that the ODrive has disconnected
            getattr(self, "_" + format_name(message.name, True) + "_event").set()
            setattr(self, "_" + format_name(message.name, True) + "_event", asyncio.Event())
