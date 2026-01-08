"""
OCR Engine for extracting text/numbers from FFT UI.
"""
import re
from typing import Dict, Optional, List, Tuple

try:
    from PIL import Image
    import numpy as np
except ImportError:
    Image = None
    np = None

try:
    import pytesseract
except ImportError:
    pytesseract = None


class OCREngine:
    """
    Extract text and numbers from game screen.
    Uses Tesseract OCR (pytesseract).
    """
    
    def __init__(self):
        if pytesseract is None:
            raise ImportError("pytesseract required: pip install pytesseract")
        if Image is None:
            raise ImportError("Pillow required: pip install pillow")
    
    def extract_text(self, image: "np.ndarray", region: Optional[Tuple[int,int,int,int]] = None) -> str:
        """
        Extract text from image or region.
        Region: (x, y, width, height)
        """
        if region:
            x, y, w, h = region
            image = image[y:y+h, x:x+w]
        
        pil_img = Image.fromarray(image)
        text = pytesseract.image_to_string(pil_img)
        return text.strip()
    
    def extract_numbers(self, image: "np.ndarray", region: Optional[Tuple[int,int,int,int]] = None) -> List[int]:
        """Extract all numbers from image."""
        text = self.extract_text(image, region)
        numbers = re.findall(r'\d+', text)
        return [int(n) for n in numbers]
    
    def extract_labeled_value(self, image: "np.ndarray", label: str, region: Optional[Tuple[int,int,int,int]] = None) -> Optional[int]:
        """
        Extract value for a label like 'HP: 150' -> 150
        """
        text = self.extract_text(image, region)
        pattern = rf'{label}\s*[:\-]?\s*(\d+)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None


class FFTOCREngine(OCREngine):
    """
    FFT-specific OCR with known UI regions.
    """
    
    # UI regions (x, y, width, height) - These need calibration for actual game
    REGIONS = {
        # Unit stats panel (typically right side)
        'unit_stats': (900, 100, 300, 200),
        # Battle log / action text
        'battle_log': (100, 500, 600, 100),
        # Menu options
        'menu': (400, 300, 400, 300),
    }
    
    def extract_unit_stats(self, frame: "np.ndarray") -> Dict[str, Optional[int]]:
        """Extract unit stats from the full frame (robust to UI position)."""
        # Scan full frame for now as UI position varies
        text = self.extract_text(frame)
        
        # Helper to find values like "HP 153/153" or "HP: 153"
        def find_stat(label: str):
            # Regex: Label followed by any non-digit chars (lazy), then the number
            # Handles "MP ae (24/24" -> finds 24
            pattern = rf'{label}\D*?(\d+)'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
            return None
            
        def find_max_stat(label: str):
             # Find max value after slash: "HP ... 153 / 153"
             # Label, non-digits, number, non-digits (inc slash), number
             pattern = rf'{label}\D*?\d+\D*?/\D*?(\d+)'
             match = re.search(pattern, text, re.IGNORECASE)
             if match:
                 return int(match.group(1))
             return None

        return {
            'hp': find_stat('HP'),
            'max_hp': find_max_stat('HP'),
            'mp': find_stat('MP'),
            'max_mp': find_max_stat('MP'),
            'ct': find_stat('CT'),
        }
    
    def extract_all_numbers(self, frame: "np.ndarray") -> Dict[str, List[int]]:
        """Extract numbers from all known regions."""
        result = {}
        for name, region in self.REGIONS.items():
            result[name] = self.extract_numbers(frame, region)
        return result


class MockOCREngine:
    """Mock OCR for testing without Tesseract."""
    
    def extract_text(self, image, region=None) -> str:
        return "HP: 150 MP: 45"
    
    def extract_numbers(self, image, region=None) -> List[int]:
        return [150, 45]
    
    def extract_labeled_value(self, image, label, region=None) -> Optional[int]:
        mock_values = {'HP': 150, 'MP': 45, 'CT': 80}
        return mock_values.get(label)


if __name__ == "__main__":
    # Test with mock
    ocr = MockOCREngine()
    hp = ocr.extract_labeled_value(None, 'HP')
    print(f"Extracted HP: {hp}")
