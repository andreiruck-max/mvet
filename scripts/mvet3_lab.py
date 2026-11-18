"""Explicit, portable laboratory commands; never uses the default Compose file."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import uuid

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env.mvet3"
COMPOSE = ["docker", "compose", "--project-name", "mvet3", "--env-file", str(ENV),
           "--file", str(ROOT / "compose.mvet3.yml")]


def run(*args, **kwargs):
    # Ignore host Compose overrides and production environment interpolation.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("COMPOSE_", "MVET3_"))}
    return subprocess.run(COMPOSE + list(args), cwd=ROOT, env=env, check=True, **kwargs)


def sql(query):
    return run("exec", "-T", "lab-db", "psql", "-X", "-v", "ON_ERROR_STOP=1",
               "-U", "mvet3_lab", "-d", "mvet3_lab", "-Atc", query,
               capture_output=True, text=True).stdout.strip()


def validate_config():
    cfg = json.loads(run("config", "--format", "json", capture_output=True, text=True).stdout)
    if cfg["name"] != "mvet3":
        raise RuntimeError("Projeto incorreto")
    if set(cfg["services"]) != {"lab-web", "lab-db"}:
        raise RuntimeError("Serviços incorretos")
    if cfg["networks"]["lab"]["internal"] is not True:
        raise RuntimeError("Rede permite saída externa")
    if cfg["volumes"]["lab_pgdata"]["name"] != "mvet3_lab_pgdata":
        raise RuntimeError("Volume incorreto")
    print("Projeto mvet3; volume mvet3_lab_pgdata; rede interna; HTTP 127.0.0.1:8001")


def audit():
    validate_config()
    run("ps")
    identity = sql("SELECT current_database() || '/' || current_user")
    if identity != "mvet3_lab/mvet3_lab":
        raise RuntimeError("Identidade inesperada do banco; operação interrompida")
    print("Banco/usuário: " + identity)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "build", "start-db", "audit", "migrate",
                                           "setup", "up", "stop", "check", "restore-test"])
    action = parser.parse_args().action
    if action == "init":
        with ENV.open("x", encoding="utf-8") as f:
            f.write("MVET3_SECRET_KEY=" + secrets.token_urlsafe(48) + "\n")
            f.write("MVET3_DB_PASSWORD=" + secrets.token_urlsafe(32) + "\n")
        ENV.chmod(0o600)
        print("Configuração de laboratório criada; nenhuma credencial de produção usada.")
        return
    validate_config()
    if action == "build":
        run("build", "lab-web")
    elif action == "start-db":
        run("up", "-d", "--wait", "lab-db")
    elif action == "stop":
        run("stop")
    else:
        audit()
        if action in ("migrate", "setup", "check"):
            command = {"migrate": ["migrate", "--noinput"], "setup": ["setup_mvet"],
                       "check": ["check"]}[action]
            run("run", "--rm", "--no-deps", "lab-web", "python", "manage.py", *command)
        elif action == "up":
            run("up", "-d", "lab-web")
        elif action == "restore-test":
            # Synthetic laboratory source only; never reads a production dump.
            target = "mvet3_restore_" + uuid.uuid4().hex
            prefix = ("exec", "-T", "lab-db")
            run(*prefix, "createdb", "-U", "mvet3_lab", target)
            try:
                dump = run(*prefix, "pg_dump", "-U", "mvet3_lab", "-d", "mvet3_lab",
                           "-Fc", capture_output=True).stdout
                run(*prefix, "pg_restore", "--exit-on-error", "--no-owner", "--no-privileges",
                    "-U", "mvet3_lab", "-d", target, input=dump)
                query = "SELECT count(*) FROM core_company; SELECT count(*) FROM django_migrations;"
                restored = run(*prefix, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "mvet3_lab",
                               "-d", target, "-Atc", query, capture_output=True, text=True).stdout.strip()
                if restored != sql(query):
                    raise RuntimeError("Contagens restauradas divergem da origem sintética")
                print("Restauração sintética validada: empresa e histórico de migrations.")
            finally:
                run(*prefix, "dropdb", "-U", "mvet3_lab", target)


if __name__ == "__main__":
    main()
