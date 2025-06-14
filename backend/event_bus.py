import asyncio
import logging
from collections import defaultdict
from typing import Callable, DefaultDict, List, Any, Coroutine

logger = logging.getLogger(__name__)

class EventBus:
    def __init__(self):
        self._subscribers: DefaultDict[str, List[Callable[..., Coroutine[Any, Any, None]]]] = defaultdict(list)
        self._async_subscribers: DefaultDict[str, List[Callable[..., Coroutine[Any, Any, None]]]] = defaultdict(list)

    def subscribe(self, event_type: str, callback: Callable[..., Coroutine[Any, Any, None]]):
        """
        Subscribes an asynchronous callback to an event type.
        """
        if not asyncio.iscoroutinefunction(callback):
            raise ValueError("Callback must be an async function (coroutine).")

        if callback not in self._subscribers[event_type]:
            self._subscribers[event_type].append(callback)
            logger.debug(f"Callback {callback.__name__} subscribed to event '{event_type}'")
        else:
            logger.debug(f"Callback {callback.__name__} already subscribed to event '{event_type}'")

    def unsubscribe(self, event_type: str, callback: Callable[..., Coroutine[Any, Any, None]]):
        """
        Unsubscribes an asynchronous callback from an event type.
        """
        if callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)
            logger.debug(f"Callback {callback.__name__} unsubscribed from event '{event_type}'")
            # Clean up event_type key if no subscribers are left
            if not self._subscribers[event_type]:
                del self._subscribers[event_type]
        else:
            logger.debug(f"Callback {callback.__name__} not found for event '{event_type}', no action taken.")

    async def publish(self, event_type: str, *args: Any, **kwargs: Any):
        """
        Publishes an event to all subscribed asynchronous callbacks.
        Callbacks are executed concurrently.
        """
        if event_type not in self._subscribers:
            logger.debug(f"No subscribers for event '{event_type}', publish is a no-op.")
            return

        callbacks_to_execute = self._subscribers[event_type][:] # Create a copy in case of modifications during iteration

        tasks = []
        for callback in callbacks_to_execute:
            try:
                # Check if the callback is still in the original list before scheduling
                # This handles cases where a callback might have been unsubscribed by another callback
                if callback in self._subscribers.get(event_type, []):
                    tasks.append(callback(*args, **kwargs))
            except Exception as e:
                logger.error(f"Error preparing callback {callback.__name__} for event '{event_type}': {e}", exc_info=True)

        if tasks:
            logger.debug(f"Publishing event '{event_type}' to {len(tasks)} subscribers with args: {args}, kwargs: {kwargs}")
            await asyncio.gather(*tasks, return_exceptions=True) # return_exceptions=True to prevent one failing task from stopping others
        else:
            logger.debug(f"No valid tasks to execute for event '{event_type}' after filtering.")

# Example Usage (can be removed or kept for module testing)
async def example_listener_1(data):
    logger.info(f"Example Listener 1 received: {data}")
    await asyncio.sleep(0.1) # Simulate async work

async def example_listener_2(message, user_id=None):
    logger.info(f"Example Listener 2 received message: '{message}' from user_id: {user_id}")
    await asyncio.sleep(0.2)

async def example_listener_3_unsubscribes(event_bus, event_type, self_callback):
    logger.info(f"Example Listener 3 triggered. It will unsubscribe itself.")
    event_bus.unsubscribe(event_type, self_callback)


async def main_example():
    logging.basicConfig(level=logging.DEBUG)
    bus = EventBus()

    # Subscribe listeners
    await bus.subscribe("user_login", example_listener_1)
    await bus.subscribe("user_login", example_listener_2)

    # For listener 3, it needs a reference to itself to unsubscribe
    # One way is to define it and then subscribe it.
    # However, direct self-reference in definition is tricky.
    # A common pattern is to pass the bus and event_type if a callback needs to unsubscribe itself.
    # Let's define a wrapper or ensure listener3 can be referenced.

    # To make example_listener_3_unsubscribes work, we need its own reference.
    # This is a bit contrived for an example, but shows unsubscribe during publish.
    # We'll subscribe it directly.
    # await bus.subscribe("special_event", lambda: example_listener_3_unsubscribes(bus, "special_event", example_listener_3_unsubscribes_ref))
    # This lambda approach for self-unsubscription is complex.
    # A simpler way for a callback to unsubscribe itself is if it has a unique ID or if the callback itself is the identifier.
    # The current implementation uses the callback function object itself as the identifier.

    # Let's try a simpler self-unsubscribing listener for demonstration.
    async def self_unsub_listener(event_bus_instance, current_event_type):
        logger.info(f"Self-unsubscribing listener triggered for {current_event_type}. Unsubscribing...")
        event_bus_instance.unsubscribe(current_event_type, self_unsub_listener) # Pass the function itself

    await bus.subscribe("logout", self_unsub_listener)


    # Publish events
    logger.info("Publishing 'user_login' event...")
    await bus.publish("user_login", {"user_id": 123, "username": "alice"}, user_id="AliceFromKwargs") # Mixed args/kwargs

    logger.info("Publishing 'user_login' again (listener 1 & 2 should still be active)...")
    await bus.publish("user_login", {"user_id": 456, "username": "bob"})

    # Publish to special_event to trigger self-unsubscription
    # This requires a bit of setup for the callback to know itself
    # For simplicity, let's make a callback that unsubscribes another one.
    async def remover_callback(bus_instance, event_to_clear, callback_to_remove):
        logger.info(f"Remover callback triggered. Will remove {callback_to_remove.__name__} from {event_to_clear}")
        bus_instance.unsubscribe(event_to_clear, callback_to_remove)

    await bus.subscribe("cleanup_event", lambda: remover_callback(bus, "user_login", example_listener_1))

    logger.info("Publishing 'cleanup_event' (will remove example_listener_1 from 'user_login')...")
    await bus.publish("cleanup_event")

    logger.info("Publishing 'user_login' again (listener 1 should be gone)...")
    await bus.publish("user_login", {"user_id": 789, "username": "charlie"})

    # Test self-unsubscribing listener
    logger.info("Publishing 'logout' event (will trigger self-unsubscription)...")
    await bus.publish("logout", bus, "logout") # Pass bus and event type for self-unsubscription

    logger.info("Publishing 'logout' event again (self_unsub_listener should be gone)...")
    await bus.publish("logout", bus, "logout")


    logger.info("Publishing 'non_existent_event'...")
    await bus.publish("non_existent_event", "some_data")


if __name__ == "__main__":
    #asyncio.run(main_example()) # Commented out, meant for direct testing of the module
    pass
