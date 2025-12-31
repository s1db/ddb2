import logging
from sklearn.tree import DecisionTreeClassifier
from sklearn.tree import _tree
from src.utils import SymbolicBasis
import numpy as np

logger = logging.getLogger(__name__)

class BasisLearner:
    """
    Learns symbolic approximations (A_i, C_i) for each variable
    using Decision Trees.
    """
    def __init__(self, input_vars, output_vars):
        self.input_vars = input_vars
        self.output_vars = output_vars
        
    def learn(self, samples_X, labels_Y):
        """
        Train trees and extract formulas.
        Returns dict: {y_var: {'A': SymbolicBasis, 'C': SymbolicBasis}}
        """
        logger.info("Starting Decision Tree learning phase...")
        candidates = {}
        X = np.array(samples_X)
        
        for i, y_var in enumerate(self.output_vars):
            y_labels = np.array(labels_Y[y_var])
            
            logger.debug(f"Training for y_{y_var} (Idx: {i}). Labels shape: {y_labels.shape}")
            
            clf = DecisionTreeClassifier(
                class_weight='balanced', 
                max_depth=10, 
                random_state=42
            )
            clf.fit(X, y_labels)
            
            # Extract A (Must-1, Class 1) and C (Must-0, Class 2)
            A_basis = SymbolicBasis(f"A_{y_var}")
            C_basis = SymbolicBasis(f"C_{y_var}")
            
            self._extract_paths(clf, self.input_vars, 1, A_basis)
            self._extract_paths(clf, self.input_vars, 2, C_basis)
            
            logger.debug(f"  y_{y_var}: Extracted {len(A_basis.cubes)} cubes for A, {len(C_basis.cubes)} cubes for C.")
            
            candidates[y_var] = {'A': A_basis, 'C': C_basis}
        for y_var in self.output_vars:
            cand = candidates[y_var]
            logger.info(f"y_{y_var}: Learned Basis - A: {len(cand['A'].cubes)} cubes, {len(cand['A'].clauses)} clauses; C: {len(cand['C'].cubes)} cubes, {len(cand['C'].clauses)} clauses")
        logger.info("Learning phase complete.")
        return candidates

    def _extract_paths(self, tree, feature_names, target_class, basis):
        """
        Traverses the tree and adds paths leading to target_class to the basis DNF.
        """
        tree_ = tree.tree_
        
        def recurse(node, path):
            if tree_.feature[node] != -2:
                name = feature_names[tree_.feature[node]]
                # threshold = tree_.threshold[node]
                
                # Left Child (<= 0.5 -> Value 0) -> Literal is -name
                recurse(tree_.children_left[node], path + [-name])
                
                # Right Child (> 0.5 -> Value 1) -> Literal is name
                recurse(tree_.children_right[node], path + [name])
            else:
                # Leaf
                predicted_class = np.argmax(tree_.value[node])
                if predicted_class == target_class:
                    basis.add_cube(path)
                    
        recurse(0, [])