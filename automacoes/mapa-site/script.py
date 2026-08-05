import os
import sys
import time
import requests
from requests.auth import HTTPBasicAuth

REQUEST_TIMEOUT = 90
MAX_TENTATIVAS = 3
PAUSA_ENTRE_PAGINAS_S = 0.5


class Cancelado(Exception):
	"""Fila interrompida pelo usuario (centro-automacoes)."""


def pedido_cancelado():
	return False


def _abortar_se_cancelado():
	if pedido_cancelado():
		print("  [AVISO] Fila cancelada pelo usuario.")
		raise Cancelado()


# Headers de navegador — sites com Mod_Security (ex.: jacinto.mg.gov.br)
# bloqueiam o User-Agent padrão do requests com HTTP 406.
HEADERS = {
	"User-Agent": (
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
		"AppleWebKit/537.36 (KHTML, like Gecko) "
		"Chrome/120.0.0.0 Safari/537.36"
	),
	"Accept": "application/json, text/plain, */*",
	"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

# =============================================================
#  CONFIGURAÇÕES
# =============================================================

WP_URL = os.environ.get("WP_URL", "").strip()
USER = os.environ.get("WP_USER", "").strip()
APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "").strip()

SLUG_MAPA_DO_SITE = "mapa-do-site"                          	#Slug do Mapa do Site Geralmente vai ser esse que está como padrão
																#Exemplo: https://conceicaodoaraguaia.pa.gov.br/mapa-do-site/


# =============================================================
#  PÁGINAS ORGANIZADAS COMO NO MAPA ( Deve ser atualizada)
# =============================================================

