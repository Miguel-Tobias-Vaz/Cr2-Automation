from backend.runners import categorias, documentos, mapa, publicacao

RUNNERS = {
    "documentos": documentos.run,
    "categorias": categorias.run,
    "publicacao": publicacao.run,
    "mapa": mapa.run,
}


def dispatch(job) -> None:
    fn = RUNNERS.get(job.service_id)
    if not fn:
        raise ValueError("Serviço desconhecido: {0}".format(job.service_id))
    fn(job)
