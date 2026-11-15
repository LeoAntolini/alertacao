#!/usr/bin/env python3
"""
Importa ou atualiza o backlog do AlertAção no GitHub: cria labels, marcos (sprints) e issues,
e opcionalmente adiciona as issues novas ao quadro (GitHub Projects).

Pré-requisitos:
  1. GitHub CLI instalado (https://cli.github.com) e login feito:  gh auth login
  2. Para adicionar ao quadro:  gh auth refresh -s project

Uso (primeiro simule, depois rode de verdade):
  python importar_backlog.py --repo SEU-USUARIO/alertacao --dry-run
  python importar_backlog.py --repo SEU-USUARIO/alertacao --atualizar
  python importar_backlog.py --repo SEU-USUARIO/alertacao --atualizar --project 1 --owner SEU-USUARIO

Como funciona:
  - Cada linha do CSV é casada com uma issue existente pelo texto do título, sem o prefixo entre
    colchetes (assim, [RF03] Reportar ponto de risco e [RF02] Reportar ponto de risco são a mesma
    issue). A coluna titulo_anterior ajuda quando o texto do título mudou.
  - Sem --atualizar, issues que já existem são puladas. Com --atualizar, título, texto, marco e labels
    são atualizados; o estado (aberta ou fechada) e a coluna do quadro NÃO são alterados.
  - Issues que não existem são criadas e, com --project, adicionadas ao quadro.
É seguro rodar de novo.
"""
import argparse, csv, json, subprocess, sys, time, unicodedata

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
PREFIXOS_GERENCIADOS = ("prio:", "tipo:", "etapa:", "pts:")


def chave(titulo):
    """Texto do título sem o prefixo [..], sem acentos e em minúsculas."""
    t = titulo.strip()
    if t.startswith("[") and "]" in t:
        t = t.split("]", 1)[1]
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(t.split())


def run(cmd, dry, mutating=True):
    if dry and mutating:
        print("  [simulação]", " ".join(repr(c) if " " in c else c for c in cmd))
        return ""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Falhou: {' '.join(cmd)}\n{r.stderr.strip()}")
    return (r.stdout or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="DONO/REPOSITORIO")
    ap.add_argument("--csv", default="backlog_alertacao.csv")
    ap.add_argument("--project", type=int, help="número do projeto (GitHub Projects)")
    ap.add_argument("--owner", help="dono do projeto (usuário ou organização)")
    ap.add_argument("--atualizar", action="store_true", help="atualiza issues que já existem")
    ap.add_argument("--dry-run", action="store_true", help="só mostra o que faria")
    a = ap.parse_args()
    if a.project and not a.owner:
        sys.exit("Use --owner junto com --project.")

    with open(a.csv, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    chaves = [chave(r["titulo"]) for r in rows]
    repetidas = {c for c in chaves if chaves.count(c) > 1}
    if repetidas:
        sys.exit(f"Títulos repetidos no CSV (mesmo texto): {sorted(repetidas)}")
    print(f"{len(rows)} itens lidos de {a.csv}")

    # 1) marcos (sprints)
    out = run(["gh", "api", f"repos/{a.repo}/milestones?state=all&per_page=100", "--jq", ".[].title"], a.dry_run, mutating=False) if not a.dry_run else ""
    existentes_ms = set(out.splitlines())
    for title, due in MILESTONES.items():
        if title in existentes_ms:
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
        run(["gh", "label", "create", name, "--repo", a.repo, "--color", LABEL_COLORS.get(name, DEFAULT_COLOR), "--force"], a.dry_run)
    print(f"{len(labels)} labels garantidas")

    # 3) issues existentes
    existentes = {}
    if not a.dry_run:
        saida = run(["gh", "issue", "list", "--repo", a.repo, "--state", "all", "--limit", "1000",
                     "--json", "number,title,labels"], False, mutating=False)
        for it in json.loads(saida or "[]"):
            existentes[chave(it["title"])] = it
    criadas = atualizadas = puladas = 0
    for r in rows:
        titulo = r["titulo"].strip()
        novos = [f"prio:{r['prioridade']}", f"tipo:{r['tipo']}", f"etapa:{r['etapa']}", f"pts:{r['pontos']}"]
        atual = existentes.get(chave(titulo)) or (existentes.get(chave(r.get("titulo_anterior", ""))) if r.get("titulo_anterior") else None)
        if atual:
            if not a.atualizar:
                puladas += 1
                print("Já existe, pulando:", titulo)
                continue
            antigos = [l["name"] for l in atual.get("labels", [])]
            remover = [l for l in antigos if l.startswith(PREFIXOS_GERENCIADOS) and l not in novos]
            cmd = ["gh", "issue", "edit", str(atual["number"]), "--repo", a.repo, "--title", titulo,
                   "--body", r["descricao"], "--milestone", r["sprint"]]
            for lb in novos:
                cmd += ["--add-label", lb]
            for lb in remover:
                cmd += ["--remove-label", lb]
            print(f"Atualizando #{atual['number']}:", titulo)
            run(cmd, a.dry_run)
            atualizadas += 1
        else:
            cmd = ["gh", "issue", "create", "--repo", a.repo, "--title", titulo, "--body", r["descricao"],
                   "--milestone", r["sprint"]]
            for lb in novos:
                cmd += ["--label", lb]
            print("Criando:", titulo)
            url = run(cmd, a.dry_run).splitlines()[-1] if not a.dry_run else "<url>"
            criadas += 1
            if a.project:
                run(["gh", "project", "item-add", str(a.project), "--owner", a.owner, "--url", url], a.dry_run)
        if not a.dry_run:
            time.sleep(1.2)  # evita limite de requisições em sequência
    print(f"Concluído: {criadas} criadas, {atualizadas} atualizadas, {puladas} puladas.")


if __name__ == "__main__":
    main()
