# Bundled semgrep rules

## Why these are bundled locally

`semgrep --config auto` (and `--config p/...`, `--config r/...`) fetch rules
from semgrep.dev's registry at request time. That domain is not reachable
from sandboxed Claude environments with a restricted network allowlist
(confirmed 2026-07-09: `HTTP 403` from `semgrep.dev/c/auto`). Rather than
have `SemgrepAnalyzer` silently fail whenever network access isn't
available - the same class of bug this suite has already hit twice this
session with CBMC and bandit (see CHANGELOG.md v2.6.0) - a curated rule
subset is bundled directly in the skill package, downloaded from GitHub
(`github.com`/`codeload.github.com`, both allowlisted) instead of
semgrep.dev's registry service.

## Source

- Repository: https://github.com/semgrep/semgrep-rules
- Branch: `develop`
- Downloaded: 2026-07-09, via `codeload.github.com` tarball
  (`https://github.com/semgrep/semgrep-rules/archive/refs/heads/develop.tar.gz`)
- Subset bundled: a **curated 20-rule selection** from `python/lang/security/**/*.yaml`
  (108KB), flattened into `python_security/` (no subdirectories - `--config`
  accepts a directory and recurses, but the flattened layout is simpler for
  the `SemgrepAnalyzer` module to reason about a single fixed path)
- **Why curated, not the full 91-rule directory:** tested first with all 91
  rules - semgrep's own rule-compilation overhead scales with rule count
  (measured ~2.7s for 1 rule, ~17s for 91 rules, roughly linear), which
  blew well past the ~5-10s timeout budget every other Phase 0 tool
  (mypy/pylint/bandit) uses. Trimmed to 20 rules covering distinct,
  high-value threat categories with minimal overlap with what bandit
  already checks: command injection (`dangerous-subprocess-use`,
  `subprocess-shell-true`, `dangerous-os-exec`, `dangerous-system-call`),
  unsafe eval/exec (`eval-detected`, `exec-detected`), unsafe
  deserialization (`pickle`, `avoid-pyyaml-load`, `marshal`), SQL injection
  (`formatted-sql-query`), XXE (`use-defused-xml`), weak crypto
  (`insecure-hash-algorithms-md5`, `weak-ssl-version`), TLS/cert issues
  (`disabled-cert-validation`, `insecure-urlopen`,
  `paramiko-implicit-trust-host-key`), ReDoS (`regex-dos`), reverse shells
  (`python-reverse-shell`), and credential handling
  (`hardcoded-password-default-argument`, `logger-credential-leak`).
  Verified: ~6-7s per scan with this subset (vs. ~17s for all 91), real
  detections confirmed across 4 of these categories against genuinely
  vulnerable code (pickle.loads, hashlib.md5, eval(), catastrophic-backtracking
  regex), zero false positives on clean code.
- No commit hash recorded (downloaded as a tarball snapshot, not a git
  clone) - if rule accuracy ever needs to be pinned/audited, re-download
  from the URL above and diff.

## License

`LICENSE` in this directory is the Semgrep Rules License v1.0
(https://semgrep.dev/legal/rules-license), copied verbatim from the
upstream repository at download time. This governs the `.yaml` rule files
in this directory, not the rest of the debug-suite skill (which is
independently MIT-licensed - see the top-level `LICENSE` file).

## Updating

To refresh or expand this subset (e.g. add `javascript/lang/security/`):

```bash
curl -sL -o semgrep-rules.tar.gz \
  https://github.com/semgrep/semgrep-rules/archive/refs/heads/develop.tar.gz
tar -xzf semgrep-rules.tar.gz
find semgrep-rules-develop/python/lang/security -name "*.yaml" \
  -exec cp {} src/common/semgrep_rules/python_security/ \;
```

## Scope note

Only Python security rules are bundled and wired in as of v2.6.0 (into
`Phase0StaticAnalysis`, alongside mypy/pylint/bandit). semgrep itself is
genuinely multi-language; `javascript/lang/security/` (30 rule files) and
others are available from the same upstream repo if `SemgrepAnalyzer` is
ever extended to cover `javascript_debug` or other language modules - not
done this session, see roadmap.md §11.7/§11.10 for scope notes.
