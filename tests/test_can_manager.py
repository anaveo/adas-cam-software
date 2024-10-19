import time

import pytest
import multiprocessing
from unittest import mock
from unittest.mock import MagicMock
from src.services.can_manager import CanManager
import logging

# Configure basic logging for the tests
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@pytest.fixture
def can_manager():
    """Fixture to create and start the CAN manager process with mocked CAN interface."""
    with mock.patch('can.interface.Bus') as mock_bus:
        manager = CanManager()
        manager.bus = mock_bus  # Mocking the CAN bus interface
        manager.start()
        yield manager
        manager.stop()


def test_validate_can_id_valid_id(can_manager):
    can_id = 0x123

    try:
        can_manager._validate_can_id(can_id)
    except MyError:
        pytest.fail("Unexpected error ..")


def test_validate_can_id_too_large_id(can_manager):
    can_id = 0x800

    with pytest.raises(ValueError):
        can_manager._validate_can_id(can_id)


def test_validate_can_id_non_int_id(can_manager):
    can_id = 'ABBA'

    with pytest.raises(TypeError):
        can_manager._validate_can_id(can_id)


def test_register_subscriber_single_id_new_id(can_manager):
    """Test that a subscriber is correctly registered for a NEW single CAN ID."""
    queue = multiprocessing.Queue()
    can_id = 0x123

    # Register the queue as a subscriber for can_id
    can_manager.register_subscriber_single_id(can_id, queue)

    # Assert that the queue has been correctly added to the id_subscriber_map
    assert can_id in can_manager.id_subscriber_map
    assert queue in can_manager.id_subscriber_map[can_id]

    # Assert that the can_id has been correctly added to the subscriber_id_map
    assert queue in can_manager.subscriber_id_map
    assert can_id in can_manager.subscriber_id_map[queue]


def test_register_subscriber_single_id_existing_id(can_manager):
    """Test that a subscriber is correctly registered for a EXISTING single CAN ID."""
    queue = multiprocessing.Queue()
    queue2 = multiprocessing.Queue()
    can_id = 0x123

    # Register the queue as a subscriber for can_id
    can_manager.register_subscriber_single_id(can_id, queue)
    can_manager.register_subscriber_single_id(can_id, queue2)

    # Assert that both queues have been correctly added to the id_subscriber_map
    assert can_id in can_manager.id_subscriber_map
    assert queue in can_manager.id_subscriber_map[can_id]
    assert queue2 in can_manager.id_subscriber_map[can_id]

    # Assert that the can_id has been correctly added to the subscriber_id_map
    assert queue in can_manager.subscriber_id_map
    assert queue2 in can_manager.subscriber_id_map
    assert can_id in can_manager.subscriber_id_map[queue]
    assert can_id in can_manager.subscriber_id_map[queue2]


def test_register_subscriber_single_id_invalid_id(can_manager):
    """Test that a subscriber is correctly registered for a EXISTING single CAN ID."""
    queue = multiprocessing.Queue()
    can_id = 0x800

    # Assert that the can_id is not added to the id_subscriber_map
    assert can_id not in can_manager.id_subscriber_map

    # Assert that the queue is not added to the subscriber_id_map
    assert queue not in can_manager.subscriber_id_map


def test_register_subscriber_range_id_new_id(can_manager):
    """Test that a subscriber is correctly registered for a range of NEW CAN IDs."""
    queue = multiprocessing.Queue()
    can_id_low = 0x123
    can_id_high = 0x133

    # Register the queue as a subscriber for can_ids
    can_manager.register_subscriber_range_id(can_id_high, can_id_low, queue)

    # Assert that the queue has been correctly added to the id_subscriber_map
    for can_id in range(can_id_low, can_id_high+1):
        assert can_id in can_manager.id_subscriber_map
        assert queue in can_manager.id_subscriber_map[can_id]

    # Assert that the can_ids have been correctly added to the subscriber_id_map
    assert queue in can_manager.subscriber_id_map
    for can_id in range(can_id_low, can_id_high+1):
        assert can_id in can_manager.subscriber_id_map[queue]


def test_register_subscriber_range_id_existing_id(can_manager):
    """Test that a subscriber is correctly registered for a range of EXISTING CAN IDs."""
    queue = multiprocessing.Queue()
    queue2 = multiprocessing.Queue()
    can_id_low = 0x123
    can_id_high = 0x133

    # Register the queue2 as a subscriber for can_ids
    can_manager.register_subscriber_range_id(can_id_high, can_id_low, queue)
    can_manager.register_subscriber_range_id(can_id_high, can_id_low, queue2)

    # Assert that the queue has been correctly added to the id_subscriber_map
    for can_id in range(can_id_low, can_id_high+1):
        assert can_id in can_manager.id_subscriber_map
        assert queue in can_manager.id_subscriber_map[can_id]
        assert queue2 in can_manager.id_subscriber_map[can_id]

    # Assert that the can_ids have been correctly added to the subscriber_id_map
    assert queue in can_manager.subscriber_id_map
    assert queue2 in can_manager.subscriber_id_map
    for can_id in range(can_id_low, can_id_high+1):
        assert can_id in can_manager.subscriber_id_map[queue]
        assert can_id in can_manager.subscriber_id_map[queue2]


