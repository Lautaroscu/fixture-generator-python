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
        self.torneos_short = [] # Torneos que jueguen solo 1 vuelta (vacio por ahora)
        
        for t_id, participantes in self.torneos_dict.items():
            num_reales = len(participantes)
            if t_id == "MENORES-B":
                self.fechas_por_torneo[t_id] = 20 # Pedido especial usuario
            elif t_id == "MENORES-C":
                self.fechas_por_torneo[t_id] = 20 # 2 ida y vuelta = 20 fechas (6 equipos)
            elif t_id in self.torneos_short:
                # Una sola vuelta: si es par N-1, si es impar N
                self.fechas_por_torneo[t_id] = num_reales - 1 if num_reales % 2 == 0 else num_reales
            else:
                # Ida y vuelta completa: si es par (N-1)*2, si es impar N*2
                ideal = (num_reales - 1) * 2 if num_reales % 2 == 0 else num_reales * 2
                self.fechas_por_torneo[t_id] = min(ideal, 26) # Tope 26
            
        self.fechas_max = 26
        # Informar la configuración
        for t_id, f in self.fechas_por_torneo.items():
            print(f"Torneo {t_id}: {len(self.torneos_dict[t_id])} equipos, {f} fechas estimadas.")
        
    def solve(self):
        model = cp_model.CpModel()
        
        self.juega = {}
        self.es_local = {}
        self.penalties = []
        
        # 2. Definir Variables
        for d in range(1, self.fechas_max + 1):
            for t_id, participantes in self.torneos_dict.items():
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
        
        # 5. Gestión de Fechas Libres (Bye Clustering - Opción C)
        for t_id, participantes in self.torneos_dict.items():
            num_reales = len(participantes)
            
            # Opción C: Forzamos a que jueguen todos contra todos en las primeras fechas para ligas pequeñas.
            if num_reales < 14:
                num_fechas_vuelta = num_reales - 1 if num_reales % 2 == 0 else num_reales
                limite = num_fechas_vuelta
                if t_id == "MENORES-C":
                    limite *= 4 # 2 ida y vuelta completo
                elif t_id not in self.torneos_short:
                    limite *= 2
                
                for d in range(1, 27):
                    for p in participantes:
                        vars_p = [self.juega[(d, t_id, p, j)] for j in participantes if p != j] + \
                                 [self.juega[(d, t_id, j, p)] for j in participantes if p != j]
                        
                        if d <= limite:
                            if num_reales % 2 == 0:
                                model.Add(sum(vars_p) == 1)
                            else:
                                model.Add(sum(vars_p) <= 1)
                        else:
                            model.Add(sum(vars_p) == 0)

                    # Si es impar, en cada fecha activa debe haber exactamente (N-1)//2 partidos
                    if d <= limite and num_reales % 2 != 0:
                        partidos_en_fecha = []
                        for i in participantes:
                            for j in participantes:
                                if i < j: # Evitar duplicados
                                    partidos_en_fecha.append(self.juega[(d, t_id, i, j)] + self.juega[(d, t_id, j, i)])
                        model.Add(sum(partidos_en_fecha) == (num_reales - 1) // 2)
            else:
                # Para ligas impares (ej. 13), el Libre es inevitable.
                # Asegurar que cada equipo juega exactamente 2 Veces contra cada uno.
                # (Ya está cubierto por las restricciones estructurales sum(juega) == 1 over dates)
                pass
        
        # 6. Restricciones Institucionales
        self._add_institutional_constraints(model)
        
        # 7. Resolver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 180.0 # Aumentamos a 3 min para asegurar factibilidad
        solver.parameters.log_search_progress = True
        
        print(f"Buscando solución para {len(self.torneos_dict)} torneos principales...")
        
        if self.penalties:
            model.Minimize(sum(self.penalties))
            
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
                for d in range(1, 27):
                    # Cada equipo juega MÁXIMO 1 partido por fecha (puede tener libre)
                    model.Add(sum(self.juega[(d, t_id, i, j)] + self.juega[(d, t_id, j, i)] for j in participantes if i != j) <= 1)
                    
                    # Relación Lógica: Si juega(d, i, j) es true, entonces i es local y j es visitante
                    # Definimos variables de localía para todas las fechas, incluso si no juega
                    for j in participantes:
                        if i != j:
                            model.AddImplication(self.juega[(d, t_id, i, j)], self.es_local[(d, t_id, i)])
                            model.AddImplication(self.juega[(d, t_id, i, j)], self.es_local[(d, t_id, j)].Not())

                # IDA Y VUELTA vs SOLO IDA
                for j in participantes:
                    if i < j:
                        if t_id in self.torneos_short:
                            # Una sola vez en total (ya sea i local o j local)
                            model.Add(sum(self.juega[(d, t_id, i, j)] + self.juega[(d, t_id, j, i)] for d in range(1, 27)) == 1)
                        elif t_id == "MENORES-B":
                            # Para Menores-B: bloques de 10 fechas (SOFT)
                            j1 = model.NewBoolVar(f"cumple_ida_{t_id}_{i}_{j}")
                            j2 = model.NewBoolVar(f"cumple_vuelta_{t_id}_{i}_{j}")
                            model.Add(sum(self.juega[(d, t_id, i, j)] for d in range(1, 11)) == j1)
                            model.Add(sum(self.juega[(d, t_id, j, i)] for d in range(11, 21)) == j2)
                            self.penalties.append(j1.Not() * 1000000)
                            self.penalties.append(j2.Not() * 1000000)
                        elif t_id == "MENORES-C":
                            # 2 ida y vuelta = 2 veces cada cruce HARD
                            model.Add(sum(self.juega[(d, t_id, i, j)] for d in range(1, 27)) == 2)
                            model.Add(sum(self.juega[(d, t_id, j, i)] for d in range(1, 27)) == 2)
                            
                            # 4 bloques de 5 fechas (SOFT)
                            b1 = model.NewBoolVar(f"b1_{t_id}_{i}_{j}")
                            b2 = model.NewBoolVar(f"b2_{t_id}_{i}_{j}")
                            b3 = model.NewBoolVar(f"b3_{t_id}_{i}_{j}")
                            b4 = model.NewBoolVar(f"b4_{t_id}_{i}_{j}")
                            model.Add(sum(self.juega[(d, t_id, i, j)] for d in range(1, 6)) == b1)
                            model.Add(sum(self.juega[(d, t_id, j, i)] for d in range(6, 11)) == b2)
                            model.Add(sum(self.juega[(d, t_id, i, j)] for d in range(11, 16)) == b3)
                            model.Add(sum(self.juega[(d, t_id, j, i)] for d in range(16, 21)) == b4)
                            for b in [b1, b2, b3, b4]:
                                self.penalties.append(b.Not() * 1000000)
                        else:
                            # Juegan exactamente una vez de ida y una de vuelta (HARD TOTAL)
                            model.Add(sum(self.juega[(d, t_id, i, j)] for d in range(1, 27)) == 1)
                            model.Add(sum(self.juega[(d, t_id, j, i)] for d in range(1, 27)) == 1)
                            
                            # Separacion por la mitad real del torneo (SOFT)
                            s1 = model.NewBoolVar(f"s1_{t_id}_{i}_{j}")
                            s2 = model.NewBoolVar(f"s2_{t_id}_{j}_{i}")
                            model.Add(sum(self.juega[(d, t_id, i, j)] for d in range(1, mitad + 1)) == s1)
                            model.Add(sum(self.juega[(d, t_id, j, i)] for d in range(mitad + 1, fechas_total + 1)) == s2)
                            self.penalties.append(s1.Not() * 1000000)
                            self.penalties.append(s2.Not() * 1000000)
                        
                        num_reales = len(participantes)
                        # El espejo de PARTIDOS solo es obligatorio si queremos 100% simetría de cruces.
                        if num_reales == 14 and t_id != "MENORES-B": # Evitar espejo en B si es asincrono
                            mitad = 13
                            for d in range(1, mitad + 1):
                                model.Add(self.juega[(d, t_id, i, j)] == self.juega[(d + mitad, t_id, j, i)])
                                
        # 3.2 Espejo de LOCALIA (Este sí es obligatorio para que los mirroring institucionales funcionen)
        for t_id, participantes in self.torneos_dict.items():
            if t_id in self.torneos_short:
                continue # No hay espejo en torneos de una sola vuelta
                
            fechas_total = self.fechas_por_torneo[t_id]
            mitad = fechas_total // 2
            for p in participantes:
                for d in range(1, mitad + 1):
                    # loc(d) != loc(d+mitad) -> Espejo clásico de localía
                    model.Add(self.es_local[(d, t_id, p)] != self.es_local[(d + mitad, t_id, p)])

            # Límite Max 2 seguidos de Local o Visitante por torneo
            for i in participantes:
                for d in range(1, 26 - 1): # Usamos horizonte fijo de 26

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
                # Recopilar variables de localía SÓLO para torneos MAYORES (es lo que importa logísticamente / policía)
                local_vars_for_club = []
                for t_id, participantes in self.torneos_dict.items():
                    if t_name in participantes and d <= self.fechas_por_torneo[t_id] and "MAYORES" in t_id:
                        local_vars_for_club.append(self.es_local[(d, t_id, t_name)])
                
                if local_vars_for_club:
                    # Crear una variable booleana que represente "La Institución es Local Hoy en Primera"
                    is_club_host = model.NewBoolVar(f"is_host_{d}_{t_name}")
                    model.AddMaxEquality(is_club_host, local_vars_for_club)
                    club_host_vars.append(is_club_host)
            
            if club_host_vars:
                # Forzar que MÁXIMO 2 clubes (instituciones) sean locales de MAYORES en la misma jornada en Ayacucho
                model.Add(sum(club_host_vars) <= 2)

        for d in range(1, self.fechas_max + 1):
            # Seguridad Juárez: Mayores de Juarense y Mayores de Alumni no pueden ser locales el mismo día
            juarense_vars = [self.es_local[(d, t_id, "Juarense")] for t_id, p in self.torneos_dict.items() if "Juarense" in p and d <= self.fechas_por_torneo[t_id] and "MAYORES" in t_id]
            alumni_vars = [self.es_local[(d, t_id, "Alumni")] for t_id, p in self.torneos_dict.items() if "Alumni" in p and d <= self.fechas_por_torneo[t_id] and "MAYORES" in t_id]
            
            if juarense_vars and alumni_vars:
                for j_v in juarense_vars:
                    for a_v in alumni_vars:
                        model.Add(j_v + a_v <= 1)

    def _add_institutional_constraints(self, model):
        # Institutional Rules (Inverso/Espejo)
        for r in self.reglas:
            tipo = r.get("tipo") # INVERSO o ESPEJO
            clubA = r.get("equipo_origen")
            clubB = r.get("equipo_destino")
            t1 = r.get("torneo_origen")
            t2 = r.get("torneo_destino")
            es_hard = r.get("hard", False)
            peso = r.get("peso", 5000) # Weight 5000 for strict enforcement mostly everywhere
            
            # Solo podemos comparar fechas en común
            fechas_comunes = min(self.fechas_por_torneo.get(t1, 0), self.fechas_por_torneo.get(t2, 0))
            
            if clubA not in self.torneos_dict.get(t1, []) or clubB not in self.torneos_dict.get(t2, []):
                continue
            
            for d in range(1, fechas_comunes + 1):
                # Opción C: No aplicar la regla si alguno de los dos está en su "zona de fantasmas"
                num_reales_t1 = len(self.torneos_dict[t1])
                num_reales_t2 = len(self.torneos_dict[t2])
                
                # Para ligas pares, la zona real termina en (N-1)*2
                limite_t1 = (num_reales_t1 - 1) * 2 if num_reales_t1 % 2 == 0 else self.fechas_por_torneo[t1]
                limite_t2 = (num_reales_t2 - 1) * 2 if num_reales_t2 % 2 == 0 else self.fechas_por_torneo[t2]
                
                if d > limite_t1 or d > limite_t2:
                    continue
                    
                locA = self.es_local[(d, t1, clubA)]
                locB = self.es_local[(d, t2, clubB)]
                
                if "MENORES-B" in [t1, t2] or "MENORES-C" in [t1, t2]:
                    peso_real = 50000 # Somewhat strict but allow flexibility for compression
                else:
                    peso_real = 5000000 if es_hard else peso
                
                penalty_var = model.NewBoolVar(f"penalty_{d}_{clubA}_{clubB}_{t1}_{t2}")
                self.penalties.append(penalty_var * peso_real)

                # INVERSO: Si juegan igual (locA == locB), penalty = 1 (Queremos que jueguen cruzado)
                if tipo == "INVERSO":
                    model.Add(locA == locB).OnlyEnforceIf(penalty_var)
                    model.Add(locA != locB).OnlyEnforceIf(penalty_var.Not())
                # ESPEJO: Si juegan cruzado (locA != locB), penalty = 1 (Queremos que jueguen igual)
                elif tipo == "ESPEJO":
                    model.Add(locA != locB).OnlyEnforceIf(penalty_var)
                    model.Add(locA == locB).OnlyEnforceIf(penalty_var.Not())



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
                                
                                estadios = self.club_dict.get(i, {}).get("estadioLocal", "Pendiente")
                                if isinstance(estadios, dict):
                                    bloque = "default"
                                    if "MAYORES" in t_id:
                                        bloque = "MAYORES"
                                    elif "FEMENINO" in t_id:
                                        bloque = "FEMENINO-A"
                                    elif "MENORES" in t_id:
                                        # Si hay estadio específico de Infantiles lo usamos (según pedido Juventud Unida)
                                        bloque = "INFANTILES" if "INFANTILES" in estadios else "JUVENILES"
                                    
                                    cancha = estadios.get(bloque, estadios.get("default", "Pendiente"))
                                else:
                                    cancha = estadios
                                
                                partidos_por_liga[t_id].append({
                                    "local": final_local,
                                    "visitante": final_visitante,
                                    "cancha": cancha
                                })
            
            # Expandir de Torneos a Categorias!
            # El Torneo MAYORES-A dicta las fechas de PRIMERA y RESERVA
            for t_id, partidos in partidos_por_liga.items():
                if partidos: # Opcion C: No imprimir si no hay partidos reales
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
