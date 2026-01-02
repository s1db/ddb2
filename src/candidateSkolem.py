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
        
    def learn(self, samples_data, labels_Y):
        """
        Train trees and extract formulas.
        samples_data: List of dicts {var_id: 0/1}
        labels_Y: Dict {var_id: [labels...]}
        
        Returns dict: {y_var: {'A': SymbolicBasis, 'C': SymbolicBasis}}
        """
        logger.info("Starting Decision Tree learning phase with dependencies...")
        candidates = {}
        
        # We iterate in topological order (as preserved in self.output_vars)
        for i, y_var in enumerate(self.output_vars):
            y_labels = np.array(labels_Y[y_var])
            
            # Dynamic Feature Selection: X + Y_{<i}
            # These are the allowed dependencies for y_i
            previous_y = self.output_vars[:i]
            feature_vars = self.input_vars + previous_y
            
            # Construct Feature Matrix X_mat for this specific variable
            # Dimensions: [num_samples, len(feature_vars)]
            X_mat = []
            for sample in samples_data:
                row = [sample[v] for v in feature_vars]
                X_mat.append(row)
            
            X_mat = np.array(X_mat)
            
            logger.debug(f"Training for y_{y_var} (Idx: {i}). Features: |X|={len(self.input_vars)} + |Y<i|={len(previous_y)}. Matrix: {X_mat.shape}")
            
            clf = DecisionTreeClassifier(
                class_weight='balanced', 
                max_depth=10, 
                random_state=42
            )
            clf.fit(X_mat, y_labels)
            
            # Extract A (Must-1, Class 1) and C (Must-0, Class 2)
            A_basis = SymbolicBasis(f"A_{y_var}")
            C_basis = SymbolicBasis(f"C_{y_var}")
            
            # Note: We pass the specific feature_vars used for this tree
            self._extract_paths(clf, feature_vars, 1, A_basis)
            self._extract_paths(clf, feature_vars, 2, C_basis)
            
            logger.debug(f"  y_{y_var}: Extracted {len(A_basis.cubes)} cubes for A, {len(C_basis.cubes)} cubes for C.")
            
            candidates[y_var] = {'A': A_basis, 'C': C_basis}
            
        logger.info("Learning phase complete.")
        return candidates

    def _extract_paths(self, tree, feature_vars, target_class, basis):
        """
        Traverses the tree and adds paths leading to target_class to the basis DNF.
        feature_vars: List of variable IDs corresponding to the tree's features columns.
        """
        tree_ = tree.tree_
        
        def recurse(node, path):
            if tree_.feature[node] != -2:
                # Map internal feature index to actual variable ID
                feature_idx = tree_.feature[node]
                var_id = feature_vars[feature_idx]
                
                # Left Child (<= 0.5 -> Value 0) -> Literal is -var_id
                recurse(tree_.children_left[node], path + [-var_id])
                
                # Right Child (> 0.5 -> Value 1) -> Literal is var_id
                recurse(tree_.children_right[node], path + [var_id])
            else:
                # Leaf
                predicted_class = np.argmax(tree_.value[node])
                if predicted_class == target_class:
                    basis.add_cube(path)
                    
        recurse(0, [])