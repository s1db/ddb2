import logging
from pysat.formula import CNF

logger = logging.getLogger(__name__)

class QDIMACSParser:
    """Parses QDIMACS files to extract matrix and variable sets."""
    def __init__(self, filepath):
        self.filepath = filepath
        self.num_vars = 0
        self.num_clauses = 0
        self.universals = set()
        self.existentials = [] # Ordered
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

class SymbolicBasis:
    """
    Represents a boolean function (A or C) that supports both
    Expansion (adding DNF cubes) and Shrinking (adding CNF clauses).
    
    Structure: F(X) = (Cube1 v Cube2 v ...) AND (Clause1 ^ Clause2 ^ ...)
    """
    def __init__(self, name):
        self.name = name
        self.cubes = []   # List of list of literals (ANDs) -> ORed together
        self.clauses = [] # List of list of literals (ORs) -> ANDed together

    def add_cube(self, lits):
        """Expand the function coverage (OR)."""
        logger.debug(f"[{self.name}] Adding Cube (Expand): {lits}")
        self.cubes.append(lits)

    def add_clause(self, lits):
        """Shrink the function coverage (AND)."""
        logger.debug(f"[{self.name}] Adding Clause (Shrink): {lits}")
        self.clauses.append(lits)

    def evaluate(self, assignment_map):
        """
        Eval F(x). Returns True/False.
        assignment_map: dict {var_int: val_bool}
        """
        # 1. Evaluate DNF part (Must be True if no cubes? No, empty DNF is False)
        # If no cubes are present, we assume False unless strictly defined otherwise,
        # but for repair loop, we start with learned cubes.
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

        # 2. Evaluate CNF part (Must be True)
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
        Requires auxiliary variables for the DNF part (Tseitin).
        Returns: (clauses, next_fresh_var, output_lit)
        """
        clauses = []
        curr_var = start_fresh_var
        
        # 1. Encode DNF part: y_dnf <-> (C1 v C2 ...)
        
        cube_lits = []
        for cube in self.cubes:
            cube_lit = curr_var
            curr_var += 1
            cube_lits.append(cube_lit)
            
            # cube_lit -> (l1 ^ l2)  => (-cube_lit v l1), (-cube_lit v l2)
            for l in cube:
                clauses.append([-cube_lit, l])
            
            # (l1 ^ l2) -> cube_lit => (-l1 v -l2 v cube_lit)
            clauses.append([-l for l in cube] + [cube_lit])
            
        dnf_out = curr_var
        curr_var += 1
        
        # dnf_out <-> OR(cube_lits)
        # dnf_out -> OR is (-dnf_out v c1 v c2...)
        clauses.append([-dnf_out] + cube_lits)
        # OR -> dnf_out is (-c1 v dnf_out), (-c2 v dnf_out)...
        for cl in cube_lits:
            clauses.append([-cl, dnf_out])
            
        if not self.cubes:
            # Empty DNF is false
            clauses.append([-dnf_out])

        # 2. Encode CNF part
        final_out = curr_var
        curr_var += 1
        
        # final_out <-> dnf_out ^ (Cl1) ^ (Cl2)...
        # final_out -> dnf_out
        clauses.append([-final_out, dnf_out])
        
        # final_out -> Cl_i
        for cl in self.clauses:
            # cl is a list of lits. final_out -> (l1 v l2) => -final_out v l1 v l2
            clauses.append([-final_out] + cl)
            
        return clauses, curr_var, final_out

    def get_cnf_constraints(self, out_lit, start_fresh_var):
        """
        Generates clauses that enforce out_lit <-> ThisBasis(X).
        """
        # Note: Logic logic is identical to previous version, just refactored inside.
        # Re-using the manual logic from before to ensure correctness of bi-implication
        
        c_list = []
        curr = start_fresh_var
        
        # 1. Encode DNF term `d`
        cube_lits = []
        for cube in self.cubes:
            c_lit = curr
            curr += 1
            cube_lits.append(c_lit)
            # c_lit <-> cube
            for l in cube: c_list.append([-c_lit, l])
            c_list.append([-l for l in cube] + [c_lit])
            
        d_lit = curr
        curr += 1
        # d_lit <-> OR(cube_lits)
        if not cube_lits:
            c_list.append([-d_lit]) # Empty DNF is false
        else:
            c_list.append([-d_lit] + cube_lits)
            for cl in cube_lits: c_list.append([-cl, d_lit])

        # 2. Link out_lit to d_lit and logical clauses
        
        cnf_lits = []
        for cl in self.clauses:
            # c_lit <-> (l1 v l2 ...)
            cl_lit = curr
            curr += 1
            cnf_lits.append(cl_lit)
            
            # cl_lit -> clause
            c_list.append([-cl_lit] + cl)
            # clause -> cl_lit
            for l in cl:
                c_list.append([-l, cl_lit])
        
        # Now: out_lit <-> (d_lit AND all cnf_lits)
        # out_lit -> d_lit
        c_list.append([-out_lit, d_lit])
        # out_lit -> cnf_lits
        for cll in cnf_lits:
            c_list.append([-out_lit, cll])
            
        # (d_lit AND all cnf_lits) -> out_lit
        # -d_lit v -cl_lit1 v ... v out_lit
        c_list.append([-d_lit] + [-x for x in cnf_lits] + [out_lit])
        
        return c_list, curr