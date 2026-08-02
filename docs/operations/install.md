# Install

## Preconditions

- Use a supported Linux host or Windows with Docker Desktop and Compose v2.
- Verify the GitHub Release asset SHA-256 values before extraction.
- Keep the environment file outside source control and restrict its filesystem permissions.
- Confirm the Product Release verification decision. A `block_product_release` RC is for evaluation only.

## Procedure

1. Extract the Product Release ZIP, then extract the nested `artifacts/releasefoundry-product-<version>-runtime.zip` into an empty runtime directory.
2. Copy the included `infra/docker/self-host.env.example` to a private location.
3. Replace placeholders with environment-specific secrets or secret-manager references.
4. Validate without starting services:

   ```bash
   RELEASEFOUNDRY_ENV_FILE=/secure/releasefoundry.env ./infra/install/install.sh --check
   ```

   ```powershell
   .\infra\install\install.ps1 -Mode Check -EnvFile C:\secure\releasefoundry.env
   ```

5. Start the stack with `--up` or `-Mode Up`.
6. Confirm database migration completion, API health, worker heartbeat, object-store access, tenant isolation, and audit writes before routing traffic.

Never convert a failed health check into a manual pass. Preserve the command output as a release receipt.
