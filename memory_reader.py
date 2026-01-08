"""
Memory Reader for Eden Emulator via GDB Stub.
Reads game state (HP, MP, stats) directly from emulator memory.
"""
import socket
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class UnitStats:
    """Stats for a single unit in battle."""
    unit_id: int
    hp: int = 0
    max_hp: int = 0
    mp: int = 0
    max_mp: int = 0
    brave: int = 0
    faith: int = 0
    speed: int = 0
    attack: int = 0
    attack2: int = 0  # Secondary attack stat
    move_count: int = 0
    max_moves: int = 0  # Movement range
    # Status
    status_shield_1: int = 0  # Status effects bitfield 1
    status_shield_2: int = 0  # Status effects bitfield 2
    magic_ready: bool = False  # Spell is charged
    # Job/Abilities (Unit 1 only)
    job_id: int = 0
    ability2_id: int = 0  # Secondary ability slot
    # Skills (Unit 1 only)
    skill_poaching: bool = False
    skill_xp_hp_move: bool = False
    skill_fly: bool = False  # Walk in the sky
    

@dataclass 
class GameMemoryState:
    """Complete game state read from memory."""
    units: List[UnitStats] = field(default_factory=list)
    gil: int = 0
    connected: bool = False
    error: Optional[str] = None


# Memory addresses from cheat codes (Atmosphere/EdiZon format)
# Base addresses for units - each unit is 0x200 apart
# Unit 1 Base: 0x01047400 approx (HP is at +0x80)
UNIT_BASE_ADDR = 0x01047400
UNIT_OFFSET = 0x200

# Offsets relative to Unit Base
OFFSETS = {
    "brave": 0x7A,
    "faith": 0x7C,
    "hp": 0x80,
    "mp": 0x84,
    "attack_power": 0x88,  # Max Attack
    "move_count": 0x91,    # Moves taken? Or remaining?
    "max_moves": 0x92,
    "status_shield_1": 0xB2,
    "status_shield_2": 0xB4,
    "max_hp": 0xCC,
    "max_mp": 0xD0,
    "speed": 0xD2,
    "attack": 0xD6,
    "attack2": 0xD8,
    "skill_poaching": 0xEA,
    "skill_xp_hp_move": 0xEC,
    "skill_fly": 0xEE,
    "magic_ready": 0x1DD, # Note: 0x1DD seems far? 0x010475DD - 0x01047400 = 0x1DD. Correct.
}

# Generate addresses for all 5 units
UNIT_ADDRESSES = {}
for i in range(5):
    unit_id = i + 1
    base = UNIT_BASE_ADDR + (i * UNIT_OFFSET)
    UNIT_ADDRESSES[unit_id] = {
        name: base + offset for name, offset in OFFSETS.items()
    }

# Ramza-specific addresses (job, abilities)
RAMZA_ADDRESSES = {
    "job_id": 0x0104C4BA,
    "ability2_id": 0x0104C4BF,
}

# Job ID mappings
JOB_NAMES = {
    0x05: "Holy Knight",
    0x08: "Ark Knight",
    0x09: "Rune Knight",
    0x0C: "Princess",
    0x0D: "Sword Saint",
    0x0F: "Dragonkin",
    0x10: "Celebrant",
    0x11: "Fell Knight",
    0x1F: "Templar",
    0x24: "Divine Knight",
    0x48: "Holy Dragon",
}

# Ability2 ID mappings
ABILITY_NAMES = {
    0x29: "Limit",
    0x2B: "Dragon",
    0x30: "Holy Sword",
    0x35: "Pugilism",
    0x36: "Subdual Arts",
    0x3B: "Sword Spirit",
    0x46: "Swordsmanship",
    0x48: "Magick Arts",
}


