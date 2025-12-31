import pycmsgen
import logging
from pysat.solvers import Glucose3

logger = logging.getLogger(__name__)

class OracleSampler:
    """
    Generates training data for the Skolem functions.
    
    Architecture:
    1. Generator: Uses pycmsgen to produce high-quality, uniform-like satisfying assignments.
    2. Oracle: Uses Glucose3 to perform the 'Poly-Check' (labeling Must-1/Must-0/Don't-Care)
       by checking the satisfiability of alternate values under the current prefix.
    """
    def __init__(self, cnf, input_vars, output_vars):
        self.cnf = cnf
        self.input_vars = input_vars
        self.output_vars = output_vars
        
        logger.debug(f"Initializing OracleSampler with {len(input_vars)} inputs, {len(output_vars)} outputs.")
        
        # --- 1. Initialize Generator (pycmsgen) ---
        self.sampler = pycmsgen.Solver()
        
        # Load clauses into pycmsgen (supports bulk addition)
        if cnf.clauses:
            self.sampler.add_clauses(cnf.clauses)
            logger.debug(f"Loaded {len(cnf.clauses)} clauses into pycmsgen.")
            
        # Note: Weights are not set explicitly; relying on default sampler behavior.

        # --- 2. Initialize Oracle (Glucose3) ---
        self.oracle = Glucose3(bootstrap_with=cnf.clauses)

    def generate_samples(self, num_samples):
        """
        Generates labeled samples for each output variable.
        Returns: 
            samples_X: List of input assignments
            labels_Y: Dict {var_idx: [label_1, label_2, ...]}
            
        Labels:
            0: Don't-Care (Both 0 and 1 are valid given prefix)
            1: Must-1     (0 is UNSAT given prefix)
            2: Must-0     (1 is UNSAT given prefix)
        """
        samples_X = []
        labels_Y = {v: [] for v in self.output_vars}
        
        generated_count = 0
        logger.info(f"Starting sample generation. Target: {num_samples}")
        
        while generated_count < num_samples:
            # 1. Generate a valid satisfying assignment (Sample)
            found = self.sampler.solve()
            
            if not found:
                logger.warning("Sampler returned False. Spec might be UNSAT or exhausted.")
                break
                
            model = self.sampler.get_model()
            
            # Map literals to values for O(1) lookup
            sample_map = {abs(l): l for l in model}
            
            # Extract Input vector X for this sample
            X_vector = []
            for x in self.input_vars:
                val = 1 if sample_map.get(x, -x) > 0 else 0
                X_vector.append(val)
            
            samples_X.append(X_vector)
            
            # 2. Labeling (The "Poly-Check")
            # For each output y_i, check if its value was "forced" by the prefix.
            for i, y_var in enumerate(self.output_vars):
                prefix_lits = []
                
                # Add X assumptions
                for x in self.input_vars:
                    prefix_lits.append(sample_map.get(x, -x))
                
                # Add Y_{<i} assumptions
                for prev_y in self.output_vars[:i]:
                    prefix_lits.append(sample_map.get(prev_y, -prev_y))
                
                # Check 0: Is F(P, y_i=0) SAT?
                can_be_zero = self.oracle.solve(assumptions=prefix_lits + [-y_var])
                
                # Check 1: Is F(P, y_i=1) SAT?
                can_be_one = self.oracle.solve(assumptions=prefix_lits + [y_var])
                
                label = 0 # Default: Don't Care
                
                if can_be_zero and can_be_one:
                    label = 0 # Don't Care
                elif not can_be_zero and can_be_one:
                    label = 1 # Must-1
                elif can_be_zero and not can_be_one:
                    label = 2 # Must-0
                else:
                    label = 0 
                
                labels_Y[y_var].append(label)
            
            generated_count += 1
            if generated_count % 50 == 0:
                logger.info(f"Generated {generated_count}/{num_samples} samples.")
            
        logger.info(f"Finished sampling. Total samples: {len(samples_X)}")
        return samples_X, labels_Y