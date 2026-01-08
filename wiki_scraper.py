"""
Wiki Scraper for FFT Knowledge.
Scrapes walkthrough content and stores in RAG database.
"""
import time
from typing import List, Dict, Any
from dataclasses import dataclass

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from knowledge_store import KnowledgeStore, ActionLearning


@dataclass
class WikiKnowledge:
    """A piece of game knowledge from wiki/guide."""
    topic: str           # e.g., "Battle 5: Dorter Slums"
    category: str        # e.g., "walkthrough", "job", "ability"
    content: str         # The actual guide text
    source_url: str      # Where it came from


class WikiKnowledgeStore(KnowledgeStore):
    """Extended knowledge store that can hold wiki/guide content."""
    
    def __init__(self, persist_directory: str = "./knowledge_db"):
        super().__init__(persist_directory)
        
        # Create separate collection for wiki knowledge
        self.wiki_collection = self.client.get_or_create_collection(
            name="wiki_knowledge",
            metadata={"description": "FFT walkthrough and guide knowledge"}
        )
        print(f"[WikiKnowledge] Initialized with {self.wiki_collection.count()} articles")
    
    def store_wiki_knowledge(self, knowledge: WikiKnowledge) -> str:
        """Store wiki knowledge entry."""
        # Create searchable text
        search_text = f"{knowledge.topic}: {knowledge.content[:500]}"
        
        # Get embedding
        embedding = self.embedding_client.embed(search_text)
        
        # Generate ID from topic
        doc_id = f"wiki_{hash(knowledge.topic) % 1000000}"
        
        # Check if already exists
        existing = self.wiki_collection.get(ids=[doc_id])
        if existing and existing["ids"]:
            print(f"[WikiKnowledge] Updating: {knowledge.topic[:50]}...")
            self.wiki_collection.update(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[knowledge.content],
                metadatas=[{
                    "topic": knowledge.topic,
                    "category": knowledge.category,
                    "source": knowledge.source_url
                }]
            )
        else:
            print(f"[WikiKnowledge] Storing: {knowledge.topic[:50]}...")
            self.wiki_collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[knowledge.content],
                metadatas=[{
                    "topic": knowledge.topic,
                    "category": knowledge.category,
                    "source": knowledge.source_url
                }]
            )
        
        return doc_id
    
    def query_wiki(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Query wiki knowledge for relevant guides."""
        embedding = self.embedding_client.embed(query)
        
        results = self.wiki_collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        knowledge = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                knowledge.append({
                    "topic": meta.get("topic", "Unknown"),
                    "category": meta.get("category", ""),
                    "content": doc,
                    "similarity": 1 - results["distances"][0][i] if results["distances"] else 0
                })
        
        return knowledge
    
    def wiki_count(self) -> int:
        """Return total wiki entries."""
        return self.wiki_collection.count()


class FFTWikiScraper:
    """Scraper for FFT walkthrough from game8.co."""
    
    BASE_URL = "https://game8.co"
    
    # All 53 battle guides from the walkthrough
    BATTLE_GUIDES = [
        # Chapter 1: The Meager
        {"name": "Battle 1: Orbonne Monastery", "url": "/games/Final-Fantasy-Tactics/archives/553162"},
        {"name": "Battle 2: Magick City of Gariland", "url": "/games/Final-Fantasy-Tactics/archives/553163"},
        {"name": "Battle 3: Mandalia Plain", "url": "/games/Final-Fantasy-Tactics/archives/553164"},
        {"name": "Battle 4: Siedge Weald", "url": "/games/Final-Fantasy-Tactics/archives/553165"},
        {"name": "Battle 5: Dorter Slums", "url": "/games/Final-Fantasy-Tactics/archives/553166"},
        {"name": "Battle 6: Sand Rat Sietch", "url": "/games/Final-Fantasy-Tactics/archives/553167"},
        {"name": "Battle 7: Brigands' Den", "url": "/games/Final-Fantasy-Tactics/archives/553168"},
        {"name": "Battle 8: Lenalian Plateau", "url": "/games/Final-Fantasy-Tactics/archives/553169"},
        {"name": "Battle 9: Fovoham Windflats", "url": "/games/Final-Fantasy-Tactics/archives/553170"},
        {"name": "Battle 10: Ziekden Fortress", "url": "/games/Final-Fantasy-Tactics/archives/553171"},
        # Chapter 2: The Manipulator and the Subservient
        {"name": "Battle 11: Merchant City of Dorter", "url": "/games/Final-Fantasy-Tactics/archives/553172"},
        {"name": "Battle 12: Araguay Woods", "url": "/games/Final-Fantasy-Tactics/archives/553173"},
        {"name": "Battle 13: Zeirchele Falls", "url": "/games/Final-Fantasy-Tactics/archives/553174"},
        {"name": "Battle 14: Castled City of Zaland", "url": "/games/Final-Fantasy-Tactics/archives/553175"},
        {"name": "Battle 15: Balias Tor", "url": "/games/Final-Fantasy-Tactics/archives/553176"},
        {"name": "Battle 16: Tchigolith Fenlands", "url": "/games/Final-Fantasy-Tactics/archives/553177"},
        {"name": "Battle 17: Goug Lowtown", "url": "/games/Final-Fantasy-Tactics/archives/553178"},
        {"name": "Battle 18: Balias Swale", "url": "/games/Final-Fantasy-Tactics/archives/553179"},
        {"name": "Battle 19: Golgollada Gallows", "url": "/games/Final-Fantasy-Tactics/archives/553180"},
        {"name": "Battle 20: Lionel Castle Gate", "url": "/games/Final-Fantasy-Tactics/archives/553181"},
        {"name": "Battle 21: Lionel Castle Keep", "url": "/games/Final-Fantasy-Tactics/archives/553182"},
        # Chapter 3: The Valiant
        {"name": "Battle 22: Mining Town of Gollund", "url": "/games/Final-Fantasy-Tactics/archives/553183"},
        {"name": "Battle 23: Lesalia Castle Postern", "url": "/games/Final-Fantasy-Tactics/archives/553184"},
        {"name": "Battle 24: Monastery Vaults Second Floor", "url": "/games/Final-Fantasy-Tactics/archives/553185"},
        {"name": "Battle 25: Monastery Vaults Third Floor", "url": "/games/Final-Fantasy-Tactics/archives/553186"},
        {"name": "Battle 26: Monastery Vaults First Level", "url": "/games/Final-Fantasy-Tactics/archives/553187"},
        {"name": "Battle 27: Grogh Heights", "url": "/games/Final-Fantasy-Tactics/archives/553188"},
        {"name": "Battle 28: Walled City of Yardrow", "url": "/games/Final-Fantasy-Tactics/archives/553189"},
        {"name": "Battle 29: Yuguewood", "url": "/games/Final-Fantasy-Tactics/archives/553190"},
        {"name": "Battle 30: Riovanes Castle Gate", "url": "/games/Final-Fantasy-Tactics/archives/553191"},
        {"name": "Battle 31: Riovanes Castle Keep (Wiegraf)", "url": "/games/Final-Fantasy-Tactics/archives/553192"},
        {"name": "Battle 32: Riovanes Castle Roof", "url": "/games/Final-Fantasy-Tactics/archives/553193"},
        # Chapter 4: In the Name of Love
        {"name": "Battle 33: Dugeura Pass", "url": "/games/Final-Fantasy-Tactics/archives/553194"},
        {"name": "Battle 34: Free City of Bervenia", "url": "/games/Final-Fantasy-Tactics/archives/553195"},
        {"name": "Battle 35: Finnath Creek", "url": "/games/Final-Fantasy-Tactics/archives/553196"},
        {"name": "Battle 36: Outlying Church", "url": "/games/Final-Fantasy-Tactics/archives/553197"},
        {"name": "Battle 37: Beddha Sandwaste", "url": "/games/Final-Fantasy-Tactics/archives/553198"},
        {"name": "Battle 38: Fort Besselat South Wall", "url": "/games/Final-Fantasy-Tactics/archives/553199"},
        {"name": "Battle 39: Fort Besselat Sluice", "url": "/games/Final-Fantasy-Tactics/archives/553200"},
        {"name": "Battle 40: Mount Germinas", "url": "/games/Final-Fantasy-Tactics/archives/553201"},
        {"name": "Battle 41: Lake Poescas", "url": "/games/Final-Fantasy-Tactics/archives/553202"},
        {"name": "Battle 42: Limberry Castle Gate", "url": "/games/Final-Fantasy-Tactics/archives/553203"},
        {"name": "Battle 43: Limberry Castle Keep", "url": "/games/Final-Fantasy-Tactics/archives/553204"},
        {"name": "Battle 44: Limberry Castle Undercroft", "url": "/games/Final-Fantasy-Tactics/archives/553205"},
        {"name": "Battle 45: Eagrose Castle Keep", "url": "/games/Final-Fantasy-Tactics/archives/553206"},
        {"name": "Battle 46: Mullonde Cathedral", "url": "/games/Final-Fantasy-Tactics/archives/553207"},
        {"name": "Battle 47: Mullonde Cathedral Nave", "url": "/games/Final-Fantasy-Tactics/archives/553208"},
        {"name": "Battle 48: Mullonde Cathedral Sanctuary", "url": "/games/Final-Fantasy-Tactics/archives/553209"},
        {"name": "Battle 49: Monastery Vaults Fourth Level", "url": "/games/Final-Fantasy-Tactics/archives/553210"},
        {"name": "Battle 50: Monastery Vaults Fifth Level", "url": "/games/Final-Fantasy-Tactics/archives/553211"},
        {"name": "Battle 51: Necrohol of Mullonde", "url": "/games/Final-Fantasy-Tactics/archives/553212"},
        {"name": "Battle 52: Lost Halidom", "url": "/games/Final-Fantasy-Tactics/archives/553213"},
        {"name": "Battle 53: Airship Graveyard (Final)", "url": "/games/Final-Fantasy-Tactics/archives/553214"},
    ]
    
    # Job guides
    JOB_GUIDES = [
        {"name": "Squire Job", "url": "/games/Final-Fantasy-Tactics/archives/553001"},
        {"name": "Chemist Job", "url": "/games/Final-Fantasy-Tactics/archives/553011"},
        {"name": "Knight Job", "url": "/games/Final-Fantasy-Tactics/archives/553010"},
        {"name": "Archer Job", "url": "/games/Final-Fantasy-Tactics/archives/553009"},
        {"name": "White Mage Job", "url": "/games/Final-Fantasy-Tactics/archives/553008"},
        {"name": "Black Mage Job", "url": "/games/Final-Fantasy-Tactics/archives/553007"},
        {"name": "Monk Job", "url": "/games/Final-Fantasy-Tactics/archives/553006"},
        {"name": "Thief Job", "url": "/games/Final-Fantasy-Tactics/archives/553005"},
        {"name": "Time Mage Job", "url": "/games/Final-Fantasy-Tactics/archives/553004"},
        {"name": "Summoner Job", "url": "/games/Final-Fantasy-Tactics/archives/553003"},
        {"name": "Mystic Job", "url": "/games/Final-Fantasy-Tactics/archives/553002"},
        {"name": "Geomancer Job", "url": "/games/Final-Fantasy-Tactics/archives/553000"},
        {"name": "Dragoon Job", "url": "/games/Final-Fantasy-Tactics/archives/552999"},
        {"name": "Orator Job", "url": "/games/Final-Fantasy-Tactics/archives/552998"},
        {"name": "Samurai Job", "url": "/games/Final-Fantasy-Tactics/archives/552997"},
        {"name": "Ninja Job", "url": "/games/Final-Fantasy-Tactics/archives/552996"},
        {"name": "Arithmetician Job", "url": "/games/Final-Fantasy-Tactics/archives/552995"},
        {"name": "Dancer Job", "url": "/games/Final-Fantasy-Tactics/archives/552994"},
        {"name": "Bard Job", "url": "/games/Final-Fantasy-Tactics/archives/552993"},
        {"name": "Onion Knight Job", "url": "/games/Final-Fantasy-Tactics/archives/552992"},
        {"name": "Dark Knight Job", "url": "/games/Final-Fantasy-Tactics/archives/552991"},
    ]
    
    # Tips and mechanics guides
    TIPS_GUIDES = [
        {"name": "How to Raise or Lower Bravery", "url": "/games/Final-Fantasy-Tactics/archives/542844"},
        {"name": "How to Farm JP (Job Points)", "url": "/games/Final-Fantasy-Tactics/archives/542549"},
        {"name": "Best Party Builds", "url": "/games/Final-Fantasy-Tactics/archives/542550"},
        {"name": "Best Abilities to Learn First", "url": "/games/Final-Fantasy-Tactics/archives/542551"},
        {"name": "How Faith Works", "url": "/games/Final-Fantasy-Tactics/archives/542845"},
        {"name": "Zodiac Compatibility Guide", "url": "/games/Final-Fantasy-Tactics/archives/542846"},
        {"name": "Speed and CT Mechanics", "url": "/games/Final-Fantasy-Tactics/archives/542847"},
        {"name": "Best Equipment Guide", "url": "/games/Final-Fantasy-Tactics/archives/542848"},
    ]
    
    # Additional guides (user-specified)
    ADDITIONAL_GUIDES = [
        {"name": "List of All Characters", "url": "/games/Final-Fantasy-Tactics/archives/542681"},
        {"name": "Best Units Tier List", "url": "/games/Final-Fantasy-Tactics/archives/541390"},
        {"name": "Locations and Battles", "url": "/games/Final-Fantasy-Tactics/archives/542480"},
        {"name": "List of All Errands", "url": "/games/Final-Fantasy-Tactics/archives/542207"},
        {"name": "List of All Items", "url": "/games/Final-Fantasy-Tactics/archives/541850"},
        {"name": "List of All Abilities", "url": "/games/Final-Fantasy-Tactics/archives/542399"},
        {"name": "Chapter Select Guide", "url": "/games/Final-Fantasy-Tactics/archives/553072"},
        {"name": "100% Walkthrough Guide", "url": "/games/Final-Fantasy-Tactics/archives/543012"},
        {"name": "List of All Weapons", "url": "/games/Final-Fantasy-Tactics/archives/541833"},
        {"name": "List of All Armor", "url": "/games/Final-Fantasy-Tactics/archives/541837"},
        {"name": "Post-Game Content Guide", "url": "/games/Final-Fantasy-Tactics/archives/554434"},
        {"name": "List of All Bosses", "url": "/games/Final-Fantasy-Tactics/archives/542669"},
        {"name": "List of All Enemies", "url": "/games/Final-Fantasy-Tactics/archives/542801"},
        {"name": "Ultimate Character Builds", "url": "/games/Final-Fantasy-Tactics/archives/542992"},
        {"name": "List of All Accessories", "url": "/games/Final-Fantasy-Tactics/archives/541853"},
        {"name": "List of All Consumables", "url": "/games/Final-Fantasy-Tactics/archives/541852"},
        {"name": "Midlight's Deep Guide", "url": "/games/Final-Fantasy-Tactics/archives/542975"},
    ]
    
    # Quick tips that don't need scraping
    QUICK_TIPS = [
        {
            "topic": "Early Game Jobs",
            "category": "tips",
            "content": """Best early game jobs in FFT:
- Squire: Good base job, learn Tailwind for speed boost
- Chemist: Essential for healing with Potions/Phoenix Down
- Black Mage: Powerful AOE damage with Fire/Thunder/Blizzard
- Knight: Tanky frontliner, Rend abilities useful
- Archer: Good range, safe positioning"""
        },
        {
            "topic": "Battle 5 Dorter Slums Strategy",
            "category": "walkthrough",
            "content": """Dorter Slums is one of the hardest early battles:
- 3 Archers on rooftops with height advantage
- Black Mage can deal heavy magic damage
- Strategy: Rush the archers first, they're fragile
- Use Knight to tank hits from melee enemies
- Chemist should stay back and heal
- Position Ramza to flank the Black Mage"""
        },
        {
            "topic": "JP Farming",
            "category": "tips",
            "content": """To farm Job Points (JP) efficiently:
- Use Squire's Throw Stone on party members (low damage)
- Have Chemist heal with Potions
- Accumulate ability builds JP for multiple jobs
- Random battles are best for farming
- Unlock higher tier jobs by leveling base jobs"""
        },
        {
            "topic": "Height and Positioning",
            "category": "tips",
            "content": """Height matters in FFT battles:
- Higher ground = more damage dealt
- Lower ground = less damage dealt
- Archers and mages excel from high positions
- Melee units need to close distance
- Use terrain to your advantage"""
        },
        {
            "topic": "Wiegraf Boss Fight",
            "category": "boss",
            "content": """Wiegraf is a notorious difficulty spike:
- Ramza fights alone in first phase
- Use Tailwind to boost speed before engaging
- Auto-Potion or reaction abilities help survival
- After transformation, focus on healing
- Don't bring too many mages, he resists magic"""
        },
    ]
    
    def __init__(self, knowledge_store: WikiKnowledgeStore = None):
        if not HAS_HTTPX:
            raise ImportError("httpx required: pip install httpx")
        
        self.store = knowledge_store or WikiKnowledgeStore()
        self.client = httpx.Client(timeout=30.0)
    
    def scrape_battle_guide(self, battle_name: str, url: str) -> str:
        """Scrape a single battle guide page."""
        full_url = f"{self.BASE_URL}{url}"
        print(f"[Scraper] Fetching: {battle_name}")
        
        try:
            response = self.client.get(full_url)
            response.raise_for_status()
            
            if HAS_BS4:
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Remove unwanted elements
                for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'aside', 'header']):
                    tag.decompose()
                
                # Try multiple selectors for Game8 content
                content = None
                selectors = [
                    ("article", {}),
                    ("div", {"class": "archive-style-wrapper"}),
                    ("div", {"class": "archive-content"}),
                    ("main", {}),
                    ("div", {"class": "content"}),
                ]
                
                for tag, attrs in selectors:
                    content = soup.find(tag, attrs) if attrs else soup.find(tag)
                    if content:
                        break
                
                if content:
                    # Extract all paragraph and heading text
                    text_parts = []
                    for elem in content.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li', 'td']):
                        text = elem.get_text(strip=True)
                        if text and len(text) > 3:  # Skip tiny fragments
                            text_parts.append(text)
                    
                    # Join with newlines
                    clean_text = "\n".join(text_parts)
                    
                    # Remove duplicate lines
                    seen = set()
                    unique_lines = []
                    for line in clean_text.split("\n"):
                        if line not in seen:
                            seen.add(line)
                            unique_lines.append(line)
                    
                    return "\n".join(unique_lines)[:4000]
                
                # Fallback: get body text
                body = soup.find("body")
                if body:
                    return body.get_text(separator="\n", strip=True)[:4000]
            
            # No BeautifulSoup fallback - strip HTML tags manually
            import re
            text = re.sub(r'<[^>]+>', ' ', response.text)
            text = re.sub(r'\s+', ' ', text)
            return text[:4000]
            
        except Exception as e:
            print(f"[Scraper] Error fetching {battle_name}: {e}")
            return ""
    
    def ingest_quick_tips(self):
        """Ingest pre-defined quick tips (no scraping needed)."""
        print("[Scraper] Ingesting quick tips...")
        
        for tip in self.QUICK_TIPS:
            knowledge = WikiKnowledge(
                topic=tip["topic"],
                category=tip["category"],
                content=tip["content"],
                source_url="pre-defined"
            )
            self.store.store_wiki_knowledge(knowledge)
        
        print(f"[Scraper] Ingested {len(self.QUICK_TIPS)} quick tips")
    
    def ingest_battle_guides(self, max_battles: int = 5):
        """Scrape and ingest battle guides."""
        print(f"[Scraper] Scraping up to {max_battles} battle guides...")
        
        for i, guide in enumerate(self.BATTLE_GUIDES[:max_battles]):
            content = self.scrape_battle_guide(guide["name"], guide["url"])
            
            if content:
                knowledge = WikiKnowledge(
                    topic=guide["name"],
                    category="walkthrough",
                    content=content,
                    source_url=f"{self.BASE_URL}{guide['url']}"
                )
                self.store.store_wiki_knowledge(knowledge)
            
            # Be nice to the server
            time.sleep(1)
        
        print(f"[Scraper] Done! Total wiki entries: {self.store.wiki_count()}")
    
    def ingest_job_guides(self, max_jobs: int = 21):
        """Scrape and ingest job guides."""
        print(f"[Scraper] Scraping up to {max_jobs} job guides...")
        
        for i, guide in enumerate(self.JOB_GUIDES[:max_jobs]):
            content = self.scrape_battle_guide(guide["name"], guide["url"])
            
            if content:
                knowledge = WikiKnowledge(
                    topic=guide["name"],
                    category="job",
                    content=content,
                    source_url=f"{self.BASE_URL}{guide['url']}"
                )
                self.store.store_wiki_knowledge(knowledge)
            
            time.sleep(1)
        
        print(f"[Scraper] Done with jobs! Total wiki entries: {self.store.wiki_count()}")
    
    def ingest_tips_guides(self):
        """Scrape and ingest tips/mechanics guides."""
        print(f"[Scraper] Scraping {len(self.TIPS_GUIDES)} tips guides...")
        
        for guide in self.TIPS_GUIDES:
            content = self.scrape_battle_guide(guide["name"], guide["url"])
            
            if content:
                knowledge = WikiKnowledge(
                    topic=guide["name"],
                    category="tips",
                    content=content,
                    source_url=f"{self.BASE_URL}{guide['url']}"
                )
                self.store.store_wiki_knowledge(knowledge)
            
            time.sleep(1)
        
        print(f"[Scraper] Done with tips! Total wiki entries: {self.store.wiki_count()}")
    
    def ingest_additional_guides(self):
        """Scrape and ingest additional user-specified guides."""
        print(f"[Scraper] Scraping {len(self.ADDITIONAL_GUIDES)} additional guides...")
        
        for guide in self.ADDITIONAL_GUIDES:
            content = self.scrape_battle_guide(guide["name"], guide["url"])
            
            if content:
                knowledge = WikiKnowledge(
                    topic=guide["name"],
                    category="reference",
                    content=content,
                    source_url=f"{self.BASE_URL}{guide['url']}"
                )
                self.store.store_wiki_knowledge(knowledge)
            
            time.sleep(1)
        
        print(f"[Scraper] Done with additional guides! Total wiki entries: {self.store.wiki_count()}")
    
    def ingest_all(self):
        """Scrape everything: tips, all battles, all jobs, mechanics, references."""
        print("=" * 60)
        print("FULL SCRAPE - Ingesting ALL FFT content")
        print("=" * 60)
        
        # Quick tips (instant)
        self.ingest_quick_tips()
        
        # All 53 battles
        print(f"\n[Scraper] Scraping all {len(self.BATTLE_GUIDES)} battle guides...")
        self.ingest_battle_guides(max_battles=len(self.BATTLE_GUIDES))
        
        # All jobs
        print(f"\n[Scraper] Scraping all {len(self.JOB_GUIDES)} job guides...")
        self.ingest_job_guides(max_jobs=len(self.JOB_GUIDES))
        
        # All tips/mechanics
        print(f"\n[Scraper] Scraping {len(self.TIPS_GUIDES)} tips guides...")
        self.ingest_tips_guides()
        
        # All additional reference guides
        print(f"\n[Scraper] Scraping {len(self.ADDITIONAL_GUIDES)} additional guides...")
        self.ingest_additional_guides()
        
        print("\n" + "=" * 60)
        print(f"COMPLETE! Total entries in RAG: {self.store.wiki_count()}")
        print("=" * 60)
    
    def close(self):
        self.client.close()


def main():
    """Main function to ingest FFT walkthrough."""
    import sys
    
    print("=" * 50)
    print("FFT Wiki Scraper - Ingesting Walkthrough")
    print("=" * 50)
    
    scraper = FFTWikiScraper()
    
    # Check for --all flag
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        scraper.ingest_all()
    else:
        # Quick mode: tips + first 10 battles
        scraper.ingest_quick_tips()
        print("\nScraping first 10 battle guides...")
        scraper.ingest_battle_guides(max_battles=10)
        print("\nTip: Run with --all to scrape ALL content (53 battles + 21 jobs)")
    
    # Test query
    print("\n" + "=" * 50)
    print("Testing RAG Query...")
    print("=" * 50)
    
    query = "How do I beat Dorter Slums battle?"
    results = scraper.store.query_wiki(query, n_results=2)
    
    print(f"\nQuery: '{query}'")
    print(f"Found {len(results)} relevant entries:")
    for r in results:
        print(f"\n--- {r['topic']} (similarity: {r['similarity']:.2f}) ---")
        print(r['content'][:300] + "...")
    
    scraper.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
