from fastapi import FastAPI, BackgroundTasks, Query, HTTPException, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Set
import uuid
import time # Solo para el ejemplo de sleep
import json
from fixture_generator import FixtureGenerator


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

# Simulamos una "base de datos" en memoria para guardar el estado de los jobs
jobs_status = {}
fixtures_db = [] 
equipos_db = []

def init_db():
    global equipos_db, fixtures_db
    # Cargar equipos
    try:
        with open("equipos.json", "r", encoding="utf-8") as file:
            data = json.load(file)
            equipos_db = data.get("equipos", [])
            print(f"Equipos cargados: {len(equipos_db)}")
    except Exception as e:
        print(f"Error loading equipos.json: {e}")
        
    # Cargar fixture generado previamente
    try:
        with open("fixture.json", "r", encoding="utf-8") as file:
            fixtures_db = json.load(file)
            print(f"Fixture cargado desde archivo: {len(fixtures_db)} fechas")
    except Exception as e:
        print(f"No se pudo cargar fixture.json (puede que no exista aún): {e}")

init_db() 

# ==========================================
# 3. Función del proceso en Segundo Plano
# ==========================================
def proceso_ortools_async(job_id: str):
    """
    Simulación del proceso pesado de OR-Tools.
    Acá llamarías a tu FixtureGenerator(equipos.json).solve()
    """
    print(f"[BACKGROUND] Iniciando trabajo {job_id}...")
    
    try:
        generator = FixtureGenerator("equipos.json")
        fechas, status_name = generator.solve()
        
        # Guardamos en nuestra mini bd
        if fechas is not None:
            fixtures_db.clear()
            fixtures_db.extend(fechas)
            
            # Persistimos a archivo también
            try:
                with open("fixture.json", "w", encoding="utf-8") as f:
                    json.dump(fechas, f, indent=4, ensure_ascii=False)
                print("[BACKGROUND] Fixture persistido en fixture.json")
            except Exception as ef:
                print(f"[BACKGROUND] Error al persistir fixture.json: {ef}")

            jobs_status[job_id] = {
                "status": "COMPLETED",
                "message": f"Generación finalizada con éxito. Status: {status_name}"
            }
        else:
            jobs_status[job_id] = {
                "status": "FAILED",
                "message": f"No se encontró solución factible. Status: {status_name}"
            }
            
        print(f"[BACKGROUND] Trabajo {job_id} finalizado! Status: {status_name}")
    except Exception as e:
        jobs_status[job_id] = {
            "status": "FAILED",
            "message": f"Error: {str(e)}"
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

def load_equipos_categorias():
    categorias_map = {}
    try:
        with open("equipos.json", "r", encoding="utf-8") as file:
            data = json.load(file)
            for eq in data.get("equipos", []):
                nombre = eq["nombre"]
                cats = eq.get("categorias", {})
                if nombre not in categorias_map:
                    categorias_map[nombre] = {}
                # Mezclamos las categorías
                for cat_name, habilitada in cats.items():
                    if habilitada:
                        categorias_map[nombre][cat_name] = True
    except Exception as e:
        print(f"Error loading equipos.json: {e}")
    return categorias_map

@app.get("/fixture", response_model=List[FechaDTO])
async def obtener_fixture(liga: str, categoria: str):
    liga_key = liga.strip().upper()
    categoria_key = categoria.strip().upper()
    
    cat_json_map = {
        "PRIMERA": "primera",
        "RESERVA": "reserva",
        "QUINTA": "quinta",
        "SEXTA": "sexta",
        "SEPTIMA": "septima",
        "OCTAVA": "octava",
        "NOVENA": "novena",
        "DECIMA": "decima",
        "UNDECIMA": "undecima",
        "FEM_PRIMERA": "femenino_primera",
        "FEM_SUB14": "femenino_sub14",
        "FEM_SUB16": "femenino_sub16",
        "FEM_SUB12": "femenino_sub12"
    }
    
    json_cat = cat_json_map.get(categoria_key)
    if not json_cat:
        return []

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

    equipos_categorias = load_equipos_categorias()
    
    # Leemos directamente del archivo para asegurar que los datos estén frescos
    try:
        with open("fixture.json", "r", encoding="utf-8") as f:
            source_fixtures = json.load(f)
    except Exception as e:
        print(f"Error loading fixture.json: {e}")
        source_fixtures = []

    filtered_fechas = []
    for f in source_fixtures:
        if f["liga"] == target_div:
            valid_partidos = []
            for p in f.get("partidos", []):
                local = p["local"]
                visitante = p["visitante"]
                
                if local.startswith("Libre_") or visitante.startswith("Libre_"):
                    continue
                
                local_categorias = equipos_categorias.get(local, {})
                visit_categorias = equipos_categorias.get(visitante, {})
                
                if local_categorias.get(json_cat) and visit_categorias.get(json_cat):
                    valid_partidos.append(p)
            
            if valid_partidos:
                # Incluimos solo los partidos válidos (donde ambos tienen esta categoría)
                filtered_fechas.append({
                    "nroFecha": f["nroFecha"],
                    "liga": f["liga"],
                    "partidos": valid_partidos
                })
                
    return filtered_fechas

@app.get("/fixture/equipos", response_model=List[EquipoDTO])
async def obtener_equipos():
    if not equipos_db:
        init_equipos_db()
        
    resultado = []
    
    cat_dto_map = {
        "primera": "PRIMERA", "reserva": "RESERVA",
        "quinta": "QUINTA", "sexta": "SEXTA", "septima": "SEPTIMA", "octava": "OCTAVA",
        "novena": "NOVENA", "decima": "DECIMA", "undecima": "UNDECIMA",
        "femenino_primera": "FEM_PRIMERA", "femenino_sub16": "FEM_SUB16",
        "femenino_sub14": "FEM_SUB14", "femenino_sub12": "FEM_SUB12"
    }
    
    for i, eq_json in enumerate(equipos_db):
        nombre = eq_json.get("nombre", "Desconocido")
        div_mayor_json = eq_json.get("divisionMayor", "A")
        
        # Agrupamos las categorías válidas de ESE equipo por bloque usando KEYS de frontend
        blocks_found = {}
        for cat, habilitada in eq_json.get("categorias", {}).items():
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
                    
        # Generar un DTO independiente por cada bloque que abarca el equipo original
        for b_idx, (b_name, b_cats) in enumerate(blocks_found.items()):
            # Asignación de liga (divisionMayor)
            if b_name in ["FEM_MAYORES", "FEM_MENORES"]:
                division_mayor = "A"
            elif b_name == "INFANTILES" and eq_json.get("divisionInfantiles"):
                division_mayor = eq_json.get("divisionInfantiles").upper()
            else:
                division_mayor = div_mayor_json.upper()

            # Asignación de días de juego
            if b_name in ["JUVENILES", "FEM_MAYORES", "FEM_MENORES"]:
                dia_de_juego = "SABADO"
            else:
                dia_de_juego = "DOMINGO"

            # En caso de no tener ID en el JSON, generamos uno compuesto para los splits
            base_id = eq_json.get("id", (i + 1) * 10)
            equipo_id = base_id + b_idx
            
            dto = EquipoDTO(
                id=equipo_id,
                nombre=nombre,
                jerarquia=eq_json.get("jerarquia", 0),
                bloque=b_name,
                categoriasHabilitadas=b_cats,
                clubId=None, 
                clubNombre=eq_json.get("clubPadre", None),
                divisionMayor=division_mayor,
                diaDeJuego=dia_de_juego
            )
            resultado.append(dto)
            print(f"Equipo cargado - {nombre} => Bloque: {b_name} | {b_cats}")
            
    return resultado

@app.get("/fixture/update-db")
async def update_db() -> ResponseDTO:
    try:
        # dataInitializer.initDesdeJson()
        return ResponseDTO(message="Base cargada correctamente", success=True)
    except Exception as e:
        # En FastAPI podes retornar un error lanzando una excepción HTTP o retornando la clase y código 400
        return JSONResponse(
            status_code=400,
            content={"message": str(e), "success": False}
        )

@app.get("/fixture/ping", response_model=ResponseDTO)
async def ping():
    return ResponseDTO(message="pong", success=True)
