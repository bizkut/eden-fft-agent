"""
Web Search for FFT Agent.
Searches the internet when RAG database doesn't have the answer.
Uses DuckDuckGo (free, no API key required).
"""
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


@dataclass
class SearchResult:
    """A web search result."""
    title: str
    url: str
    snippet: str


class WebSearcher:
    """
    Web search using DuckDuckGo Instant Answer API.
    Falls back to scraping if needed.
    """
    
    DDG_API = "https://api.duckduckgo.com/"
    
    def __init__(self):
        if not HAS_HTTPX:
            raise ImportError("httpx required: pip install httpx")
        self.client = httpx.Client(timeout=15.0)
    
    def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """
        Search the web for the given query.
        Returns list of search results.
        """
        # Try DuckDuckGo Instant Answer API first
        results = self._search_instant_answer(query, max_results)
        
        # If no results, try HTML search fallback
        if not results:
            results = self._search_html(query, max_results)
        
        return results
    
    def _search_instant_answer(self, query: str, max_results: int) -> List[SearchResult]:
        """Use DuckDuckGo Instant Answer API."""
        try:
            response = self.client.get(
                self.DDG_API,
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1,
                }
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            
            # Check for instant answer
            if data.get("AbstractText"):
                results.append(SearchResult(
                    title=data.get("Heading", "DuckDuckGo Answer"),
                    url=data.get("AbstractURL", ""),
                    snippet=data["AbstractText"]
                ))
            
            # Check for related topics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append(SearchResult(
                        title=topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                        url=topic.get("FirstURL", ""),
                        snippet=topic.get("Text", "")
                    ))
            
            return results[:max_results]
            
        except Exception as e:
            print(f"[WebSearch] Instant Answer API error: {e}")
            return []
    
    def _search_html(self, query: str, max_results: int) -> List[SearchResult]:
        """Fallback: Scrape DuckDuckGo HTML search results."""
        try:
            response = self.client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            )
            response.raise_for_status()
            
            results = []
            # Simple parsing without BeautifulSoup
            html = response.text
            
            # Extract result blocks (basic regex-like parsing)
            import re
            # Find result snippets
            snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)<', html)
            titles = re.findall(r'class="result__a"[^>]*>([^<]+)<', html)
            urls = re.findall(r'class="result__url"[^>]*href="([^"]+)"', html)
            
            for i in range(min(len(snippets), max_results)):
                results.append(SearchResult(
                    title=titles[i] if i < len(titles) else f"Result {i+1}",
                    url=urls[i] if i < len(urls) else "",
                    snippet=snippets[i].strip()
                ))
            
            return results
            
        except Exception as e:
            print(f"[WebSearch] HTML search error: {e}")
            return []
    
    def search_fft(self, question: str) -> List[SearchResult]:
        """Search specifically for FFT-related content."""
        query = f"Final Fantasy Tactics {question}"
        return self.search(query)
    
    def get_answer(self, question: str) -> Optional[str]:
        """
        Get a direct answer to a question if available.
        Returns the best snippet or None.
        """
        results = self.search_fft(question)
        if results:
            return results[0].snippet
        return None
    
    def close(self):
        self.client.close()