PAGINAS = {
	"Informações Institucionais": [
		("Estrutura Organizacional", "https://www.portalcr2.com.br/estrutura-organizacional/estrutura-maracana"),
		("Agenda Externa", "https://www.portalcr2.com.br/agenda-externa/agenda-maracana"),
		("Perguntas Frequentes", "https://www.portalcr2.com.br/perguntas-frequentes/perguntas-maracana"),
		("Leis e Atos Normativos", "https://www.portalcr2.com.br/leis-e-atos/leis-maracana"),
		("Conselhos Municipais", "https://www.portalcr2.com.br/conselho-municipal/conselhomunicipal-maracana"),
	],

	"Receitas e Despesas": [
		("Receitas", "https://www.portalcr2.com.br/receitas/receitas-maracana"),
		("Renúncia de Receitas", "https://www.portalcr2.com.br/renuncias/renuncias-receita-maracana"),
		("Dívida Ativa", "https://www.portalcr2.com.br/divida-ativa/divida-maracana"),
		("Programas e Ações", "https://www.portalcr2.com.br/programas/programas-maracana"),
		("Despesas", "https://www.portalcr2.com.br/despesas/despesas-maracana"),
		("Gastos com Cartão de Crédito", "https://www.portalcr2.com.br/gastos-cartao-de-credito/cartao-de-credito-maracana"),
		("Notas Fiscais Liquidadas", "https://www.portalcr2.com.br/notas-fiscais/notas-fiscais-maracana"),
		("Emendas Parlamentares", "https://www.portalcr2.com.br/emendas-parlamentares/emendas-maracana"),
		("Ordem Cronológica de Pagamentos", "https://www.portalcr2.com.br/pagamentos/pagamentos-maracana"),
	],

	"Recursos Humanos": [
		("Relação Nominal de Remuneração", "https://www.portalcr2.com.br/relacao-remuneracao/relacao-nominal-remuneracao-maracana"),
		("Relação de Cargos e Remuneração", "https://www.portalcr2.com.br/relacao-cargos-remuneracao/cargos-remuneracao-maracana"),
		("Relação de Estagiários", "https://www.portalcr2.com.br/relacao-estagiarios/estagiarios-maracana"),
		("Relação de Prestadores de Serviços Terceirizados", "https://www.portalcr2.com.br/relacao_prestadores/servicos-terceirizados-maracana"),
		("Concursos e Processos Seletivos", "https://www.portalcr2.com.br/concurso-processo-seletivo/concursos-e-pss-maracana"),
		("Diárias", "https://www.portalcr2.com.br/diarias/diarias-maracana"),
		("Tabela com os Valores das Diárias", "https://www.portalcr2.com.br/valores_diarias/valores-diarias-maracana"),
	],

	"Licitações, Contratos, Convênios, Transferências Voluntárias e Obras": [
		("Licitações", "https://www.portalcr2.com.br/licitacoes/licitacoes-maracana"),
		("Aviso de Licitação", "https://www.portalcr2.com.br/aviso-licitacao/aviso-licitacao-maracana"),
		("Contratos", "https://www.portalcr2.com.br/contratos/contratos-maracana"),
		("Plano Anual de Contratações", "https://www.portalcr2.com.br/plano-de-contratacoes/contratacoes-anuais-maracana"),
		("Licitantes / Contratos Sancionados Administrativamente", "https://www.portalcr2.com.br/contratados-sancionados/contratados-sancionados-administrativamente-maracana"),
		("Cadastro de Fornecedores", "https://www.portalcr2.com.br/cadastro-fornecedores/fornecedores-maracana"),
		("Convênios / Transferências Voluntárias", "https://www.portalcr2.com.br/convenio-tranf-voluntaria/transferencias-voluntarias-maracana"),
		("Obras", "https://www.portalcr2.com.br/obras/obras-maracana"),
		("Obras Paralisadas", "https://www.portalcr2.com.br/obras-paralisadas/obras-paralisadas-maracana"),
	],

	"Patrimônio": [
		("Bens Móveis", "https://www.portalcr2.com.br/bens-moveis/bens-moveis-maracana"),
		("Bens Imóveis", "https://www.portalcr2.com.br/bens-imoveis/bens-imoveis-maracana"),
		("Veículos", "https://www.portalcr2.com.br/veiculos/veiculos-maracana"),
	],

	"Saúde": [
		("Planejamento e Relatórios da Saúde", "https://www.portalcr2.com.br/saude-planejamento/saude-planejamento-relatorio-maracana"),
		("Serviços de Saúde", "https://www.portalcr2.com.br/servicos-de-saude/servicos-maracana"),
		("Lista de Medicamentos e Estoques das Farmácias", "https://www.portalcr2.com.br/lista-de-medicamentos-e-estoques-das-farmacias/lista-de-medicamentos-e-estoques-das-farmacias-maracana"),
		("Como Obter Medicamentos", "https://www.portalcr2.com.br/como-obter-medicamentos/como-obter-medicamentos-maracana"),
		("Fila de Espera por Serviços de Saúde", "https://www.portalcr2.com.br/fila-de-espera-por-servicos-de-saude/fila-maracana"),
	],

	"Educação": [
		("Planejamento e Relatórios da Educação", "https://www.portalcr2.com.br/educacao-planejamento/educacao-planejamento-relatorio-maracana"),
		("Lista de Espera em Creches e Escolas", "https://www.portalcr2.com.br/educacao-lista-espera/lista-espera-creche-escola-maracana"),
	],

	"Planejamento e Prestação de Contas": [
		("Balancete Financeiro", "https://www.portalcr2.com.br/balancete-financeiro/balancete-maracana"),
		("Balanço e Relatórios Anuais", "https://www.portalcr2.com.br/balanco-relatorio-anual/relatorios-anuais-maracana"),
		("LDO, LOA e PPA", "https://www.portalcr2.com.br/ldo-loa-ppa/ldo-loa-ppa-maracana"),
		("Parecer do Tribunal de Contas", "https://www.portalcr2.com.br/parecer-tribunal-contas/tribunal-de-contas-maracana"),
		("Julgamento das Contas do Executivo pelo Legislativo", "https://www.portalcr2.com.br/julgamento-de-contas/julgamento-executivo-legislativo-maracana"),
		("Relatório de Gestão Fiscal - RGF", "https://www.portalcr2.com.br/relatorio-gestao-fiscal/rgf-maracana"),
		("Relatório Resumido de Execução Orçamentária - RREO", "https://www.portalcr2.com.br/relatorio-resumido-rreo/rreo-maracana"),
		("Planejamento Estratégico", "https://www.portalcr2.com.br/planejamento-estrategico/planejamento-maracana"),
	],

	"Ouvidoria / Serviço de Informação ao Cidadão": [
		("Ouvidoria", "https://www.portalcr2.com.br/ouvidoria/ouvidoria-maracana"),
		("Serviço de Informação ao Cidadão", "https://www.portalcr2.com.br/sic/sic-maracana"),
		("Consultar Manifestações", "https://www.portalcr2.com.br/consultar-manifestacao/consultar-manifestacao-maracana"),
		("Manifestações Realizadas", "https://www.portalcr2.com.br/manifestacoes-realizadas/manifestacoes-realizadas-maracana"),
		("Relatórios Estatísticos", "https://www.portalcr2.com.br/relatorios-estatisticos/relatorios-estatisticos-maracana"),
		("Regulamentação", "https://www.portalcr2.com.br/regulamentacao/regulamentacao-maracana"),
		("Documentos e Informações Sigilosas", "https://www.portalcr2.com.br/documentos-sigilosos/docs-informacoes-sigilosas-maracana"),
	],

	"LGPD e Governo Digital": [
		("LGPD e Governo Digital", "https://www.portalcr2.com.br/lgpd/lgpd-maracana"),
		("Dados Abertos", "https://www.portalcr2.com.br/dados-abertos/dados-abertos-maracana"),
		("Serviço Online", "https://www.portalcr2.com.br/servico-online/servico-online-maracana"),
		("Carta de Serviços ao Usuário", "https://www.portalcr2.com.br/carta-servico/carta-de-servico-maracana"),
		("Pesquisas de Satisfação", "https://www.portalcr2.com.br/pesquisa-de-satisfacao/pesquisa-satisfacao-maracana"),
	],
}

