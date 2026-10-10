"""Request state for one DataJ source lifetime, independent of statistics patch."""
import threading


class SourceBudget:
    """Inject one instance into adapters that belong to the same application."""
    def __init__(self):
        self.lock = threading.Lock()
        self.request_lock = threading.Lock()
        self.http_slots = threading.BoundedSemaphore(3)
        self.background_slot = threading.BoundedSemaphore(1)
        self.background_next_request = 0.0
        self.background_wait = threading.Event()
        self.inflight = {}
        self.next_request = 0.0
