import asyncio
import unittest
from unittest.mock import AsyncMock, call # Changed from Mock to AsyncMock for async callbacks

from backend.event_bus import EventBus

class TestEventBus(unittest.TestCase):

    def setUp(self):
        self.bus = EventBus()
        # Attempt to get existing event loop or create a new one if none exists for the current context
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

    def tearDown(self):
        # If we created a new loop in setUp, we should close it.
        # This is a simplified cleanup; robust loop management can be complex.
        # For unittest with asyncio, IsolatedAsyncioTestCase (Python 3.8+) handles this better.
        if hasattr(self, '_new_loop_created') and self._new_loop_created:
             self.loop.close()
             asyncio.set_event_loop(None)


    def run_async(self, coro):
        # Helper to run async functions if not using IsolatedAsyncioTestCase
        # For Python 3.8+ unittest.IsolatedAsyncioTestCase is preferred for async tests
        return self.loop.run_until_complete(coro)

    def test_subscribe_and_publish_single_listener(self):
        listener = AsyncMock()
        event_type = "test_event"

        self.bus.subscribe(event_type, listener)
        self.run_async(self.bus.publish(event_type, "data1", key="value1"))

        listener.assert_called_once_with("data1", key="value1")

    def test_publish_no_subscribers(self):
        # This test essentially checks that publish doesn't raise an error
        # and completes successfully.
        event_type = "unheard_event"
        try:
            self.run_async(self.bus.publish(event_type, "should_not_be_seen"))
        except Exception as e:
            self.fail(f"Publishing to an event with no subscribers raised an exception: {e}")

    def test_unsubscribe_listener(self):
        listener = AsyncMock()
        event_type = "unsubscribe_event"

        self.bus.subscribe(event_type, listener)
        self.run_async(self.bus.publish(event_type, "first_call"))
        listener.assert_called_once_with("first_call")

        self.bus.unsubscribe(event_type, listener)
        self.run_async(self.bus.publish(event_type, "second_call"))
        # Listener should still only have been called once (the first time)
        listener.assert_called_once()

    def test_multiple_subscribers_for_same_event(self):
        listener1 = AsyncMock()
        listener2 = AsyncMock()
        event_type = "multi_listener_event"

        self.bus.subscribe(event_type, listener1)
        self.bus.subscribe(event_type, listener2)

        self.run_async(self.bus.publish(event_type, "shared_data", source="test"))

        listener1.assert_called_once_with("shared_data", source="test")
        listener2.assert_called_once_with("shared_data", source="test")

    def test_publish_with_different_args_and_kwargs(self):
        listener = AsyncMock()
        event_type = "args_kwargs_event"

        self.bus.subscribe(event_type, listener)

        self.run_async(self.bus.publish(event_type, 1, 2, three=3, four="four"))
        listener.assert_called_once_with(1, 2, three=3, four="four")

    def test_subscribe_non_async_callback_raises_error(self):
        def non_async_listener(data):
            pass # pragma: no cover

        event_type = "non_async_event"
        with self.assertRaises(ValueError) as context:
            self.bus.subscribe(event_type, non_async_listener)
        self.assertIn("Callback must be an async function", str(context.exception))

    def test_unsubscribe_from_within_callback(self):
        # This test requires an event loop that can run the async setup and publish.
        # We'll use run_async to manage the async parts.

        bus = EventBus() # Local bus for this test
        event_type = "internal_unsubscribe"

        listener_A_mock = AsyncMock(name="ListenerA")
        listener_B_mock = AsyncMock(name="ListenerB")

        async def listener_A_unsubscribes_B(data):
            listener_A_mock(data)
            bus.unsubscribe(event_type, listener_B) # Unsubscribe B

        # Listener B is just a simple mock
        async def listener_B(data): # pragma: no cover (covered by mock)
            listener_B_mock(data)

        bus.subscribe(event_type, listener_A_unsubscribes_B)
        bus.subscribe(event_type, listener_B)

        self.run_async(bus.publish(event_type, "payload1"))

        listener_A_mock.assert_called_once_with("payload1")

        # Behavior of listener_B_mock during the first publish:
        # The EventBus.publish creates tasks for all callbacks in a copy of the subscriber list.
        # It then checks `if callback in self._subscribers.get(event_type, [])` before appending the task.
        # If listener_A_unsubscribes_B executes and removes listener_B before listener_B's task
        # is prepared in the loop, listener_B_mock might not be called.
        # This depends on asyncio.gather's scheduling.
        # We will check listener_B_mock's call status after the first publish,
        # but the most critical assertion is its behavior on the *second* publish.

        # Second publish: Only A should be called, as B was unsubscribed.
        self.run_async(bus.publish(event_type, "payload2"))

        self.assertEqual(listener_A_mock.call_count, 2)
        listener_A_mock.assert_called_with("payload2")

        # Assert that listener_B was not called with "payload2".
        # And it should have been called at most once (with "payload1").
        called_with_payload2 = False
        for mock_call in listener_B_mock.mock_calls:
            if mock_call == call("payload2"): # Correct way to check call arguments
                called_with_payload2 = True
                break
        self.assertFalse(called_with_payload2, "Listener B should not have been called with 'payload2'")

        if listener_B_mock.called:
            self.assertEqual(listener_B_mock.call_count, 1, "Listener B should have been called at most once.")
            listener_B_mock.assert_any_call("payload1") # Use assert_any_call if it was called once

        self.assertNotIn(listener_B, bus._subscribers.get(event_type, []))


    def test_multiple_event_types(self):
        listener_event1 = AsyncMock()
        listener_event2 = AsyncMock()

        self.bus.subscribe("event1", listener_event1)
        self.bus.subscribe("event2", listener_event2)

        self.run_async(self.bus.publish("event1", "data_for_event1"))
        self.run_async(self.bus.publish("event2", "data_for_event2"))

        listener_event1.assert_called_once_with("data_for_event1")
        listener_event2.assert_called_once_with("data_for_event2")
        self.assertEqual(listener_event1.call_count, 1) # Ensure it wasn't called by event2
        self.assertEqual(listener_event2.call_count, 1) # Ensure it wasn't called by event1

    def test_unsubscribe_non_existent_listener(self):
        listener = AsyncMock()
        event_type = "event_with_no_such_listener"

        # Try to unsubscribe a listener that was never subscribed
        try:
            self.bus.unsubscribe(event_type, listener)
            # Also try to unsubscribe from an event type that doesn't exist
            self.bus.unsubscribe("non_existent_event_type", listener)
        except Exception as e: # pragma: no cover
            self.fail(f"Unsubscribing a non-existent listener raised an exception: {e}")

        # Ensure no error if event_type list becomes empty and is deleted
        real_listener = AsyncMock()
        self.bus.subscribe(event_type, real_listener)
        self.bus.unsubscribe(event_type, real_listener) # list becomes empty
        self.assertNotIn(event_type, self.bus._subscribers) # check internal state for cleanup

    def test_subscribe_same_listener_multiple_times_is_idempotent(self):
        listener = AsyncMock()
        event_type = "idempotent_subscribe_event"

        self.bus.subscribe(event_type, listener)
        self.bus.subscribe(event_type, listener) # Subscribe again with the same listener

        self.assertEqual(len(self.bus._subscribers[event_type]), 1) # Should only be one entry

        self.run_async(self.bus.publish(event_type, "data"))
        listener.assert_called_once_with("data")


# For Python 3.8+ and to avoid manual loop management, use IsolatedAsyncioTestCase
# Example:
# class TestEventBusAsync(unittest.IsolatedAsyncioTestCase):
#     async def asyncSetUp(self):
#         self.bus = EventBus()

#     async def test_subscribe_and_publish_single_listener_async(self):
#         listener = AsyncMock()
#         event_type = "test_event_async"

#         # await self.bus.subscribe(event_type, listener) # subscribe is sync
#         self.bus.subscribe(event_type, listener)

#         await self.bus.publish(event_type, "data_async", key_async="value_async")

#         listener.assert_called_once_with("data_async", key_async="value_async")

if __name__ == '__main__': # pragma: no cover
    unittest.main()