# =============================================================
#  FUNÇÕES
# =============================================================

def _auth():
	return HTTPBasicAuth(USER, APP_PASSWORD)


def _request(metodo, url, **kwargs):
	"""GET/POST com timeout e retry — evita travar se o WordPress demorar."""
	kwargs.setdefault("auth", _auth())
	kwargs.setdefault("timeout", REQUEST_TIMEOUT)
	headers = dict(HEADERS)
	headers.update(kwargs.pop("headers", None) or {})
	kwargs["headers"] = headers

	for tentativa in range(1, MAX_TENTATIVAS + 1):
		try:
			return requests.request(metodo, url, **kwargs)
		except requests.Timeout:
			print(
				"  [TIMEOUT {}/{} — servidor demorou >{}s]".format(
					tentativa, MAX_TENTATIVAS, REQUEST_TIMEOUT
				),
				flush=True,
			)
		except requests.RequestException as erro:
			print("  [ERRO rede: {}]".format(erro), flush=True)

		if tentativa < MAX_TENTATIVAS:
			time.sleep(2 * tentativa)

	return None


def calcular_total_paginas():
	total = 0

	for categoria, itens in PAGINAS.items():
		total += len(itens)

	return total


def testar_conexao():
	print("Testando conexão com a REST API...")

	url = f"{WP_URL}/wp-json/wp/v2/users/me"

	response = _request("GET", url)

	if response is None:
		print("  [ERRO] Sem resposta do servidor (timeout/rede).")
		return False

	if response.status_code == 200:
		dados = response.json()
		print("  Conectado como: " + dados.get("name", USER))
		return True

	print("  [ERRO] Não foi possível conectar.")
	print("  Status:", response.status_code)
	print("  Resposta:", response.text)
	return False


def buscar_pagina_mapa():
	print("")
	print("Buscando página do mapa pelo slug...")

	url = f"{WP_URL}/wp-json/wp/v2/pages?slug={SLUG_MAPA_DO_SITE}"

	response = _request("GET", url)

	if response is None:
		print("  [ERRO] Sem resposta ao buscar mapa (timeout/rede).")
		return None

	if response.status_code != 200:
		print("  [ERRO] Erro ao buscar página do mapa.")
		print("  Status:", response.status_code)
		print("  Resposta:", response.text)
		return None

	paginas = response.json()

	if not paginas:
		print("  [ERRO] Página do mapa não encontrada pelo slug:", SLUG_MAPA_DO_SITE)
		return None

	id_mapa = paginas[0]["id"]
	print("  Página do mapa encontrada. ID:", id_mapa)
	return id_mapa


