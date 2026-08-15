# ADR 5: Artifact Repository

**Status:** Accepted (2026-07-26)

**Update (2026-08-12):** Repositories are declared under `[repositories]` in
`.yak/context.toml` (`sources` for the default read set, plus named entries
like `[repositories.acme]`). A repository is both a read source (`add
--from <repo>`) and a deploy target (`deploy --to <repo>`); `deploy` is the
write side of the same model.

## Context

Artifacts need to be shareable between developers. The local `~/.yak/artifacts/`
works within a team that shares a filesystem, but not across the internet.

## Decision

1. **Yakoon does not host a registry.** Registries are existing infrastructure
   (GitHub Releases, S3, HTTP servers). Yakoon implements clients, not servers.

2. **ArtifactSource is renamed to `Repository`.** A Repository answers one
   question: "Do you know artifact X?" The concept is user-facing, like Git
   remotes.

3. **`_collect_roots` becomes a list of Repository instances.** Not file paths.

4. **GitHub Releases is the first remote Repository.**

5. **Cache is content-addressed by fingerprint.** `~/.yak/cache/github/<repo>/<fingerprint>/`

6. **Repositories can be declared in environment.yml** for persistent configuration.

## Consequences

### Benefits

- `install` and `sync` remain unchanged — they iterate Repositories
- Adding S3, HTTP, or a private registry is another Repository implementation
- GitHub Releases require no server-side infrastructure
- Repositories are composable — multiple sources can be combined:
  ```yaml
  repositories:
    - local
    - github:yakoon-runtime/packs
    - github:company/internal-packs
  ```
- Cache by fingerprint reduces network requests to one per version
- No operational costs — hosting is provided by the repository platform
- Works with existing infrastructure (GitHub organisations, permissions, CDN)

### Trade-offs

- Availability depends on the selected repository provider. Yakoon distributes
  artifacts — it does not operate an ecosystem.
- Repository discovery (search, metadata) is delegated to the hosting platform.
- Private repositories require authentication managed by the provider.
- Authentication tokens are passed via environment variables (`YAK_GITHUB_TOKEN`),
  never stored in configuration files.
