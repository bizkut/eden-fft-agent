from cemuhook_server import CemuhookServer, ControllerState
import time
import sys

def test_inputs():
    print("Connecting to existing CemuhookUDP server...")
    # Reuse connection logic from main.py (mock server object)
    server = CemuhookServer.__new__(CemuhookServer)
    server.state = ControllerState()
    
    # Actually, we need to CONNECT to the running server or BE the server.
    # Since main.py runs the server, this script cannot really inject unless it IS a client.
    # BUT CemuhookUDP is a server the EMULATOR connects TO.
    # So we can't have two servers on port 26760.
    
    # Instead, let's just use the CemuhookServer class directly 
    # assuming the user stops valid main.py first.
    
    print("Starting OWN server on port 26760...")
    try:
        real_server = CemuhookServer()
        real_server.start()
        time.sleep(2) # Wait for emulator to connect
    except OSError:
        print("Port in use! Please STOP main.py first.")
        return

    print("Sending inputs in 3 seconds...")
    time.sleep(3)
    
    print("Pressing A (Circle)...")
    real_server.press_a()
    time.sleep(1)
    
    print("Pressing Down...")
    real_server.press_dpad('down')
    time.sleep(1)
    
    print("Pressing Right...")
    real_server.press_dpad('right')
    time.sleep(1)
    
    print("Done. Stopping server.")
    real_server.stop()

if __name__ == "__main__":
    test_inputs()
