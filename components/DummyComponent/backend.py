# This is a placeholder backend for DummyComponent.
# It allows the component discovery mechanism to import a module,
# preventing a ModuleNotFoundError.
# This component might be frontend-only, or its backend is not yet implemented.

# To truly make it frontend-only, the component registry would ideally
# check for the presence of 'backend_class' in manifest.json before
# attempting to import a backend module.

# Placeholder class (optional, but might prevent AttributeError if registry
# tries to getattr)
class DummycomponentBackend:
    def __init__(self, *args, **kwargs):
        print("DummycomponentBackend initialized (placeholder)")

    def update(self, inputs):
        print(f"DummycomponentBackend update called with: {inputs}")
        return {}

    def get_state(self):
        print("DummycomponentBackend get_state called")
        return {}

logger = None
try:
    import logging
    logger = logging.getLogger(__name__)
    if logger:
        logger.info("DummyComponent backend placeholder loaded.")
except ImportError:
    pass

if __name__ == '__main__':
    if logger:
        logger.info(
            "DummyComponent backend placeholder script executed directly."
        )
    else:
        print(
            "DummyComponent backend placeholder script executed directly "
            "(logging not available)."
        )
