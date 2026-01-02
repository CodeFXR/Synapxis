from dataclasses import dataclass, field
from typing import List

@dataclass
class Note:
    """Represents a single Zettel/Note."""
    id: str
    title: str
    content: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    modified_at: str = ""
    
    # We will add a method to easily serialize this for JSON
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }
