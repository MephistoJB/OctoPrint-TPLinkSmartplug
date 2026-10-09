"""Thread-owned asyncio loop for the upstream 2.0 device operations."""
import asyncio
import threading


class AsyncTaskWorker:
    def __init__(self):
        self._ready = threading.Event()
        self._closed = False
        self._thread = threading.Thread(target=self.run, name="tplink-device-worker", daemon=True)
        self._thread.start()
        self._ready.wait()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._ready.set()
        try:
            self.loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            if pending:
                self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.run_until_complete(self.loop.shutdown_default_executor())
            self.loop.close()

    def shutdown(self, **kwargs):
        if self._closed:
            return
        self._closed = True
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join()

    def run_coroutine_threadsafe(self, coro):
        if self._closed:
            coro.close()
            raise RuntimeError("The device worker has stopped.")
        return asyncio.run_coroutine_threadsafe(coro, self.loop)
