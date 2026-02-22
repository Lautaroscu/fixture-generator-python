import json
from ortools.sat.python import cp_model

class FixtureGenerator:
    def __init__(self, json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        self.equipos = []
        for eq_data in data.get("equipos", []):
            self.equipos.append(eq_data)
            
        self.reglas = data.get("reglas", [])
            
        self.divisiones = {}
        for eq in self.equipos:
            cats = eq.get("categorias", {})
            nombre = eq.get("nombre", "")
            
            if cats.get("primera") or cats.get("reserva"):
                liga = eq.get("divisionMayor", "A").upper()
                self.divisiones.setdefault(f"MAYORES-{liga}", []).append(nombre)
                
            if cats.get("quinta") or cats.get("sexta") or cats.get("septima") or cats.get("octava"):
                liga = eq.get("divisionMayor", "A").upper()
                self.divisiones.setdefault(f"JUVENILES-{liga}", []).append(nombre)
                
            if cats.get("novena") or cats.get("decima") or cats.get("undecima"):
                liga = eq.get("divisionInfantiles", eq.get("divisionMayor", "A")).upper()
                self.divisiones.setdefault(f"INFANTILES-{liga}", []).append(nombre)
                
            if cats.get("femenino_primera") or cats.get("femenino_sub16"):
                self.divisiones.setdefault("FEMENINO MAYORES-A", []).append(nombre)
                
            if cats.get("femenino_sub14") or cats.get("femenino_sub12"):
                self.divisiones.setdefault("FEMENINO MENORES-A", []).append(nombre)
        
        self.fechas_por_div = {}
        for div, teams in self.divisiones.items():
            # Pad to the nearest even number
            while len(self.divisiones[div]) % 2 != 0:
                dummy_name = f"Libre_{div}_{len(self.divisiones[div])}"
                self.divisiones[div].append(dummy_name)
                self.equipos.append({"nombre": dummy_name, "is_dummy": True})
            
            # (Teams - 1) * 2 matches because of home and away
            self.fechas_por_div[div] = (len(self.divisiones[div]) - 1) * 2
            
        self.fechas_max = max(self.fechas_por_div.values()) if self.fechas_por_div else 0

        self.clubes_padre = set()
        for eq in self.equipos:
            if eq.get("is_dummy"):
                padre = eq["nombre"]
            else:
                padre = eq.get("clubPadre", eq["nombre"])
            self.clubes_padre.add(padre)

    def _has_primera_reserva(self, e):
        cats = e.get("categorias", {})
        return cats.get("primera", False) or cats.get("reserva", False)

    def _has_infantiles(self, e):
        cats = e.get("categorias", {})
        return any(cats.get(k, False) for k in ["quinta", "sexta", "septima", "octava", "novena", "decima", "undecima"])
        
    def _has_femenino(self, e):
        cats = e.get("categorias", {})
        return any(cats.get(k, False) for k in ["femenino_primera", "femenino_sub16", "femenino_sub14", "femenino_sub12"])

    def _get_entidad(self, eq_name):
        for e in self.equipos:
            if e["nombre"] == eq_name:
                if e.get("is_dummy"): return eq_name
                return e.get("clubPadre", e["nombre"])
        return eq_name

    def solve(self):
        model = cp_model.CpModel()
        
        self.juega = {}
        self.es_local = {}
        
        for d in range(1, self.fechas_max + 1):
            for e in self.clubes_padre:
                self.es_local[(d, e)] = model.NewBoolVar(f"es_local_d{d}_{e}")
                
            for div, equipos_div in self.divisiones.items():
                if d > self.fechas_por_div[div]:
                    continue
                    
                for i in equipos_div:
                    for j in equipos_div:
                        if i != j:
                            self.juega[(d, div, i, j)] = model.NewBoolVar(f"juega_d{d}_{div}_{i}_{j}")

        self._add_structural_constraints(model)
        self._add_logistical_constraints(model)
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60.0
        solver.parameters.log_search_progress = True
        print("Starting solver...")
        status = solver.Solve(model)
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print("Solución encontrada!")
            fechas_dto = self._build_fechas_dto(solver)
            return fechas_dto, solver.StatusName(status)
        else:
            print("Status:", solver.StatusName(status))
            print("No se encontró solución factible en el tiempo estipulado.")
            return None, solver.StatusName(status)

    def _build_fechas_dto(self, solver):
        fechas_dict = {}
        for d in range(1, self.fechas_max + 1):
            
            # Buscamos qué partidos se juegan esta fecha
            for div, equipos_div in self.divisiones.items():
                if d > self.fechas_por_div[div]:
                    continue
                
                # Check if this division+date already exists in dictionary
                key = (d, div)
                if key not in fechas_dict:
                    fechas_dict[key] = {
                        "nroFecha": d,
                        "liga": div,
                        "partidos": []
                    }
                
                for i in equipos_div:
                    for j in equipos_div:
                        if i != j:
                            if solver.BooleanValue(self.juega[(d, div, i, j)]):
                                # Avoid adding Free (Libre) matches to the final fixture unless desired
                                if not i.startswith("Libre_") and not j.startswith("Libre_"):
                                    cancha = self._get_entidad(i) # Basic fallback
                                    for e in self.equipos:
                                        if e["nombre"] == i and "estadioLocal" in e:
                                            cancha = e["estadioLocal"]
                                            break
                                            
                                    fechas_dict[key]["partidos"].append({
                                        "local": i,
                                        "visitante": j,
                                        "cancha": cancha
                                    })
        
        # Convert dictionary to flat list
        return list(fechas_dict.values())

    def _add_structural_constraints(self, model):
        for div, equipos_div in self.divisiones.items():
            fechas_total = self.fechas_por_div[div]
            fechas_ida = fechas_total // 2
            
            for d in range(1, fechas_total + 1):
                for i in equipos_div:
                    for j in equipos_div:
                        if i != j:
                            if not i.startswith("Libre_") and not j.startswith("Libre_"):
                                entidad_i = self._get_entidad(i)
                                entidad_j = self._get_entidad(j)
                                
                                # Since divisions have different lengths, strict es_local synchronization 
                                # across different length calendars causes cyclical infeasibility due to Vuelta reflection mismatch.
                                # Thus we tie them to division-specific local variables, and optionally append penalties later
                                # OR we simply allow es_local to just enforce the *largest* division's localia, 
                                # and we don't strictly tie it for smaller divisions unless they match lengths.
                                
                                # Let's define es_local as just applying to the main 26-date divisions, 
                                # but for structural simplicity, we will just tie it directly. 
                                # Wait, to avoid the cycle, we create div-specific es_local.
                                if not hasattr(self, 'es_local_div'):
                                    self.es_local_div = {}
                                
                                if (d, div, i) not in self.es_local_div:
                                    var_loc_i = model.NewBoolVar(f"loc_{d}_{div}_{i}")
                                    self.es_local_div[(d, div, i)] = var_loc_i
                                    
                                    match_i = model.NewBoolVar(f"sync_global_loc_{d}_{div}_{i}")
                                    model.Add(match_i == var_loc_i).OnlyEnforceIf(self.es_local[(d, entidad_i)])
                                    model.Add(match_i == var_loc_i.Not()).OnlyEnforceIf(self.es_local[(d, entidad_i)].Not())
                                    if not hasattr(self, 'sync_rewards'):
                                        self.sync_rewards = []
                                    self.sync_rewards.append(match_i)
                                    
                                if (d, div, j) not in self.es_local_div:
                                    var_loc_j = model.NewBoolVar(f"loc_{d}_{div}_{j}")
                                    self.es_local_div[(d, div, j)] = var_loc_j
                                    
                                    match_j = model.NewBoolVar(f"sync_global_loc_{d}_{div}_{j}")
                                    model.Add(match_j == var_loc_j).OnlyEnforceIf(self.es_local[(d, entidad_j)])
                                    model.Add(match_j == var_loc_j.Not()).OnlyEnforceIf(self.es_local[(d, entidad_j)].Not())
                                    if not hasattr(self, 'sync_rewards'):
                                        self.sync_rewards = []
                                    self.sync_rewards.append(match_j)

                                var_loc_i = self.es_local_div[(d, div, i)]
                                var_loc_j = self.es_local_div[(d, div, j)]
                                
                                model.AddImplication(self.juega[(d, div, i, j)], var_loc_i)
                                model.AddImplication(self.juega[(d, div, i, j)], var_loc_j.Not())

            # 0. Alterrnancia Hard por División (Max 2 seguidos)
            for i in equipos_div:
                if i.startswith("Libre_"): continue
                for d in range(1, fechas_total - 1):
                    v1 = self.es_local_div[(d, div, i)]
                    v2 = self.es_local_div[(d+1, div, i)]
                    v3 = self.es_local_div[(d+2, div, i)]
                    model.Add(v1 + v2 + v3 <= 2)
                    model.Add(v1 + v2 + v3 >= 1)

            # 1. Round Robin: exactamente 1 enfrentamiento en la IDA (puede ser local o visit)
            for i_idx, i in enumerate(equipos_div):
                for j_idx, j in enumerate(equipos_div):
                    if i_idx < j_idx:
                        enfrentamientos_ida = []
                        for d in range(1, fechas_ida + 1):
                            enfrentamientos_ida.append(self.juega[(d, div, i, j)])
                            enfrentamientos_ida.append(self.juega[(d, div, j, i)])
                        model.AddExactlyOne(enfrentamientos_ida)
                        
            # 2. Espejo de la VUELTA: La vuelta es el fixture invertido
            for i in equipos_div:
                for j in equipos_div:
                    if i != j:
                        for d in range(1, fechas_ida + 1):
                            d_vuelta = d + fechas_ida
                            model.Add(self.juega[(d_vuelta, div, i, j)] == self.juega[(d, div, j, i)])

            # 3. Restricción Semanal
            for i in equipos_div:
                for d in range(1, fechas_total + 1):
                    partidos = []
                    for j in equipos_div:
                        if i != j:
                            partidos.append(self.juega[(d, div, i, j)])
                            partidos.append(self.juega[(d, div, j, i)])
                    model.Add(sum(partidos) <= 1)

    def _get_vars_for_team(self, d, team_name, cat_filter="ANY"):
        found = []
        if not hasattr(self, 'es_local_div'): return found
        
        # Determine strict name matches to avoid substring overlaps
        for (d_var, div, eq), var in self.es_local_div.items():
            if d_var != d: continue
            
            # Exact mapping or specific parent mapping
            padre_eq = eq
            if eq.startswith("Libre_"):
                continue
            
            # Extract main club pad from `_get_entidad`
            base_entidad = self._get_entidad(eq)
            # Match if name matches EXACTLY or if it's the clubPadre
            match_team = False
            if eq == team_name:
                match_team = True
            else:
                # Check if this record belongs to the clubPadre requested
                for e_info in self.equipos:
                    if e_info["nombre"] == eq:
                        if e_info.get("clubPadre") == team_name:
                            match_team = True
                        break

            if match_team:
                if cat_filter == 'MAYORES' and 'MAYORES' in div and 'FEMENINO' not in div:
                    found.append((var, div, eq))
                elif cat_filter == 'JUVENILES' and 'JUVENILES' in div:
                    found.append((var, div, eq))
                elif cat_filter == 'INFANTILES' and 'INFANTILES' in div:
                    found.append((var, div, eq))
                elif cat_filter == 'INFERIORES' and ('JUVENILES' in div or 'INFANTILES' in div):
                    found.append((var, div, eq))
                elif cat_filter == 'MASCULINO' and 'FEMENINO' not in div:
                    found.append((var, div, eq))
                elif cat_filter == 'FEMENINO' and 'FEMENINO' in div:
                    found.append((var, div, eq))
                elif cat_filter == 'FEM_MAYORES' and 'FEMENINO MAYORES' in div:
                    found.append((var, div, eq))
                elif cat_filter == 'FEM_MENORES' and 'FEMENINO MENORES' in div:
                    found.append((var, div, eq))
                elif cat_filter == 'ANY':
                    found.append((var, div, eq))
                    
        return found

    def _apply_user_constraints(self, model):
        if not hasattr(self, 'user_sync_rewards'):
            self.user_sync_rewards = []
            
        for d in range(1, self.fechas_max + 1):
            for r in self.reglas:
                club_a = r.get("clubA")
                club_b = r.get("clubB")
                bloque_a = r.get("bloqueA")
                bloque_b = r.get("bloqueB")
                tipo = r.get("tipo") # ESPEJO or INVERSO
                peso = r.get("peso", 500)
                
                vars_a = self._get_vars_for_team(d, club_a, bloque_a)
                vars_b = self._get_vars_for_team(d, club_b, bloque_b)
                
                if not vars_a or not vars_b:
                    # Optional: print(f"Warning: Rule skipped {club_a}/{bloque_a} -> {club_b}/{bloque_b}")
                    continue
                
                for var_a, div_a, eq_a in vars_a:
                    for var_b, div_b, eq_b in vars_b:
                        # "A raja tabla": Highest priority soft constraints
                        # We use a weight of 1,000,000 * peso to ensure these rules override everything else.
                        sync_ok = model.NewBoolVar(f"sync_ok_d{d}_{club_a[:3]}_{bloque_a[:3]}_{club_b[:3]}_{bloque_b[:3]}")
                        
                        if tipo == "ESPEJO":
                            model.Add(var_a == var_b).OnlyEnforceIf(sync_ok)
                            model.Add(var_a != var_b).OnlyEnforceIf(sync_ok.Not())
                        elif tipo == "INVERSO":
                            model.Add(var_a != var_b).OnlyEnforceIf(sync_ok)
                            model.Add(var_a == var_b).OnlyEnforceIf(sync_ok.Not())
                        
                        self.user_sync_rewards.append(sync_ok * (peso * 1000000))

    def _add_logistical_constraints(self, model):
        # 1. Alternancia:
        for e in self.clubes_padre:
            if e.startswith("Libre_"): continue
            
            # Max 2 consecutive locals, Max 2 consecutive visitors
            for d in range(1, self.fechas_max - 1):
                model.Add(self.es_local[(d, e)] + self.es_local[(d+1, e)] + self.es_local[(d+2, e)] <= 2)
                model.Add(self.es_local[(d, e)] + self.es_local[(d+1, e)] + self.es_local[(d+2, e)] >= 1)

        self.penalties = []

        # 2. Ayacucho Policía - SOFT CONSTRAINT
        ayacucho = ["BOTAFOGO F.C.", "ATLETICO AYACUCHO", "SARMIENTO (AYACUCHO)", "DEFENSORES DE AYACUCHO", "ATENEO ESTRADA"]
        ayacucho_valid = [x for x in ayacucho if x in self.clubes_padre]
        for d in range(1, self.fechas_max + 1):
            sum_locals = sum(self.es_local[(d, e)] for e in ayacucho_valid)
            excess = model.NewIntVar(0, len(ayacucho_valid), f"exceso_ayac_{d}")
            model.Add(excess >= sum_locals - 2)
            self.penalties.append(excess * 50) # Heavy penalty for exceeding police limit

        self._apply_user_constraints(model)
        
        # Maximize the synchronization points minus penalties
        model.Maximize(sum(self.sync_rewards) + sum(getattr(self, 'user_sync_rewards', [])) - sum(self.penalties))

    def _exists(self, nombre):
        for e in self.equipos:
            if e["nombre"] == nombre:
                return True
        return False

if __name__ == "__main__":
    generator = FixtureGenerator("equipos.json")
    fechas, status = generator.solve()
    print(f"Status: {status}. Fechas generadas: {len(fechas) if fechas else 0}")
    
    if fechas:
        with open("fixture.json", "w", encoding="utf-8") as f:
            json.dump(fechas, f, indent=4, ensure_ascii=False)
        print("Fixture guardado en fixture.json")
