import numpy as np
import struct

# Configuration
MAP_WIDTH = 16
MAP_HEIGHT = 16
CHANNELS = 8

class TensorBuilder:
    def __init__(self):
        # Channel definitions
        self.CH_TERRAIN_HEIGHT = 0
        self.CH_TERRAIN_TYPE = 1
        self.CH_UNIT_ALLY = 2
        self.CH_UNIT_ENEMY = 3
        self.CH_UNIT_CURRENT = 4
        self.CH_HP_PCT = 5
        self.CH_MOVE_RANGE = 6
        self.CH_ACTION_RANGE = 7

    def build_tensor_from_memory(self, memory_reader):
        """
        Constructs a [8, 16, 16] tensor from raw game memory.
        """
        # 1. Initialize empty tensor (Channels, Height, Width)
        tensor = np.zeros((CHANNELS, MAP_HEIGHT, MAP_WIDTH), dtype=np.float32)

        # 2. Read Map Data (Static or Cached)
        # Memory: [Tile0][Tile1]... where Tile requires ~4 bytes
        # Byte 0: Terrain Type, Byte 1: Elevation, Byte 2: Flags
        raw_map_data = memory_reader.read_map_array() 
        
        for y in range(MAP_HEIGHT):
            for x in range(MAP_WIDTH):
                idx = y * MAP_WIDTH + x
                # Extract bytes
                t_type = raw_map_data[idx * 4 + 0]
                elevation = raw_map_data[idx * 4 + 1]
                
                # Channel 0: Normalized Height (0-15 -> 0.0-1.0)
                tensor[self.CH_TERRAIN_HEIGHT, y, x] = elevation / 15.0
                
                # Channel 1: Terrain Type (Categorical / Scaled)
                # Simple: Scaling ID. Better: One-hot encoding (would need more channels)
                tensor[self.CH_TERRAIN_TYPE, y, x] = t_type / 255.0

        # 3. Read Unit Data (Dynamic)
        # Unit Struct: [X, Y, Team, HP, MaxHP, ...]
        active_units = memory_reader.read_unit_list()
        current_actor_idx = memory_reader.read_current_actor_index()

        for unit in active_units:
            x, y = unit.x, unit.y
            
            # Boundary check
            if not (0 <= x < MAP_WIDTH and 0 <= y < MAP_HEIGHT):
                continue

            # Channel 2/3: Team Presence
            if unit.team == 0:  # 0 = Ally
                tensor[self.CH_UNIT_ALLY, y, x] = 1.0
            else:               # 1 = Enemy
                tensor[self.CH_UNIT_ENEMY, y, x] = 1.0
            
            # Channel 5: HP Percentage
            if unit.max_hp > 0:
                tensor[self.CH_HP_PCT, y, x] = unit.hp / unit.max_hp

            # Channel 4: Is this the specific unit acting right now?
            if unit.index == current_actor_idx:
                tensor[self.CH_UNIT_CURRENT, y, x] = 1.0
                
                # Channel 6: Move Range (Calculated or Read)
                # (Simulated function to fill reachable tiles)
                reachable_tiles = self.calculate_reachable(unit, raw_map_data)
                for (rx, ry) in reachable_tiles:
                     tensor[self.CH_MOVE_RANGE, ry, rx] = 1.0

        return tensor

    def calculate_reachable(self, unit, map_data):
        # Implementation of BFS using map_data constraints
        return [(unit.x + dx, unit.y + dy) for dx, dy in [(0,1), (1,0), (0,-1), (-1,0)]]

# --- Mock Classes for Demonstration ---

class MockMemoryReader:
    def read_map_array(self):
        # Simulating 16x16 map with 4 bytes per tile
        return bytes([0, 5, 0, 0] * (16 * 16)) 
    
    def read_unit_list(self):
        class Unit: pass
        u1 = Unit(); u1.x=5; u1.y=5; u1.team=0; u1.hp=80; u1.max_hp=100; u1.index=0
        u2 = Unit(); u2.x=6; u2.y=6; u2.team=1; u2.hp=50; u2.max_hp=50; u2.index=1
        return [u1, u2]

    def read_current_actor_index(self):
        return 0

# --- Execution ---
if __name__ == "__main__":
    builder = TensorBuilder()
    reader = MockMemoryReader()
    tensor = builder.build_tensor_from_memory(reader)
    
    print(f"Tensor Shape: {tensor.shape}")
    print(f"Sample Slice (Ally Unit Layer):\n{tensor[2]}")
