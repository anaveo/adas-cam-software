import asyncio
import os
import can
import json
import logging
import binascii
logger = logging.getLogger('services.can_manager')


class CanManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(CanManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, can_config_path='../config/can_config.json', loop: asyncio.AbstractEventLoop = None):
        if not hasattr(self, 'initialized'):  # Ensures `__init__` only runs once
            self.msg_table = {}
            with open(can_config_path, 'r') as f:
                self.msg_table = json.load(f)

            self.loop = loop or asyncio.get_event_loop()
            self.id_callback_map = {}
            self.callback_id_map = {}
            self.can_interface = None
            self.is_running = False
            self.initialized = True

    def __call__(self):
        """Returns the same instance every time the class is called."""
        return self._instance

    async def start(self, bitrate=125000, interface='can0'):
        """
        Initializes and starts the CAN interface.
        """
        try:
            logger.info("Setting up CAN interface...")
            # Configure CAN interface (e.g., bitrate)
            os.system(f'sudo ip link set {interface} type can bitrate {bitrate}')
            os.system(f'sudo ifconfig {interface} up')

            # Set up the CAN interface with python-can
            self.can_interface = can.ThreadSafeBus(channel=interface, bustype='socketcan')

            # Define the filter for CAN IDs 0x100 to 0x4FF
            filters = [
                {"id": 0x100, "can_mask": 0x700, "extended": False},  # Filter for 0x100 to 0x4FF
            ]

            # Set the filters on the bus
            # self.can_interface.set_filters(filters)

            # Start an asyncio task for reading CAN messages
            self.loop.create_task(self.read_can_messages())
            self.is_running = True
            logger.info(f"CAN Bus started on interface {interface} with bitrate {bitrate}")
        except Exception as e:
            logger.error(f"Error starting CAN Bus on interface {interface}: {e}")

    async def stop(self, interface='can0'):
        """
        Stops the CAN interface.
        """
        if self.is_running:
            try:
                os.system(f'sudo ifconfig {interface} down')
                self.is_running = False
                logger.info(f"CAN Bus on interface {interface} stopped.")
            except Exception as e:
                logger.error(f"Error stopping CAN Bus: {e}")

    async def read_can_messages(self):
        """
        Asynchronously reads CAN messages from the bus and dispatches them to registered id_callback_map.
        """
        while self.is_running:
            try:
                # Receive message from the CAN bus
                message = self.can_interface.recv(timeout=1)  # Blocking read with timeout
                if message is not None:
                    logger.info(f"Received CAN message: {hex(message.arbitration_id)} - {binascii.hexlify(message.data)}")
                    await self.dispatch_message(message)
            except Exception as e:
                logger.error(f"Error reading CAN message: {e}")
            await asyncio.sleep(0.01)  # Avoids busy-waiting

    async def dispatch_message(self, message):
        """
        Dispatches received CAN message to registered id_callback_map based on the message ID.
        """
        message_id = message.arbitration_id
        if message_id in self.id_callback_map:
            for callback in self.id_callback_map[message_id]:
                try:
                    # Call the callback asynchronously
                    await callback(message)
                except Exception as e:
                    logger.error(f"Error in callback for message ID {hex(message_id)}: {e}")
        else:
            logger.warning(f"No callback registered for CAN message ID {hex(message_id)}")

    def register_callback_single_id(self, message_id, callback):
        """
        Registers a callback for a specific CAN message ID.
        """
        if callback not in self.callback_id_map:
            self.callback_id_map[callback] = []
        self.callback_id_map[callback].append(message_id)
        if message_id not in self.id_callback_map:
            self.id_callback_map[message_id] = []
        self.id_callback_map[message_id].append(callback)
        logger.info(f"Callback registered for CAN message ID {hex(message_id)}")

    def register_callback_range_id(self, message_id_low, message_id_high, callback):
        """
        Registers a callback for a range of CAN message IDs.
        """
        if callback not in self.callback_id_map:
            self.callback_id_map[callback] = []
        for (message_id) in range(message_id_low, message_id_high+1):
            self.callback_id_map[callback].append(message_id)
            if message_id not in self.id_callback_map:
                self.id_callback_map[message_id] = []
            self.id_callback_map[message_id].append(callback)
        logger.info(f"Callback registered for CAN message ID range {hex(message_id_low)} to {hex(message_id_high)}")

    def unregister_callback(self, callback):
        """
        Unregisters a callback for a specific CAN message ID.
        """
        if callback in self.callback_id_map:
            for message_id in self.callback_id_map[callback]:
                self.id_callback_map[message_id].remove(callback)
                if not self.id_callback_map[message_id]:
                    del self.id_callback_map[message_id]
            del self.callback_id_map[callback]
            logger.info("Callback unregistered")

    async def send_can_message(self, message_id, data, interface='can0'):
        """
        Sends a CAN message.
        """
        try:
            message = can.Message(arbitration_id=message_id, data=data, is_extended_id=False)
            self.can_interface.send(message)
            logger.info(f"Sent CAN message ID {message_id}: {data}")
        except Exception as e:
            logger.error(f"Error sending CAN message ID {hex(message_id)}: {e}")
