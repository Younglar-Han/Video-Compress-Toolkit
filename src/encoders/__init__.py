from .base import BaseEncoder
from .intel import IntelEncoder
from .nvidia import NvidiaEncoder
from .mac import MacEncoder

def get_encoder(name: str) -> BaseEncoder:
    """Factory function to get an encoder instance."""
    encoders = {
        "intel": IntelEncoder(),
        "nvidia": NvidiaEncoder(),
        "mac": MacEncoder(),
    }
    if name not in encoders:
        raise ValueError(f"Unknown encoder: {name}. Available: {list(encoders.keys())}")
    return encoders[name]
