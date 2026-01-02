import logging
import collections
from pysat.formula import CNF

logger = logging.getLogger(__name__)

class QDIMACSParser:
    """Parses QDIMACS files to extract matrix and variable sets."""
    def __init__(self, filepath):
        self.filepath = filepath
        self.num_vars = 0
        self.num_clauses = 0
        self.universals = set()
        self.existentials = [] # Ordered list from file
        self.clauses = []
        self._parse()

    def _parse(self):
        logger.info(f"Parsing QDIMACS file: {self.filepath}")
        with open(self.filepath, 'r') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('c'):
                continue
            
            if line.startswith('p cnf'):
                parts = line.split()
                self.num_vars = int(parts[2])
                self.num_clauses = int(parts[3])
                logger.debug(f"Header found: {self.num_vars} vars, {self.num_clauses} clauses")
                continue
            
            if line.startswith('a') or line.startswith('e'):
                quant = line.split()[0]
                vars_ = [int(x) for x in line.split()[1:] if x != '0']
                if quant == 'a':
                    self.universals.update(vars_)
                else:
                    self.existentials.extend(vars_)
                continue
            
            # Clause
            lits = [int(x) for x in line.split() if x != '0']
            if lits:
                self.clauses.append(lits)
        
        logger.info(f"Parsed {len(self.universals)} universal and {len(self.existentials)} existential variables.")

    def get_cnf(self):
        cnf = CNF()
        for c in self.clauses:
            cnf.append(c)
        return cnf

    def get_dependency_order(self):
        """
        Determines a topological ordering of existential variables based on 
        clause connectivity to universal variables.
        
        Method:
        1. Build Variable Interaction Graph (VIG) where edge (u,v) exists if they appear in same clause.
        2. Perform BFS starting from Universal variables (X) to find 'closest' Existentials (Y).
        3. Append any disconnected components.
        """
        logger.info("Computing topological dependency order...")
        
        # 1. Build Adjacency Graph
        # Note: We track connections for all variables.
        adj = collections.defaultdict(set)
        for cl in self.clauses:
            # We don't need full clique; just connecting adjacent lits in list is NOT enough.
            # We need full clique for the clause? 
            # Optimization: Just connect all vars in clause to each other.
            # For short clauses this is fine.
            vars_in_clause = [abs(l) for l in cl]
            for i in range(len(vars_in_clause)):
                u = vars_in_clause[i]
                for j in range(i + 1, len(vars_in_clause)):
                    v = vars_in_clause[j]
                    adj[u].add(v)
                    adj[v].add(u)
                    
        # 2. BFS Initialization
        order = []
        visited = set(self.universals) # Mark inputs as visited
        queue = collections.deque(sorted(list(self.universals)))
        
        # If no universals (SAT problem), pick a heuristic start node
        if not queue and self.existentials:
             # Heuristic: Start with variable having highest degree (most constrained)
             start_node = max(self.existentials, key=lambda x: len(adj[x]))
             visited.add(start_node)
             if start_node in self.existentials:
                 order.append(start_node)
             queue.append(start_node)

        # 3. BFS Traversal
        existential_set = set(self.existentials)
        
        while queue:
            u = queue.popleft()
            
            # Get neighbors in specific order (e.g. numerical) for determinism
            neighbors = sorted(list(adj[u]))
            
            for v in neighbors:
                if v not in visited:
                    visited.add(v)
                    queue.append(v)
                    if v in existential_set:
                        order.append(v)
        
        # 4. Handle Disconnected Components
        # Append remaining existentials that weren't reached (unconstrained by X or main component)
        # We preserve their relative file order as a fallback.
        remaining = [y for y in self.existentials if y not in visited]
        if remaining:
            logger.info(f"Appending {len(remaining)} disconnected variables to order.")
            order.extend(remaining)
            
        logger.debug(f"Computed order: {order}")
        return order

