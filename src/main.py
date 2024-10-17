import os
import json
import logging.config
import asyncio
import signal

# Device stats sender
from src.device_stats_sender import DeviceStatsSender

# Communication managers
from src.services.network_manager import NetworkManager
from src.services.can_manager import CanManager

import logging
logger = logging.getLogger('main')


def setup_logging(config_path=None):
    if config_path is None:
        # Get the absolute path of the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Construct the absolute path to the logging_config.json file
        config_path = os.path.join(script_dir, '../config/logging_config.json')

    with open(config_path, 'r') as f:
        config = json.load(f)
        logging.config.dictConfig(config)
        logging.info("Logging setup from config file complete.")


class Application:
    def __init__(self):
        self.device_stats_sender = None
        self.net_manager = None
        self.can_manager = None
        self.loop = asyncio.get_event_loop()

    async def start(self):
        # Set up necessary configurations
        script_dir = os.path.dirname(os.path.abspath(__file__))
        can_config_path = os.path.join(script_dir, '../config/can_config.json')

        # Initialize network manager
        self.net_manager = NetworkManager()
        await self.net_manager.start()

        # Initialize CAN manager
        self.can_manager = CanManager(can_config_path=can_config_path)
        await self.can_manager.start()
        self.can_manager.register_callback_single_id(message_id=0x100, callback=self.shutdown_callback)

        # Initialize and start the device stats sender
        self.device_stats_sender = DeviceStatsSender()
        await self.device_stats_sender.start()

        logger.info("Application started. Running device stats sender asynchronously.")

        # Keep the event loop running
        await asyncio.Event().wait()  # Keep the asyncio event loop alive

    async def stop(self):
        # Cleanly stop all managers and services
        if self.device_stats_sender:
            await self.device_stats_sender.stop()
        if self.net_manager:
            await self.net_manager.stop()
        if self.can_manager:
            await self.can_manager.stop()

        logger.info("Resources stopped successfully.")

    async def shutdown_callback(self):
        """
        Callback function to handle shutdown via CAN message or signal.
        """
        logger.info("Shutdown signal received. Stopping all services...")

        # Stop all resources
        await self.stop()

        # Stop the event loop
        logger.info("Shutting down event loop.")
        self.loop.stop()  # Gracefully stop the loop

        logger.info("Application shutdown complete.")


async def main():
    # Create the application instance
    app = Application()

    # Register a signal handler for clean shutdown (e.g., Ctrl+C or kill signal)
    def handle_signal(signal, frame):
        logger.info(f"Received signal {signal}. Initiating shutdown...")
        asyncio.create_task(app.shutdown_callback())  # Trigger the shutdown callback

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Start the application
    await app.start()


if __name__ == '__main__':
    # Set up logging
    setup_logging(config_path='../config/logging_config.json')

    # Create an asyncio event loop and run the application
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        # Ensure proper cleanup
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())  # Clean up async generators
        finally:
            loop.close()
        logger.info("Application exited.")
