import asyncio
import time
import cv2
import numpy as np

from picamera2 import Picamera2, MappedArray
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput, FfmpegOutput

from src.services.can_manager import CanManager

import logging

logger = logging.getLogger('video_streamer')


class VideoStreamer:

    def __init__(self, receiver_ip, receiver_port, frame_width=200, frame_height=200, fps=30):
        super().__init__()

        # Stream parameters
        self.receiver_ip = receiver_ip
        self.receiver_port = receiver_port

        # Video parameters
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.fps = fps

        self.camera = None
        self.encoder = None

        self._task = None
        self._running = False
        self.strongest_lines = []
        self.process_hz = 0

    @staticmethod
    def _get_strongest_lines(edges):
        """
        Detects lines using HoughLinesP and returns the two strongest lines.
        If fewer than two lines are detected, the undetected lines are set to None.
        """

        # Detect lines using HoughLinesP
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=50, maxLineGap=20)

        # Check if lines are detected
        if lines is not None:
            # Calculate lengths of detected lines
            lengths = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                lengths.append((length, line[0]))

            # Sort lines by length in descending order
            lengths.sort(reverse=True, key=lambda x: x[0])

            # Extract the top 2 strongest lines
            strongest_lines = [lengths[i][1] for i in range(min(2, len(lengths)))]

            # If fewer than 2 lines, add None for the missing lines
            if len(strongest_lines) < 2:
                strongest_lines.extend([None] * (2 - len(strongest_lines)))
        else:
            # No lines detected, return two None values
            strongest_lines = [None, None]

        return strongest_lines

    @staticmethod
    def _format_lines_for_output(lines):
        """
        Efficiently formats the strongest lines into a string of the specified format.
        If a line is None, it will be replaced with None in the output string.
        """
        # List to collect formatted line parts
        formatted_lines = []

        for line in lines:
            if line is None:
                formatted_lines.append("None")
            else:
                # Unpack line coordinates and format as a string
                x1, y1, x2, y2 = line[0]
                formatted_lines.append(f"({x1}, {y1}, {x2}, {y2})")

        # Join all formatted parts into the final string
        return f"[{', '.join(formatted_lines)}]"

    async def start(self):
        try:
            # Initialize and configure camera
            self.camera = Picamera2()
            config = self.camera.create_video_configuration(
                main={"size": (self.frame_width, self.frame_height)},
                lores={"size": (self.frame_width, self.frame_height), "format": "YUV420"},
                display="main"
            )
            old_width = self.frame_width
            old_height = self.frame_height
            self.camera.align_configuration(config)
            (self.frame_width, self.frame_height) = config["lores"]["size"]
            if old_width != self.frame_width or old_height != self.frame_height:
                logging.warning(
                    f"Frame dimensions altered for efficiency: ({old_width}, {old_height}) --> ({self.frame_width}, {self.frame_height})")
            self.camera.configure(config)
            (w1, h1) = self.camera.stream_configuration("lores")["size"]
            self.camera.post_callback = self._draw_lines

            # Configure stream encoder
            self.encoder = H264Encoder(bitrate=1000000, repeat=True)
            self.encoder.frame_skip_count = 2

            logger.info("VideoStreamer started")

        except Exception as e:
            logger.error(f"Error starting VideoStreamer: {e}")
            await self.stop()

    async def start_stream(self):
        try:
            self._running = True
            # Start camera stream
            stream_url = f"udp://{self.receiver_ip}:{self.receiver_port}"
            self.camera.start_recording(self.encoder, output=FfmpegOutput(f"-safe 0 -f concat -segment_time_metadata 1 -i file.txt -vf select=concatdec_select -af aselect=concatdec_select,aresample=async=1 {stream_url}"))

            # Schedule the frame processor task
            self._task = asyncio.create_task(self.process_frames())

            logger.info(f"Started stream at {stream_url}")
        except Exception as e:
            logger.error(f"Error starting stream: {e}")
            await self.stop_stream()

    async def stop_stream(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task  # Wait for the task to finish
            except asyncio.CancelledError:
                pass
        if self.camera:
            self.camera.stop()
        if self.encoder:
            self.camera.stop_encoder()
        logger.info("Stream stopped")
        pass

    async def process_frames(self):
        try:
            while self._running:
                # Process frame (line detection)
                start_time = time.time()
                array = self.camera.capture_array("lores")
                gray = array[:self.frame_height, :self.frame_width]  # Extract the grayscale image
                edges = cv2.Canny(gray, 50, 150, apertureSize=3)

                self.strongest_lines = _get_strongest_lines(edges)
                end_time = time.time()
                process_time = end_time - start_time

                # Calculate process frequency
                self.process_hz = 1 / process_time if process_time > 0 else float('inf')

                # TODO: Send line data
                # if strongest_lines[0] is not None:
                #     try:
                #         lines_data = format_lines_for_output(strongest_lines)
                #     except Exception as e:
                #         logger.error(f"Error sending line data: {e}")
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred during frame processing: {e}", exc_info=True)

    def _draw_lines(self, request):
        """
        Callback function to draw lines and processing frequency on the camera stream.
        This function is called by the Picamera2 library during video capture.
        """
        with MappedArray(request, "main") as m:
            # Draw the processing frequency
            cv2.putText(m.array, f"{self.process_hz:.2f} Hz", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            # Draw the detected lines
            # for line in self.strongest_lines:
            #     if line is not None:
            #         x1, y1, x2, y2 = line[0]
            #         cv2.line(m.array, (x1, y1), (x2, y2), (255, 0, 0), 2)

    async def stop(self):
        await self.stop_stream()
        logging.info("Camera stopped and resources released")
