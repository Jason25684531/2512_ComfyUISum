# Environment Boundary Guide

`deployment_matrix.yaml` is the repository's deployment contract. Validate it before deployment:

```bash
python scripts/validate_deployment_matrix.py
```

The validator checks canonical compose entries, environment contracts, required services and proxy settings. It also rejects the retired hard-coded cloud IP literals in repository source files.

Use `docker-compose.yml` with `.env.local` for local development and `docker-compose.base.yml` with `.env.twcc` for the TWCC Base VM.
