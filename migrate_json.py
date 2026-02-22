import json
from sqlmodel import Session, select
from database import engine, init_db
from models import Club, Equipo, Regla

def migrate():
    print("Iniciando migración de datos...")
    init_db()
    with Session(engine) as session:
        try:
            with open("equipos.json", "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error al abrir equipos.json: {e}")
            return
        
        # 1. Identificación de Clubes
        clubs_dict = {} # nombre -> Club object
        
        # Primero recolectamos todos los nombres que actúan como "padres" o clubes base
        all_club_names = set()
        for eq in data.get("equipos", []):
            all_club_names.add(eq.get("clubPadre") or eq["nombre"])
        for r in data.get("reglas", []):
            all_club_names.add(r["clubA"])
            all_club_names.add(r["clubB"])
            
        print(f"Se encontraron {len(all_club_names)} clubes únicos.")

        for club_name in all_club_names:
            # Buscamos si ya existe
            statement = select(Club).where(Club.nombre == club_name)
            db_club = session.exec(statement).first()
            if not db_club:
                # Intentamos buscar info de este club en la lista de equipos para llenar localidad y estadio
                matching_eq = None
                for eq in data.get("equipos", []):
                    if eq.get("clubPadre") == club_name or eq["nombre"] == club_name:
                        matching_eq = eq
                        break
                
                new_club = Club(
                    nombre=club_name,
                    localidad=matching_eq.get("localidad") if matching_eq else None,
                    estadio_local=matching_eq.get("estadioLocal") if matching_eq else None,
                    estadio_propio=matching_eq.get("estadioPropio", True) if matching_eq else True
                )
                session.add(new_club)
                clubs_dict[club_name] = new_club
            else:
                clubs_dict[club_name] = db_club
        
        session.commit()
        for c in clubs_dict.values():
            session.refresh(c)

        # 2. Creación de Equipos
        print("Migrando equipos...")
        for eq in data.get("equipos", []):
            club_name = eq.get("clubPadre") or eq["nombre"]
            club = clubs_dict[club_name]
            
            new_equipo = Equipo(
                nombre=eq["nombre"],
                club_id=club.id,
                division_mayor=eq.get("divisionMayor", "A"),
                division_infantiles=eq.get("divisionInfantiles"),
                jerarquia=eq.get("jerarquia", 0),
                categorias=eq.get("categorias", {})
            )
            session.add(new_equipo)
        
        # 3. Creación de Reglas
        print("Migrando reglas...")
        for r in data.get("reglas", []):
            club_a_name = r["clubA"]
            club_b_name = r["clubB"]
            
            club_a = clubs_dict.get(club_a_name)
            club_b = clubs_dict.get(club_b_name)
            
            if club_a and club_b:
                new_regla = Regla(
                    club_a_id=club_a.id,
                    club_b_id=club_b.id,
                    bloque_a=r["bloqueA"],
                    bloque_b=r["bloqueB"],
                    tipo=r["tipo"],
                    peso=r.get("peso", 500)
                )
                session.add(new_regla)
            else:
                print(f"Aviso: Regla omitida, club no encontrado: {club_a_name} o {club_b_name}")

        session.commit()
        print("Migración completada con éxito.")

if __name__ == "__main__":
    migrate()
