import streamlit as st
from supabase import create_client, Client
import uuid
from datetime import datetime, timezone, timedelta

# --- CONFIGURAÇÃO PÁGINA ---
st.set_page_config(
    page_title="Suporte & Chamados",
    page_icon="🎫",
    layout="centered"
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

    /* Botões de filtro */
    div.stHorizontalBlock { gap: 6px !important; }
    div.stHorizontalBlock > div { flex: 0 1 auto !important; width: auto !important; }
    div.stButton > button {
        width: auto !important;
        white-space: nowrap !important;
        padding-left: 12px !important;
        padding-right: 12px !important;
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
        background-color: #ffebee !important;
        border: 1px solid #f44336 !important;
    }
    [class*="st-key-chamado_finalizado_"] > div > [data-testid="stExpander"] {
        background-color: #e8f5e9 !important;
        border: 1px solid #4caf50 !important;
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

# --- ESTADO DE AUTENTICAÇÃO E LOGS ---
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

if "crud_logs" not in st.session_state:
    st.session_state.crud_logs = []

if "status_filter" not in st.session_state:
    st.session_state.status_filter = "Todos"

def registrar_log(acao, detalhes):
    fuso_br = timezone(timedelta(hours=-3))
    agora_br = datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M:%S")
    st.session_state.crud_logs.append({
        "data": agora_br,
        "acao": acao,
        "detalhes": detalhes
    })

# --- FUNÇÃO AUXILIAR DE CORES DOS STATUS ---
def badge_status(status):
    """Retorna uma string HTML estilizada para cada status."""
    cores = {
        "Em Aberto": {"bg": "#ffeb3b", "color": "#000000"},            # Amarelo
        "Enviado ao Desenvolvimento": {"bg": "#2196f3", "color": "#ffffff"}, # Azul
        "Em Andamento": {"bg": "#f44336", "color": "#ffffff"},          # Vermelho
        "Finalizado": {"bg": "#4caf50", "color": "#ffffff"}               # Verde
    }
    
    config = cores.get(status, {"bg": "#9e9e9e", "color": "#ffffff"})
    return f'<span style="background-color: {config["bg"]}; color: {config["color"]}; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em;">{status}</span>'

# Função auxiliar para mapear a classe CSS do expander baseada no status
def obter_classe_expander(status):
    mapa = {
        "Em Aberto": "aberto",
        "Enviado ao Desenvolvimento": "dev",
        "Em Andamento": "andamento",
        "Finalizado": "finalizado",
    }
    return mapa.get(status, "outro")

# --- UPLOAD DE IMAGENS / ARQUIVOS ---
def upload_images(files):
    urls = []
    bucket_name = "chamados-anexos"
    
    for file in files:
        ext = file.name.split(".")[-1]
        file_path = f"anexos/{uuid.uuid4()}.{ext}"
        file_bytes = file.getvalue()
        
        supabase.storage.from_(bucket_name).upload(
            file_path,
            file_bytes,
            file_options={"content-type": file.type}
        )
        
        public_url_res = supabase.storage.from_(bucket_name).get_public_url(file_path)
        
        if isinstance(public_url_res, dict):
            public_url = public_url_res.get("publicUrl") or public_url_res.get("public_url") or public_url_res.get("signedURL", "")
        else:
            public_url = str(public_url_res)
            
        urls.append(public_url)
        
    return urls

# Função auxiliar para formatar data ISO para o padrão BR
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

# --- MENU LATERAL (SE ADMIN LOGADO) ---
pagina_selecionada = "Painel de Administrador"

if st.session_state.admin_logged_in:
    st.sidebar.title("🔧 Menu Admin")
    pagina_selecionada = st.sidebar.radio(
        "Navegação:",
        ["Painel de Administrador", "Acessar Log de Sistema"]
    )
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Sair do Admin", use_container_width=True):
        st.session_state.admin_logged_in = False
        st.rerun()

# --- INTERFACE PRINCIPAL ---
st.title("🛠️ Suporte ao Sistema")

# Exibe o painel correspondente ao perfil
if not st.session_state.admin_logged_in:
    # ----------------------------------------------------
    # TELA DO COLABORADOR (ABERTURA DE CHAMADO)
    # ----------------------------------------------------
    st.subheader("Abrir Novo Chamado")
    st.caption("Preencha as informações abaixo para relatar seu problema.")

    with st.form(key="form_chamado", clear_on_submit=True):
        nome = st.text_input("Seu Nome*", placeholder="Ex: Maria Silva")
        email = st.text_input("Seu E-mail*", placeholder="Ex: maria@multprocessing.com.br")
        titulo = st.text_input("Título do Chamado*", placeholder="Ex: Ajustar tag nota fiscal")
        importador = st.text_input("Importador*", placeholder="Ex: Nome do importador")
        resumo = st.text_area("Resumo do Problema*", placeholder="Descreva um resumo do chamado...", height=120)
        imagens = st.file_uploader(
            "Anexar imagens/prints da tela", 
            type=["png", "jpg", "jpeg", "webp"], 
            accept_multiple_files=True
        )

        submit_button = st.form_submit_button(label="🚀 Enviar Chamado")

    if submit_button:
        if not nome or not email or not titulo or not importador or not resumo:
            st.error("Por favor, preencha todos os campos obrigatórios (*).")
        else:
            try:
                urls_imagens = []
                if imagens:
                    with st.spinner("Enviando imagens..."):
                        urls_imagens = upload_images(imagens)

                dados_chamado = {
                    "nome": nome,
                    "email": email,
                    "titulo": titulo,
                    "importador": importador,
                    "resumo": resumo,
                    "imagens": urls_imagens,
                    "status": "Em Aberto",
                    "responsavel": "Renan",
                    "historico": []
                }

                supabase.table("chamados").insert(dados_chamado).execute()
                registrar_log("CREATE", f"Novo chamado aberto por {nome} - Título: '{titulo}' | Importador: '{importador}'")
                st.success("✅ Chamado registrado com sucesso! Nossa equipe irá entrar em contato em breve.")
            except Exception as e:
                st.error(f"Erro ao salvar chamado: {e}")

else:
    # ----------------------------------------------------
    # SEÇÃO DE LOGS (SE ESCOLHIDO NO MENU LATERAL)
    # ----------------------------------------------------
    if pagina_selecionada == "Acessar Log de Sistema":
        st.markdown("---")
        st.subheader("📜 Histórico de Logs (CRUD)")
        st.caption("Acompanhe todas as ações e alterações realizadas na sessão atual.")
        
        logs = st.session_state.get("crud_logs", [])
        if logs:
            for log in reversed(logs):
                st.text(f"[{log['data']}] [{log['acao']}] {log['detalhes']}")
        else:
            st.info("Nenhum log registrado na sessão atual.")
            
    # ----------------------------------------------------
    # PAINEL ADMIN (GESTÃO DE CHAMADOS)
    # ----------------------------------------------------
    else:
        st.markdown("---")
        st.subheader("⚙️ Painel do Administrador")

        st.markdown("**Filtrar por Status:**")
        col_todos, col_aberto, col_dev, col_andamento, col_fin = st.columns(5)

        with col_todos:
            if st.button("🌐 Todos", type="primary" if st.session_state.status_filter == "Todos" else "secondary"):
                st.session_state.status_filter = "Todos"
                st.rerun()
        with col_aberto:
            if st.button("🟡 Em Aberto", type="primary" if st.session_state.status_filter == "Em Aberto" else "secondary"):
                st.session_state.status_filter = "Em Aberto"
                st.rerun()
        with col_dev:
            if st.button("🔵 Enviado ao Desenvolvimento", type="primary" if st.session_state.status_filter == "Enviado ao Desenvolvimento" else "secondary"):
                st.session_state.status_filter = "Enviado ao Desenvolvimento"
                st.rerun()
        with col_andamento:
            if st.button("🔴 Em Andamento", type="primary" if st.session_state.status_filter == "Em Andamento" else "secondary"):
                st.session_state.status_filter = "Em Andamento"
                st.rerun()
        with col_fin:
            if st.button("🟢 Finalizado", type="primary" if st.session_state.status_filter == "Finalizado" else "secondary"):
                st.session_state.status_filter = "Finalizado"
                st.rerun()

        status_filter = st.session_state.status_filter

        try:
            query = supabase.table("chamados").select("*").order("created_at", desc=True)
            if status_filter != "Todos":
                query = query.eq("status", status_filter)
            
            response = query.execute()
            chamados = response.data

            st.info(f"Total de chamados exibidos: {len(chamados)}")

            for c in chamados:
                resp_atual_badge = c.get('responsavel', 'Não atribuído')
                status_html = badge_status(c['status'])
                classe_css = obter_classe_expander(c['status'])
                importador_val = c.get('importador', 'Não informado')
            
                with st.container(key=f"chamado_{classe_css}_{c['id']}"), \
                     st.expander(f"{c['status'].upper()} - {c['titulo']} (Por: {c['nome']} | Resp: {resp_atual_badge})"):
                    st.markdown(f"**Status Atual:** {status_html}", unsafe_allow_html=True)
                    st.write(f"**Solicitante:** {c['nome']} ({c['email']})")
                    st.write(f"**Importador:** {importador_val}")
                    st.write(f"**Responsável Atual:** {resp_atual_badge}")
                    data_criacao_br = formatar_data_br(c.get('created_at'))
                    st.write(f"**Data de Abertura:** {data_criacao_br}")
                    st.write(f"**Descrição:**")
                    st.info(c['resumo'])

                    imgs = c.get("imagens", [])
                    if imgs:
                        st.write("**Anexos Iniciais:**")
                        cols = st.columns(min(len(imgs), 3))
                        for idx, item in enumerate(imgs):
                            if isinstance(item, dict):
                                img_url = item.get("publicUrl") or item.get("public_url") or item.get("signedURL", "")
                            else:
                                img_url = str(item)

                            if img_url and img_url.startswith("http"):
                                col_atual = cols[idx % 3]
                                with col_atual:
                                    st.markdown(
                                        f"""
                                        <a href="{img_url}" target="_blank" title="Clique para ver a imagem em tamanho original">
                                            <img src="{img_url}" style="width: 100%; border-radius: 6px; border: 1px solid #ddd; cursor: pointer; transition: 0.2s;" />
                                        </a>
                                        """,
                                        unsafe_allow_html=True
                                    )

                    st.markdown("---")
                    
                    # --- HISTÓRICO DE ATUALIZAÇÕES ---
                    st.write("📜 **Histórico de Atualizações**")
                    historico = c.get("historico", [])
                    if historico:
                        for h in historico:
                            data_registro_br = formatar_data_br(h.get('data_registro') or h.get('data'))
                            data_evento_br = formatar_data_br(h.get('data_evento') or h.get('data'))
                            responsavel_update = h.get('responsavel', 'Não informado')
                            status_hist_html = badge_status(h.get('status'))
                            
                            st.markdown(f"🔹 **Registrado em:** {data_registro_br} | **Responsável:** `{responsavel_update}` | **Status:** {status_hist_html}", unsafe_allow_html=True)
                            st.markdown(f"> **[{data_evento_br}]** {h.get('observacao')}")
                            
                            anexos_hist = h.get("anexos", [])
                            if anexos_hist:
                                st.caption("Anexos desta atualização:")
                                cols_h = st.columns(min(len(anexos_hist), 3))
                                for idx_h, anexo_url in enumerate(anexos_hist):
                                    with cols_h[idx_h % 3]:
                                        st.markdown(
                                            f"""
                                            <a href="{anexo_url}" target="_blank" title="Ver anexo">
                                                <img src="{anexo_url}" style="width: 100%; border-radius: 4px; border: 1px solid #ddd;" />
                                            </a>
                                            """,
                                            unsafe_allow_html=True
                                        )
                            st.markdown("---")
                    else:
                        st.caption("Nenhuma atualização registrada ainda.")

                    # --- AÇÕES DE ATUALIZAÇÃO E EXCLUSÃO PELO ADMIN ---
                    with st.expander("✏️ Atualizar ou Excluir Chamado"):
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
                                "Anexar arquivos/prints (Opcional, múltiplos)",
                                type=["png", "jpg", "jpeg", "webp", "pdf"],
                                accept_multiple_files=True,
                                key=f"upload_{c['id']}"
                            )

                            btn_submit_update = st.form_submit_button("💾 Salvar Atualização")

                            if btn_submit_update:
                                if not observacao.strip():
                                    st.warning("Por favor, preencha a observação.")
                                else:
                                    try:
                                        urls_novos_anexos = []
                                        if novos_anexos:
                                            with st.spinner("Enviando anexos..."):
                                                urls_novos_anexos = upload_images(novos_anexos)

                                        data_registro_iso = datetime.now(fuso_br).isoformat()
                                        data_hora_combinada = datetime.combine(data_input, hora_input).replace(tzinfo=fuso_br)
                                        data_evento_iso = data_hora_combinada.isoformat()

                                        novo_registro = {
                                            "status": novo_status,
                                            "responsavel": novo_responsavel, 
                                            "observacao": observacao,
                                            "data_registro": data_registro_iso,
                                            "data_evento": data_evento_iso,
                                            "anexos": urls_novos_anexos
                                        }

                                        historico_atual = c.get("historico", [])
                                        if not isinstance(historico_atual, list):
                                            historico_atual = []
                                        
                                        historico_atual.append(novo_registro)

                                        supabase.table("chamados").update({
                                            "status": novo_status,
                                            "responsavel": novo_responsavel,
                                            "historico": historico_atual
                                        }).eq("id", c['id']).execute()

                                        # Ajustado para exibir Título e Importador em vez do ID no Log de Update
                                        registrar_log("UPDATE", f"Chamado '{c['titulo']}' (Importador: '{importador_val}') atualizado. Resp: {novo_responsavel}, Status: {novo_status}")
                                        st.success("Chamado atualizado com sucesso!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro ao atualizar chamado: {e}")

                        # --- ZONA DE PERIGO: EXCLUIR CHAMADO COM SENHA DE ADMIN ---
                        st.markdown("---")
                        st.markdown("⚠️ **Excluir Chamado**")
                        senha_exclusao = st.text_input(
                            "Digite a senha de admin para confirmar exclusão:",
                            type="password",
                            key=f"del_pass_{c['id']}"
                        )
                        if st.button("🗑️ Apagar Chamado Definitivamente", key=f"btn_del_{c['id']}", type="primary"):
                            str_senha = st.secrets.get("ADMIN_PASSWORD")
                            if senha_exclusao == str_senha:
                                try:
                                    supabase.table("chamados").delete().eq("id", c['id']).execute()
                                    
                                    # Ajustado para exibir Título e Importador em vez do ID no Log de Delete
                                    registrar_log("DELETE", f"Chamado '{c['titulo']}' (Importador: '{importador_val}') excluído por administrador.")
                                    
                                    st.success(f"Chamado '{c['titulo']}' excluído com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao excluir chamado: {e}")
                            else:
                                st.error("Senha de administrador incorreta!")

        except Exception as e:
            st.error(f"Erro ao carregar chamados: {e}")

# ----------------------------------------------------
# RODAPÉ - ACESSO ÁREA ADMIN
# ----------------------------------------------------
st.markdown("---")
if not st.session_state.admin_logged_in:
    with st.popover("🔒 Acesso Restrito (Admin)", use_container_width=False):
        senha_input = st.text_input("Digite a senha do Admin", type="password", key="admin_login_password_input")
        if st.button("Entrar", key="admin_login_submit_btn"):
            str_senha = st.secrets.get("ADMIN_PASSWORD")
            if senha_input == str_senha:
                st.session_state.admin_logged_in = True
                registrar_log("READ", "Administrador acessou o painel.")
                st.success("Acesso liberado!")
                st.rerun()
            else:
                st.error("Senha incorreta!")
