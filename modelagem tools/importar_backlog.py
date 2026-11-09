#!/usr/bin/env python3
"""
Importa o backlog do AlertAção para o GitHub: cria labels, marcos (sprints) e issues.
Opcionalmente adiciona cada issue ao quadro (GitHub Projects).

Pré-requisitos:
  1. GitHub CLI instalado (https://cli.github.com) e login feito:  gh auth login
  2. Para adicionar ao quadro:  gh auth refresh -s project

Uso (primeiro simule, depois rode de verdade):
  python importar_backlog.py --repo SEU-USUARIO/alertacao --dry-run
  python importar_backlog.py --repo SEU-USUARIO/alertacao
  python importar_backlog.py --repo SEU-USUARIO/alertacao --project 1 --owner SEU-USUARIO

É seguro rodar de novo: itens cujo título já existe no repositório são pulados.
"""
import argparse, csv, json, subprocess, sys, time

MILESTONES = {
    "Sprint 1 (07-13/11)": "2026-11-13T23:59:00Z",
    "Sprint 2 (14-20/11)": "2026-11-20T23:59:00Z",
    "Sprint 3 (21-25/11)": "2026-11-25T23:59:00Z",
    "Pós-MVP": None,
}

LABEL_COLORS = {
    "prio:must": "B60205", "prio:should": "FBCA04", "prio:could": "0E8A16",
    "tipo:implementacao": "1D76DB", "tipo:infra": "5319E7", "tipo:teste": "C2E0C6",
    "tipo:requisito": "D93F0B", "tipo:modelagem": "0052CC", "tipo:arquitetura": "006B75",
    "tipo:documentacao": "BFD4F2",
}
DEFAULT_COLOR = "EDEDED"


def run(cmd, dry, capture=True):
    if dry:
        print("  [simulação]", " ".join(repr(c) if " " in c else c for c in cmd))
        return ""
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Falhou: {' '.join(cmd)}\n{r.stderr.strip()}")
    return (r.stdout or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="DONO/REPOSITORIO")
    ap.add_argument("--csv", default="backlog_alertacao.csv")
    ap.add_argument("--project", type=int, help="número do projeto (GitHub Projects)")
    ap.add_argument("--owner", help="dono do projeto (usuário ou organização)")
    ap.add_argument("--dry-run", action="store_true", help="só mostra o que faria")
    a = ap.parse_args()
    if a.project and not a.owner:
        sys.exit("Use --owner junto com --project.")

    with open(a.csv, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"{len(rows)} itens lidos de {a.csv}")

    # 1) marcos (sprints)
    existing_ms = set()
    if not a.dry_run:
        out = run(["gh", "api", f"repos/{a.repo}/milestones?state=all&per_page=100", "--jq", ".[].title"], False)
        existing_ms = set(out.splitlines())
    for title, due in MILESTONES.items():
        if title in existing_ms:
            continue
        cmd = ["gh", "api", f"repos/{a.repo}/milestones", "-f", f"title={title}"]
        if due:
            cmd += ["-f", f"due_on={due}"]
        print("Marco:", title)
        run(cmd, a.dry_run)

    # 2) labels
    labels = set()
    for r in rows:
        labels |= {f"prio:{r['prioridade']}", f"tipo:{r['tipo']}", f"etapa:{r['etapa']}", f"pts:{r['pontos']}"}
    for name in sorted(labels):
        color = LABEL_COLORS.get(name, DEFAULT_COLOR)
        run(["gh", "label", "create", name, "--repo", a.repo, "--color", color, "--force"], a.dry_run)
    print(f"{len(labels)} labels garantidas")

    # 3) issues
    existing = set()
    if not a.dry_run:
        out = run(["gh", "issue", "list", "--repo", a.repo, "--state", "all", "--limit", "1000",
                   "--json", "title", "--jq", ".[].title"], False)
        existing = set(out.splitlines())
    created = skipped = 0
    for r in rows:
        title = r["titulo"].strip()
        if title in existing:
            skipped += 1
            print("Já existe, pulando:", title)
            continue
        cmd = ["gh", "issue", "create", "--repo", a.repo, "--title", title, "--body", r["descricao"],
               "--milestone", r["sprint"]]
        for lb in (f"prio:{r['prioridade']}", f"tipo:{r['tipo']}", f"etapa:{r['etapa']}", f"pts:{r['pontos']}"):
            cmd += ["--label", lb]
        print("Issue:", title)
        url = run(cmd, a.dry_run).splitlines()[-1] if not a.dry_run else "<url>"
        created += 1
        if a.project:
            run(["gh", "project", "item-add", str(a.project), "--owner", a.owner, "--url", url], a.dry_run)
        if not a.dry_run:
            time.sleep(1.2)  # evita limite de criação em sequência
    print(f"Concluído: {created} criadas, {skipped} puladas.")


if __name__ == "__main__":
    main()