class SmartKnowledgeRetriever:
    """
    Retrieves knowledge from RAG first, falls back to web search.
    """
    
    def __init__(self, knowledge_store=None, web_searcher=None):
        self.rag = knowledge_store
        self.web = web_searcher or WebSearcher()
        self.min_similarity = 0.5  # Threshold for "good enough" RAG result
    
    def query(self, question: str, n_results: int = 3) -> Dict[str, Any]:
        """
        Query for knowledge: RAG first, web search fallback.
        Returns dict with source, results, and confidence.
        """
        result = {
            "source": "none",
            "results": [],
            "confidence": 0.0,
            "query": question
        }
        
        # Try RAG first (strategy_guides collection)
        if self.rag:
            try:
                # Try strategy guides first
                rag_results = self.rag.query_strategy(question, n_results)
                
                if rag_results and rag_results[0].get("similarity", 0) >= self.min_similarity:
                    result["source"] = "rag"
                    result["results"] = [
                        {"topic": r["title"], "content": r["content"]}
                        for r in rag_results
                    ]
                    result["confidence"] = rag_results[0]["similarity"]
                    print(f"[Knowledge] Found in RAG (confidence: {result['confidence']:.2f})")
                    return result
            except Exception as e:
                print(f"[Knowledge] RAG error: {e}")
        
        # Fallback to web search
        print(f"[Knowledge] RAG insufficient, searching web for: {question}")
        web_results = self.web.search_fft(question)
        
        if web_results:
            result["source"] = "web"
            result["results"] = [
                {"topic": r.title, "content": r.snippet, "url": r.url}
                for r in web_results
            ]
            result["confidence"] = 0.7  # Web results have medium confidence
            print(f"[Knowledge] Found {len(web_results)} web results")
            
            # Cache useful web results to RAG for future use
            self._cache_to_rag(question, web_results)
        else:
            print(f"[Knowledge] No results found")
        
        return result
    
    def _cache_to_rag(self, query: str, web_results: List[Any]):
        """Fetch full article content from URLs and store in RAG."""
        if not self.rag:
            return
        
        cached_count = 0
        for r in web_results[:2]:  # Process top 2 results
            try:
                # Extract actual URL from DuckDuckGo redirect
                url = r.url
                if "uddg=" in url:
                    import urllib.parse
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                    url = parsed.get("uddg", [url])[0]
                
                # Fetch full page content
                full_content = self._fetch_page_content(url)
                
                if full_content and len(full_content) > 100:
                    self.rag.store_strategy_guide(
                        title=r.title[:100],
                        content=full_content,
                        tags=["web_learned", query.split()[0] if query else "general"]
                    )
                    cached_count += 1
                    print(f"[Knowledge] Learned: {r.title[:50]}... ({len(full_content)} chars)")
                    
            except Exception as e:
                print(f"[Knowledge] Failed to fetch {r.title[:30]}: {e}")
        
        if cached_count:
            print(f"[Knowledge] Stored {cached_count} articles to brain")
    
    def _fetch_page_content(self, url: str, max_length: int = 5000) -> str:
        """Fetch and extract main text content from a webpage."""
        try:
            response = self.web.client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
                follow_redirects=True,
                timeout=10.0
            )
            response.raise_for_status()
            html = response.text
            
            # Simple content extraction (no BeautifulSoup dependency)
            import re
            
            # Remove script and style tags
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
            
            # Extract text from paragraphs and headers
            paragraphs = re.findall(r'<(?:p|h[1-6]|li)[^>]*>([^<]+(?:<[^>]+>[^<]*)*)</[^>]+>', html)
            
            # Clean up extracted text
            text_parts = []
            for p in paragraphs:
                # Remove remaining HTML tags
                clean = re.sub(r'<[^>]+>', ' ', p)
                # Decode HTML entities
                clean = clean.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                clean = clean.replace('&#x27;', "'").replace('&quot;', '"').replace('&nbsp;', ' ')
                clean = ' '.join(clean.split())  # Normalize whitespace
                if len(clean) > 20:  # Skip very short fragments
                    text_parts.append(clean)
            
            content = '\n'.join(text_parts)
            
            # Truncate if too long
            if len(content) > max_length:
                content = content[:max_length] + "..."
            
            return content
            
        except Exception as e:
            print(f"[Knowledge] Fetch error: {e}")
            return ""
    
    def get_knowledge_for_prompt(self, question: str) -> str:
        """
        Get formatted knowledge string for including in LLM prompt.
        """
        result = self.query(question)
        
        if not result["results"]:
            return ""
        
        lines = []
        if result["source"] == "rag":
            lines.append("## Relevant Knowledge (from database):")
        else:
            lines.append("## Relevant Knowledge (from web search):")
        
        for r in result["results"][:3]:
            topic = r.get("topic", "")
            content = r.get("content", "")[:300]
            lines.append(f"**{topic}**: {content}...")
        
        return "\n".join(lines)
    
    def close(self):
        self.web.close()


# Test
if __name__ == "__main__":
    print("Testing Web Search...")
    
    searcher = WebSearcher()
    results = searcher.search_fft("how to beat Wiegraf")
    
    print(f"Found {len(results)} results:")
    for r in results:
        print(f"\n--- {r.title} ---")
        print(f"URL: {r.url}")
        print(f"Snippet: {r.snippet[:200]}...")
    
    searcher.close()
