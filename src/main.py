import os
import json
import multiprocessing
import logging.config
import signal
import time
from logging.handlers import QueueHandler, QueueListener

# Device stats sender
from src.device_stats_sender import DeviceStatsSender

# Video Streamer
from src.video_streamer import VideoStreamer

# Communication managers
from src.services.can_manager import CanManager

from src.services.udp_logger import UDPLogger
import logging

logger = logging.getLogger('main')


def setup_logging(config_path='../config/logging_config.json', log_queue=None):
    # Get the absolute path of the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, config_path)

    with open(config_path, 'r') as f:
        config = json.load(f)
        logging.config.dictConfig(config)
        logger.info("Logging setup from config file complete.")

    # If a log_queue is provided, set up a QueueHandler for the main logger
    if log_queue:
        queue_handler = QueueHandler(log_queue)
        logger.addHandler(queue_handler)
        logger.setLevel(logging.DEBUG)
        logger.info("Logging queue for other processes initialized.")

def main():
    # Command queue for sending CAN messages
    can_command_queue = multiprocessing.Queue()

    # Event for signalling process termination
    stop_event = multiprocessing.Event()

    # Setup logging
    log_queue = multiprocessing.Queue()
    setup_logging(config_path='../config/logging_config.json', log_queue=log_queue)
    listener = QueueListener(log_queue, *logging.getLogger('main').handlers)
    listener.start()

    # Initialize CAN manager
    can_manager = CanManager(can_command_queue)
    can_manager.start()

    # Initialize and start the stats sender in a separate process
    stats_sender_process = multiprocessing.Process(target=DeviceStatsSender(can_command_queue, stop_event, log_queue).start)
    stats_sender_process.start()

    # Initialize and start the video streamer in a separate process with the queue for CAN messages
    # camera_control_queue = multiprocessing.Queue()
    # video_streamer_process = multiprocessing.Process(target=VideoStreamer, args=(command_queue, camera_control_queue, stop_event))
    # video_streamer_process.start()

    # Link video streamer with camera control CAN command
    # can_manager.register_subscriber_single_id(0x120, camera_control_queue)

    try:
        while True:
            time.sleep(1)  # Simulate work in the main thread

    except KeyboardInterrupt:
        logger.info("Stopping CAN manager and subscribers...")

    finally:
        # Signal processes to terminate
        stop_event.set()

        # Clean up processes
        stats_sender_process.join()

        # Clean up CAN manager
        can_manager.stop()

        # Stop the listener
        listener.stop()


if __name__ == '__main__':
    main()
