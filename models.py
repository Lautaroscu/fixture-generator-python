from typing import Optional, List, Dict
from sqlmodel import SQLModel, Field, Relationship, JSON, Column

class Club(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str = Field(index=True, unique=True)
    localidad: Optional[str] = None
    estadio_local: Optional[str] = None
    estadio_propio: bool = True

    equipos: List["Equipo"] = Relationship(back_populates="club")

class Equipo(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str # Display name (e.g. "Loma Negra Inferiores")
    club_id: int = Field(foreign_key="club.id")
    division_mayor: str = "A"
    division_infantiles: Optional[str] = None
    jerarquia: int = 0
    
    # Stores categories as a dict: {"primera": True, "reserva": False, ...}
    categorias: Dict[str, bool] = Field(default={}, sa_column=Column(JSON))

    club: Club = Relationship(back_populates="equipos")

class Regla(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    club_a_id: int = Field(foreign_key="club.id")
    club_b_id: int = Field(foreign_key="club.id")
    bloque_a: str
    bloque_b: str
    tipo: str # ESPEJO / INVERSO
    peso: int = 500

class FechaFixture(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nro_fecha: int
    liga: str # e.g. "MAYORES-A"

    partidos: List["PartidoFixture"] = Relationship(back_populates="fecha")

class PartidoFixture(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    fecha_id: int = Field(foreign_key="fechafixture.id")
    local_id: int = Field(foreign_key="equipo.id")
    visitante_id: int = Field(foreign_key="equipo.id")
    cancha: Optional[str] = None

    fecha: FechaFixture = Relationship(back_populates="partidos")
    equipo_local: Equipo = Relationship(sa_relationship_kwargs={"foreign_keys": "[PartidoFixture.local_id]"})
    equipo_visitante: Equipo = Relationship(sa_relationship_kwargs={"foreign_keys": "[PartidoFixture.visitante_id]"})
