from multiprocessing import Queue, Process
import can
import time
import logging
import threading
import os
import binascii

logger = logging.getLogger('services.can_manager')


class CanManager(Process):
    def __init__(self, command_queue: Queue):
        super().__init__()
        self.id_subscriber_map = {}  # Map from CAN ID to list of queues (subscribers)
        self.subscriber_id_map = {}  # Map from queue (subscriber) to list of CAN IDs
        self.is_running = False
        self.bus = None

        # CAN output queue
        self.command_queue = command_queue

        # Create a lock for thread-safe operations
        self.lock = threading.Lock()

        # Create threads for receiving and sending CAN messages
        self.receiver_thread = threading.Thread(target=self._receive_can_messages)
        self.sender_thread = threading.Thread(target=self._send_can_messages)

    def start(self, bitrate=125000, interface='can0'):
        """Start the CAN transceiver threads."""
        self.is_running = True
        logger.info("Setting up CAN interface...")
        # Configure CAN interface (e.g., bitrate)
        os.system(f'sudo ip link set {interface} type can bitrate {bitrate}')
        os.system(f'sudo ifconfig {interface} up')

        # Initialize your CAN interface (e.g., socketcan, see python-can documentation)
        self.bus = can.interface.Bus(channel=interface, bustype='socketcan')  # Replace with your config

        self.receiver_thread.start()
        self.sender_thread.start()

    def stop(self, interface='can0'):
        """Stop the CAN transceiver threads."""
        self.is_running = False

        # Signal the threads to wake up and exit
        self.command_queue.put(None)  # Ensure the sender thread exits if waiting for a message

        # Wait for both threads to complete
        self.receiver_thread.join()
        self.sender_thread.join()

        # Clean up CAN interface
        try:
            os.system(f'sudo ifconfig {interface} down')
            self.is_running = False
            logger.info(f"CAN Bus on interface {interface} stopped.")
        except Exception as e:
            logger.error(f"Error stopping CAN Bus: {e}")

        logger.info("CAN Manager stopped and resources cleaned up.")

    def _validate_can_id(self, can_id: int):
        """Validates the CAN ID for the standard 11-bit identifier."""
        if not isinstance(can_id, int):
            raise TypeError(f"CAN ID must be an integer, got {type(can_id)}")
        if can_id < 0 or can_id >= 0x800:
            raise ValueError(f"CAN ID {hex(can_id)} is out of range (must be a 11-bit identifier)")

    def register_subscriber_single_id(self, can_id: int, queue: Queue):
        """Add a subscriber for a specific CAN ID."""
        self._validate_can_id(can_id)

        with self.lock:  # Ensure thread safety
            # Add the queue to id_subscriber_map
            if can_id not in self.id_subscriber_map:
                self.id_subscriber_map[can_id] = set()
            self.id_subscriber_map[can_id].add(queue)

            # Add the CAN ID to subscriber_id_map for the specific queue
            if queue not in self.subscriber_id_map:
                self.subscriber_id_map[queue] = set()
            self.subscriber_id_map[queue].add(can_id)

            logger.info(f"Subscriber queue registered for CAN ID {hex(can_id)}")

    def register_subscriber_range_id(self, can_id_high: int, can_id_low: int, queue: Queue):
        """Add a subscriber for a range of CAN IDs."""
        self._validate_can_id(can_id_high)
        self._validate_can_id(can_id_low)

        if can_id_high < can_id_low:
            raise ValueError(f"Lower CAN ID {can_id_low} greater than upper CAN ID {can_id_high}")

        with self.lock:  # Ensure thread safety
            for can_id in range(can_id_low, can_id_high + 1):
                if can_id not in self.id_subscriber_map:
                    self.id_subscriber_map[can_id] = set()
                self.id_subscriber_map[can_id].add(queue)

            if queue not in self.subscriber_id_map:
                self.subscriber_id_map[queue] = set()
            for can_id in range(can_id_low, can_id_high + 1):
                self.subscriber_id_map[queue].add(can_id)

            logger.info(f"Callback registered for CAN message ID range {hex(can_id_high)} to {hex(can_id_low)}")

    def deregister_subscriber(self, can_id: int, queue: Queue):
        """Remove a subscriber from a specific CAN ID."""
        with self.lock:  # Ensure thread safety
            if can_id not in self.id_subscriber_map or queue not in self.subscriber_id_map:
                raise ValueError(f"CAN ID {can_id} or queue {queue} not previously registered")

            # Remove the queue from id_subscriber_map
            if can_id in self.id_subscriber_map:
                if queue in self.id_subscriber_map[can_id]:
                    self.id_subscriber_map[can_id].remove(queue)

                # If there are no more subscribers for this CAN ID, clean it up
                if not self.id_subscriber_map[can_id]:
                    del self.id_subscriber_map[can_id]

            # Remove the CAN ID from subscriber_id_map
            if queue in self.subscriber_id_map:
                if can_id in self.subscriber_id_map[queue]:
                    self.subscriber_id_map[queue].remove(can_id)

                # If there are no more CAN IDs for this queue, clean it up
                if not self.subscriber_id_map[queue]:
                    del self.subscriber_id_map[queue]

            logger.info(f"Subscriber queue {queue} deregistered for CAN ID {hex(can_id)}")

    def _receive_can_messages(self):
        """Reads CAN messages from the bus and dispatches them to specified queues."""
        while self.is_running:
            try:
                message = self.bus.recv(timeout=1)  # Blocking read with timeout
                if message is not None:
                    can_id = message.arbitration_id
                    logger.info(f"Received CAN message: {hex(can_id)} - {binascii.hexlify(message.data)}")
                    if can_id in self.id_subscriber_map:
                        for queue in self.id_subscriber_map[can_id]:
                            queue.put(message)
            except Exception as e:
                logger.error(f"Error reading/processing CAN message: {e}")

    def _send_can_messages(self):
        """Sends a CAN message."""
        while self.is_running:
            try:
                message = self.command_queue.get(timeout=1)  # Blocking read with timeout
                if message is not None:
                    can_id = message.arbitration_id
                    logger.info(f"Sending CAN message: {hex(can_id)} - {binascii.hexlify(message.data)}")
                    self.bus.send(message)
            except Exception as e:
                logger.error(f"Error sending/processing CAN message: {e}")
