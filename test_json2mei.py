import sys
import json
from pathlib import Path

# Add src to sys.path so we can import dmp
sys.path.append(str(Path("src").resolve()))

from dmp.exporters.json2mei import generate_mei

pattern_12_44 = {
    "title": "Test 12 4/4",
    "signature": "4/4",
    "length": 12,
    "tracks": {
        "BassDrum": ["Note", "Rest", "Rest", "Note", "Rest", "Rest", "Note", "Rest", "Rest", "Note", "Rest", "Rest"],
        "ClosedHiHat": ["Note", "Note", "Note", "Note", "Note", "Note", "Note", "Note", "Note", "Note", "Note", "Note"]
    }
}

pattern_32 = {
    "title": "Test 32",
    "signature": "4/4",
    "length": 32,
    "tracks": {
        "BassDrum": ["Note"] + ["Rest"] * 15 + ["Note"] + ["Rest"] * 15
    }
}

print("Testing length=12, signature=4/4")
print(generate_mei(pattern_12_44))

print("\n\nTesting length=32")
print(generate_mei(pattern_32))

pattern_12_128 = {
    "title": "Test 12 12/8",
    "signature": "12/8",
    "length": 12,
    "tracks": {
        "BassDrum": ["Note", "Rest", "Rest", "Note", "Rest", "Rest", "Note", "Rest", "Rest", "Note", "Rest", "Rest"],
        "ClosedHiHat": ["Note", "Note", "Note", "Note", "Note", "Note", "Note", "Note", "Note", "Note", "Note", "Note"]
    }
}

print("\n\nTesting length=12, signature=12/8")
print(generate_mei(pattern_12_128))
