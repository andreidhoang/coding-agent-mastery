FROM python@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app
WORKDIR /app

# Generate a hash-checked exact-version requirements set from the existing lock.
# Base + production closure only; no compute/GPU dependencies or resolver update.
# Conditional dependencies are included as a locked superset. Ambiguous version
# branches fail closed rather than silently choosing a version for this image.
COPY uv.lock /build/uv.lock
RUN python - <<'PY'
import pathlib
import tomllib

lock = tomllib.loads(pathlib.Path('/build/uv.lock').read_text())
packages = {}
for package in lock['package']:
    packages.setdefault(package['name'], []).append(package)
project = packages['coding-agent-mastery'][0]
queue = list(project.get('dependencies', []))
queue += project.get('optional-dependencies', {}).get('production', [])
selected = {}
seen = set()
while queue:
    requirement = queue.pop()
    name = requirement['name']
    extra = tuple(sorted(requirement.get('extra', [])))
    if (name, extra) in seen:
        continue
    seen.add((name, extra))
    candidates = packages.get(name, [])
    if len(candidates) != 1:
        raise RuntimeError(f'lock has an unsupported version branch for {name}')
    package = candidates[0]
    if package.get('source', {}).get('registry') != 'https://pypi.org/simple':
        raise RuntimeError(f'unsupported locked dependency source for {name}')
    selected[name] = package
    queue += package.get('dependencies', [])
    for group in extra:
        queue += package.get('optional-dependencies', {}).get(group, [])
lines = []
for name, package in sorted(selected.items()):
    hashes = {wheel['hash'] for wheel in package.get('wheels', [])}
    if not hashes or any(not value.startswith('sha256:') for value in hashes):
        raise RuntimeError(f'no supported wheel hashes for {name}')
    lines.append(f"{name}=={package['version']} " + ' '.join('--hash=' + value for value in sorted(hashes)))
pathlib.Path('/build/requirements.txt').write_text('\n'.join(lines) + '\n')
PY
RUN python -m pip install --no-cache-dir --no-deps --require-hashes --only-binary=:all: -r /build/requirements.txt

# Explicit source selection excludes runtime evidence, secret files and host envs.
COPY service/ /app/service/
COPY workloads/ /app/workloads/
COPY evals/ /app/evals/
COPY compute/ /app/compute/
USER 65532:65532

# This factory has no store/principals configured: protected routes return 503.
# No port is published, no credentials baked in, and no worker is auto-started.
CMD ["python", "-m", "uvicorn", "service.api:create_app", "--factory", "--host", "127.0.0.1", "--port", "8000"]
