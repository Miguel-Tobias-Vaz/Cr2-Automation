from backend.runners import (
    categorias,
    contratos,
    dic_est_ter,
    documentos,
    licitacoes,
    mapa,
    normas,
    pub_repasses,
    publicacao,
    repasses,
    sessao,
    tcm_licitacoes,
)
from backend.runners.isolated import run_isolated, uses_subprocess

RUNNERS = {
    "documentos": documentos.run,
    "categorias": categorias.run,
    "normas": normas.run,
    "licitacoes": licitacoes.run,
    "tcm_licitacoes": tcm_licitacoes.run,
    "contratos": contratos.run,
    "publicacao": publicacao.run,
    "sessao": sessao.run,
    "mapa": mapa.run,
    "repasses": repasses.run,
    "pub_repasses": pub_repasses.run,
    "dic_est_ter": dic_est_ter.run,
}


def dispatch(job) -> None:
    if uses_subprocess(job.service_id):
        run_isolated(job)
        return
    fn = RUNNERS.get(job.service_id)
    if not fn:
        raise ValueError("Serviço desconhecido: {0}".format(job.service_id))
    fn(job)
