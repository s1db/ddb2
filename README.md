# ddb: The Data Driven Basis Algorithm

* **Version 2.0.0:** MVP + MaxSAT
* **Objective:** Synthesis of flexible Skolem Basis vectors for Boolean functional specifications.

## 1. Introduction

Standard Boolean Functional Synthesis takes a relational specification $F(X, Y)$ and produces a single, rigid function vector $\Psi(X) \rightarrow Y$. While sufficient for satisfiability, this rigid approach discards the inherent flexibility of the solution space, which is critical for downstream tasks like optimization or counting.

**ddb (Data Driven Basis)** is an algorithm that synthesizes a **Skolem Basis** instead of a single function. For each output variable $y_i$, it learns three regions:

* **Must-1 ($A_i$):** Inputs where $y_i$ **must** be 1.
* **Must-0 ($C_i$):** Inputs where $y_i$ **must** be 0.
* **Don't-Care ($B_i$):** Inputs where $y_i$ can be freely chosen.

This basis is encoded into a parameterized function $\psi_i(X, g_i)$, where $g_i$ is a free variable exposed to the user. This allows the user to optimize the output by tuning $g_i$ without violating the hard specification $F$.

---

## 2. Theoretical Formulation

For a given output variable $y_i$, we define the synthesis target $\psi_i$ using the **Must-1 ($A$)** and **Must-0 ($C$)** sets. The Don't-Care set ($B$) is implicitly defined as the region where neither $A$ nor $C$ applies.

The synthesized function is formulated as:

$$\psi_i(X, Y_{<i}, g_i) = A_i \lor (g_i \land \neg C_i)$$

### Properties

1. **If $A_i$ is true:** The output is **1** (regardless of $g_i$).
2. **If $C_i$ is true:** The output is **0** (because $\neg C_i$ is 0, forcing the AND gate to 0).
3. **If neither is true (Region $B_i$):** The output simplifies to $g_i$. The user has full control.

### Guarantees

