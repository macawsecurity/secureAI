-- Tutorial 3 setup (same tables as Tutorial 2). Paste into the Databricks SQL editor and run all.
-- Uses the `workspace` catalog; change it if yours is named differently.
-- Running it again resets the tables to this data.

CREATE SCHEMA IF NOT EXISTS workspace.xyz_fincorp;

CREATE OR REPLACE TABLE workspace.xyz_fincorp.employees (
  id          INT,
  name        STRING,
  department  STRING,
  base_salary INT,
  bonus       INT
);

INSERT INTO workspace.xyz_fincorp.employees VALUES
  (1, 'Asha Rao',    'Finance',     95000,  4000),
  (2, 'Daniel Kim',  'Engineering', 120000, 6000),
  (3, 'Maria Lopez', 'Sales',       80000,  3000),
  (4, 'Tom Becker',  'Operations',  70000,  2000);

CREATE OR REPLACE TABLE workspace.xyz_fincorp.hr_salaries (
  id     INT,
  name   STRING,
  salary INT
);

INSERT INTO workspace.xyz_fincorp.hr_salaries VALUES
  (1, 'Asha Rao',    95000),
  (2, 'Daniel Kim',  120000),
  (3, 'Maria Lopez', 80000),
  (4, 'Tom Becker',  70000);
