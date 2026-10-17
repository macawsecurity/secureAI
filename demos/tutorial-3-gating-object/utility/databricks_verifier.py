"""
databricks_verifier.py -- value-level pre-verifier for Databricks SQL writes.

AST-parses (sqlglot) every column<-value write from UPDATE / MERGE / INSERT into
invocation params. Column-agnostic: the MAPL policy decides which columns/thresholds
matter, e.g.
    comp_change_approved::{ params.bonus_resolution == 'resolved' AND params.bonus > 10000 }
    unclear_value::{ params.bonus_resolution == 'unresolved' }
So gating a new column is a policy edit, never a code change.

  extract_assignments(sql) -> {column: (resolution, value)}    # AST parse
  DatabricksSQLVerifier                                        # thin SDK glue

resolution is "resolved" (integer literal) or "unresolved" (expression / subquery /
variable / non-integer). The verifier writes <col>_resolution ALWAYS, and the value
param ONLY when resolved (never a sentinel) -- so params.<col> exists iff it is a
real, known integer. Unresolved fails closed via the policy's unclear_value gate.

A column written more than once (multi-row VALUES, two MERGE branches) keeps the
largest value, or "unresolved" if any of its values is. A write whose columns cannot
be named (INSERT with no column list, INSERT *, UPDATE SET *) is denied with a message.

Tutorial 3 adds a second verifier on both SQL tools:

  read_tables(sql) -> (stmt_type, ["catalog/schema/table", ...])
  DatabricksTableVerifier   stamps params.table and params.stmt_type

The app policy attests "databricks:{params.table}", so MACAW loads the object policy of
every table the query names, or databricks:base when a table has none.
"""
from typing import Dict, List, Optional, Tuple

import sqlglot
from sqlglot import expressions as exp


class UnreadableWrite(ValueError):
    """A write the verifier cannot map to columns. The message goes back to the caller."""


def extract_assignments(sql: str) -> Dict[str, Tuple[str, Optional[int]]]:
    """AST-extract every column<-value write from UPDATE / MERGE / INSERT.
    Unparseable SQL raises -> the verifier turns that into a fail-closed deny."""
    out: Dict[str, Tuple[str, Optional[int]]] = {}

    def record(col: str, rhs) -> None:
        col = col.lower()
        if isinstance(rhs, exp.Literal) and rhs.is_int:
            new = ("resolved", int(rhs.name))
        else:
            new = ("unresolved", None)             # expr / var / subquery / non-int / no value
        if col in out:                             # written again: keep the worst case
            # ponytail: "worst" = largest; a policy that gates on a minimum would need the smallest too
            (r1, v1), (r2, v2) = out[col], new
            new = ("unresolved", None) if "unresolved" in (r1, r2) else ("resolved", max(v1, v2))
        out[col] = new

    for stmt in sqlglot.parse(sql):                # handles ; batches
        if stmt is None:
            continue
        # UPDATE ... SET col = val -- find_all ALSO reaches the UPDATE nested inside a
        # MERGE (WHEN MATCHED THEN UPDATE), which a top-level isinstance() check misses.
        for upd in stmt.find_all(exp.Update):
            for eq in upd.args.get("expressions", []):
                if not isinstance(eq, exp.EQ):     # MERGE ... UPDATE SET *
                    raise UnreadableWrite("UPDATE SET * copies every column from the source, "
                                          "so the values cannot be read. Name the columns.")
                record(eq.this.name, eq.expression)
        # INSERT INTO t (c1, c2) VALUES (...), (...)  /  INSERT INTO t (c1, c2) SELECT ...
        # MERGE ... WHEN NOT MATCHED THEN INSERT (c1, c2) VALUES (...)  (columns and row are Tuples)
        for ins in stmt.find_all(exp.Insert):
            target, source = ins.this, ins.expression
            if not isinstance(target, (exp.Schema, exp.Tuple)):   # no column list, or INSERT *
                raise UnreadableWrite("INSERT without a column list, the verifier cannot tell "
                                      "which value goes into which column. List the columns.")
            cols = [c.name for c in target.expressions]
            if isinstance(source, exp.Values):
                rows = [row.expressions for row in source.expressions]  # every row, not just the last
            elif isinstance(source, exp.Tuple):
                rows = [source.expressions]        # the MERGE INSERT row
            else:
                rows = [[None] * len(cols)]        # INSERT ... SELECT: values come from a query
            for row in rows:
                for col, rhs in zip(cols, row):
                    record(col, rhs)
    return out


class UnreadableQuery(ValueError):
    """A query the table verifier cannot read. The message goes back to the caller."""


