import psutil
import asyncio
import logging
from src.services.can_manager import CanManager

logger = logging.getLogger('model.diagnostic_model')


class DeviceStatsSender:

    def __init__(self):
        super().__init__()
        self._can_manager = None
        self._running = False

    async def start(self):
        try:
            self._can_manager = CanManager()
            self._running = True

            # Schedule the device stats sending task
            asyncio.create_task(self._send_device_stats())

            logger.info("Successfully started")
        except Exception as e:
            logger.error(f"Failed to start: {e}")
            await self.stop()

    async def _send_device_stats(self):
        """
        Asynchronously send device health/fault data every 10 seconds.
        """
        while self._running:
            try:
                core_temp = psutil.sensors_temperatures()['cpu_thermal'][0].current
                cpu_usage = psutil.cpu_percent(interval=1)

                # Send CAN message based on health/fault conditions
                if core_temp > 60:
                    await self._can_manager.send_can_message(message_id=0x320, message=[1])
                elif cpu_usage > 90:
                    await self._can_manager.send_can_message(message_id=0x320, message=[6])

                await self._can_manager.send_can_message(message_id=0x220, message=[core_temp, cpu_usage])

                # Wait for 10 seconds before sending the next stats
                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Error in sending device stats: {e}")
                break

    async def stop(self):
        """
        Stop the device stats sending and clean up resources.
        """
        self._running = False
        logger.info("Successfully stopped")

