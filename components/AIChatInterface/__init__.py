# components/AIChatInterface/__init__.py

# Expose the backend class for easier importing
try:
    from .backend import AIChatInterfaceBackend
except ImportError as e:
    # This can happen if 'backend.py' doesn't exist or has issues
    # Or if this __init__.py is processed in a way that '.' relative import fails
    print(f"AIChatInterface: Could not import AIChatInterfaceBackend from .backend: {e}")
    # Optionally, re-raise or define a placeholder if critical
    AIChatInterfaceBackend = None

__all__ = ['AIChatInterfaceBackend']
