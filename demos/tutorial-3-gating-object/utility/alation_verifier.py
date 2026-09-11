"""
alation_verifier.py -- content guard for the Alation MCP SQL tools.

MAPL matches parameter values; it cannot read SQL. So this verifier parses the SQL with
sqlglot before the policy decision and stamps flat params the policy gates on:

    stmt_type        -- select / update / insert / ... / other / nl_only / denied  (AST root)
    touches_salary   -- true / false  (identifier contains "salary")
    touches_eng_comp -- true / false  (references a SENSITIVE_TABLES table)

Principles: classify by the ROOT node, not keywords (INSERT ... SELECT writes); allow-list, so
anything unrecognized is "other" and denied; fail closed -- empty, multi-statement, or
unparseable SQL becomes "denied".
"""
from typing import Tuple  # noqa: F401  (kept for callers importing type hints)

import sqlglot
from sqlglot import expressions as exp
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers

DIALECT = "databricks"              # MUST match the executor's dialect
SENSITIVE_TOKENS = ("salary",)      # substring match on identifiers; add "bonus","ssn" to extend


SENSITIVE_TABLES = ("eng_comp",)

#
SQL_PARAM_NAMES = ("sql", "query")

_ROOT_MAP = (
    (exp.Select, "select"),
    (exp.Union, "select"),          # a set operation over SELECTs is still a read
    (exp.Update, "update"),
    (exp.Insert, "insert"),
    (exp.Delete, "delete"),
    (exp.Merge, "merge"),
    (exp.Create, "create"),
    (exp.Drop, "drop"),
    (exp.TruncateTable, "truncate"),
)

# Worst-wins ranking when a call carries more than one SQL param.
_SEVERITY = {
    "select": 10, "update": 20, "insert": 50, "delete": 60, "merge": 60,
    "create": 60, "drop": 70, "truncate": 70, "other": 80, "nl_only": 90, "denied": 99,
}


def classify_sql(sql: str) -> Tuple[str, bool, bool]:
    """Return (stmt_type, touches_salary, touches_sensitive_table) for exactly ONE statement.

    Raises for every input that must FAIL CLOSED: empty, multi-statement, `exp.Command`
    (dynamic / unsupported syntax), or unparseable (sqlglot.ParseError propagates).
    """
    if not sql or not sql.strip():
        raise ValueError("empty sql")
    stmts = sqlglot.parse(sql, read=DIALECT)
    if len(stmts) != 1 or stmts[0] is None:
        raise ValueError(f"expected exactly 1 statement, got {len(stmts)}")
    root = stmts[0]
    if isinstance(root, exp.Command):   # EXECUTE IMMEDIATE, ALTER ..., SET ...
        raise ValueError("dynamic or unsupported statement (parsed as Command)")
    root = normalize_identifiers(root, dialect=DIALECT)

    stmt_type = "other"
    for cls, name in _ROOT_MAP:
        if isinstance(root, cls):
            stmt_type = name
            break

    toks = tuple(t.lower() for t in SENSITIVE_TOKENS)
    touches = any(any(k in i.name.lower() for k in toks) for i in root.find_all(exp.Identifier))

    # .name is the table segment only -- catalog/schema are .catalog/.db -- so a guarded table is
    # caught however the caller qualifies it. Covers the UPDATE/DELETE target and every FROM/JOIN.
    guarded = tuple(t.lower() for t in SENSITIVE_TABLES)
    touches_table = any(t.name.lower() in guarded for t in root.find_all(exp.Table))
    return stmt_type, touches, touches_table


# --- SDK glue (lazy import so classify_sql stays importable/testable without the SDK) --------
# NOTE: `macaw` is a submodule injected by the macaw_client .so, so it imports only AFTER
# macaw_client has been imported (the gateway imports macaw_adapters/macaw_client first).
try:
    from macaw.security.verification.verifier import Verifier
    from macaw.security.verification.result import VerificationResult

    class AlationSQLGuardVerifier(Verifier):
        """Stamps params.stmt_type so the MAPL policy can gate A/B/C.

        Always returns success=True -- the DENY decision belongs to the policy. Fail-closed
        inputs are stamped stmt_type="denied", which is outside the policy's allowed_values
        and therefore hard-denied.
        """

        def __init__(self):
            super().__init__(name="alation_sql_guard_verifier")

            # NOTE:  add tools from your alation agent studio that expose a sql parameter these are for example. DO NOT USE!
            self.scope.resource_patterns = [
                # "*run_query_sql_custom",
                # "*run_analytics_agent_macaw",
                # "*run_data_product_query_macaw_ii"
                "*sql_execution_tool",          # not currently published; kept for legacy/return
            ]
            self.scope.compile_patterns()

        def verify(self, invocation, context):
            params = invocation.params            # mutate the REAL params, never a copy
            if params is None:
                return VerificationResult(True, "no params to gate")

            sqls = [str(params[p]) for p in SQL_PARAM_NAMES
                    if params.get(p) and str(params[p]).strip()]
            if not sqls:
                # Scoped SQL tool called with NO SQL: the agent would write the SQL server-side
                # where this verifier can never see it -- allowing that is a free bypass
                # ("in English: delete the rows"). Not in the policy allow-list.
                params["stmt_type"] = "nl_only"
                params["touches_salary"] = "true"        # unknown -> conservative
                params["touches_eng_comp"] = "true"      # unknown -> conservative
                return VerificationResult(True, "no SQL param -> nl_only (fail-closed)")

            results = []
            for s in sqls:
                try:
                    results.append(classify_sql(s))
                except Exception:  # noqa: BLE001 -- ParseError, ValueError, anything
                    results.append(("denied", True, True))    # fail closed

            # Worst classification wins, so a benign `sql` can't mask a destructive `query`.
            stmt_type = max((r[0] for r in results), key=lambda t: _SEVERITY.get(t, 99))
            touches = any(r[1] for r in results)
            touches_table = any(r[2] for r in results)
            params["stmt_type"] = stmt_type
            params["touches_salary"] = "true" if touches else "false"
            params["touches_eng_comp"] = "true" if touches_table else "false"
            return VerificationResult(
                True, f"{stmt_type}/salary={touches}/eng_comp={touches_table}")
except ImportError:
    pass   # classify_sql remains usable without macaw_client loaded
