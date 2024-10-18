import asyncio
import logging
from src.services.can_manager import CanManager
import psutil
logger = logging.getLogger('device_stats_sender')


class DeviceStatsSender:

    def __init__(self):
        super().__init__()
        self._can_manager = None
        self._running = False
        self._task = None  # Track the task to ensure it's running

    async def start(self):
        try:
            self._can_manager = CanManager()
            self._running = True

            # Clear any existing faults
            await self._can_manager.send_can_message(message_id=0x320, data=[0])

            # Schedule the device stats sending task
            self._task = asyncio.create_task(self._send_device_stats())

            logger.info("DeviceStatsSender started")
        except Exception as e:
            logger.error(f"Error starting DeviceStatsSender: {e}")
            await self.stop()

    async def _send_device_stats(self):
        """
        Asynchronously send device health/fault data every 10 seconds.
        """
        try:
            while self._running:
                logger.info("Sending device stats...")
                core_temp = int(psutil.sensors_temperatures()['cpu_thermal'][0].current)
                cpu_usage = int(psutil.cpu_percent(interval=1))

                # Send CAN message based on health/fault conditions
                if 60 < core_temp <= 70:
                    logger.warning("High temperature detected")
                    await self._can_manager.send_can_message(message_id=0x320, data=[1])
                elif core_temp > 70:
                    logger.error("Critical temperature reached. Shutting down...")
                    await self.stop()
                elif cpu_usage > 90:
                    logger.warning("High CPU usage detected")
                    await self._can_manager.send_can_message(message_id=0x320, data=[6])
                else:
                    await self._can_manager.send_can_message(message_id=0x320, data=[0])

                await self._can_manager.send_can_message(message_id=0x220, data=[core_temp, cpu_usage])

                await asyncio.sleep(10)  # Simulating sending device stats every 10 seconds
        except asyncio.CancelledError:
            # Handle the task being cancelled properly here
            raise  # Let the exception propagate to notify asyncio that it has been cancelled
        except Exception as e:
            logger.error(f"Error in sending device stats: {e}")

    async def stop(self):
        """
        Stop the device stats sending and clean up resources.
        """
        self._running = False
        if self._task:
            self._task.cancel()  # Cancel the task if it's running
            try:
                await self._task  # Wait for the task to finish
            except asyncio.CancelledError:
                pass
        logger.info("DeviceStatsSender stopped")
