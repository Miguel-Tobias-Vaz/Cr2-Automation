# Deploy VPS — proteção de dados de produção
#
# NUNCA copie / sincronize estes caminhos de /root → /opt:
#   - centro-automacoes/data/     (usuários, jobs, PDFs, auth)
#   - **/venv/                   (ambiente Python)
#   - centro-automacoes/deploy/opto.env
#   - caches, __pycache__, *.log
#
# Use sempre:
#   bash /opt/opto-automacoes/centro-automacoes/deploy/atualizar-vps.sh
#   (ou a cópia em /root/.../deploy/atualizar-vps.sh apontando para o clone)
#
# Exclusões canônicas: rsync-exclude.txt
#
# Se data/ de teste ainda estiver no Git:
#   git rm -r --cached centro-automacoes/data/users
#   (mantém users.example.json)
