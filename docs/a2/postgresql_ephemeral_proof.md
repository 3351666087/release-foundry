# A2 ephemeral PostgreSQL persistence proof

This recipe produces a real PostgreSQL persistence proof without placing a
database credential in source control or public evidence.

1. The operator creates a temporary PostgreSQL database and supplies its DSN
   out of band. Use a dedicated role and database with the minimum permissions
   needed for the test.
2. Review the command without reading or printing a DSN:

   ```powershell
   python scripts/a2_postgresql_proof_launcher.py --dry-run
   ```

3. Put the temporary DSN only in the current process and execute the proof:

   ```powershell
   $env:POSTGRES_DSN = '<operator-supplied-ephemeral-dsn>'
   python scripts/a2_postgresql_proof_launcher.py
   ```

   The launcher passes the DSN to the child test process. It must not serialize
   the DSN into evidence or print it.

4. Record only public-safe facts: test selection, pass/fail counts, provider
   class (`postgresql`), execution time, and hashes required by the evidence
   schema.
5. After the proof, remove the process variable and revoke or destroy the
   temporary role/database:

   ```powershell
   Remove-Item Env:POSTGRES_DSN
   ```

An offline SQLite or deterministic substitute is useful for regression
coverage, but it is **not** a real PostgreSQL persistence proof and must not be
reported as one.
