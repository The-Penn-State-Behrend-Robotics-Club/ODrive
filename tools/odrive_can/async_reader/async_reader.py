from typing import Callable, Any, Union

import asyncio
from can import Message, Listener
import sys
import warnings

if sys.version_info < (3, 9):
    from typing import AsyncGenerator, AsyncIterator
else:
    from collections.abc import AsyncGenerator, AsyncIterator

# Submit this file as a PR to python-can when ready
# Also add docs


class AsyncResponseReader(Listener):
    """
    A message distributor for use with :mod:`asyncio`

    Allows a caller to subscribe to a certain message id, waiting for either one
    occurrence or all occurences of it.

    Use :meth:`get_message` to listen for a single response

    Use :meth:`get_messages` to get an async stream of messages that can be used
    in a `for` loop
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        self._listeners: asyncio.Queue[(Callable[[int], bool], asyncio.Future)]

        if "loop" in kwargs:
            warnings.warn(
                "The 'loop' argument is deprecated since python-can 4.0.0 "
                "and has no effect starting with Python 3.10",
                DeprecationWarning,
            )
            if sys.version_info < (3, 10):
                self._listeners = asyncio.Queue(loop=kwargs["loop"])
                return

        self._listeners = asyncio.Queue()

    def on_message_received(self, msg: Message) -> None:
        """
        Distributes the provided message to all subscribed listeners

        Must only be called inside an event loop!
        """
        # Wake up all listeners that accept the current message id.
        for i in range(self._listeners.qsize()):
            # Get one of the waiting listeners
            filter, listener = self._listeners.get_nowait()
            # Ensure that the listener wasn't already canceled
            if not listener.done():
                # Check if the listener accepts the given id
                if filter(msg.arbitration_id):
                    # Provide the message to the waiting listener
                    listener.set_result(msg)
                else:
                    # Recycle the listener until the next message
                    self._listeners.put_nowait((filter, listener))

    async def get_message(
        self,
        id: Union[int, Callable[[int], bool]] = lambda: True
    ) -> Message:
        """
        Returns the next message matching the provided id or predicate

        :param id: An arbitration id or predicate used to select a message
        """
        if type(id) == int:
            target_id = id
            id = lambda id: id == target_id  # noqa: E731
        listener = asyncio.get_running_loop().create_future()
        await self._listeners.put((id, listener))
        return await listener

    async def get_messages(
        self,
        id: Union[int, Callable[[int], bool]] = lambda: True
    ) -> AsyncGenerator[Message, None]:
        """
        Returns all following messages with a matching id or predicate

        :param id: An arbitration id or predicate used to select messages
        """
        if type(id) == int:
            target_id = id
            id = lambda id: id == target_id  # noqa: E731
        while True:
            listener = asyncio.get_running_loop().create_future()
            await self._listeners.put((id, listener))
            yield await listener

    def __aiter__(self) -> AsyncIterator[Message]:
        return self.get_messages()

    def clear(self) -> None:
        """
        Clears all pending listeners
        """
        for i in range(self._listeners.qsize()):
            # Get one of the waiting listeners
            filter, listener = self._listeners.get_nowait()
            # Ensure that the listener wasn't already canceled
            if not listener.done():
                listener.set_exception(asyncio.CancelledError)

    def stop(self) -> None:
        """
        Clears all pending listeners and prohibits future listeners
        """
        self.clear()
        # TODO: Prohibit future listeners
