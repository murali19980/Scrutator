"""Interactive user approval flow for applying memories."""

from typing import List, Generator
from memory.types import MemoryEntry

def apply_memory_interactively(
    memories: List[MemoryEntry],
    query: str
) -> Generator[MemoryEntry, None, None]:
    """
    Show relevant memories to the user and ask if they want to apply them.
    Yields each approved memory.
    """
    if not memories:
        return
        
    print("\n🧠 Relevant memories discovered:")
    for mem in memories:
        print(f"\n[{mem.type.upper()}] Topic: {mem.topic}")
        print(f"Content: {mem.content}")
        
        while True:
            response = input("Apply this memory to the current research? (y/n): ").strip().lower()
            if response in ['y', 'yes']:
                yield mem
                break
            elif response in ['n', 'no']:
                break
            else:
                print("Please enter 'y' or 'n'.")