def criar_pagina(titulo, url_cr2, id_pai, idx, total):
	print("[" + str(idx).zfill(2) + "/" + str(total) + "] " + titulo[:50] + " ...", end=" ", flush=True)

	conteudo = (
		"<ul>\n"
		"	<li><a href=\"" + url_cr2 + "\" target=\"_blank\" rel=\"noopener noreferrer\">Clique aqui para acessar</a></li>\n"
		"</ul>"
	)

	dados = {
		"title": titulo,
		"content": conteudo,
		"status": "publish",
		"parent": id_pai
	}

	url = f"{WP_URL}/wp-json/wp/v2/pages"

	response = _request("POST", url, json=dados)

	if response is None:
		print("[ERRO] Timeout/rede — pagina nao criada.")
		return None

	if response.status_code == 201:
		pagina = response.json()
		print("OK (ID: " + str(pagina["id"]) + ")")
		return pagina["link"]

	print("[ERRO]")
	print("  Status:", response.status_code)
	print("  Resposta:", response.text)
	return None


def montar_html_mapa(paginas_criadas):
	novo_html = ""

	for categoria, itens in PAGINAS.items():
		novo_html += "<h2>" + categoria + "</h2>\n"
		novo_html += "<ul>\n"

		for titulo, url_cr2 in itens:
			link_pagina_wp = paginas_criadas.get(titulo, "#")

			novo_html += (
				"	<li><a href=\"" + link_pagina_wp + "\" target=\"_blank\" rel=\"noopener\">"
				+ titulo +
				"</a></li>\n"
			)

		novo_html += "</ul>\n"

	return novo_html


def atualizar_mapa_do_site(id_mapa, conteudo):
	print("")
	print("Atualizando mapa-do-site...")

	url = f"{WP_URL}/wp-json/wp/v2/pages/{id_mapa}"

	dados = {
		"content": conteudo
	}

	response = _request("POST", url, json=dados)

	if response is None:
		print("  [ERRO] Timeout/rede ao atualizar mapa.")
		return False

	if response.status_code == 200:
		print("  Mapa do site atualizado com sucesso!")
		return True

	print("  [ERRO] Erro ao atualizar mapa.")
	print("  Status:", response.status_code)
	print("  Resposta:", response.text)
	return False


def main():
	total = calcular_total_paginas()

	print("=" * 65)
	print("  CRIADOR DE PÁGINAS - WORDPRESS REST API")
	print("  Total de páginas: " + str(total))
	print("=" * 65)
	print("")

	if not testar_conexao():
		print("")
		print("Verifique usuário e senha de aplicativo.")
		print("Se o status for 406, o firewall (Mod_Security) pode estar bloqueando.")
		raise RuntimeError("Falha na conexão com a REST API do WordPress.")

	id_mapa = buscar_pagina_mapa()

	if not id_mapa:
		print("")
		print("Não foi possível continuar porque a página do mapa não foi encontrada.")
		raise RuntimeError("Página do mapa não encontrada (slug: {0}).".format(SLUG_MAPA_DO_SITE))
	print("")
	print("Criando páginas...")
	print("-" * 65)

	ok = 0
	erros = 0
	contador = 1
	paginas_criadas = {}
	cancelado = False

	try:
		for categoria, itens in PAGINAS.items():
			for titulo, url_cr2 in itens:
				_abortar_se_cancelado()
				link_pagina = criar_pagina(titulo, url_cr2, id_mapa, contador, total)

				if link_pagina:
					ok += 1
					paginas_criadas[titulo] = link_pagina
				else:
					erros += 1

				contador += 1
				time.sleep(PAUSA_ENTRE_PAGINAS_S)
				sys.stdout.flush()
	except Cancelado:
		cancelado = True

	if not cancelado:
		conteudo_mapa = montar_html_mapa(paginas_criadas)
		atualizar_mapa_do_site(id_mapa, conteudo_mapa)

	print("")
	print("=" * 65)
	print("  " + ("CANCELADO!" if cancelado else "CONCLUIDO!"))
	print("  Criadas: " + str(ok) + " | Erros: " + str(erros) + " | Total: " + str(total))
	print("=" * 65)
	print("")
	if cancelado:
		raise Cancelado()
	if erros:
		raise RuntimeError("Mapa finalizado com {0} erro(s) de criacao.".format(erros))


if __name__ == "__main__":
	main()