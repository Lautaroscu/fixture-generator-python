from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Set, Dict
import uuid
import json
import os
from fixture_generator import FixtureGenerator
from database import init_db, get_session
from models import Club, Equipo, Regla, FechaFixture, PartidoFixture
from sqlmodel import Session, select
from migrate_json import migrate


# ==========================================
# 1. DTOs (Modelos Pydantic)
# ==========================================

class EquipoDTO(BaseModel):
    id: int
    nombre: str
    jerarquia: int
    bloque: str                 # En Java sería Enum (e.g., Bloque.A)
    categoriasHabilitadas: Set[str] # Set de Enum en Java
    clubId: Optional[int]       # Puede ser null (None en Python)
    clubNombre: Optional[str]
    divisionMayor: str          # Enum Liga
    diaDeJuego: str             # Enum DiaJuego

class PartidoDTO(BaseModel):
    local: str
    visitante: str
    cancha: str

class FechaDTO(BaseModel):
    nroFecha: int
    liga: str
    partidos: List[PartidoDTO] = []

class ResponseDTO(BaseModel):
    message: str
    success: bool

class JobStatusDTO(BaseModel):
    jobId: str
    status: str
    message: str

# ==========================================
# 2. Configuración de la App FastAPI
# ==========================================

app = FastAPI(title="Fixture API Liga de Tandil")

# ==========================================
# Configuración de CORS
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()
    print("Database initialized")

# global para estados de jobs únicamente (esto podría ir a DB también, pero por ahora está bien aquí)
jobs_status = {}

# ==========================================
# 3. Función del proceso en Segundo Plano
# ==========================================
def proceso_ortools_async(job_id: str):
    print(f"[BACKGROUND] Iniciando job {job_id}...")
    
    with Session(engine) as session:
        # 1. Cargamos datos de la DB
        equipos_db = session.exec(select(Equipo)).all()
        reglas_db = session.exec(select(Regla)).all()
        
        # 2. Preparamos datos para el generador
        # El generador espera nombres para las reglas, pero en DB tenemos IDs. 
        # Vamos a mapearlos.
        club_names = {c.id: c.nombre for c in session.exec(select(Club)).all()}
        
        reglas_formateadas = []
        for r in reglas_db:
            reglas_formateadas.append({
                "clubA": club_names.get(r.club_a_id),
                "clubB": club_names.get(r.club_b_id),
                "bloqueA": r.bloque_a,
                "bloqueB": r.bloque_b,
                "tipo": r.tipo,
                "peso": r.peso
            })

        # 3. Generamos
        try:
            generator = FixtureGenerator(equipos_db, reglas_formateadas)
            fechas, status = generator.solve()
            
            if fechas is not None:
                # 4. Guardamos en la DB
                # Limpiamos fixture anterior (opcional, dependiendo de lo que quiera el usuario)
                # Por simplicidad, borramos todo y creamos nuevo
                session.exec("DELETE FROM partidofixture")
                session.exec("DELETE FROM fechafixture")
                session.commit()
                
                # Mapeo de nombres de equipos a IDs de DB para los partidos
                equipo_map = {e.nombre: e.id for e in equipos_db}
                
                for f_data in fechas:
                    nueva_fecha = FechaFixture(
                        nro_fecha=f_data["nroFecha"],
                        liga=f_data["liga"]
                    )
                    session.add(nueva_fecha)
                    session.flush() # Para obtener el ID de la fecha
                    
                    for p_data in f_data["partidos"]:
                        local_id = equipo_map.get(p_data["local"])
                        visitante_id = equipo_map.get(p_data["visitante"])
                        
                        if local_id and visitante_id:
                            nuevo_partido = PartidoFixture(
                                fecha_id=nueva_fecha.id,
                                local_id=local_id,
                                visitante_id=visitante_id,
                                cancha=p_data.get("cancha")
                            )
                            session.add(nuevo_partido)
                
                session.commit()
                print(f"[BACKGROUND] Fixture guardado en DB para job {job_id}")

                jobs_status[job_id] = {
                    "status": "COMPLETED",
                    "message": f"Finalizado con éxito: {status}"
                }
            else:
                jobs_status[job_id] = {
                    "status": "FAILED",
                    "message": f"No se pudo generar un fixture factible: {status}"
                }
        except Exception as e:
            print(f"[BACKGROUND] Error en job {job_id}: {e}")
            jobs_status[job_id] = {
                "status": "FAILED",
                "message": str(e)
            }

# ==========================================
# 4. Endpoints (Controllers)
# ==========================================

@app.get("/fixture/generar-ortools")
async def generar_fixture_ortools(background_tasks: BackgroundTasks):
    # 1. Generamos ID único
    job_id = str(uuid.uuid4())
    
    # 2. Registramos el estado inicial
    jobs_status[job_id] = {
        "status": "PROCESSING",
        "message": "Generación iniciada en segundo plano."
    }
    
    # 3. Disparamos la tarea pesada vía background task de FastAPI
    background_tasks.add_task(proceso_ortools_async, job_id)
    
    # 4. Devolvemos HTTP 202 Accepted inmediatamente
    return JSONResponse(
        status_code=202,
        content={
            "jobId": job_id,
            "status": "PROCESSING",
            "message": "Generación iniciada en segundo plano."
        }
    )

@app.get("/fixture/status/{job_id}", response_model=JobStatusDTO)
async def consultar_estado(job_id: str):
    if job_id not in jobs_status:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
        
    estado = jobs_status[job_id]
    return JobStatusDTO(
        jobId=job_id,
        status=estado["status"],
        message=estado["message"]
    )