_ROOT_MAP = (                                      # statement type from the parsed root node
    (exp.Select, "select"), (exp.Union, "select"), (exp.Update, "update"),
    (exp.Insert, "insert"), (exp.Delete, "delete"), (exp.Merge, "merge"),
    (exp.Create, "create"), (exp.Drop, "drop"), (exp.TruncateTable, "truncate"),
)


def read_tables(sql: str) -> Tuple[str, List[str]]:
    """Return (stmt_type, tables) for exactly one statement. Each table is
    "catalog/schema/table" in lower case (policy ids cannot hold dots). A query that
    names no table gets ["unknown"], so it still resolves to a policy (databricks:base)."""
    if not sql or not sql.strip():
        raise UnreadableQuery("empty query")
    stmts = [s for s in sqlglot.parse(sql, read="databricks") if s is not None]
    if len(stmts) != 1:
        raise UnreadableQuery(f"send one statement per call, got {len(stmts)}")
    root = stmts[0]
    if isinstance(root, exp.Command):              # SHOW, SET, EXECUTE IMMEDIATE, ...
        raise UnreadableQuery("the verifier cannot read which tables this statement uses")
    stmt_type = next((name for cls, name in _ROOT_MAP if isinstance(root, cls)), "other")
    ctes = {c.alias_or_name.lower() for c in root.find_all(exp.CTE)}
    tables: List[str] = []
    for t in root.find_all(exp.Table):             # FROM, JOIN, subquery, UPDATE/INSERT/MERGE target
        if not t.name or (not t.db and t.name.lower() in ctes):   # WITH x AS (...) is not a table
            continue
        tid = "/".join(p for p in (t.catalog, t.db, t.name) if p).lower()
        if tid not in tables:
            tables.append(tid)
    return stmt_type, tables or ["unknown"]


# --- SDK glue (lazy import so extract_assignments stays import-safe without the SDK) --
try:
    try:
        from macaw.security.verification.verifier import Verifier
        from macaw.security.verification.result import VerificationResult
    except ImportError:  # wheel >=0.9.10 namespaces these under macaw_client
        from macaw_client.macaw.security.verification.verifier import Verifier
        from macaw_client.macaw.security.verification.result import VerificationResult

    class DatabricksSQLVerifier(Verifier):
        """Writes each extracted assignment to params so policy conditions can read it.
        - <col>_resolution: always set ("resolved" | "unresolved") -- authoritative signal.
        - <col>: real int ONLY when resolved; popped otherwise (no sentinel, no stale or
          forgeable value left behind).
        Fail-closed: unparseable SQL or a write it cannot map to columns -> success=False (deny)."""

        def __init__(self):
            super().__init__(name="databricks_sql_verifier")
            self.scope.resource_patterns = ["*databricks*execute_sql"]  # write tool only
            self.scope.compile_patterns()

        def verify(self, invocation, context):
            sql = (invocation.params or {}).get("query", "")
            try:
                assignments = extract_assignments(sql)
            except UnreadableWrite as e:
                return VerificationResult(False, f"Denied: {e}")
            except Exception as e:
                return VerificationResult(False, f"Unparseable SQL, denied (fail-closed): {e}")
            for col, (res, val) in assignments.items():
                invocation.params[f"{col}_resolution"] = res
                if res == "resolved":
                    invocation.params[col] = val            # real int, only when known
                else:
                    invocation.params.pop(col, None)        # never leave a stale/forgeable value
            read = ", ".join(f"{c}={v if r == 'resolved' else 'unresolved'}"
                             for c, (r, v) in assignments.items())
            return VerificationResult(True, f"Read: {read}" if read else "No column writes")

    class DatabricksTableVerifier(Verifier):
        """Stamps params.table (the object policy reference) and params.stmt_type.
        Always overwrites both, so a caller cannot pick the policy. Fail-closed: a query
        it cannot read -> success=False (deny) with the reason."""

        def __init__(self):
            super().__init__(name="databricks_table_verifier")
            self.scope.resource_patterns = ["*databricks*execute_sql*"]  # both SQL tools
            self.scope.compile_patterns()

        def verify(self, invocation, context):
            sql = (invocation.params or {}).get("query", "")
            try:
                stmt_type, tables = read_tables(sql)
            except UnreadableQuery as e:
                return VerificationResult(False, f"Denied: {e}")
            except Exception as e:
                return VerificationResult(False, f"Unparseable SQL, denied (fail-closed): {e}")
            invocation.params["stmt_type"] = stmt_type
            # one table: a plain string (the routing shape already proven live); several: a list,
            # which MACAW expands to one policy reference per table
            invocation.params["table"] = tables[0] if len(tables) == 1 else tables
            return VerificationResult(True, f"Tables: {', '.join(tables)}; statement: {stmt_type}")
except ImportError:
    pass  # extractor remains importable/usable without the SDK present
