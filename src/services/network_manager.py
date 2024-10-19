import asyncio
import socket

import logging
logger = logging.getLogger('services.network_manager')


class UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, port, manager):
        self.port = port
        self.transport = None
        self.manager = manager

    def connection_made(self, transport):
        self.transport = transport
        self.transport.get_extra_info('socket').setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF,
                                                           128)  # Example buffer size
        logger.info(f"UDP Listening on port {self.port}")

    def datagram_received(self, data, addr):
        message = data.decode('utf-8')
        logger.info(f"UDP Received {message} from {addr} on port {self.port}")
        # Call the registered callback for this port
        self.manager.handle_udp_data(self.port, message, addr)

    def send_data(self, data, addr):
        if self.transport:
            self.transport.sendto(data, addr)
        else:
            logger.warning(f"UDP Transport is not available for port {self.port}")


class TCPProtocol(asyncio.Protocol):
    def __init__(self, manager):
        self.manager = manager
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        logger.info(f"TCP Connection established from {transport.get_extra_info('peername')}")

    def data_received(self, data):
        message = data.decode()
        logger.info(f"TCP Received {message}")
        # Call the registered callback for this TCP connection
        for callback in self.manager.tcp_callbacks:
            callback(data, self.transport.get_extra_info('peername'))

    def connection_lost(self, exc):
        logger.info(f"TCP Connection lost: {exc}")
        self.transport = None

    def send_data(self, data):
        if self.transport:
            self.transport.write(data)
        else:
            logger.warning("TCP Transport is not available")


class NetworkManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(NetworkManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, loop: asyncio.AbstractEventLoop = None):
        if not hasattr(self, 'initialized'):  # Ensures `__init__` only runs once
            self.loop = loop or asyncio.get_event_loop()
            self.udp_ports = set()
            self.udp_protocols = {}
            self.udp_transports = {}
            self.udp_callbacks = {}  # {port: [callback1, callback2, ...]}
            self.tcp_callbacks = []  # List of callback functions for TCP connections
            self.initialized = True

    def __call__(self):
        """Returns the same instance every time the class is called."""
        return self._instance

    async def start(self):
        port_success_count = 0
        for port in self.udp_ports:
            port_success = await self._create_udp_protocol_for_port(port)
            if port_success:
                port_success_count += 1
        logger.info("NetworkManager started")
        logger.info(f"{port_success_count} of {len(self.udp_ports)} UDP ports are up and running")

    async def _create_udp_protocol_for_port(self, port):
        try:
            protocol = UDPProtocol(port, self)
            self.udp_protocols[port] = protocol
            transport, _ = await self.loop.create_datagram_endpoint(
                lambda: protocol,  # Pass protocol instance to lambda
                local_addr=('0.0.0.0', port)
            )
            self.udp_transports[port] = transport
            return True
        except Exception as e:
            logger.error(f"Error creating UDP protocol for port {port}: {e}")
            return False

    async def add_udp_port(self, port):
        try:
            if port not in self.udp_ports:
                self.udp_ports.add(port)
                await self._create_udp_protocol_for_port(port)
                logger.info(f"UDP Port {port} added")
            else:
                logger.info(f"UDP Port {port} is already managed by this server")
        except Exception as e:
            logger.error(f"Error adding UDP port {port}: {e}")

    async def remove_udp_port(self, port):
        try:
            if port in self.udp_ports:
                self.udp_ports.remove(port)
                transport = self.udp_transports.pop(port, None)
                if transport:
                    transport.close()
                    logger.info(f"UDP Port {port} removed")
                protocol = self.udp_protocols.pop(port, None)
                if protocol:
                    # If protocol has extra cleanup, it should be handled here
                    pass
                self.udp_callbacks.pop(port, None)  # Remove id_subscriber_map for this port
            else:
                logger.warning(f"UDP Port {port} is not managed by this server")
        except Exception as e:
            logger.error(f"Error removing UDP port {port}: {e}")

    def register_udp_callback(self, port, callback):
        """Register a callback function for a specific UDP port."""
        if port not in self.udp_callbacks:
            self.udp_callbacks[port] = []  # Initialize as an empty list
        self.udp_callbacks[port].append(callback)
        logger.info(f"Callback registered for port {port}")

    def unregister_udp_callback(self, port, callback):
        if port in self.udp_callbacks:
            self.udp_callbacks[port].remove(callback)
            if not self.udp_callbacks[port]:
                del self.udp_callbacks[port]
            logger.info(f"Callback unregistered for port {port}")

    def handle_udp_data(self, port, data, addr):
        """Handle the incoming data from the UDP port."""
        if port in self.udp_callbacks:
            callback = self.udp_callbacks[port]
            logger.info(f"Handling data from {addr} on port {port}: {data}")
            callback(data, addr)  # Call the registered callback
        else:
            logger.warning(f"No callback registered for port {port}")

    def register_tcp_callback(self, callback):
        self.tcp_callbacks.append(callback)

    def unregister_tcp_callback(self, callback):
        self.tcp_callbacks.remove(callback)

    async def start_tcp_server(self, host='0.0.0.0', port=8888):
        try:
            server = await asyncio.start_server(
                lambda: TCPProtocol(self),
                host, port
            )
            logger.info(f"TCP Server started on {host}:{port}")
            async with server:
                await server.serve_forever()
        except Exception as e:
            logger.error(f"Error starting TCP server on {host}:{port}: {e}")

    def send_udp_data(self, port, data, addr):
        try:
            if port in self.udp_protocols:
                self.udp_protocols[port].send_data(data, addr)
            else:
                logger.warning(f"UDP Port {port} is not managed by this server")
        except Exception as e:
            logger.error(f"Error sending UDP data on port {port}: {e}")

    def send_tcp_data(self, data, transport):
        try:
            if transport:
                transport.write(data)
            else:
                logger.warning("TCP Transport is not available")
        except Exception as e:
            logger.error(f"Error sending TCP data: {e}")

    async def stop(self):
        try:
            for transport in self.udp_transports.values():
                transport.close()
            await asyncio.sleep(1)  # Give some time for transports to close
            logger.info("NetworkManager stopped")
        except Exception as e:
            logger.error(f"Error stopping NetworkManager: {e}")
