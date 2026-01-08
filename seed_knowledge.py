"""
Seed the Knowledge Base with FFT Strategy Guides.

Run this script once to populate the RAG database with useful FFT knowledge.
This data will be retrieved during battles to help the LLM make better decisions.
"""
from knowledge_store import KnowledgeStore

# FFT Strategy Guides - curated knowledge for the agent
STRATEGY_GUIDES = [
    {
        "title": "Early Game Jobs Priority",
        "tags": ["jobs", "early_game", "builds"],
        "content": """
Early game job priority for FFT:

1. **Squire**: Learn JP Boost first (doubles JP gain). Essential for fast progression.
2. **Chemist**: Get Item, Phoenix Down. Reliable healing without MP.
3. **Knight**: Break abilities are powerful. Speed Break cripples fast enemies.
4. **Archer**: Charge+1 through Charge+5 boost damage. Good for ranged harassment.
5. **White Mage**: Cure is essential. Raise for emergencies.
6. **Black Mage**: Fire/Ice/Thunder for AoE damage. Weak early but scales.

Key insight: JP Boost should be learned on EVERY character before branching.
"""
    },
    {
        "title": "Battle Positioning Fundamentals",
        "tags": ["tactics", "positioning", "combat"],
        "content": """
FFT Positioning Rules:

1. **High Ground Advantage**: +1 height = +10% damage dealt. Always climb.
2. **Rear Attack Bonus**: Attacking from behind = higher hit rate and damage.
3. **Side Attack**: Better than front, worse than rear.
4. **Elevation for Archers**: Place archers 2+ tiles higher for massive range.
5. **Choke Points**: Use corridors to funnel enemies into AoE spells.
6. **Avoid Clustering**: Enemy mages will punish grouped units with AoE.

Golden rule: Never end turn in water or low ground if enemies have mages.
"""
    },
    {
        "title": "Priority Target Selection",
        "tags": ["tactics", "targeting", "combat"],
        "content": """
Target Priority in FFT Battles:

1. **Healers/White Mages**: Kill first. They undo your damage.
2. **Time Mages**: Haste/Slow swings battles. Eliminate early.
3. **Black Mages**: High damage but fragile. Flank and kill.
4. **Archers on High Ground**: They snipe your mages. Close distance or use magic.
5. **Knights/Tanks**: Ignore until threats are dead. They're slow.
6. **Summoners**: Casting is slow. Interrupt with physical attacks.

Exception: If the boss has a "Defeat X to Win" condition, focus them.
"""
    },
    {
        "title": "Brave and Faith Mechanics",
        "tags": ["stats", "brave", "faith"],
        "content": """
Brave and Faith Explained:

**Brave (BRV)**:
- Affects physical damage dealt and received.
- Affects Reaction Ability trigger rate (Counter, etc.).
- High Brave (70+) = Strong physical damage.
- Low Brave (<10) = Unit becomes Chicken (uncontrollable).

**Faith (FTH)**:
- Affects magic damage dealt AND received.
- High Faith (70+) = Strong spells but vulnerable to enemy magic.
- Low Faith (<5) = Unit leaves party permanently (too skeptical).

Optimal builds:
- Physical DPS: 97 Brave, 03 Faith (immune to magic, max physical)
- Mage: 50 Brave, 97 Faith (max magic, accept vulnerability)
- Tank: 70 Brave, 30 Faith (balanced)
"""
    },
    {
        "title": "Dorter Trade City Strategy",
        "tags": ["battle", "chapter1", "dorter"],
        "content": """
Dorter Trade City - Chapter 1 Boss Battle:

**Enemy Composition**: 
- 2 Archers (rooftops), 2 Knights, 1 Black Mage, 1 White Mage

**Strategy**:
1. Turn 1: Rush the right side. Archers on rooftops are the biggest threat.
2. Kill the White Mage early - she heals the Black Mage.
3. Use ranged attacks or climb to reach rooftop archers.
4. The Black Mage casts Fire - spread your units.
5. Knights are slow, ignore until archers/mages are dead.

**Common Mistake**: Staying in the starting area and getting sniped.
**Winning Move**: Send one fast unit (Thief/Monk) to flank the mages.
"""
    },
    {
        "title": "Status Effects Priority",
        "tags": ["status", "debuffs", "combat"],
        "content": """
Most Impactful Status Effects:

**Offensive (Apply to Enemies)**:
1. **Stop**: Target cannot act. Broken.
2. **Don't Act**: Skip their turn. Very strong.
3. **Slow**: Halves CT gain. Effectively removes a unit.
4. **Confusion**: Enemy attacks allies. Chaos.
5. **Silence**: Shuts down mages.

**Defensive (Cure on Allies)**:
1. **Stone/Petrify**: Cure immediately or lose the unit.
2. **KO**: Revive within 3 turns or permadeath.
3. **Stop**: Wait for it to wear off.

**Abilities to Get**:
- Esuna (White Mage) cures most negative statuses.
- Stigma Magic (Holy Knight) cures allies in AoE.
"""
    },
    {
        "title": "Speed Stat Importance",
        "tags": ["stats", "speed", "combat"],
        "content": """
Speed is King in FFT:

**Why Speed Matters**:
- Speed determines turn order (CT system).
- A unit with 2x speed gets 2x turns.
- More turns = more damage, more healing, more control.

**Speed Boosting**:
1. **Haste** spell: +50% CT gain. Cast on your damage dealers.
2. **Speed Save** ability: Prevents Speed Break.
3. **Thief**: Highest natural speed. Great for stealing and disrupting.
4. **Ninja**: Fast + dual wield = devastating.

**Speed Breaking Enemies**:
- Knight's Speed Break is devastating on bosses.
- A slowed enemy is a dead enemy.

Rule: If you can Haste or Slow, do it before attacking.
"""
    },
]


def seed_database():
    """Seed the knowledge store with FFT guides."""
    print("Initializing Knowledge Store...")
    store = KnowledgeStore()
    
    print(f"\nSeeding {len(STRATEGY_GUIDES)} strategy guides...\n")
    
    for guide in STRATEGY_GUIDES:
        store.store_strategy_guide(
            title=guide["title"],
            content=guide["content"],
            tags=guide["tags"]
        )
    
    print(f"\n✅ Done! Knowledge store now has strategy guides.")
    print(f"   Total items in action_learnings: {store.collection.count()}")
    print(f"   Total items in strategy_guides: {store.strategy_collection.count()}")


if __name__ == "__main__":
    seed_database()
