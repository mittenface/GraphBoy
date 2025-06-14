import unittest
from unittest.mock import AsyncMock # unittest.mock.call removed

from backend.event_bus import EventBus

class TestEventBus(unittest.IsolatedAsyncioTestCase): # Changed to IsolatedAsyncioTestCase

    async def asyncSetUp(self): # Renamed from setUp and made async
        self.bus = EventBus()

    async def test_subscribe_and_publish_single_listener(self): # Made async
        listener = AsyncMock()
        event_type = "test_event"

        self.bus.subscribe(event_type, listener)
        await self.bus.publish(event_type, "data1", key="value1") # Used await

        listener.assert_called_once_with("data1", key="value1")

    async def test_publish_no_subscribers(self): # Made async
        event_type = "unheard_event"
        try:
            await self.bus.publish(event_type, "should_not_be_seen") # Used await
        except Exception as e:
            self.fail(
                f"Publishing to an event with no subscribers raised an exception: {e}"
            )

    async def test_unsubscribe_listener(self): # Made async
        listener = AsyncMock()
        event_type = "unsubscribe_event"

        self.bus.subscribe(event_type, listener)
        await self.bus.publish(event_type, "first_call") # Used await
        listener.assert_called_once_with("first_call")

        self.bus.unsubscribe(event_type, listener)
        await self.bus.publish(event_type, "second_call") # Used await
        listener.assert_called_once()

    async def test_multiple_subscribers_for_same_event(self): # Made async
        listener1 = AsyncMock()
        listener2 = AsyncMock()
        event_type = "multi_listener_event"

        self.bus.subscribe(event_type, listener1)
        self.bus.subscribe(event_type, listener2)

        await self.bus.publish(event_type, "shared_data", source="test") # Used await

        listener1.assert_called_once_with("shared_data", source="test")
        listener2.assert_called_once_with("shared_data", source="test")

    async def test_publish_with_different_args_and_kwargs(self): # Made async
        listener = AsyncMock()
        event_type = "args_kwargs_event"

        self.bus.subscribe(event_type, listener)

        await self.bus.publish(event_type, 1, 2, three=3, four="four") # Used await
        listener.assert_called_once_with(1, 2, three=3, four="four")

    def test_subscribe_non_async_callback_raises_error(self): # Kept as sync
        def non_async_listener(data):
            pass # pragma: no cover

        event_type = "non_async_event"
        with self.assertRaises(ValueError) as context:
            self.bus.subscribe(event_type, non_async_listener)
        self.assertIn("Callback must be an async function", str(context.exception))

    async def test_unsubscribe_from_within_callback(self): # Made async
        bus = EventBus()
        event_type = "internal_unsubscribe"

        listener_A_mock = AsyncMock(name="ListenerA")
        listener_B_mock = AsyncMock(name="ListenerB")

        async def listener_A_unsubscribes_B(data):
            await listener_A_mock(data) # This is a call to an AsyncMock, now awaited
            bus.unsubscribe(event_type, listener_B)

        async def listener_B(data): # pragma: no cover
            await listener_B_mock(data) # This is a call to an AsyncMock, now awaited

        bus.subscribe(event_type, listener_A_unsubscribes_B)
        bus.subscribe(event_type, listener_B)

        await bus.publish(event_type, "payload1") # Used await
        listener_A_mock.assert_called_once_with("payload1")

        await bus.publish(event_type, "payload2") # Used await
        self.assertEqual(listener_A_mock.call_count, 2)
        listener_A_mock.assert_called_with("payload2")

        # Check if listener_B was called with "payload2"
        # Since unittest.mock.call was removed, we inspect mock_calls directly.
        called_with_payload2 = False
        for mc in listener_B_mock.mock_calls:
            # mc is a tuple: (name, args, kwargs)
            if mc[1] == ("payload2",): # Check if args match ("payload2",)
                called_with_payload2 = True
                break
        self.assertFalse(
            called_with_payload2,
            "Listener B should not have been called with 'payload2'"
        )

        if listener_B_mock.called:
            self.assertEqual(listener_B_mock.call_count, 1,
                             "Listener B should have been called at most once.")
            # Check if it was called with "payload1"
            called_with_payload1 = False
            for mc in listener_B_mock.mock_calls:
                 if mc[1] == ("payload1",):
                    called_with_payload1 = True
                    break
            self.assertTrue(
                called_with_payload1,
                "Listener B should have been called with 'payload1' if called at all."
            )

        self.assertNotIn(listener_B, bus._subscribers.get(event_type, []))

    async def test_multiple_event_types(self): # Made async
        listener_event1 = AsyncMock()
        listener_event2 = AsyncMock()

        self.bus.subscribe("event1", listener_event1)
        self.bus.subscribe("event2", listener_event2)

        await self.bus.publish("event1", "data_for_event1") # Used await
        await self.bus.publish("event2", "data_for_event2") # Used await

        listener_event1.assert_called_once_with("data_for_event1")
        listener_event2.assert_called_once_with("data_for_event2")
        self.assertEqual(listener_event1.call_count, 1)
        self.assertEqual(listener_event2.call_count, 1)

    def test_unsubscribe_non_existent_listener(self): # Kept as sync
        listener = AsyncMock()
        event_type = "event_with_no_such_listener"

        try:
            self.bus.unsubscribe(event_type, listener)
            self.bus.unsubscribe("non_existent_event_type", listener)
        except Exception as e: # pragma: no cover
            self.fail(
                f"Unsubscribing a non-existent listener raised an exception: {e}"
            )

        real_listener = AsyncMock()
        self.bus.subscribe(event_type, real_listener)
        self.bus.unsubscribe(event_type, real_listener)
        self.assertNotIn(event_type, self.bus._subscribers)

    async def test_subscribe_same_listener_multiple_times_is_idempotent(self): # Made async
        listener = AsyncMock()
        event_type = "idempotent_subscribe_event"

        self.bus.subscribe(event_type, listener)
        self.bus.subscribe(event_type, listener)

        self.assertEqual(len(self.bus._subscribers[event_type]), 1)

        await self.bus.publish(event_type, "data") # Used await
        listener.assert_called_once_with("data")

if __name__ == '__main__': # pragma: no cover
    unittest.main()
