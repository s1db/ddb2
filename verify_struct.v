module verification(
  x_2,
  x_3,
  y_orig_1,
  y_orig_4,
  g_1,
  g_4,
  out
);
  input x_2;
  input x_3;
  input y_orig_1;
  input y_orig_4;
  input g_1;
  input g_4;
  output out;

  wire a_1_dnf;
  assign a_1_dnf = (~x_2) | (x_2 & ~x_3);
  wire a_1_cnf;
  assign a_1_cnf = 1'b1;
  wire w_a_1;
  assign w_a_1 = a_1_dnf & a_1_cnf;
  wire c_1_dnf;
  assign c_1_dnf = 1'b0;
  wire c_1_cnf;
  assign c_1_cnf = 1'b1;
  wire w_c_1;
  assign w_c_1 = c_1_dnf & c_1_cnf;
  wire y_syn_1;
  assign y_syn_1 = w_a_1 | (g_1 & ~w_c_1);
  wire a_4_dnf;
  assign a_4_dnf = 1'b0;
  wire a_4_cnf;
  assign a_4_cnf = 1'b1;
  wire w_a_4;
  assign w_a_4 = a_4_dnf & a_4_cnf;
  wire c_4_dnf;
  assign c_4_dnf = 1'b0;
  wire c_4_cnf;
  assign c_4_cnf = 1'b1;
  wire w_c_4;
  assign w_c_4 = c_4_dnf & c_4_cnf;
  wire y_syn_4;
  assign y_syn_4 = w_a_4 | (g_4 & ~w_c_4);

  wire valid_orig;
  formula_f check_orig (
    .valid(valid_orig),
    .v_2(x_2),
    .v_3(x_3),
    .v_1(y_orig_1),
    .v_4(y_orig_4)
  );
  wire valid_syn;
  formula_f check_syn (
    .valid(valid_syn),
    .v_2(x_2),
    .v_3(x_3),
    .v_1(y_syn_1),
    .v_4(y_syn_4)
  );

  assign out = valid_orig & ~valid_syn;
endmodule

module formula_f(
  valid,
  v_1,
  v_2,
  v_3,
  v_4
);
  output valid;
  input v_1;
  input v_2;
  input v_3;
  input v_4;
  wire cl_0;
  assign cl_0 = ~v_1 | v_2;
  wire cl_1;
  assign cl_1 = ~v_1 | v_3;
  wire cl_2;
  assign cl_2 = v_1 | v_2 | v_3;
  wire cl_3;
  assign cl_3 = v_4;
  assign valid = cl_0 & cl_1 & cl_2 & cl_3;
endmodule