def test_register_subscriber_range_id_mix_id(can_manager):
    """Test that a subscriber is correctly registered for a range of EXISTING CAN IDs."""
    queue = multiprocessing.Queue()
    queue2 = multiprocessing.Queue()
    can_id_low1 = 0x123
    can_id_high1 = 0x133
    can_id_low2 = 0x130
    can_id_high2 = 0x140

    # Register the queues as a subscriber for can_ids
    can_manager.register_subscriber_range_id(can_id_high1, can_id_low1, queue)
    can_manager.register_subscriber_range_id(can_id_high2, can_id_low2, queue2)

    # Assert that the queue has been correctly added to the id_subscriber_map
    for can_id in range(can_id_low1, can_id_high1+1):
        assert can_id in can_manager.id_subscriber_map
        assert queue in can_manager.id_subscriber_map[can_id]
    for can_id in range(can_id_low2, can_id_high2+1):
        assert can_id in can_manager.id_subscriber_map
        assert queue2 in can_manager.id_subscriber_map[can_id]

    # Assert that the can_ids have been correctly added to the subscriber_id_map
    assert queue in can_manager.subscriber_id_map
    assert queue2 in can_manager.subscriber_id_map
    for can_id in range(can_id_low1, can_id_high1+1):
        assert can_id in can_manager.subscriber_id_map[queue]
    for can_id in range(can_id_low2, can_id_high2+1):
        assert can_id in can_manager.subscriber_id_map[queue2]


def test_register_subscriber_range_id_invalid_id_too_large(can_manager):
    """Test that a subscriber is correctly registered for a EXISTING single CAN ID."""
    queue = multiprocessing.Queue()
    can_id_low = 0x799
    can_id_high = 0x800

    # Register the queue as a subscriber for can_ids
    with pytest.raises(ValueError):
        can_manager.register_subscriber_range_id(can_id_high, can_id_low, queue)

    # Assert that the queue has not been added to the id_subscriber_map
    for can_id in range(can_id_low, can_id_high+1):
        assert can_id not in can_manager.id_subscriber_map

    # Assert that the can_ids have not been added to the subscriber_id_map
    assert queue not in can_manager.subscriber_id_map


def test_register_subscriber_range_id_invalid_id_swapped(can_manager):
    """Test that a subscriber is correctly registered for a EXISTING single CAN ID."""
    queue = multiprocessing.Queue()
    can_id_low = 0x200
    can_id_high = 0x190

    # Ensure registration fails
    with pytest.raises(ValueError):
        can_manager.register_subscriber_range_id(can_id_high, can_id_low, queue)

    # Assert that the queue has not been added to the id_subscriber_map
    for can_id in range(can_id_high, can_id_low+1):
        assert can_id not in can_manager.id_subscriber_map

    # Assert that the can_ids have not been added to the subscriber_id_map
    assert queue not in can_manager.subscriber_id_map


def test_deregister_subscriber(can_manager):
    """Test that a subscriber is correctly removed from a specific CAN ID."""
    queue = multiprocessing.Queue()
    can_id = 0x123

    # Register the queue as a subscriber for can_id
    can_manager.register_subscriber_single_id(can_id, queue)

    # Remove the queue from can_id
    can_manager.deregister_subscriber(can_id, queue)

    # Assert that the queue has been removed from id_subscriber_map
    assert can_id not in can_manager.id_subscriber_map or queue not in can_manager.id_subscriber_map[can_id]

    # Assert that the can_id has been removed from subscriber_id_map
    assert queue not in can_manager.subscriber_id_map or can_id not in can_manager.subscriber_id_map[queue]


def test_deregister_subscriber_unknown_id(can_manager):
    """Test that a subscriber is correctly removed from a specific CAN ID."""
    queue = multiprocessing.Queue()
    can_id = 0x123
    can_id2 = 0x133

    # Register the queue as a subscriber for can_id
    can_manager.register_subscriber_single_id(can_id, queue)

    # Remove the queue from can_id
    with pytest.raises(ValueError):
        can_manager.deregister_subscriber(can_id2, queue)


def test_deregister_subscriber_unknown_subscriber(can_manager):
    """Test that a subscriber is correctly removed from a specific CAN ID."""
    queue = multiprocessing.Queue()
    queue2 = multiprocessing.Queue()
    can_id = 0x123

    # Register the queue as a subscriber for can_id
    can_manager.register_subscriber_single_id(can_id, queue)

    # Remove the queue from can_id
    with pytest.raises(ValueError):
        can_manager.deregister_subscriber(can_id, queue2)

