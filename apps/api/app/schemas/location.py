from pydantic import BaseModel, Field


class PlaceOut(BaseModel):
    id: int  # LGD code
    name: str  # in the requested language, falling back to English
    name_en: str


class NearbyTehsilOut(PlaceOut):
    rank: int  # 0 = self, 1.. curated neighbours, 99 = same-district fallback


class NeighbourIn(BaseModel):
    tehsil_id: int
    rank: int = Field(default=1, ge=1, le=50)


class NeighboursIn(BaseModel):
    neighbours: list[NeighbourIn]