class GDBMemoryReader:
    """
    Reads memory from Eden emulator via GDB Remote Serial Protocol.
    
    GDB protocol basics:
    - Commands are prefixed with '$' and suffixed with '#XX' (checksum)
    - 'm<addr>,<len>' reads memory at address
    - Response is hex-encoded bytes
    """
    
    def __init__(self, host: str = "127.0.0.1", port: int = 6543, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None
        self._connected = False
    
    def connect(self) -> bool:
        """Connect to Eden's GDB stub."""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((self.host, self.port))
            self._connected = True
            print(f"[MemoryReader] Connected to GDB stub at {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"[MemoryReader] Connection failed: {e}")
            self._connected = False
            return False
    
    def disconnect(self):
        """Disconnect from GDB stub."""
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
        self._socket = None
        self._connected = False
    
    def _checksum(self, data: str) -> str:
        """Calculate GDB packet checksum."""
        return f"{sum(ord(c) for c in data) % 256:02x}"
    
    def _send_packet(self, command: str) -> Optional[str]:
        """Send a GDB packet and receive response."""
        if not self._socket or not self._connected:
            return None
        
        # Build packet: $<command>#<checksum>
        packet = f"${command}#{self._checksum(command)}"
        
        try:
            self._socket.sendall(packet.encode('ascii'))
            
            # Receive response
            response = b""
            while True:
                chunk = self._socket.recv(1024)
                if not chunk:
                    break
                response += chunk
                # GDB responses end with #XX
                if b"#" in response and len(response) >= response.index(b"#") + 3:
                    break
            
            # Parse response: +$<data>#<checksum>
            resp_str = response.decode('ascii', errors='ignore')
            if '$' in resp_str and '#' in resp_str:
                start = resp_str.index('$') + 1
                end = resp_str.rindex('#')
                return resp_str[start:end]
            
            return resp_str
            
        except socket.timeout:
            print("[MemoryReader] Timeout waiting for response")
            return None
        except Exception as e:
            print(f"[MemoryReader] Send error: {e}")
            return None
    
    def read_memory(self, address: int, size: int = 4) -> Optional[int]:
        """
        Read memory at address.
        
        Args:
            address: Memory address to read
            size: Number of bytes to read (1, 2, or 4)
        
        Returns:
            Integer value at address, or None on failure
        """
        # GDB read memory command: m<addr>,<len>
        command = f"m{address:x},{size}"
        response = self._send_packet(command)
        
        if response and response != "E00" and len(response) >= size * 2:
            try:
                # Response is hex-encoded bytes (little-endian on ARM)
                hex_bytes = response[:size * 2]
                # Convert from little-endian hex
                value = int.from_bytes(
                    bytes.fromhex(hex_bytes), 
                    byteorder='little'
                )
                return value
            except ValueError:
                pass
        
        return None
    
    def read_unit_stats(self, unit_id: int) -> Optional[UnitStats]:
        """Read stats for a specific unit."""
        if unit_id not in UNIT_ADDRESSES:
            return None
        
        addrs = UNIT_ADDRESSES[unit_id]
        stats = UnitStats(unit_id=unit_id)
        
        # Read each stat
        if "hp" in addrs:
            val = self.read_memory(addrs["hp"], 2)
            if val is not None:
                stats.hp = val & 0xFFFF  # Lower 16 bits
        
        if "mp" in addrs:
            val = self.read_memory(addrs["mp"], 2)
            if val is not None:
                stats.mp = val & 0xFFFF
        
        if "max_hp" in addrs:
            val = self.read_memory(addrs["max_hp"], 2)
            if val is not None:
                stats.max_hp = val & 0xFFFF
        
        if "max_mp" in addrs:
            val = self.read_memory(addrs["max_mp"], 2)
            if val is not None:
                stats.max_mp = val & 0xFFFF
        
        if "brave" in addrs:
            val = self.read_memory(addrs["brave"], 1)
            if val is not None:
                stats.brave = val
        
        if "faith" in addrs:
            val = self.read_memory(addrs["faith"], 1)
            if val is not None:
                stats.faith = val
        
        if "speed" in addrs:
            val = self.read_memory(addrs["speed"], 1)
            if val is not None:
                stats.speed = val
        
        if "attack" in addrs:
            val = self.read_memory(addrs["attack"], 2)
            if val is not None:
                stats.attack = val
        
        if "attack2" in addrs:
            val = self.read_memory(addrs["attack2"], 2)
            if val is not None:
                stats.attack2 = val
        
        if "move_count" in addrs:
            val = self.read_memory(addrs["move_count"], 1)
            if val is not None:
                stats.move_count = val
        
        if "max_moves" in addrs:
            val = self.read_memory(addrs["max_moves"], 2)
            if val is not None:
                stats.max_moves = val
        
        # Status shields (bitfields)
        if "status_shield_1" in addrs:
            val = self.read_memory(addrs["status_shield_1"], 2)
            if val is not None:
                stats.status_shield_1 = val
        
        if "status_shield_2" in addrs:
            val = self.read_memory(addrs["status_shield_2"], 2)
            if val is not None:
                stats.status_shield_2 = val
        
        # Magic ready
        if "magic_ready" in addrs:
            val = self.read_memory(addrs["magic_ready"], 1)
            if val is not None:
                stats.magic_ready = val == 1
        
        # Skills (check if enabled)
        if "skill_poaching" in addrs:
            val = self.read_memory(addrs["skill_poaching"], 2)
            if val is not None:
                stats.skill_poaching = val != 0
        
        if "skill_xp_hp_move" in addrs:
            val = self.read_memory(addrs["skill_xp_hp_move"], 2)
            if val is not None:
                stats.skill_xp_hp_move = val != 0
        
        if "skill_fly" in addrs:
            val = self.read_memory(addrs["skill_fly"], 2)
            if val is not None:
                stats.skill_fly = val != 0
        
        # Ramza-specific: Job and Ability2 (only for unit 1)
        if unit_id == 1:
            job_val = self.read_memory(RAMZA_ADDRESSES["job_id"], 1)
            if job_val is not None:
                stats.job_id = job_val
            
            ability_val = self.read_memory(RAMZA_ADDRESSES["ability2_id"], 1)
            if ability_val is not None:
                stats.ability2_id = ability_val
        
        return stats
    
    def read_game_state(self) -> GameMemoryState:
        """Read complete game state from memory."""
        state = GameMemoryState()
        
        if not self._connected:
            if not self.connect():
                state.error = "Failed to connect to GDB stub"
                return state
        
        state.connected = True
        
        # Read all 5 units
        for unit_id in range(1, 6):
            unit = self.read_unit_stats(unit_id)
            if unit:
                state.units.append(unit)
        
        return state
    
    def format_for_llm(self, state: GameMemoryState) -> str:
        """Format game state as text for LLM prompt."""
        if not state.connected:
            return f"[Memory Read Failed: {state.error or 'Not connected'}]"
        
        lines = ["## Live Game State (from memory)"]
        
        for unit in state.units:
            if unit.hp > 0 or unit.max_hp > 0:  # Only show units with data
                unit_label = f"Unit {unit.unit_id}"
                if unit.unit_id == 1:
                    unit_label = "Unit 1 (Ramza)"
                lines.append(f"\n### {unit_label}")
                
                # Core stats
                lines.append(f"- HP: {unit.hp}/{unit.max_hp}")
                lines.append(f"- MP: {unit.mp}/{unit.max_mp}")
                
                if unit.brave:
                    lines.append(f"- Brave: {unit.brave}")
                if unit.faith:
                    lines.append(f"- Faith: {unit.faith}")
                if unit.speed:
                    lines.append(f"- Speed: {unit.speed}")
                if unit.attack:
                    attack_str = f"- Attack: {unit.attack}"
                    if unit.attack2:
                        attack_str += f" / {unit.attack2}"
                    lines.append(attack_str)
                
                # Movement
                if unit.move_count or unit.max_moves:
                    lines.append(f"- Movement: {unit.move_count} used, {unit.max_moves} range")
                
                # Magic ready
                if unit.magic_ready:
                    lines.append(f"- ⚡ Spell CHARGED and ready!")
                
                # Job and abilities (Ramza only)
                if unit.unit_id == 1:
                    if unit.job_id:
                        job_name = JOB_NAMES.get(unit.job_id, f"Unknown ({unit.job_id:#x})")
                        lines.append(f"- Job: {job_name}")
                    if unit.ability2_id:
                        ability_name = ABILITY_NAMES.get(unit.ability2_id, f"Unknown ({unit.ability2_id:#x})")
                        lines.append(f"- Ability2: {ability_name}")
                
                # Active skills
                skills = []
                if unit.skill_poaching:
                    skills.append("Poaching")
                if unit.skill_xp_hp_move:
                    skills.append("XP+HP After Move")
                if unit.skill_fly:
                    skills.append("Walk in Sky")
                if skills:
                    lines.append(f"- Skills: {', '.join(skills)}")
                
                # Status (if any effects active)
                if unit.status_shield_1 or unit.status_shield_2:
                    lines.append(f"- Status flags: {unit.status_shield_1:#x}, {unit.status_shield_2:#x}")
        
        return "\n".join(lines)


# Singleton instance for easy access
_reader: Optional[GDBMemoryReader] = None


def get_memory_reader(host: str = "127.0.0.1", port: int = 6543) -> GDBMemoryReader:
    """Get or create the memory reader singleton."""
    global _reader
    if _reader is None:
        _reader = GDBMemoryReader(host=host, port=port)
    return _reader


if __name__ == "__main__":
    # Test connection
    reader = GDBMemoryReader()
    
    if reader.connect():
        print("\nReading game state...")
        state = reader.read_game_state()
        print(reader.format_for_llm(state))
        reader.disconnect()
    else:
        print("Could not connect to Eden GDB stub.")
        print("Make sure:")
        print("1. Eden is running with the game loaded")
        print("2. GDB stub is enabled on port 6543")
