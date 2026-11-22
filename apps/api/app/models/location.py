from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.scripts import LANG_SCRIPT, detect_script
from app.models.base import Base, TimestampMixin


class _Named:
    """PK is the official LGD code; names keyed by language code."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    names: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    def name_in(self, lang: str | None) -> str:
        # Exact language, else the untagged local name if it is in this language's
        # script (Devanagari serves mr + hi readers), else English. Never show a
        # Tamil reader Devanagari.
        if not lang or lang == "en":
            return self.name_en
        if self.names.get(lang):
            return self.names[lang]
        local = self.names.get("local")
        if local and LANG_SCRIPT.get(lang) and detect_script(local) == LANG_SCRIPT[lang]:
            return local
        return self.name_en


class State(_Named, TimestampMixin, Base):
    __tablename__ = "states"

    default_language: Mapped[str | None] = mapped_column(String(10))


class District(_Named, TimestampMixin, Base):
    __tablename__ = "districts"

    state_id: Mapped[int] = mapped_column(ForeignKey("states.id"), nullable=False)


class Tehsil(_Named, TimestampMixin, Base):
    __tablename__ = "tehsils"

    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), nullable=False)


class Village(_Named, TimestampMixin, Base):
    __tablename__ = "villages"

    tehsil_id: Mapped[int] = mapped_column(ForeignKey("tehsils.id"), nullable=False)


class TehsilNeighbour(Base):
    __tablename__ = "tehsil_neighbours"

    tehsil_id: Mapped[int] = mapped_column(
        ForeignKey("tehsils.id", ondelete="CASCADE"), primary_key=True
    )
    neighbour_tehsil_id: Mapped[int] = mapped_column(
        ForeignKey("tehsils.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="import")


class DealerServiceArea(Base):
    __tablename__ = "dealer_service_areas"

    dealer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dealers.id", ondelete="CASCADE"), primary_key=True
    )
    tehsil_id: Mapped[int] = mapped_column(ForeignKey("tehsils.id"), primary_key=True)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
