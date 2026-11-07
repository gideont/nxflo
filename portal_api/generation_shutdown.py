"""Drain at durable boundaries; never interrupt an in-flight paid request."""
import signal

_requested = False


class WorkerDraining(Exception):
    pass


def request_stop(signum=None, frame=None):
    global _requested
    _requested = True


def requested():
    return _requested


def checkpoint():
    if _requested:
        raise WorkerDraining()


def install_handlers():
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
