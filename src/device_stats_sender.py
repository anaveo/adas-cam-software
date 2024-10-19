import logging
import psutil
import time
from multiprocessing import Queue, Event
from logging.handlers import QueueHandler

logger = logging.getLogger('device_stats_sender')


class DeviceStatsSender:

    def __init__(self, can_out_queue: Queue, stop_event: Event, log_queue: Queue):
        super().__init__()
        self._running = True
        self.stop_event = stop_event # Event to signal process termination
        self.can_out_queue = can_out_queue  # Queue for control commands

        # Set up QueueHandler for logging
        queue_handler = QueueHandler(log_queue)
        logger.addHandler(queue_handler)
        logger.setLevel(logging.INFO)  # Set appropriate logging level

    def start(self):
        try:
            self._running = True

            logger.info("DeviceStatsSender started")

            self._send_device_stats()  # Start sending stats synchronously

        except Exception as e:
            logger.error(f"Error starting DeviceStatsSender: {e}")
            self.stop()

    def _send_device_stats(self):
        """
        Send device health/fault data every 10 seconds.
        """
        try:
            while self._running:
                logger.info("Sending device stats...")
                core_temp = int(psutil.sensors_temperatures()['cpu_thermal'][0].current)
                cpu_usage = int(psutil.cpu_percent(interval=None))

                # Send CAN message based on health/fault conditions
                if 60 < core_temp <= 70:
                    logger.warning("High temperature detected")
                    self.can_out_queue.put([1])
                elif core_temp > 70:
                    logger.error("Critical temperature reached. Shutting down...")
                    self.stop()
                elif cpu_usage > 90:
                    logger.warning("High CPU usage detected")
                    self.can_out_queue.put([6])
                else:
                    self.can_out_queue.put([0])

                self.can_out_queue.put([core_temp, cpu_usage])

                # Sleep for 10 seconds
                self.stop_event.wait(10)  # Use event wait for blocking

        except Exception as e:
            logger.error(f"Error in sending device stats: {e}")

    def stop(self):
        """
        Stop the device stats sending and clean up resources.
        """
        self._running = False
        logger.info("DeviceStatsSender stopped")
