import logging
import socket
import asyncio


class UDPLogger(logging.Handler):
    """
    Custom logging handler that sends logs over UDP asynchronously.
    """

    def __init__(self, ip, port):
        super().__init__()
        self.address = (ip, port)
        self.loop = asyncio.get_event_loop()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._is_closed = False  # Track if the logger is closed

    def emit(self, record):
        log_entry = self.format(record)

        if not self._is_closed:
            try:
                asyncio.run_coroutine_threadsafe(self._send_log(log_entry), self.loop)
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    logging.error("Attempted to log but the event loop is closed.")
                else:
                    logging.error(f"Error while logging: {e}")

    async def _send_log(self, log_entry):
        if self._is_closed:
            return  # Don't send if closed

        try:
            # Send log message over UDP
            self.sock.sendto(log_entry.encode('utf-8'), self.address)
        except OSError as e:
            logging.error(f"Logging error: {e}")
            self.handleError(None)  # Handle the error appropriately

    def close(self):
        """
        Clean up resources and close the socket.
        """
        self._is_closed = True
        self.sock.close()  # Close the UDP socket
        super().close()  # Call the parent close method
