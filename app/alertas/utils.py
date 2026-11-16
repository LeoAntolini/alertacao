def formatar_duracao(delta):
    """Texto curto para uma duração: '2 dias e 3 horas', '5 horas e 10 minutos', '20 minutos'."""
    total = int(delta.total_seconds())
    if total <= 0:
        return "agora"
    dias, resto = divmod(total, 86400)
    horas, resto = divmod(resto, 3600)
    minutos = resto // 60
    partes = []
    if dias:
        partes.append(f"{dias} dia{'s' if dias != 1 else ''}")
    if horas:
        partes.append(f"{horas} hora{'s' if horas != 1 else ''}")
    if minutos and not dias:
        partes.append(f"{minutos} minuto{'s' if minutos != 1 else ''}")
    if not partes:
        return "menos de 1 minuto"
    return " e ".join(partes[:2])
