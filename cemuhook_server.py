"""
CemuhookUDP Server for controller input injection.
Implements DSU protocol (Cemuhook v1001) to send controller inputs to Eden emulator.

Based on: https://cemuhook.sshnuke.net/padudpserver.html
Protocol: DSUS/DSUC (DS4 USB Server/Client)
"""
import socket
import struct
import time
import threading
import zlib
from dataclasses import dataclass, field
from typing import Optional


# Protocol constants
SERVER_MAGIC = 0x53555344  # "DSUS"
CLIENT_MAGIC = 0x43555344  # "DSUC"
PROTOCOL_VERSION = 1001

# Message types
TYPE_VERSION = 0x00100000
TYPE_PORTINFO = 0x00100001
TYPE_PADDATA = 0x00100002


@dataclass
class ControllerState:
    """Current state of virtual controller."""
    buttons: int = 0  # 16-bit bitfield
    left_stick_x: int = 128  # 0-255, 128 = center
    left_stick_y: int = 128
    right_stick_x: int = 128
    right_stick_y: int = 128
    packet_counter: int = field(default=0, repr=False)


class CemuhookServer:
    """
    UDP server that emulates a DSU (CemuhookUDP) controller.
    Eden connects to this server and receives controller inputs.
    """
    
    # Button bit positions (matches DSU protocol)
    BUTTON_SHARE = 0x0001
    BUTTON_L3 = 0x0002
    BUTTON_R3 = 0x0004
    BUTTON_OPTIONS = 0x0008
    BUTTON_UP = 0x0010
    BUTTON_RIGHT = 0x0020
    BUTTON_DOWN = 0x0040
    BUTTON_LEFT = 0x0080
    BUTTON_L2 = 0x0100
    BUTTON_R2 = 0x0200
    BUTTON_L1 = 0x0400
    BUTTON_R1 = 0x0800
    BUTTON_TRIANGLE = 0x1000
    BUTTON_CIRCLE = 0x2000
    BUTTON_CROSS = 0x4000
    BUTTON_SQUARE = 0x8000
    
    # Switch button mapping
    SWITCH_A = BUTTON_CIRCLE
    SWITCH_B = BUTTON_CROSS
    SWITCH_X = BUTTON_TRIANGLE
    SWITCH_Y = BUTTON_SQUARE
    SWITCH_L = BUTTON_L1
    SWITCH_R = BUTTON_R1
    SWITCH_ZL = BUTTON_L2
    SWITCH_ZR = BUTTON_R2
    SWITCH_PLUS = BUTTON_OPTIONS
    SWITCH_MINUS = BUTTON_SHARE
    SWITCH_DPAD_UP = BUTTON_UP
    SWITCH_DPAD_DOWN = BUTTON_DOWN
    SWITCH_DPAD_LEFT = BUTTON_LEFT
    SWITCH_DPAD_RIGHT = BUTTON_RIGHT
    
    def __init__(self, host: str = "127.0.0.1", port: int = 26760):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.setblocking(False)
        
        self.state = ControllerState()
        self.client_addr: Optional[tuple] = None
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.server_id = 0x12345678
    
    def _compute_crc32(self, data: bytes) -> int:
        """Compute CRC32 checksum."""
        return zlib.crc32(data) & 0xFFFFFFFF
    
    def _build_header(self, msg_type: int, payload_len: int) -> bytes:
        """Build 20-byte DSU header."""
        # Header: magic(4) + version(2) + length(2) + crc(4) + id(4) + type(4)
        header = struct.pack('<IHHIII',
            SERVER_MAGIC,      # 4 bytes
            PROTOCOL_VERSION,  # 2 bytes
            payload_len,       # 2 bytes (length of payload, not including header magic/version/length/crc)
            0,                 # 4 bytes CRC placeholder
            self.server_id,    # 4 bytes server ID
            msg_type,          # 4 bytes message type
        )
        return header
    
    def _build_port_info(self) -> bytes:
        """Build PortInfo response (12 bytes)."""
        # PortInfo: id(1) + state(1) + model(1) + connection(1) + mac(6) + battery(1) + active(1)
        return struct.pack('<BBBB6sBB',
            0,              # Pad ID
            2,              # State: Connected (2)
            3,              # Model: Generic (3)
            1,              # Connection: USB (1)
            b'\x00' * 6,    # MAC address
            5,              # Battery: Full (5)
            1,              # Is active
        )
    
    def _build_pad_data(self) -> bytes:
        """Build complete PadData message (100 bytes total: 20 header + 80 payload)."""
        self.state.packet_counter += 1
        
        # PortInfo (12 bytes)
        port_info = self._build_port_info()
        
        # PadData payload after PortInfo
        # packet_counter (4) + digital_button (2) + home (1) + touch_hard_press (1) + 
        # sticks (4) + analog_buttons (12) + touch (12) + timestamp (8) + accel (12) + gyro (12)
        # = 4 + 2 + 1 + 1 + 4 + 12 + 12 + 8 + 12 + 12 = 68 bytes (+ 12 port_info = 80 total)
        
        pad_data = struct.pack('<I',  # packet_counter
            self.state.packet_counter,
        )
        pad_data += struct.pack('<H',  # digital_button
            self.state.buttons,
        )
        pad_data += struct.pack('<BB',  # home, touch_hard_press
            0, 0,
        )
        pad_data += struct.pack('<BBBB',  # sticks
            self.state.left_stick_x,
            self.state.left_stick_y,
            self.state.right_stick_x,
            self.state.right_stick_y,
        )
        pad_data += b'\x00' * 12  # analog_buttons (12 bytes)
        pad_data += b'\x00' * 12  # touch pads (2 * 6 bytes)
        pad_data += struct.pack('<Q', int(time.time() * 1000000))  # motion_timestamp (8 bytes)
        pad_data += struct.pack('<fff', 0.0, 0.0, 0.0)  # accelerometer (12 bytes)
        pad_data += struct.pack('<fff', 0.0, 0.0, 0.0)  # gyroscope (12 bytes)
        
        # Full payload = port_info + pad_data
        payload = port_info + pad_data
        assert len(payload) == 80, f"Payload should be 80 bytes, got {len(payload)}"
        
        # Build header - payload_length must be sizeof(payload) + sizeof(Type) per DSU spec
        header = self._build_header(TYPE_PADDATA, len(payload) + 4)
        
        # Combine and compute CRC
        message = bytearray(header + payload)
        
        # CRC is computed over entire message with CRC field set to 0
        crc = self._compute_crc32(bytes(message))
        struct.pack_into('<I', message, 8, crc)  # CRC is at offset 8
        
        return bytes(message)
    
    def _build_version_response(self) -> bytes:
        """Build Version response."""
        payload = struct.pack('<H', PROTOCOL_VERSION)
        header = self._build_header(TYPE_VERSION, len(payload) + 4)
        message = bytearray(header + payload)
        crc = self._compute_crc32(bytes(message))
        struct.pack_into('<I', message, 8, crc)
        return bytes(message)
    
    def _build_portinfo_response(self) -> bytes:
        """Build standalone PortInfo response."""
        payload = self._build_port_info()
        header = self._build_header(TYPE_PORTINFO, len(payload) + 4)
        message = bytearray(header + payload)
        crc = self._compute_crc32(bytes(message))
        struct.pack_into('<I', message, 8, crc)
        return bytes(message)
    
    def _parse_request(self, data: bytes) -> Optional[int]:
        """Parse incoming request and return message type."""
        if len(data) < 20:
            return None
        magic, version, length, crc, client_id, msg_type = struct.unpack('<IHHIII', data[:20])
        if magic != CLIENT_MAGIC:
            return None
        return msg_type
    
    def _handle_requests(self):
        """Handle incoming requests from emulator."""
        try:
            data, addr = self.sock.recvfrom(100)
            self.client_addr = addr
            
            msg_type = self._parse_request(data)
            if msg_type == TYPE_VERSION:
                print(f"[Cemuhook] Handshake: Version request from {addr}")
                self.sock.sendto(self._build_version_response(), addr)
            elif msg_type == TYPE_PORTINFO:
                print(f"[Cemuhook] Handshake: PortInfo request from {addr}")
                self.sock.sendto(self._build_portinfo_response(), addr)
            elif msg_type == TYPE_PADDATA:
                self.sock.sendto(self._build_pad_data(), addr)
        except BlockingIOError:
            pass
    
    def _loop(self):
        """Main server loop."""
        while self.running:
            self._handle_requests()
            # Send periodic updates
            if self.client_addr:
                try:
                    self.sock.sendto(self._build_pad_data(), self.client_addr)
                except Exception:
                    pass
            time.sleep(0.016)  # ~60 Hz
    
    def start(self):
        """Start server in background thread."""
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"CemuhookUDP server running on {self.host}:{self.port}")
    
    def stop(self):
        """Stop server."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        self.sock.close()
    
    # High-level input methods
    def press_button(self, button: int, duration: float = 0.25):
        """Press a button for specified duration."""
        self.state.buttons |= button
        time.sleep(duration)
        self.state.buttons &= ~button
    
    def press_a(self):
        self.press_button(self.SWITCH_A)
    
    def press_b(self):
        self.press_button(self.SWITCH_B)

    def press_x(self):
        self.press_button(self.SWITCH_X)

    def press_y(self):
        self.press_button(self.SWITCH_Y)
    
    def press_dpad(self, direction: str):
        """Press d-pad: 'up', 'down', 'left', 'right'."""
        mapping = {
            'up': self.SWITCH_DPAD_UP,
            'down': self.SWITCH_DPAD_DOWN,
            'left': self.SWITCH_DPAD_LEFT,
            'right': self.SWITCH_DPAD_RIGHT,
        }
        if direction in mapping:
            self.press_button(mapping[direction])
    
    def move_cursor(self, dx: int, dy: int):
        """Move cursor by delta. Positive = right/down."""
        for _ in range(abs(dx)):
            self.press_dpad('right' if dx > 0 else 'left')
            time.sleep(0.05)
        for _ in range(abs(dy)):
            self.press_dpad('down' if dy > 0 else 'up')
            time.sleep(0.05)


if __name__ == "__main__":
    server = CemuhookServer()
    server.start()
    print("Press Ctrl+C to stop...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
