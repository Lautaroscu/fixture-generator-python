import json
from ortools.sat.python import cp_model

class FixtureGenerator:
    def __init__(self, json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        self.clubes = data.get("clubes", [])
        self.torneos = data.get("torneos", [])
        self.reglas = data.get("reglas_institucionales", [])
        
        self.club_dict = {c["nombre"]: c for c in self.clubes}
        self.torneos_dict = {}
        for t in self.torneos:
            self.torneos_dict[t["id"]] = t["participantes"].copy()
            
        self.fechas_por_torneo = {}
        
        # 1. Agregar "Libre" para que todos los torneos tengan cantidad par
        for t_id, participantes in self.torneos_dict.items():
            while len(participantes) % 2 != 0:
                dummy_name = f"Libre_{t_id}_{len(participantes)}"
                participantes.append(dummy_name)
            self.fechas_por_torneo[t_id] = (len(participantes) - 1) * 2
            
        self.fechas_max = max(self.fechas_por_torneo.values()) if self.fechas_por_torneo else 0

    def solve(self):
        model = cp_model.CpModel()
        
        self.juega = {}
        self.es_local = {}
        
        # 2. Definir Variables
        for d in range(1, self.fechas_max + 1):
            for t_id, participantes in self.torneos_dict.items():
                if d <= self.fechas_por_torneo[t_id]:
                    # Variable de localía
                    for p in participantes:
                        self.es_local[(d, t_id, p)] = model.NewBoolVar(f"local_d{d}_{t_id}_{p}")
                    
                    # Variable de partido
                    for i in participantes:
                        for j in participantes:
                            if i != j:
                                self.juega[(d, t_id, i, j)] = model.NewBoolVar(f"juega_d{d}_{t_id}_{i}_{j}")

        # 3. Restricciones Estructurales
        self._add_structural_constraints(model)
        
        # 4. Restricciones Logísticas
        self._add_logistical_constraints(model)
        
        # 5. Resolver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60.0 # Más que suficiente para este modelo simplificado
        solver.parameters.log_search_progress = True
        
        print(f"Buscando solución para {len(self.torneos_dict)} torneos principales...")
        status = solver.Solve(model)
        status_name = solver.StatusName(status)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            print(f"Solución encontrada ({status_name})")
            return self._extract_solution(solver), status_name
        else:
            print("No se encontró solución factible (INFEASIBLE).")
            return None, status_name

    def _add_structural_constraints(self, model):
        for t_id, participantes in self.torneos_dict.items():
            fechas_total = self.fechas_por_torneo[t_id]
            mitad = fechas_total // 2
            
            for i in participantes:
                for d in range(1, fechas_total + 1):
                    # Cada equipo juega exactamente 1 partido por fecha
                    model.Add(sum(self.juega[(d, t_id, i, j)] + self.juega[(d, t_id, j, i)] for j in participantes if i != j) == 1)
                    
                    # Relación Lógica: Si juega(d, i, j) es true, entonces i es local y j es visitante
                    for j in participantes:
                        if i != j:
                            model.AddImplication(self.juega[(d, t_id, i, j)], self.es_local[(d, t_id, i)])
                            model.AddImplication(self.juega[(d, t_id, i, j)], self.es_local[(d, t_id, j)].Not())

                # Limitamos que nadie juegue contra los dummies más de lo necesario
                # Esto sucede orgánicamente al ser Round Robin, pero lo garantizamos
                for j in participantes:
                    if i != j:
                        # Juegan exactamente una vez de ida y una de vuelta (si aplica)
                        model.Add(sum(self.juega[(d, t_id, i, j)] for d in range(1, fechas_total + 1)) == 1)
                        # Todos vs Todos, espejo perfecto en la segunda rueda
                        for d in range(1, mitad + 1):
                            model.Add(self.juega[(d, t_id, i, j)] == self.juega[(d + mitad, t_id, j, i)])

            # Límite Max 2 seguidos de Local o Visitante por torneo
            for i in participantes:
                if i.startswith("Libre_"): continue
                for d in range(1, fechas_total - 1):
                    v1 = self.es_local[(d, t_id, i)]
                    v2 = self.es_local[(d+1, t_id, i)]
                    v3 = self.es_local[(d+2, t_id, i)]
                    model.Add(v1 + v2 + v3 <= 2)
                    model.Add(v1 + v2 + v3 >= 1)

    def _add_logistical_constraints(self, model):
        ayacucho_teams = ["SARMIENTO AYACUCHO", "DEFENSORES DE AYACUCHO", "ATLETICO AYACUCHO", "ATENEO ESTRADA"]
        for d in range(1, self.fechas_max + 1):
            club_host_vars = []
            
            for t_name in ayacucho_teams:
                # Recopilar todas las variables de localía de este club específico en cualquier torneo en la fecha D
                local_vars_for_club = []
                for t_id, participantes in self.torneos_dict.items():
                    if t_name in participantes and d <= self.fechas_por_torneo[t_id]:
                        local_vars_for_club.append(self.es_local[(d, t_id, t_name)])
                
                if local_vars_for_club:
                    # Crear una variable booleana que represente "La Institución es Local Hoy"
                    is_club_host = model.NewBoolVar(f"is_host_{d}_{t_name}")
                    # is_club_host es True si al menos una categoría juega de local
                    model.AddMaxEquality(is_club_host, local_vars_for_club)
                    club_host_vars.append(is_club_host)
            
            if club_host_vars:
                # Forzar que MÁXIMO 2 clubes (instituciones) sean locales en la misma jornada
                model.Add(sum(club_host_vars) <= 2)

        for d in range(1, self.fechas_max + 1):
            juarense_vars = [self.es_local[(d, t_id, "Juarense")] for t_id, p in self.torneos_dict.items() if "Juarense" in p and d <= self.fechas_por_torneo[t_id]]
            alumni_vars = [self.es_local[(d, t_id, "Alumni")] for t_id, p in self.torneos_dict.items() if "Alumni" in p and d <= self.fechas_por_torneo[t_id]]
            
            if juarense_vars and alumni_vars:
                # We expect them to only be in 1 primary tournament each (MAYORES-A, MAYORES-B), but just in case we ANY them
                for j_v in juarense_vars:
                    for a_v in alumni_vars:
                        model.Add(j_v + a_v <= 1)

        penalties = []
        # Institutional Rules (Inverso/Espejo)
        for r in self.reglas:
            tipo = r.get("tipo") # INVERSO o ESPEJO
            clubA = r.get("equipo_origen")
            clubB = r.get("equipo_destino")
            t1 = r.get("torneo_origen")
            t2 = r.get("torneo_destino")
            peso = r.get("peso", 5000) # Weight 5000 for strict enforcement mostly everywhere
            
            # Solo podemos comparar fechas en común
            fechas_comunes = min(self.fechas_por_torneo.get(t1, 0), self.fechas_por_torneo.get(t2, 0))
            
            if clubA not in self.torneos_dict.get(t1, []) or clubB not in self.torneos_dict.get(t2, []):
                continue
            
            for d in range(1, fechas_comunes + 1):
                locA = self.es_local[(d, t1, clubA)]
                locB = self.es_local[(d, t2, clubB)]
                
                penalty_var = model.NewBoolVar(f"penalty_{d}_{clubA}_{clubB}_{t1}_{t2}")
                penalties.append(penalty_var * peso)

                # INVERSO: Si juegan igual (locA == locB), penalty = 1 (Queremos que jueguen cruzado)
                if tipo == "INVERSO":
                    model.Add(locA == locB).OnlyEnforceIf(penalty_var)
                    model.Add(locA != locB).OnlyEnforceIf(penalty_var.Not())
                # ESPEJO: Si juegan cruzado (locA != locB), penalty = 1 (Queremos que jueguen igual)
                elif tipo == "ESPEJO":
                    model.Add(locA != locB).OnlyEnforceIf(penalty_var)
                    model.Add(locA == locB).OnlyEnforceIf(penalty_var.Not())

        if penalties:
            model.Minimize(sum(penalties))

    def _extract_solution(self, solver):
        fixtures_por_fecha = []
        
        for d in range(1, self.fechas_max + 1):
            # Agrupar los partidos por liga
            partidos_por_liga = {}
            for t_id, participantes in self.torneos_dict.items():
                if d <= self.fechas_por_torneo[t_id]:
                    partidos_por_liga[t_id] = []
                    for i in participantes:
                        for j in participantes:
                            if i != j and solver.Value(self.juega[(d, t_id, i, j)]):
                                # Evaluar cancha
                                cancha = ""
                                final_local = i
                                final_visitante = j
                                
                                if i.startswith("Libre_"):
                                    final_local = "LIBRE"
                                elif j.startswith("Libre_"):
                                    final_visitante = "LIBRE"
                                else:
                                    cancha = self.club_dict.get(i, {}).get("estadioLocal", "Pendiente")
                                
                                partidos_por_liga[t_id].append({
                                    "local": final_local,
                                    "visitante": final_visitante,
                                    "cancha": cancha
                                })
            
            # Expandir de Torneos a Categorias!
            # El Torneo MAYORES-A dicta las fechas de PRIMERA y RESERVA
            for t_id, partidos in partidos_por_liga.items():
                fixtures_por_fecha.append({
                    "nroFecha": d,
                    "liga": t_id,
                    "partidos": partidos
                })
                
        return fixtures_por_fecha

if __name__ == "__main__":
    generator = FixtureGenerator("equipos_tiras.json")
    fechas, status = generator.solve()
    print(f"Status: {status}. Fechas generadas: {len(fechas) if fechas else 0}")
    
    if fechas:
        with open("fixture.json", "w", encoding="utf-8") as f:
            json.dump(fechas, f, indent=4, ensure_ascii=False)
        print("Fixture guardado en fixture.json (formato de torneos/tiras)")
