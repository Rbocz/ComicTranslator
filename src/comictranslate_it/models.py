"""Versioned JSON project entities; all locations are in original-image pixels."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Literal


@dataclass
class Rect:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self):
        return self.x2 - self.x1

    @property
    def height(self):
        return self.y2 - self.y1

    def clamp(self, width: int, height: int) -> "Rect":
        return Rect(max(0, min(width, self.x1)), max(0, min(height, self.y1)),
                    max(0, min(width, self.x2)), max(0, min(height, self.y2)))

    def valid(self) -> bool:
        return self.x2 > self.x1 and self.y2 > self.y1

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x1, self.y1, self.x2, self.y2)


@dataclass
class Region:
    id: str
    balloon: Rect
    words: list[Rect] = field(default_factory=list)
    original: str = ""
    italian: str = ""
    kind: Literal["dialogue", "caption", "art_text"] = "dialogue"
    shape: Literal["rect", "ellipse", "polygon"] = "rect"
    polygon: list[list[int]] = field(default_factory=list)
    detected: bool = False
    approved: bool = False
    confidence: float = 0.0
    source: str = "manual"
    font_size_max: int = 42
    font_size_min: int = 12
    uppercase: bool = True
    preferred_lines: int = 0
    margin: int = 7
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Region":
        data = dict(d)
        data["balloon"] = Rect(**data["balloon"])
        data["words"] = [Rect(**word) for word in data.get("words", [])]
        return cls(**data)

    def to_dict(self):
        return asdict(self)


@dataclass
class Page:
    filename: str
    width: int
    height: int
    regions: list[Region] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Page":
        return cls(d["filename"], d["width"], d["height"],
                   [Region.from_dict(r) for r in d.get("regions", [])])

    def to_dict(self):
        return asdict(self)
