import argparse
import logging
from src.utils import QDIMACSParser
from src.sampler import OracleSampler
from src.candidateSkolem import BasisLearner
from src.repair import Verifier, Repairer

def main():
    # Setup Logging
    logging.basicConfig(
        level=logging.DEBUG, 
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("ddb_main")

    parser = argparse.ArgumentParser(description="DDB: Data Driven Basis Synthesis")
    parser.add_argument("spec_file", help="Path to QDIMACS specification file")
    parser.add_argument("--samples", type=int, default=500, help="Number of training samples")
    parser.add_argument("--iterations", type=int, default=50, help="Max repair iterations")
    
    # Topology sort toggle
    parser.add_argument("--topo-sort", action="store_true", default=True, help="Enable topological sort of output variables (Default)")
    parser.add_argument("--no-topo-sort", action="store_false", dest="topo_sort", help="Disable topological sort (Use QDIMACS order)")
    
    args = parser.parse_args()
    
    logger.info(f"Processing specification: {args.spec_file}")
    qparser = QDIMACSParser(args.spec_file)
    logger.info(f"Input dimensions: |X|={len(qparser.universals)}, |Y|={len(qparser.existentials)}")
    
    input_vars = list(qparser.universals)
    
    if args.topo_sort:
        logger.info("Computing topological dependency order...")
        output_vars = qparser.get_dependency_order()
    else:
        logger.info("Using QDIMACS file order for output variables.")
        output_vars = list(qparser.existentials)

    logger.info(f"Variable Order: {output_vars}")
    
    # Phase 2: Sampling
    logger.info(f"Starting Phase 2: Sampling ({args.samples} samples)")
    sampler = OracleSampler(qparser.get_cnf(), input_vars, output_vars)
    # samples_data contains the full trace (X + Y)
    samples_data, labels_Y = sampler.generate_samples(args.samples)
    
    # Phase 3: Learning
    logger.info("Starting Phase 3: Learning Initial Basis")
    learner = BasisLearner(input_vars, output_vars)
    # Pass full samples_data so learner can extract Y_{<i} features
    candidates = learner.learn(samples_data, labels_Y)
    
    # Initialize G variables
    max_var = qparser.num_vars
    g_vars = {}
    for y in output_vars:
        max_var += 1
        g_vars[y] = max_var
        
    logger.info("Starting Phase 4: Verification & Repair Loop")
    verifier = Verifier(qparser, input_vars, output_vars)
    repairer = Repairer(qparser, input_vars, output_vars)
    
    for iteration in range(args.iterations):
        logger.info(f"--- Iteration {iteration+1}/{args.iterations} ---")
        is_safe, cex = verifier.verify(candidates, g_vars)
        
        if is_safe:
            logger.info("SUCCESS! Valid Skolem Basis Synthesized.")
            _print_solution(candidates, output_vars)
            return
        
        logger.info("Result: UNSAFE. Attempting repair...")
        candidates = repairer.localize_and_repair(candidates, cex)
        
    logger.error("FAILURE: Synthesis loop exceeded iteration limit.")

def _print_solution(candidates, output_vars):
    print("\n--- Synthesized Skolem Basis ---")
    for y in output_vars:
        cand = candidates[y]
        print(f"y_{y}:")
        print(f"  Must-1 (A): {len(cand['A'].cubes)} cubes, {len(cand['A'].clauses)} clauses")
        print(f"  Must-0 (C): {len(cand['C'].cubes)} cubes, {len(cand['C'].clauses)} clauses")
        
if __name__ == "__main__":
    main()