* **Safety (Validity):** The algorithm guarantees that for **any** choice of $g_i$, the specification $F$ holds.
* **Optimality (Maximality):** In the MVP, the algorithm prioritizes Safety. It guarantees that $A$ and $C$ are correct "Must" sets, but $B$ may be an under-approximation (i.e., some Don't-Cares might be temporarily classified as "Must").

---

## 3. The ddb Algorithm

* **Input:** Relational Specification $F(X, Y)$ (qdimacs format where the universal variables are X and existential variables are Y).
* **Output:** Vector of functions $\Psi = \langle \psi_1, \dots, \psi_m \rangle$ parameterized by $G = \langle g_1, \dots, g_m \rangle$.

### Phase 1: Dependency Analysis

Determine a topological ordering of output variables $Y$. Let $Y_{ordered} = \langle y_1, y_2, \dots, y_m \rangle$. For each $y_i$, the allowed input features are $X$ and the upstream outputs $Y_{<i}$.

### Phase 2: Sampling and Labeling

We generate training data labeled with "Must-1", "Must-0", or "Don't-Care".

1. **Generate Samples:** Use a constrained sampler (e.g., CMSGen) to generate a set of valid satisfying assignments $\Sigma = \{ \sigma_1, \dots, \sigma_N \}$ for $F(X, Y)$.
2. **Labeling:** For each sample $\sigma \in \Sigma$ and each output $y_i$:
    * Fix the prefix: Let $\pi = \sigma[X \cup Y_{<i} \cup Y_{>i}]$.
    * **Check 0:** Is $F(\pi, y_i=0)$ SAT? (Note: If $\sigma[y_i]=0$, this is trivially True).
    * **Check 1:** Is $F(\pi, y_i=1)$ SAT? (Note: If $\sigma[y_i]=1$, this is trivially True).
3. **Assign Label:**
    * Only Check 0 is SAT $\rightarrow$ Label: **Must-0 ($C$)**
    * Only Check 1 is SAT $\rightarrow$ Label: **Must-1 ($A$)**
    * Both are SAT $\rightarrow$ Label: **Don't-Care ($B$)**

*Computational Note: Because the assignment $\pi$ is complete (all variables fixed), the SAT checks are $O(1)$ (constant time propagation) rather than NP-Hard queries.*

### Phase 3: Learning

Train symbolic approximations ($\hat{A}_i, \hat{C}_i$) from the labeled data.

* **Dataset:** Features $= \{X, Y_{<i}\}$, Labels $= \{A, B, C\}$.
* **Classifier:** Train a Multi-Class Decision Tree (or Random Forest).
* **Extraction Mechanism:** The goal is to convert the decision tree paths into Boolean formulas.
  * **Step A: Path Tracing.** For each leaf node labeled **Must-1**: Trace the path from Root to Leaf. Collect literals (Right=True, Left=False) and form a conjunction $P$.
  * **Step B: Aggregation.**
    * $\hat{A}_i = \bigvee \{ P \mid \text{Leaf is Must-1} \}$
    * $\hat{C}_i = \bigvee \{ P \mid \text{Leaf is Must-0} \}$
    * *Don't-Care leaves are ignored.* They naturally fall into the gap where $\hat{A}$ is false and $\hat{C}$ is false.

* **Example Tree:**

    ```plaintext
        [x_1?]
        /      \
        0        1
    [x_2?]    [Must-1] (Leaf 1)
    /    \
    0      1
    [Must-0] [Don't-Care]
    (Leaf 2)   (Leaf 3)
    ```

* Result: $\psi_1 = x_1 \lor (g_1 \land \neg(\neg x_1 \land \neg x_2))$.

### Phase 4: Verification & Repair

We must verify that the learned approximations $\hat{A}_i$ and $\hat{C}_i$ are **safe** for any user choice of $g_i$.

**The Error Formula:**
$$ E(X, G, Y, Y') = \exists X, G, Y, Y' . \quad F(X, Y) \land \neg F(X, Y') \land (Y' \leftrightarrow \Psi(X, G)) $$

**The Loop:**

1. **CheckSat($E$):**
    * If **UNSAT**: Terminate. The functions are valid.
    * If **SAT**: The solver returns a counterexample model ($\sigma[X]$, $g_{val}$, $\Psi_{val}$).
2. **Fault Localization (MaxSAT):** Find the minimal set of erring candidate functions.
    * **Hard Constraints:** $F(X, Y) \land (X \leftrightarrow \sigma[X])$.
    * **Soft Constraints:** $(y_i \leftrightarrow \Psi_{val}[i])$.
    * **Solve:** Returns optimal solution $Y_{fix}$.
3. **Identify Candidates:** $Ind = \{ i \mid Y_{fix}[i] \neq \Psi_{val}[i] \}$.
4. **Repair Execution:** For each index $i \in Ind$, synthesize a repair.
    * Let $Y_{fix}$ (Target) and $Y'_{val}$ (Current Erroneous Output).

#### Diagnosis Table

| $Y_{fix}$ (Target) | $g_{val}$ | $Y'_{val}$ (Current) | Effective Logic | Repair Action |
| :---: | :---: | :---: | :--- | :--- |
| **0** | **0** | **1** | $A$ forced 1. | **Shrink $\hat{A}$** |
| **0** | **1** | **1** | $A$ forced 1 OR $\neg C$ allowed 1. | **Check $\hat{A}(\sigma)$:**<br>• If True $\to$ **Shrink $\hat{A}$**<br>• Else $\to$ **Expand $\hat{C}$** |
| **1** | **0** | **0** | $A$ failed to be 1. | **Expand $\hat{A}$** |
| **1** | **1** | **0** | $\neg C$ forced 0. | **Shrink $\hat{C}$** |

1. **Unsat Core Patching:**
    * Construct Conflict Formula ($H_k$):
        To repair candidate $k$, we use the conflict formula derived from the Manthan paper. Crucially, we assume all downstream variables ($\hat{Y}$) are fixed to their correct values from the MaxSAT solution, isolating the error at index $k$.

        Let $\hat{Y} = \{ y_j \mid j > k \}$ (Variables appearing after $y_k$ in the topological order).

        $$H_k(X, Y) = (\psi_k(X, g_{val}) \leftrightarrow Y'_{val}) \land F(X, Y) \land (X \leftrightarrow \sigma[X]) \land (\hat{Y} \leftrightarrow Y_{fix}[\hat{Y}])$$

        *(Logic: "Given the fixed input $\sigma[X]$ and correct future values $\hat{Y}$, why did function $k$ produce $Y'_{val}$ which contradicts the spec F?")*
    * Extract Unsat Core $\rightarrow$ Form $\beta$.
    * **Update:**
        * Shrink: $S_{new} \leftarrow S_{old} \land \neg \beta$
        * Expand: $S_{new} \leftarrow S_{old} \lor \beta$
2. Repeat Verification Loop.

---

## 4. Implementation Details

### The Repair Precedence

In the case where Target=0 and g=1, the logic $\psi = A \lor \neg C$ produces 1. This could be because $A$ is effectively 1 (overriding everything) OR because $C$ is effectively 0 (allowing the $g=1$ to pass through).

* You **must** evaluate $\hat{A}(\sigma)$ first.
* If $\hat{A}$ evaluates to True, the error is in $\hat{A}$ (Shrink $\hat{A}$).
* Only if $\hat{A}$ evaluates to False is the error in $\hat{C}$ (Expand $\hat{C}$).

### Handling Hard-to-Learn Functions

If a specific variable $y_i$ undergoes repair more than a threshold $T$ (e.g., 50 times), it is considered "Hard-to-Learn".

* **Fallback:** Switch to semantic derivation.
  * $\hat{A}_i = F|_{y_i=1} \land \neg F|_{y_i=0}$ (Semantic Must-1).
  * $\hat{C}_i = F|_{y_i=0} \land \neg F|_{y_i=1}$ (Semantic Must-0).
* *(Note: This is computationally expensive and should be a last resort).*

---

## 5. Conclusion

The **ddb** algorithm produces a Skolem vector that is correct by construction (via the $g$-check) and flexible by design. By separating the logic into Must-1, Must-0, and Don't-Care regions, it empowers downstream users to perform optimization tasks on the valid solution space that were previously impossible with rigid synthesis tools.
