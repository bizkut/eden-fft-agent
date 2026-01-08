"""
Power Manager Module.

This module provides the ability to buff characters via GDB memory writes.
Use with caution - this is essentially a "cheat" system for emergency situations.
"""
from typing import Optional
from memory_reader import GDBMemoryReader, UNIT_ADDRESSES, OFFSETS, UnitStats, GameMemoryState


class PowerManager:
    """
    Manages character power-ups via memory modification.
    
    This should only be used in critical situations when the StrategyAdvisor
    determines the party is at risk of losing the battle.
    """
    
    def __init__(self, memory_reader: GDBMemoryReader):
        self.reader = memory_reader
        self.enabled = True  # Can be disabled via config
        self.power_ups_used = 0
        self.max_power_ups_per_battle = 3  # Limit to avoid over-cheating
    
    def can_power_up(self) -> bool:
        """Check if power-ups are available."""
        return (
            self.enabled and 
            self.reader._connected and 
            self.power_ups_used < self.max_power_ups_per_battle
        )
    
    def heal_unit(self, unit_id: int, amount: Optional[int] = None) -> bool:
        """
        Heal a unit by restoring HP.
        
        Args:
            unit_id: Unit to heal (1-5)
            amount: HP to restore (None = full heal)
        
        Returns:
            True if successful
        """
        if not self.can_power_up():
            return False
        
        if unit_id not in UNIT_ADDRESSES:
            return False
        
        addrs = UNIT_ADDRESSES[unit_id]
        
        # Read current and max HP
        current_hp = self.reader.read_memory(addrs["hp"], 2)
        max_hp = self.reader.read_memory(addrs["max_hp"], 2)
        
        if current_hp is None or max_hp is None:
            return False
        
        # Calculate new HP
        if amount is None:
            new_hp = max_hp  # Full heal
        else:
            new_hp = min(current_hp + amount, max_hp)
        
        # Write new HP
        if self.reader.write_memory(addrs["hp"], new_hp, 2):
            self.power_ups_used += 1
            print(f"[PowerManager] Healed Unit {unit_id}: {current_hp} -> {new_hp} HP")
            return True
        
        return False
    
    def restore_mp(self, unit_id: int, amount: Optional[int] = None) -> bool:
        """
        Restore MP for a unit.
        
        Args:
            unit_id: Unit to restore (1-5)
            amount: MP to restore (None = full restore)
        
        Returns:
            True if successful
        """
        if not self.can_power_up():
            return False
        
        if unit_id not in UNIT_ADDRESSES:
            return False
        
        addrs = UNIT_ADDRESSES[unit_id]
        
        current_mp = self.reader.read_memory(addrs["mp"], 2)
        max_mp = self.reader.read_memory(addrs["max_mp"], 2)
        
        if current_mp is None or max_mp is None:
            return False
        
        if amount is None:
            new_mp = max_mp
        else:
            new_mp = min(current_mp + amount, max_mp)
        
        if self.reader.write_memory(addrs["mp"], new_mp, 2):
            self.power_ups_used += 1
            print(f"[PowerManager] Restored Unit {unit_id}: {current_mp} -> {new_mp} MP")
            return True
        
        return False
    
    def boost_brave(self, unit_id: int, target_brave: int = 97) -> bool:
        """
        Boost a unit's Brave stat (affects physical damage/crit/reaction chance).
        
        Args:
            unit_id: Unit to boost
            target_brave: Target Brave value (max 97 for permanent)
        """
        if not self.can_power_up():
            return False
        
        if unit_id not in UNIT_ADDRESSES:
            return False
        
        addrs = UNIT_ADDRESSES[unit_id]
        
        if self.reader.write_memory(addrs["brave"], min(target_brave, 100), 1):
            self.power_ups_used += 1
            print(f"[PowerManager] Boosted Unit {unit_id} Brave to {target_brave}")
            return True
        
        return False
    
    def boost_faith(self, unit_id: int, target_faith: int = 97) -> bool:
        """
        Boost a unit's Faith stat (affects magic damage dealt/received).
        
        Args:
            unit_id: Unit to boost
            target_faith: Target Faith value
        """
        if not self.can_power_up():
            return False
        
        if unit_id not in UNIT_ADDRESSES:
            return False
        
        addrs = UNIT_ADDRESSES[unit_id]
        
        if self.reader.write_memory(addrs["faith"], min(target_faith, 100), 1):
            self.power_ups_used += 1
            print(f"[PowerManager] Boosted Unit {unit_id} Faith to {target_faith}")
            return True
        
        return False
    
    def emergency_revive(self, unit_id: int) -> bool:
        """
        Emergency revive a dead unit (sets HP to 50% of max).
        
        Args:
            unit_id: Unit to revive
        """
        if not self.can_power_up():
            return False
        
        if unit_id not in UNIT_ADDRESSES:
            return False
        
        addrs = UNIT_ADDRESSES[unit_id]
        max_hp = self.reader.read_memory(addrs["max_hp"], 2)
        
        if max_hp is None:
            return False
        
        revive_hp = max_hp // 2
        
        if self.reader.write_memory(addrs["hp"], revive_hp, 2):
            self.power_ups_used += 1
            print(f"[PowerManager] Revived Unit {unit_id} with {revive_hp} HP")
            return True
        
        return False
    
    def reset_battle_counter(self):
        """Reset power-up counter at the start of a new battle."""
        self.power_ups_used = 0
    
    def emergency_assist(self, state: GameMemoryState) -> int:
        """
        Automatically assist the party based on current state.
        Called by StrategyAdvisor when in EMERGENCY mode.
        
        Returns:
            Number of power-ups applied
        """
        assists = 0
        
        for unit in state.units:
            if unit.max_hp == 0:
                continue
            
            # Revive dead units
            if unit.hp == 0:
                if self.emergency_revive(unit.unit_id):
                    assists += 1
            
            # Heal critical units (< 30% HP)
            elif unit.hp < unit.max_hp * 0.3:
                if self.heal_unit(unit.unit_id):
                    assists += 1
        
        return assists