class SymbolicBasis:
    """
    Represents a boolean function (A or C) that supports both
    Expansion (adding DNF cubes) and Shrinking (adding CNF clauses).
    """
    def __init__(self, name):
        self.name = name
        self.cubes = []   # List of list of literals (ANDs) -> ORed together
        self.clauses = [] # List of list of literals (ORs) -> ANDed together

    def add_cube(self, lits):
        """
        Expand the function coverage (OR).
        Ensures that existing clauses do not block this new cube by removing conflicting clauses.
        """
        logger.debug(f"[{self.name}] Adding Cube (Expand): {lits}")
        
        # 1. Filter out conflicting clauses
        # A clause C conflicts with cube K if K => !C.
        # This happens if for every lit l in C, -l is in K.
        
        cube_lit_set = set(lits)
        non_conflicting_clauses = []
        removed_count = 0
        
        for clause in self.clauses:
            is_conflicting = True
            for cl_lit in clause:
                # If clause literal matches a cube literal, clause is satisfied by cube. No conflict.
                if cl_lit in cube_lit_set:
                    is_conflicting = False
                    break
                # If clause literal's negation is NOT in cube, then cube doesn't force this lit to False.
                if -cl_lit not in cube_lit_set:
                    is_conflicting = False
                    break
            
            if is_conflicting:
                removed_count += 1
            else:
                non_conflicting_clauses.append(clause)
        
        if removed_count > 0:
            logger.debug(f"[{self.name}] Removed {removed_count} conflicting clauses to allow expansion.")
            self.clauses = non_conflicting_clauses

        self.cubes.append(lits)

    def add_clause(self, lits):
        """Shrink the function coverage (AND)."""
        logger.debug(f"[{self.name}] Adding Clause (Shrink): {lits}")
        self.clauses.append(lits)

    def evaluate(self, assignment_map):
        """
        Eval F(x). Returns True/False.
        """
        # 1. Evaluate DNF part
        dnf_val = False
        if not self.cubes:
            dnf_val = False 
        else:
            for cube in self.cubes:
                cube_sat = True
                for lit in cube:
                    var = abs(lit)
                    val = assignment_map.get(var, False)
                    if lit < 0: val = not val
                    if not val:
                        cube_sat = False
                        break
                if cube_sat:
                    dnf_val = True
                    break
        
        if not dnf_val:
            return False

        # 2. Evaluate CNF part
        for clause in self.clauses:
            clause_sat = False
            for lit in clause:
                var = abs(lit)
                val = assignment_map.get(var, False)
                if lit < 0: val = not val
                if val:
                    clause_sat = True
                    break
            if not clause_sat:
                return False
        
        return True

    def to_cnf(self, start_fresh_var):
        """
        Convert the internal structure to pure CNF clauses for solver encoding.
        """
        clauses = []
        curr_var = start_fresh_var
        
        # 1. Encode DNF part
        cube_lits = []
        for cube in self.cubes:
            cube_lit = curr_var
            curr_var += 1
            cube_lits.append(cube_lit)
            
            # cube_lit -> (l1 ^ l2)
            for l in cube:
                clauses.append([-cube_lit, l])
            
            # (l1 ^ l2) -> cube_lit
            clauses.append([-l for l in cube] + [cube_lit])
            
        dnf_out = curr_var
        curr_var += 1
        
        # dnf_out <-> OR(cube_lits)
        clauses.append([-dnf_out] + cube_lits)
        for cl in cube_lits:
            clauses.append([-cl, dnf_out])
            
        if not self.cubes:
            clauses.append([-dnf_out])

        # 2. Encode CNF part
        final_out = curr_var
        curr_var += 1
        
        # final_out <-> dnf_out ^ (Cl1) ^ (Cl2)...
        clauses.append([-final_out, dnf_out])
        
        for cl in self.clauses:
            clauses.append([-final_out] + cl)
            
        return clauses, curr_var, final_out

    def get_cnf_constraints(self, out_lit, start_fresh_var):
        """
        Generates clauses that enforce out_lit <-> ThisBasis(X).
        """
        c_list = []
        curr = start_fresh_var
        
        # 1. Encode DNF term `d`
        cube_lits = []
        for cube in self.cubes:
            c_lit = curr
            curr += 1
            cube_lits.append(c_lit)
            for l in cube: c_list.append([-c_lit, l])
            c_list.append([-l for l in cube] + [c_lit])
            
        d_lit = curr
        curr += 1
        if not cube_lits:
            c_list.append([-d_lit])
        else:
            c_list.append([-d_lit] + cube_lits)
            for cl in cube_lits: c_list.append([-cl, d_lit])

        # 2. Link out_lit to d_lit and logical clauses
        cnf_lits = []
        for cl in self.clauses:
            cl_lit = curr
            curr += 1
            cnf_lits.append(cl_lit)
            
            c_list.append([-cl_lit] + cl)
            for l in cl:
                c_list.append([-l, cl_lit])
        
        c_list.append([-out_lit, d_lit])
        for cll in cnf_lits:
            c_list.append([-out_lit, cll])
            
        c_list.append([-d_lit] + [-x for x in cnf_lits] + [out_lit])
        
        return c_list, curr