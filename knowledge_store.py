"""
Knowledge Store for Visual Feedback Learning.
Uses ChromaDB for vector storage and LM Studio for embeddings.
"""
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import json
import time

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    chromadb = None

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


class EmbeddingClient:
    """
    Embedding client with sentence-transformers as default.
    Falls back to LM Studio API if sentence-transformers unavailable.
    """
    
    def __init__(
        self,
        use_local: bool = True,
        local_model: str = "all-MiniLM-L6-v2",  # Fast & good quality
        api_base_url: str = "http://localhost:1234/v1",
        api_model: str = "text-embedding-nomic-embed-text-v1.5"
    ):
        self.use_local = use_local and HAS_SENTENCE_TRANSFORMERS
        
        if self.use_local:
            print(f"[Embeddings] Using local sentence-transformers: {local_model}")
            self.model = SentenceTransformer(local_model)
        elif HAS_HTTPX:
            print(f"[Embeddings] Using LM Studio API: {api_base_url}")
            self.api_url = api_base_url.rstrip("/")
            self.api_model = api_model
        else:
            raise ImportError("Either sentence-transformers or httpx required")
    
    def embed(self, text: str) -> List[float]:
        """Get embedding vector for text."""
        if self.use_local:
            return self.model.encode(text).tolist()
        else:
            return self._embed_via_api(text)
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts."""
        if self.use_local:
            return [e.tolist() for e in self.model.encode(texts)]
        else:
            return [self._embed_via_api(t) for t in texts]
    
    def _embed_via_api(self, text: str) -> List[float]:
        """Fallback: Get embedding via LM Studio API."""
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self.api_url}/embeddings",
                json={"model": self.api_model, "input": text}
            )
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]


@dataclass
class ActionLearning:
    """A learned action-effect pair."""
    button: str                    # e.g., "a", "up", "down"
    game_phase: str                # e.g., "battle_menu", "move_mode"
    context_description: str       # LLM description of before state
    effect_description: str        # LLM description of what changed
    before_frame_path: Optional[str] = None
    after_frame_path: Optional[str] = None
    timestamp: float = 0.0


class KnowledgeStore:
    """
    Vector store for action-effect learnings using ChromaDB.
    Stores what happens when buttons are pressed in different contexts.
    """
    
    def __init__(
        self,
        persist_directory: str = "./knowledge_db",
        use_local_embeddings: bool = True
    ):
        if not HAS_CHROMADB:
            raise ImportError("chromadb required: pip install chromadb")
        
        self.persist_dir = persist_directory
        self.embedding_client = EmbeddingClient(use_local=use_local_embeddings)
        
        # Initialize ChromaDB with persistence
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        # Create or get the action learnings collection
        self.collection = self.client.get_or_create_collection(
            name="action_learnings",
            metadata={"description": "Button press effects learned from visual feedback"}
        )

        # Create or get the strategy guides collection
        self.strategy_collection = self.client.get_or_create_collection(
            name="strategy_guides",
            metadata={"description": "Game strategy guides, job classes, and tactics"}
        )
        
        print(f"[KnowledgeStore] Initialized with {self.collection.count()} learnings")
    
    def store_learning(self, learning: ActionLearning) -> str:
        """Store a new action-effect learning."""
        # Create searchable text from the learning
        search_text = f"Button: {learning.button} | Phase: {learning.game_phase} | Context: {learning.context_description}"
        
        # Get embedding
        embedding = self.embedding_client.embed(search_text)
        
        # Generate unique ID
        doc_id = f"learn_{int(learning.timestamp * 1000)}"
        
        # Store in ChromaDB
        self.collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[search_text],
            metadatas=[{
                "button": learning.button,
                "game_phase": learning.game_phase,
                "context": learning.context_description,
                "effect": learning.effect_description,
                "before_frame": learning.before_frame_path or "",
                "after_frame": learning.after_frame_path or "",
                "timestamp": learning.timestamp
            }]
        )
        
        print(f"[KnowledgeStore] Stored learning: {learning.button} in {learning.game_phase} -> {learning.effect_description[:50]}...")
        return doc_id
    
    def query_similar(
        self,
        button: str,
        game_phase: str,
        context_description: str,
        n_results: int = 3
    ) -> List[Dict[str, Any]]:
        """Find similar past experiences for a given situation."""
        # Create query text
        query_text = f"Button: {button} | Phase: {game_phase} | Context: {context_description}"
        
        # Get embedding
        embedding = self.embedding_client.embed(query_text)
        
        # Query ChromaDB
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        # Format results
        learnings = []
        if results and results["metadatas"]:
            for i, meta in enumerate(results["metadatas"][0]):
                learnings.append({
                    "button": meta["button"],
                    "game_phase": meta["game_phase"],
                    "context": meta["context"],
                    "effect": meta["effect"],
                    "similarity": 1 - results["distances"][0][i] if results["distances"] else 0
                })
        
        return learnings
    
    def get_button_knowledge(self, button: str, game_phase: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all learnings for a specific button (optionally filtered by phase)."""
        where_filter = {"button": button}
        if game_phase:
            where_filter = {"$and": [{"button": button}, {"game_phase": game_phase}]}
        
        results = self.collection.get(
            where=where_filter,
            include=["documents", "metadatas"]
        )
        
        learnings = []
        if results and results["metadatas"]:
            for meta in results["metadatas"]:
                learnings.append({
                    "button": meta["button"],
                    "game_phase": meta["game_phase"],
                    "context": meta["context"],
                    "effect": meta["effect"]
                })
        
        return learnings
    
    def count(self) -> int:
        """Return total number of learnings stored."""
        return self.collection.count()

    def store_strategy_guide(self, title: str, content: str, tags: List[str] = []) -> str:
        """Store a strategy guide or wiki page."""
        embedding = self.embedding_client.embed(content)
        doc_id = f"guide_{int(time.time() * 1000)}"
        
        self.strategy_collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[{
                "title": title,
                "tags": ",".join(tags),
                "timestamp": time.time()
            }]
        )
        print(f"[KnowledgeStore] Stored guide: {title}")
        return doc_id

    def query_strategy(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Query strategy guides."""
        embedding = self.embedding_client.embed(query)
        results = self.strategy_collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        guides = []
        if results and results["metadatas"]:
            for i, meta in enumerate(results["metadatas"][0]):
                guides.append({
                    "title": meta["title"],
                    "content": results["documents"][0][i],
                    "similarity": 1 - results["distances"][0][i] if results["distances"] else 0
                })
        return guides


# Test
if __name__ == "__main__":
    print("Testing KnowledgeStore...")
    
    store = KnowledgeStore()
    
    # Create test learning
    learning = ActionLearning(
        button="a",
        game_phase="battle_menu",
        context_description="Menu showing Move, Act, Wait options. Cursor on Move.",
        effect_description="Blue movement tiles appeared around the character.",
        timestamp=time.time()
    )
    
    # Store it
    doc_id = store.store_learning(learning)
    print(f"Stored with ID: {doc_id}")
    
    # Query similar
    results = store.query_similar(
        button="a",
        game_phase="battle_menu",
        context_description="Battle menu open, cursor pointer visible"
    )
    print(f"Found {len(results)} similar experiences:")
    for r in results:
        print(f"  - {r['button']} in {r['game_phase']}: {r['effect'][:50]}...")
