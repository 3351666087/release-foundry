INSERT INTO organizations (id, slug, display_name)
VALUES (
  '11111111-1111-4111-8111-111111111111',
  'releasefoundry-local-auth',
  'ReleaseFoundry Local Auth'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO workspaces (id, organization_id, slug, display_name)
VALUES (
  '22222222-2222-4222-8222-222222222222',
  '11111111-1111-4111-8111-111111111111',
  'local-workspace',
  'Local Workspace'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO projects (id, organization_id, workspace_id, slug, display_name)
VALUES (
  '33333333-3333-4333-8333-333333333333',
  '11111111-1111-4111-8111-111111111111',
  '22222222-2222-4222-8222-222222222222',
  'local-project',
  'Local Project'
)
ON CONFLICT (id) DO NOTHING;