def get_equipos_categorias_db(session: Session):
    categorias_map = {}
    statement = select(Equipo)
    equipos = session.exec(statement).all()
    for eq in equipos:
        nombre = eq.nombre
        cats = eq.categorias or {}
        if nombre not in categorias_map:
            categorias_map[nombre] = {}
        # Mezclamos las categorías
        for cat_name, habilitada in cats.items():
            if habilitada:
                categorias_map[nombre][cat_name.upper()] = True
    return categorias_map

@app.get("/fixture", response_model=List[Dict])
def obtener_fixture(
    liga: str = Query(..., description="A, B o C"),
    categoria: str = Query(..., description="Nombre de la categoría (ej: PRIMERA, QUINTA)"),
    session: Session = Depends(get_session)
):
    liga_key = liga.upper()
    categoria_key = categoria.upper()

    # Mapeo de categorías a divisiones del generador
    if categoria_key in ["PRIMERA", "RESERVA"]:
        target_div = f"MAYORES-{liga_key}"
    elif categoria_key in ["QUINTA", "SEXTA", "SEPTIMA", "OCTAVA"]:
        target_div = f"JUVENILES-{liga_key}"
    elif categoria_key in ["NOVENA", "DECIMA", "UNDECIMA"]:
        target_div = f"INFANTILES-{liga_key}"
    elif categoria_key in ["FEM_PRIMERA", "FEM_SUB16"]:
        target_div = "FEMENINO MAYORES-A"
    elif categoria_key in ["FEM_SUB14", "FEM_SUB12"]:
        target_div = "FEMENINO MENORES-A"
    else:
        return []

    equipos_categorias = get_equipos_categorias_db(session)
    
    # Consultamos FechasFixture de la DB
    statement = select(FechaFixture).where(FechaFixture.liga == target_div)
    db_fechas = session.exec(statement).all()

    filtered_fechas = []
    for f in db_fechas:
        valid_partidos = []
        for p in f.partidos:
            local = p.equipo_local.nombre
            visitante = p.equipo_visitante.nombre
            
            local_cats = equipos_categorias.get(local, {})
            visit_cats = equipos_categorias.get(visitante, {})
            
            if local_cats.get(categoria_key) and visit_cats.get(categoria_key):
                valid_partidos.append({
                    "local": local,
                    "visitante": visitante,
                    "cancha": p.cancha
                })
        
        if valid_partidos:
            filtered_fechas.append({
                "nroFecha": f.nro_fecha,
                "liga": f.liga,
                "partidos": valid_partidos
            })
                
    return sorted(filtered_fechas, key=lambda x: x["nroFecha"])

@app.get("/fixture/equipos", response_model=List[EquipoDTO])
def obtener_equipos(session: Session = Depends(get_session)):
    statement = select(Equipo)
    db_equipos = session.exec(statement).all()
        
    resultado = []
    
    cat_dto_map = {
        "primera": "PRIMERA", "reserva": "RESERVA",
        "quinta": "QUINTA", "sexta": "SEXTA", "septima": "SEPTIMA", "octava": "OCTAVA",
        "novena": "NOVENA", "decima": "DECIMA", "undecima": "UNDECIMA",
        "femenino_primera": "FEM_PRIMERA", "femenino_sub16": "FEM_SUB16",
        "femenino_sub14": "FEM_SUB14", "femenino_sub12": "FEM_SUB12"
    }
    
    for eq in db_equipos:
        nombre = eq.nombre
        div_mayor = eq.division_mayor
        club_nombre = eq.club.nombre if eq.club else None
        
        # Agrupamos las categorías válidas de ESE equipo por bloque usando KEYS de frontend
        blocks_found = {}
        for cat, habilitada in (eq.categorias or {}).items():
            if habilitada:
                dto_cat = cat_dto_map.get(cat, cat.upper())
                if cat in ["primera", "reserva"]:
                    blocks_found.setdefault("MAYORES", set()).add(dto_cat)
                elif cat in ["quinta", "sexta", "septima", "octava"]:
                    blocks_found.setdefault("JUVENILES", set()).add(dto_cat)
                elif cat in ["novena", "decima", "undecima"]:
                    blocks_found.setdefault("INFANTILES", set()).add(dto_cat)
                elif cat in ["femenino_primera", "femenino_sub16"]:
                    blocks_found.setdefault("FEM_MAYORES", set()).add(dto_cat)
                elif cat in ["femenino_sub14", "femenino_sub12"]:
                    blocks_found.setdefault("FEM_MENORES", set()).add(dto_cat)
                    
        # Generar un DTO independiente por cada bloque
        for b_name, b_cats in blocks_found.items():
            division_actual = div_mayor
            if b_name == "INFANTILES" and eq.division_infantiles:
                division_actual = eq.division_infantiles
            
            # Asignación de días de juego
            if b_name in ["JUVENILES", "FEM_MAYORES", "FEM_MENORES"]:
                dia_de_juego = "SABADO"
            else:
                dia_de_juego = "DOMINGO"

            dto = EquipoDTO(
                id=eq.id,
                nombre=nombre,
                jerarquia=eq.jerarquia,
                bloque=b_name,
                categoriasHabilitadas=list(b_cats),
                clubId=eq.club_id,
                clubNombre=club_nombre,
                divisionMayor=division_actual,
                diaDeJuego=dia_de_juego
            )
            resultado.append(dto)
            
    return resultado

@app.get("/fixture/update-db")
def update_db() -> ResponseDTO:
    try:
        migrate()
        return ResponseDTO(message="Base de datos actualizada desde JSON", success=True)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"message": f"Error en migración: {str(e)}", "success": False}
        )

@app.get("/fixture/ping", response_model=ResponseDTO)
async def ping():
    return ResponseDTO(message="pong", success=True)
