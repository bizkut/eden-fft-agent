"""
Frame capture from Eden emulator using direct memory capture via Quartz.
No disk I/O - captures directly to numpy array.
"""
import os
from typing import Optional

try:
    from PIL import Image
    import numpy as np
except ImportError:
    Image = None
    np = None

try:
    import Quartz
    from Quartz import CGWindowListCopyWindowInfo, CGWindowListCreateImage
    from Quartz import kCGWindowListOptionOnScreenOnly, kCGNullWindowID
    from Quartz import kCGWindowListOptionIncludingWindow, kCGWindowImageBoundsIgnoreFraming
    from Quartz import CGRectNull
    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False


class FrameCapture:
    """
    Capture frames from the emulator directly to memory using Quartz.
    Works even when Eden is in the background.
    """
    
    def __init__(self, window_name: str = "eden"):
        if Image is None or np is None:
            raise ImportError("Pillow and numpy required: pip install pillow numpy")
        if not HAS_QUARTZ:
            raise ImportError("pyobjc-framework-Quartz required: pip install pyobjc-framework-Quartz")
        
        self.window_name = window_name.lower()
        self._window_id: Optional[int] = None
        self._find_window()
    
    def _find_window(self) -> Optional[int]:
        """Find the Eden window ID using Quartz."""
        try:
            window_list = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly,
                kCGNullWindowID
            )
            
            for window in window_list:
                owner = window.get('kCGWindowOwnerName', '') or ''
                name = window.get('kCGWindowName', '') or ''
                owner_lower = owner.lower()
                
                # Match Eden app specifically - owner must be "eden" not just contain it
                # Avoid matching Terminal/iTerm that might have "eden" in the window title
                is_terminal = owner_lower in ['terminal', 'iterm2', 'iterm', 'warp', 'kitty', 'alacritty']
                
                if owner_lower == 'eden' or (self.window_name in owner_lower and not is_terminal):
                    self._window_id = window.get('kCGWindowNumber')
                    print(f"Found Eden window: {owner} - {name} (ID: {self._window_id})")
                    return self._window_id
                    
        except Exception as e:
            print(f"Window search failed: {e}")
        
        print(f"Warning: Eden window not found. Make sure Eden is running.")
        return None
    
    def _cgimage_to_numpy(self, cg_image) -> "np.ndarray":
        """Convert CGImage to numpy array (RGB)."""
        width = Quartz.CGImageGetWidth(cg_image)
        height = Quartz.CGImageGetHeight(cg_image)
        bytes_per_row = Quartz.CGImageGetBytesPerRow(cg_image)
        
        # Get pixel data
        data_provider = Quartz.CGImageGetDataProvider(cg_image)
        data = Quartz.CGDataProviderCopyData(data_provider)
        
        # Convert to numpy - data is BGRA format
        arr = np.frombuffer(data, dtype=np.uint8)
        arr = arr.reshape((height, bytes_per_row // 4, 4))
        arr = arr[:, :width, :]  # Trim padding
        
        # Convert BGRA to RGB
        return arr[:, :, [2, 1, 0]]  # Swap B and R channels
    
    def capture(self) -> "np.ndarray":
        """Capture current frame as numpy array (H, W, 3) RGB."""
        try:
            # Refresh window ID if not found
            if self._window_id is None:
                self._find_window()
            
            if self._window_id:
                # Capture specific window directly to memory
                cg_image = CGWindowListCreateImage(
                    CGRectNull,  # Capture full window bounds
                    kCGWindowListOptionIncludingWindow,
                    self._window_id,
                    kCGWindowImageBoundsIgnoreFraming  # Exclude window frame
                )
                
                if cg_image:
                    frame = self._cgimage_to_numpy(cg_image)
                    # Crop title bar if it looks like a window capture
                    if self._window_id and frame.shape[0] > 100:
                         # Heuristic: Title bar is usually top ~28-40px on macOS
                         # Eden content starts below valid content
                         return frame[40:, :, :]
                    return frame
            
            # Fallback: capture entire screen
            cg_image = Quartz.CGWindowListCreateImage(
                CGRectNull,
                kCGWindowListOptionOnScreenOnly,
                kCGNullWindowID,
                0
            )
            
            if cg_image:
                return self._cgimage_to_numpy(cg_image)
                
        except Exception as e:
            print(f"Capture failed: {e}")
        
        # Return blank frame on failure
        return np.zeros((720, 1280, 3), dtype=np.uint8)
    
    def capture_region(self, x: int, y: int, w: int, h: int) -> "np.ndarray":
        """Capture specific region of the screen."""
        full = self.capture()
        return full[y:y+h, x:x+w]


class MockFrameCapture:
    """Mock capture for testing without emulator."""
    
    def capture(self) -> "np.ndarray":
        import numpy as np
        return np.zeros((720, 1280, 3), dtype=np.uint8)
    
    def capture_region(self, x: int, y: int, w: int, h: int) -> "np.ndarray":
        import numpy as np
        return np.zeros((h, w, 3), dtype=np.uint8)


if __name__ == "__main__":
    import time
    
    cap = FrameCapture()
    print(f"Window ID: {cap._window_id}")
    
    # Benchmark
    start = time.time()
    for _ in range(10):
        frame = cap.capture()
    elapsed = time.time() - start
    
    print(f"Captured frame shape: {frame.shape}")
    print(f"Average capture time: {elapsed/10*1000:.1f}ms")
