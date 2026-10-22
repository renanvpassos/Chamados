import streamlit as st
from supabase import create_client, Client
import uuid
from datetime import datetime, timezone, timedelta
import smtplib
import ssl
import html
from email.message import EmailMessage
from streamlit_quill import st_quill
import re
import base64
import os

# --- ESTADO DE AUTENTICAÇÃO (Necessário antes do set_page_config) ---
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

if "status_filter" not in st.session_state:
    st.session_state.status_filter = "Todos"

if "crit_filter" not in st.session_state:
    st.session_state.crit_filter = "Todos"

# --- CONFIGURAÇÃO PÁGINA (Dinâmica: wide para admin, centered para usuário) ---
st.set_page_config(
    page_title="Suporte & Chamados",
    page_icon="🎫",
    layout="wide" if st.session_state.admin_logged_in else "centered"
)

st.markdown(
    """
    <style>
    /* ===== VARIÁVEIS DE ESPAÇAMENTO (ajuste aqui) ===== */
    :root {
        --espaco-fechado: -8px;   /* distância entre chamados FECHADOS (mais negativo = mais colado) */
        --espaco-aberto: 24px;    /* espaço abaixo de um chamado ABERTO (nunca sobrepõe o próximo) */
        --espaco-fim-expander: 20px; /* respiro no fim do conteúdo de QUALQUER expander (inclusive o de atualização) */
    }

    /* Reduz tamanho dos botões de filtro e fontes para caber na tela */
    div.stHorizontalBlock { gap: 4px !important; }
    div.stHorizontalBlock > div { flex: 0 1 auto !important; width: auto !important; }
    div.stButton > button {
        width: auto !important;
        white-space: nowrap !important;
        padding-left: 8px !important;
        padding-right: 8px !important;
        padding-top: 4px !important;
        padding-bottom: 4px !important;
        font-size: 0.8rem !important;
        min-height: unset !important;
    }

    /* Reduzir o tamanho da fonte dos títulos dos filtros */
    .filter-label {
        font-size: 0.85rem !important;
        font-weight: 600;
        margin-bottom: 2px;
    }

    /* ===== CARD DO CHAMADO: FECHADO ===== */
    [class*="st-key-chamado_"] {
        margin-bottom: var(--espaco-fechado) !important;
    }

    /* ===== CARD DO CHAMADO: ABERTO (só o expander principal, não os internos) ===== */
    [class*="st-key-chamado_"]:has(> div > [data-testid="stExpander"] > details[open]) {
        margin-bottom: var(--espaco-aberto) !important;
    }

    /* Respiro no fim de TODO expander aberto (principal e o de "Atualizar ou Excluir") */
    [data-testid="stExpander"] details[open] > div[data-testid="stExpanderDetails"],
    [data-testid="stExpander"] details[open] > div:last-child {
        padding-bottom: var(--espaco-fim-expander) !important;
    }

    /* ===== CORES POR STATUS (apenas o expander principal) ===== */
    [class*="st-key-chamado_aberto_"] > div > [data-testid="stExpander"] {
        background-color: #fffde7 !important;
        border: 1px solid #ffeb3b !important;
    }
    [class*="st-key-chamado_dev_"] > div > [data-testid="stExpander"] {
        background-color: #e3f2fd !important;
        border: 1px solid #2196f3 !important;
    }
    [class*="st-key-chamado_andamento_"] > div > [data-testid="stExpander"] {
        background-color: #ffCfff !important;
        border: 1px solid #ffCfff !important;
    }
    [class*="st-key-chamado_finalizado_"] > div > [data-testid="stExpander"] {
        background-color: #e8f5e9 !important;
        border: 1px solid #4caf50 !important;
    }

    /* ===== BORDAS ARREDONDADAS NOS CARDS COLORIDOS ===== */
    [class*="st-key-chamado_"] > div > [data-testid="stExpander"] {
        border-radius: 0.5rem !important;
        overflow: hidden !important;
    }
    [class*="st-key-chamado_"] > div > [data-testid="stExpander"] > details {
        border-radius: 0.5rem !important;
        border: none !important;
        background: transparent !important;
    }
    [class*="st-key-chamado_"] > div > [data-testid="stExpander"] > details > summary {
        border-radius: 0.5rem !important;
        display: flex !important;
        justify-content: space-between !important;
        align-items: center !important;
    }

    [class*="st-key-chamado_"] > div > [data-testid="stExpander"] > details > summary > p {
        width: 100% !important;
        margin-bottom: 0 !important;
    }

    /* ===== URGENTE / CRÍTICO: FUNDO VERMELHO (sobrescreve a cor do status, exceto Finalizado) ===== */
    [class*="st-key-chamado_"]:not([class*="st-key-chamado_finalizado_"])[class*="_urg_"] > div > [data-testid="stExpander"] {
        background-color: #ef9a9a !important;
        border: 1px solid #ef9a9a !important;
    }
    [class*="st-key-chamado_"]:not([class*="st-key-chamado_finalizado_"])[class*="_crit_"] > div > [data-testid="stExpander"] {
        background-color: #ff8585 !important;
        border: 2px solid #ff8585 !important;
    }

    /* ===== ÍCONES DE CRITICIDADE (canto direito do chamado) ===== */
    [class*="st-key-chamado_"] > div > [data-testid="stExpander"] > details > summary {
        position: relative;
        padding-right: 6rem !important;
    }
    [class*="st-key-chamado_"][class*="_crit_"] > div > [data-testid="stExpander"] > details > summary::after {
        content: "💣";
        position: absolute;
        right: 3.5rem;
        top: 50%;
        transform: translateY(-50%);
        font-size: 1.2rem;
    }
    [class*="st-key-chamado_"][class*="_urg_"] > div > [data-testid="stExpander"] > details > summary::after {
        content: "❗";
        position: absolute;
        right: 3.5rem;
        top: 50%;
        transform: translateY(-50%);
        font-size: 1.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- CONEXÃO SUPABASE ---
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

def registrar_log(acao, detalhes):
    """Salva o log diretamente no Supabase para persistir mesmo após atualizar a página"""
    try:
        fuso_br = timezone(timedelta(hours=-3))
        agora_iso = datetime.now(fuso_br).isoformat()
        
        supabase.table("logs_sistema").insert({
            "acao": acao,
            "detalhes": detalhes,
            "created_at": agora_iso
        }).execute()
    except Exception as e:
        print(f"Erro ao registrar log no Supabase: {e}")

# --- ENVIO DE E-MAIL ---
def enviar_email_novo_chamado(dados):
    try:
        destinatarios = st.secrets.get("EMAIL_DESTINATARIOS", [])
        if isinstance(destinatarios, str):
            destinatarios = [e.strip() for e in destinatarios.split(",") if e.strip()]
        destinatarios = list(destinatarios)

        if not destinatarios:
            return False, "Nenhum destinatário configurado em EMAIL_DESTINATARIOS."

        host = st.secrets["SMTP_HOST"]
        porta = int(st.secrets.get("SMTP_PORT", 587))
        usuario = st.secrets["SMTP_USER"]
        senha = st.secrets["SMTP_PASSWORD"]
        remetente = st.secrets.get("EMAIL_REMETENTE", usuario)

        e = lambda campo: html.escape(str(dados.get(campo, "")))
        titulo_limpo = str(dados.get("titulo", "")).replace("\r", " ").replace("\n", " ")
        qtd_anexos = len(dados.get("imagens", []))

        msg = EmailMessage()
        msg["Subject"] = f"🎫 Novo chamado: {titulo_limpo}"
        msg["From"] = remetente
        msg["To"] = ", ".join(destinatarios)
        msg["Reply-To"] = str(dados.get("email", "")).replace("\r", "").replace("\n", "")

        msg.set_content(
            f"Novo chamado aberto\n\n"
            f"Título: {dados.get('titulo')}\n"
            f"Solicitante: {dados.get('nome')} ({dados.get('email')})\n"
            f"Importador: {dados.get('importador')}\n"
            f"Responsável: {dados.get('responsavel')}\n"
            f"Anexos: {qtd_anexos}\n\n"
            f"Resumo:\n{dados.get('resumo')}\n"
        )
        msg.add_alternative(
            f"""
            <h3>🎫 Novo chamado aberto</h3>
            <p><b>Título:</b> {e('titulo')}<br>
            <b>Solicitante:</b> {e('nome')} ({e('email')})<br>
            <b>Importador:</b> {e('importador')}<br>
            <b>Responsável:</b> {e('responsavel')}<br>
            <b>Anexos:</b> {qtd_anexos}</p>
            <p><b>Resumo:</b></p>
            <blockquote style="border-left:4px solid #2196f3; padding-left:10px; margin-left:0;">
                {e('resumo').replace(chr(10), '<br>')}
            </blockquote>
            """,
            subtype="html",
        )

        contexto = ssl.create_default_context()
        if porta == 465:
            with smtplib.SMTP_SSL(host, porta, context=contexto, timeout=15) as server:
                server.login(usuario, senha)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, porta, timeout=15) as server:
                server.starttls(context=contexto)
                server.login(usuario, senha)
                server.send_message(msg)

        return True, None
    except Exception as ex:
        return False, str(ex)

# --- CRITICIDADE ---
OPCOES_CRITICIDADE = ["Normal", "Urgente", "Crítico"]
ORDEM_CRITICIDADE = {"Crítico": 0, "Urgente": 1}

def rank_criticidade(chamado):
    return ORDEM_CRITICIDADE.get(chamado.get("criticidade"), 2)

def tag_criticidade(criticidade):
    return {"Crítico": "crit", "Urgente": "urg"}.get(criticidade, "sem")

def badge_criticidade(criticidade):
    if criticidade == "Crítico":
        return '<span style="background-color: #ff8585; color: #000000; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em;">💣 Crítico</span>'
    if criticidade == "Urgente":
        return '<span style="background-color: #ef9a9a; color: #000000; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em;">❗ Urgente</span>'
    return '<span style="background-color: #9e9e9e; color: #000000; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em;">Normal</span>'

def badge_status(status):
    cores = {
        "Em Aberto": {"bg": "#ffc042", "color": "#000000"},
        "Enviado ao Desenvolvimento": {"bg": "#2196f3", "color": "#ffffff"},
        "Em Andamento": {"bg": "#e427f5", "color": "#ffffff"},
        "Finalizado": {"bg": "#4caf50", "color": "#ffffff"}
    }
    config = cores.get(status, {"bg": "#9e9e9e", "color": "#ffffff"})
    return f'<span style="background-color: {config["bg"]}; color: {config["color"]}; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em;">{status}</span>'

def obter_classe_expander(status):
    mapa = {
        "Em Aberto": "aberto",
        "Enviado ao Desenvolvimento": "dev",
        "Em Andamento": "andamento",
        "Finalizado": "finalizado",
    }
    return mapa.get(status, "outro")

def calcular_tempo_ultima_atualizacao(chamado):
    fuso_br = timezone(timedelta(hours=-3))
    agora = datetime.now(fuso_br)
    
    historico = chamado.get("historico", [])
    data_ref_str = None
    if historico and isinstance(historico, list):
        ultimo_evento = historico[-1]
        data_ref_str = ultimo_evento.get('data_registro') or ultimo_evento.get('data_evento') or ultimo_evento.get('data')
    
    if not data_ref_str:
        data_ref_str = chamado.get("created_at")
        
    if not data_ref_str:
        return "N/A"

    try:
        if data_ref_str.endswith("Z"):
            dt_ref = datetime.fromisoformat(data_ref_str.replace("Z", "+00:00"))
        else:
            dt_ref = datetime.fromisoformat(data_ref_str)
        
        dt_ref_local = dt_ref.astimezone(fuso_br)
        diferenca = agora - dt_ref_local
        
        total_segundos = int(diferenca.total_seconds())
        if total_segundos < 0:
            total_segundos = 0
            
        dias = total_segundos // 86400
        horas = (total_segundos % 86400) // 3600
        minutos = (total_segundos % 3600) // 60
        
        partes = []
        if dias > 0:
            partes.append(f"{dias}d")
        if horas > 0 or dias > 0:
            partes.append(f"{horas}h")
        partes.append(f"{minutos}m")
        
        return " ".join(partes)
    except Exception:
        return "N/A"

def upload_files(files):
    anexos_info = []
    bucket_name = "chamados-anexos"
    
    for file in files:
        nome_original = file.name
        ext = nome_original.split(".")[-1] if "." in nome_original else "bin"
        file_path = f"anexos/{uuid.uuid4()}.{ext}"
        file_bytes = file.getvalue()
        
        supabase.storage.from_(bucket_name).upload(
            file_path,
            file_bytes,
            file_options={"content-type": file.type if hasattr(file, 'type') else "application/octet-stream"}
        )
        
        public_url_res = supabase.storage.from_(bucket_name).get_public_url(file_path)
        
        if isinstance(public_url_res, dict):
            public_url = public_url_res.get("publicUrl") or public_url_res.get("public_url") or public_url_res.get("signedURL", "")
        else:
            public_url = str(public_url_res)
            
        anexos_info.append({
            "name": nome_original,
            "url": public_url
        })
        
    return anexos_info

def formatar_data_br(data_str):
    if not data_str:
        return "N/A"
    try:
        if data_str.endswith("Z"):
            dt = datetime.fromisoformat(data_str.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(data_str)
        fuso_br = timezone(timedelta(hours=-3))
        dt_local = dt.astimezone(fuso_br)
        return dt_local.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return data_str

def renderizar_anexos(lista_anexos):
    if not lista_anexos:
        return
    
    EXTENSOES_IMAGEM = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'}
    
    for item in lista_anexos:
        if isinstance(item, dict):
            url = item.get("url") or item.get("publicUrl") or item.get("public_url") or item.get("signedURL", "")
            nome = item.get("name", "Arquivo Anexado")
        else:
            url = str(item)
            nome = url.split("/")[-1].split("?")[0] if "/" in url else "Arquivo Anexado"

        extensao = nome.split(".")[-1].lower() if "." in nome else ""

        if url and url.startswith("http"):
            if extensao in EXTENSOES_IMAGEM:
                st.image(url, caption=f"📎 {nome}", width=300)
            else:
                st.markdown(f"📄 [{nome}]({url})", unsafe_allow_html=False)

# --- MENU LATERAL (SE ADMIN LOGADO) ---
pagina_selecionada = "Painel de Administrador"

if st.session_state.admin_logged_in:
    st.sidebar.title("🔧 Menu Admin")
    pagina_selecionada = st.sidebar.radio(
        "Navegação:",
        ["Painel de Administrador", "Log do Sistema"]
    )
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Sair do Admin", use_container_width=True):
        st.session_state.admin_logged_in = False
        st.rerun()

# --- INTERFACE PRINCIPAL ---
st.title("Suporte de Chamados")

if not st.session_state.admin_logged_in:
    st.subheader("Abrir Novo Chamado")
    st.caption("Preencha as informações abaixo para relatar seu problema.")

    with st.form(key="form_chamado", clear_on_submit=True):
        nome = st.text_input("Seu Nome*", placeholder="Ex: Maria Silva")
        email = st.text_input("Seu E-mail*", placeholder="Ex: maria@multprocessing.com.br")
        titulo = st.text_input("Título do Chamado*", placeholder="Ex: Ajustar tag nota fiscal")
        importador = st.text_input("Importador*", placeholder="Ex: Nome do importador")
        
        st.markdown("**Resumo do Problema*:**")
        resumo = st_quill(
            placeholder="Descreva o problema detalhadamente...",
            key="quill_resumo_chamado"
        )
        
        arquivos_descricao = st.file_uploader(
            "Adicionar arquivos/anexos à descrição (Opcional)", 
            accept_multiple_files=True,
            key="imagens_desc_form"
        )
    
        submit_button = st.form_submit_button(label="🚀 Enviar Chamado")

    if submit_button:
        if not nome or not email or not titulo or not importador or not resumo:
            st.error("Por favor, preencha todos os campos obrigatórios (*).")
        else:
            try:
                anexos_info = []
                if arquivos_descricao:
                    with st.spinner("A enviar arquivos..."):
                        anexos_info = upload_files(arquivos_descricao)

                dados_chamado = {
                    "nome": nome,
                    "email": email,
                    "titulo": titulo,
                    "importador": importador,
                    "resumo": resumo,
                    "imagens": anexos_info,
                    "status": "Em Aberto",
                    "responsavel": "Não atribuído",
                    "historico": [],
                    "ativo": True
                }

                supabase.table("chamados").insert(dados_chamado).execute()
                registrar_log("CREATE", f"Novo chamado aberto por {nome} - Título: '{titulo}' | Importador: '{importador}'")
                
                with st.spinner("Notificando a equipe..."):
                    email_ok, email_erro = enviar_email_novo_chamado(dados_chamado)
                
                if email_ok:
                    registrar_log("EMAIL", f"Notificação enviada para o chamado '{titulo}'")
                else:
                    registrar_log("EMAIL_ERRO", f"Falha ao notificar chamado '{titulo}': {email_erro}")
                
                st.success("✅ Chamado registrado com sucesso! Nossa equipe irá entrar em contato em breve.")
            except Exception as e:
                st.error(f"Erro ao salvar chamado: {e}")

else:
    if pagina_selecionada == "Log do Sistema":
        st.markdown("---")
        st.subheader("📜 Logs")
        st.caption("Acompanhe todas as ações e alterações realizadas no sistema (salvas no banco de dados).")
        
        try:
            response_logs = (
                supabase.table("logs_sistema")
                .select("*")
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )
            logs = response_logs.data or []

            if logs:
                for log in logs:
                    data_formatada = formatar_data_br(log.get('created_at'))
                    st.text(f"[{data_formatada}] [{log.get('acao')}] {log.get('detalhes')}")
            else:
                st.info("Nenhum log registrado no sistema ainda.")
        except Exception as e:
            st.error(f"Erro ao carregar logs do banco de dados: {e}")
            st.info("💡 Certifique-se de criar a tabela 'logs_sistema' no Supabase.")
            
    else:
        st.markdown("---")
        st.subheader("⚙️ Painel do Administrador")

        termo_busca = st.text_input("🔍 Buscar por qualquer detalhe (Título, Solicitante, Importador, Responsável, Descrição...):", placeholder="Digite para filtrar os chamados instantaneamente...")

        try:
            response = (
                supabase.table("chamados")
                .select("*")
                .eq("ativo", True)
                .order("created_at", desc=True)
                .execute()
            )
            todos_chamados = response.data or []

            def contar_status(nome_status):
                if nome_status == "Todos":
                    return len(todos_chamados)
                return sum(1 for x in todos_chamados if x.get("status") == nome_status)

            col_status_section, col_espaco, col_crit_section = st.columns([4, 2, 4])

            with col_status_section:
                st.markdown('<p class="filter-label">Filtrar por Status:</p>', unsafe_allow_html=True)
                col_todos, col_aberto, col_dev, col_andamento, col_fin = st.columns(5)

                with col_todos:
                    if st.button(f"🌐 Todos ({contar_status('Todos')})", use_container_width=True, type="primary" if st.session_state.status_filter == "Todos" else "secondary"):
                        st.session_state.status_filter = "Todos"
                        st.rerun()
                with col_aberto:
                    if st.button(f"🟡 Em Aberto ({contar_status('Em Aberto')})", use_container_width=True, type="primary" if st.session_state.status_filter == "Em Aberto" else "secondary"):
                        st.session_state.status_filter = "Em Aberto"
                        st.rerun()
                with col_dev:
                    if st.button(f"🔵 Enviado ao Desenvolvimento ({contar_status('Enviado ao Desenvolvimento')})", use_container_width=True, type="primary" if st.session_state.status_filter == "Enviado ao Desenvolvimento" else "secondary"):
                        st.session_state.status_filter = "Enviado ao Desenvolvimento"
                        st.rerun()
                with col_andamento:
                    if st.button(f"🟣 Andamento ({contar_status('Em Andamento')})", use_container_width=True, type="primary" if st.session_state.status_filter == "Em Andamento" else "secondary"):
                        st.session_state.status_filter = "Em Andamento"
                        st.rerun()
                with col_fin:
                    if st.button(f"🟢 Finalizado ({contar_status('Finalizado')})", use_container_width=True, type="primary" if st.session_state.status_filter == "Finalizado" else "secondary"):
                        st.session_state.status_filter = "Finalizado"
                        st.rerun()

            status_filter = st.session_state.status_filter

            if status_filter == "Todos":
                chamados_status = list(todos_chamados)
            else:
                chamados_status = [x for x in todos_chamados if x.get("status") == status_filter]

            qtd_total_status = len(chamados_status)
            qtd_critico = sum(1 for x in chamados_status if x.get("criticidade") == "Crítico")
            qtd_urgente = sum(1 for x in chamados_status if x.get("criticidade") == "Urgente")

            with col_crit_section:
                st.markdown('<p class="filter-label" style="text-align: left;">Filtrar por Criticidade:</p>', unsafe_allow_html=True)
                
                sub_c1, sub_c2, sub_c3 = st.columns(3)

                with sub_c1:
                    if st.button(f"📋 Todas ({qtd_total_status})", key="crit_btn_todos", use_container_width=True, type="primary" if st.session_state.crit_filter == "Todos" else "secondary"):
                        st.session_state.crit_filter = "Todos"
                        st.rerun()
                with sub_c2:
                    if st.button(f"💣 Crítico ({qtd_critico})", key="crit_btn_critico", use_container_width=True, type="primary" if st.session_state.crit_filter == "Crítico" else "secondary"):
                        st.session_state.crit_filter = "Crítico"
                        st.rerun()
                with sub_c3:
                    if st.button(f"❗ Urgente ({qtd_urgente})", key="crit_btn_urgente", use_container_width=True, type="primary" if st.session_state.crit_filter == "Urgente" else "secondary"):
                        st.session_state.crit_filter = "Urgente"
                        st.rerun()

            crit_filter = st.session_state.crit_filter

            if crit_filter == "Todos":
                chamados = chamados_status
            else:
                chamados = [x for x in chamados_status if x.get("criticidade") == crit_filter]

            if termo_busca.strip():
                termo = termo_busca.strip().lower()
                chamadosfiltrados = []
                for c in chamados:
                    texto_completo = f"{c.get('id', '')} {c.get('titulo', '')} {c.get('nome', '')} {c.get('email', '')} {c.get('importador', '')} {c.get('resumo', '')} {c.get('responsavel', '')} {c.get('status', '')} {c.get('criticidade', '')}".lower()
                    if termo in texto_completo:
                        chamadosfiltrados.append(c)
                chamados = chamadosfiltrados

            chamados = sorted(chamados, key=rank_criticidade)

            st.markdown("---")

            if not chamados:
                st.info("Nenhum chamado encontrado com os filtros e termos de busca aplicados.")

            for c in chamados:
                resp_atual_badge = c.get('responsavel', 'Não atribuído')
                status_html = badge_status(c['status'])
                classe_css = obter_classe_expander(c['status'])
                importador_val = c.get('importador', 'Não informado')
                criticidade_atual = c.get('criticidade')
                tag_crit = tag_criticidade(criticidade_atual)
                
                tempo_decorrido = calcular_tempo_ultima_atualizacao(c)

                titulo_expander = f"{c['status'].upper()} - {c['titulo']} (Por: {c['nome']} | Resp: {resp_atual_badge})          ⏱️ {tempo_decorrido}"
            
                with st.container(key=f"chamado_{classe_css}_{tag_crit}_{c['id']}"), \
                     st.expander(titulo_expander):
                    st.markdown(f"**Status Atual:** {status_html}", unsafe_allow_html=True)
                    st.markdown(f"**Criticidade:** {badge_criticidade(criticidade_atual)}", unsafe_allow_html=True)
                    st.write(f"**Solicitante:** {c['nome']} ({c['email']})")
                    st.write(f"**Importador:** {importador_val}")
                    st.write(f"**Responsável Atual:** {resp_atual_badge}")
                    data_criacao_br = formatar_data_br(c.get('created_at'))
                    st.write(f"**Data de Abertura:** {data_criacao_br}")
                    st.write(f"**Descrição:**")
                    
                    st.markdown(
                        f"""
                        <div class="descricao-chamado" style="background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 12px; border-radius: 6px; color: #31333F;">
                            {c['resumo']}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )  

                    imgs = c.get("imagens", [])
                    if imgs:
                        st.write("**Anexos Iniciais:**")
                        renderizar_anexos(imgs)

                    st.markdown("---")
                    
                    st.write("📜 **Histórico de Atualizações**")
                    historico = c.get("historico", [])
                    if historico:
                        for h in historico:
                            data_registro_br = formatar_data_br(h.get('data_registro') or h.get('data'))
                            data_evento_br = formatar_data_br(h.get('data_evento') or h.get('data'))
                            responsavel_update = h.get('responsavel', 'Não informado')
                            status_hist_html = badge_status(h.get('status'))
                            crit_hist = h.get('criticidade')
                            crit_hist_txt = f" | **Criticidade:** {badge_criticidade(crit_hist)}" if crit_hist else ""
                            
                            st.markdown(f"🔹 **Registrado em:** {data_registro_br} | **Responsável:** `{responsavel_update}` | **Status:** {status_hist_html}{crit_hist_txt}", unsafe_allow_html=True)
                            st.markdown(f"> **[{data_evento_br}]** {h.get('observacao')}")
                            
                            anexos_hist = h.get("anexos", [])
                            if anexos_hist:
                                st.caption("Anexos desta atualização:")
                                renderizar_anexos(anexos_hist)
                            st.markdown("---")
                    else:
                        st.caption("Nenhuma atualização registrada ainda.")

                    with st.expander("✏️ Atualizar Chamado"):
                        fuso_br = timezone(timedelta(hours=-3))
                        agora_local = datetime.now(fuso_br)

                        with st.form(key=f"form_update_{c['id']}"):
                            responsaveis_list = ["Renan", "Brunno"]
                            resp_db = c.get('responsavel', 'Renan')
                            idx_resp = responsaveis_list.index(resp_db) if resp_db in responsaveis_list else 0

                            novo_responsavel = st.selectbox(
                                "Responsável pelo Chamado *",
                                options=responsaveis_list,
                                index=idx_resp,
                                key=f"resp_{c['id']}"
                            )

                            status_options = ["Em Aberto", "Enviado ao Desenvolvimento", "Em Andamento", "Finalizado"]
                            idx_status = status_options.index(c['status']) if c['status'] in status_options else 0
                            novo_status = st.selectbox(
                                "Alterar Status:",
                                options=status_options,
                                index=idx_status,
                                key=f"status_{c['id']}"
                            )

                            idx_crit = OPCOES_CRITICIDADE.index(criticidade_atual) if criticidade_atual in OPCOES_CRITICIDADE else 0
                            nova_criticidade = st.selectbox(
                                "Criticidade (opcional):",
                                options=OPCOES_CRITICIDADE,
                                index=idx_crit,
                                key=f"crit_{c['id']}"
                            )
                            
                            observacao = st.text_area(
                                "Observação (Máx. 700 caracteres)*", 
                                max_chars=700,
                                placeholder="Descreva o que foi feito ou o motivo da alteração...",
                                key=f"obs_{c['id']}"
                            )
                            
                            col_dt1, col_dt2 = st.columns(2)
                            with col_dt1:
                                data_input = st.date_input("Data da Atualização", value=agora_local.date(), key=f"date_{c['id']}")
                            with col_dt2:
                                hora_input = st.time_input("Hora da Atualização", value=agora_local.time(), key=f"time_{c['id']}")

                            novos_anexos = st.file_uploader(
                                "Anexar arquivos (Opcional, múltiplos)",
                                accept_multiple_files=True,
                                key=f"upload_{c['id']}"
                            )

                            btn_submit_update = st.form_submit_button("💾 Salvar Atualização")

                            if btn_submit_update:
                                if not observacao.strip():
                                    st.warning("Por favor, preencha a observação.")
                                else:
                                    try:
                                        anexos_novos_info = []
                                        if novos_anexos:
                                            with st.spinner("Enviando anexos..."):
                                                anexos_novos_info = upload_files(novos_anexos)

                                        data_registro_iso = datetime.now(fuso_br).isoformat()
                                        data_hora_combinada = datetime.combine(data_input, hora_input).replace(tzinfo=fuso_br)
                                        data_evento_iso = data_hora_combinada.isoformat()

                                        criticidade_salvar = None if nova_criticidade == "Normal" else nova_criticidade

                                        novo_registro = {
                                            "status": novo_status,
                                            "responsavel": novo_responsavel, 
                                            "criticidade": criticidade_salvar,
                                            "observacao": observacao,
                                            "data_registro": data_registro_iso,
                                            "data_evento": data_evento_iso,
                                            "anexos": anexos_novos_info
                                        }

                                        historico_atual = c.get("historico", [])
                                        if not isinstance(historico_atual, list):
                                            historico_atual = []
                                        
                                        historico_atual.append(novo_registro)

                                        supabase.table("chamados").update({
                                            "status": novo_status,
                                            "responsavel": novo_responsavel,
                                            "criticidade": criticidade_salvar,
                                            "historico": historico_atual
                                        }).eq("id", c['id']).execute()

                                        registrar_log("UPDATE", f"Chamado '{c['titulo']}' (Importador: '{importador_val}') atualizado. Resp: {novo_responsavel}, Status: {novo_status}, Criticidade: {nova_criticidade}")
                                        st.success("Chamado atualizado com sucesso!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro ao atualizar chamado: {e}")

                    st.markdown("---")
                    with st.popover("🗑️ Excluir Chamado", use_container_width=True):
                        st.markdown("⚠️ **Atenção:** O chamado será removido do app, mas continuará salvo no banco de dados.")
                        senha_exclusao = st.text_input(
                            "Senha de Administrador:",
                            type="password",
                            key=f"del_pass_{c['id']}"
                        )
                        if st.button("Confirmar Exclusão", key=f"btn_del_{c['id']}", type="primary", use_container_width=True):
                            str_senha = st.secrets.get("ADMIN_PASSWORD")
                            if senha_exclusao == str_senha:
                                try:
                                    fuso_br = timezone(timedelta(hours=-3))
                                    supabase.table("chamados").update({
                                        "ativo": False,
                                        "excluido_em": datetime.now(fuso_br).isoformat()
                                    }).eq("id", c['id']).execute()
                                    registrar_log("DELETE", f"Chamado '{c['titulo']}' (Importador: '{importador_val}') desativado por administrador (mantido no banco).")
                                    st.success(f"Chamado excluído com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao excluir chamado: {e}")
                            else:
                                st.error("Senha de administrador incorreta!")

        except Exception as e:
            st.error(f"Erro ao carregar chamados: {e}")

st.markdown("---")
if not st.session_state.admin_logged_in:
    with st.popover("🔒 Gestão de Chamados", use_container_width=False):
        senha_input = st.text_input(
            "Senha de Administrador:",
            type="password",
            key="login_admin_pass"
        )
        if st.button("Entrar", key="btn_login_admin", type="primary", use_container_width=True):
            senha_correta = st.secrets.get("ADMIN_PASSWORD")
            if senha_correta and senha_input == senha_correta:
                st.session_state.admin_logged_in = True
                st.rerun()
            else:
                st.error("Senha de administrador incorreta!")
