# =============================================================================
# ===== INÍCIO DO CÓDIGO DE PROTEÇÃO FINAL ====================================
# =============================================================================
import streamlit as st
import hashlib
from datetime import datetime, timezone
from st_supabase_connection import SupabaseConnection
import time

def init_connection():
    """Inicializa conexão com Supabase. Requer secrets configurados."""
    try:
        return st.connection("supabase", type=SupabaseConnection)
    except Exception as e:
        st.error(f"Erro ao conectar com Supabase: {e}")
        return None

def verify_and_consume_nonce(token: str) -> tuple[bool, str | None]:
    """Verifica um token de uso único (nonce) no banco de dados e o consome."""
    conn = init_connection()
    if not conn:
        return False, None

    try:
        # 1. Cria o hash do token recebido para procurar no banco
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        # 2. Procura pelo token no banco de dados
        response = conn.table("auth_tokens").select("*").eq("token_hash", token_hash).execute()
        
        if not response.data:
            st.error("Token de acesso inválido ou não encontrado.")
            return False, None
        
        token_data = response.data[0]
        
        # 3. Verifica se o token já foi utilizado
        if token_data["is_used"]:
            st.error("Este link de acesso já foi utilizado e não é mais válido.")
            return False, None
            
        # 4. Verifica se o token expirou
        expires_at = datetime.fromisoformat(token_data["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            st.error("O link de acesso expirou. Por favor, gere um novo no portal.")
            return False, None
            
        # 5. Se tudo estiver correto, marca o token como usado (consumido)
        conn.table("auth_tokens").update({"is_used": True}).eq("id", token_data["id"]).execute()
        
        user_email = token_data["user_email"]
        return True, user_email
        
    except Exception as e:
        st.error(f"Ocorreu um erro crítico durante a validação do acesso: {e}")
        return False, None

# --- Lógica Principal de Autenticação ---
query_params = st.query_params
token = query_params.get("access_token")

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if token and not st.session_state.authenticated:
    time.sleep(1) # PAUSA ESTRATÉGICA PARA EVITAR RACE CONDITION
    is_valid, email = verify_and_consume_nonce(token)
    if is_valid:
        st.session_state.authenticated = True
        st.session_state.user_email = email

# --- Barreira de Acesso ---
if not st.session_state.get('authenticated'):
    st.title("🔒 Acesso Restrito")
    st.error("Este aplicativo requer autenticação. Por favor, faça o login através do portal.")
    
    st.link_button(
        "Ir para o Portal de Login",
        "https://app-unificadopy-j9wgzbt2sqm5pgaeqzxyme.streamlit.app/",
        use_container_width=True,
        type="primary"
    )
    st.stop()

# =============================================================================
# ===== FIM DO CÓDIGO DE PROTEÇÃO =============================================
# =============================================================================

# Mensagem de boas-vindas para o usuário autenticado
st.success(f"Autenticação bem-sucedida! Bem-vindo, {st.session_state.get('user_email', 'usuário')}.")

# O CÓDIGO PRINCIPAL DO SEU APLICATIVO COMEÇA AQUI
# Streamlit - Limpar cabeçalho de TXT e manter apenas a(s) tabela(s)
# Funciona bem com arquivos TRIOS/TA Instruments e afins.

import re
import io
import os

st.set_page_config(page_title="Limpar Cabeçalho TXT", page_icon="🧹", layout="centered")

st.title("🧹 Limpar Cabeçalho de TXT")
st.write(
    "Envie um arquivo `.txt` com cabeçalho (metadata) + tabela. "
    "O app detecta onde a tabela começa, remove o cabeçalho e exporta um TXT só com as colunas."
)

# --------------------------
# Utilidades de parsing
# --------------------------
NUM_RE = re.compile(r'^[+-]?((\d+(\.\d*)?)|(\.\d+))([eE][+-]?\d+)?$')

def split_tokens(line: str):
    # Divide por qualquer espaço/aba múltipla
    return re.findall(r'\S+', line.strip())

def is_numeric_token(tok: str) -> bool:
    return bool(NUM_RE.match(tok))

def looks_like_column_header(line: str) -> bool:
    """
    Heurística: linha de cabeçalho de coluna tende a ter 2+ tokens com letras,
    pouca ou nenhuma numeração, e não conter ':' (que é comum em metadados).
    Ex.: 'Time Temperature Weight Weight'
    """
    tokens = split_tokens(line)
    if len(tokens) < 2:
        return False
    alpha_tokens = sum(any(ch.isalpha() for ch in t) and not any(ch.isdigit() for ch in t) for t in tokens)
    has_colon = any(':' in t for t in tokens)
    return (alpha_tokens >= 2) and (not has_colon)

def find_table_start(lines):
    """
    Retorna (idx_header, idx_units, idx_data) se encontrar cabeçalho+unidades+tabela.
    Caso contrário, retorna (None, None, idx_data_inferido) usando heurística numérica.
    """
    # 1) Caminho preferencial: bloco [step] -> header -> units -> dados
    step_positions = [i for i, ln in enumerate(lines) if "[step]" in ln.lower()]
    search_starts = step_positions + [0]  # também tenta desde o início, caso não exista [step]

    for start in search_starts:
        for i in range(start, len(lines) - 2):
            if looks_like_column_header(lines[i]):
                # Assume próxima linha são unidades e depois começam dados
                header_idx = i
                units_idx = i + 1
                data_idx = i + 2
                # Sanidade: verifique se as duas primeiras linhas de dados parecem numéricas
                if data_idx < len(lines) - 1:
                    t1 = split_tokens(lines[data_idx])
                    t2 = split_tokens(lines[data_idx + 1])
                    if len(t1) >= 2 and len(t2) >= 2:
                        nratio1 = sum(is_numeric_token(x) for x in t1) / max(1, len(t1))
                        nratio2 = sum(is_numeric_token(x) for x in t2) / max(1, len(t2))
                        if nratio1 >= 0.6 and nratio2 >= 0.6:
                            return header_idx, units_idx, data_idx

    # 2) Fallback: encontra o primeiro bloco longo "numeric-like" consistente
    for i in range(len(lines) - 6):
        t0 = split_tokens(lines[i])
        if len(t0) < 2:
            continue
        nratio0 = sum(is_numeric_token(x) for x in t0) / len(t0)
        if nratio0 < 0.6:
            continue
        # Valida próximas linhas
        num_cols = len(t0)
        good = True
        for k in range(1, 6):
            tk = split_tokens(lines[i + k])
            if len(tk) < 2:
                good = False
                break
            nratio = sum(is_numeric_token(x) for x in tk) / len(tk)
            if nratio < 0.6:
                good = False
                break
            # opcional: aceita variação de colunas, mas prefere consistência
            if abs(len(tk) - num_cols) > 1:
                good = False
                break
        if good:
            return None, None, i

    # Não encontrado
    return None, None, None

def build_dataframe_like(lines, idx_header, idx_units, idx_data, max_rows_preview=50):
    """
    Constrói uma 'tabela' simples (lista de listas) + nomes de colunas (lista),
    sem depender de pandas (para reduzir dependências).
    """
    col_names = None
    if idx_header is not None:
        col_names = split_tokens(lines[idx_header])

    # Lê dados até acabar ou até encontrar linha vazia/bloco novo
    rows = []
    num_cols_target = None
    for j in range(idx_data, len(lines)):
        ln = lines[j].strip()
        if not ln:
            # linha vazia indica fim provável
            break
        if ln.startswith('[') and ln.endswith(']'):
            # novo bloco [....] indica fim provável da tabela
            break
        toks = split_tokens(ln)
        if len(toks) < 2:
            continue
        # filtra óbvios ruídos de log
        if any(k in ln.lower() for k in (":", "segment", "started", "version", "entry", "log", "calibration")):
            # geralmente é texto; pula
            continue
        # mantém consistência de colunas
        if num_cols_target is None:
            num_cols_target = len(toks)
        elif abs(len(toks) - num_cols_target) > 1:
            # se fugir muito, encerra (evita pegar outro bloco)
            break
        rows.append(toks)

        if len(rows) >= max_rows_preview and st.session_state.get("preview_only", True):
            # em preview limitamos para não pesar
            pass

    # Se não há nomes, cria genéricos
    if not col_names:
        n = max((len(r) for r in rows), default=0)
        col_names = [f"col{i+1}" for i in range(n)]

    # Ajusta linhas para o mesmo número de colunas
    ncols = len(col_names)
    clean_rows = []
    for r in rows:
        if len(r) == ncols:
            clean_rows.append(r)
        elif len(r) == ncols - 1:
            # se faltar 1, tenta preencher com vazio (raro, mas útil)
            clean_rows.append(r + [""])
        elif len(r) > ncols:
            clean_rows.append(r[:ncols])
        # se faltar demais, descarta

    return col_names, clean_rows

def make_txt(col_names, rows, sep, include_header=True, decimal_to_dot=False):
    """
    Monta o texto final.
    """
    def fix_decimal(tok: str) -> str:
        # opcional: troca vírgula por ponto
        if decimal_to_dot:
            return tok.replace(",", ".")
        return tok

    out = io.StringIO()
    if include_header and col_names:
        out.write(sep.join(col_names) + "\n")
    for r in rows:
        out.write(sep.join(fix_decimal(x) for x in r) + "\n")
    return out.getvalue()

# --------------------------
# UI
# --------------------------
uploaded = st.file_uploader("Envie o arquivo .txt", type=["txt"])
col1, col2 = st.columns(2)
with col1:
    custom_marker = st.text_input("Marcador antes da tabela (opcional)", value="[step]")
with col2:
    output_sep_label = st.selectbox(
        "Delimitador de saída",
        ["Tab (\\t)", "Vírgula (,)", "Ponto e vírgula (;)", "Espaço ( )"],
        index=0,
    )

sep_map = {
    "Tab (\\t)": "\t",
    "Vírgula (,)": ",",
    "Ponto e vírgula (;)": ";",
    "Espaço ( )": " ",
}

include_header = st.checkbox("Incluir linha com nomes das colunas na saída", value=True)
decimal_to_dot = st.checkbox("Trocar vírgula por ponto nos decimais", value=False)
manual_skip = st.number_input("Ignorar N linhas manualmente (opcional)", min_value=0, value=0, step=1)

st.session_state["preview_only"] = True

if uploaded:
    # Decodifica com fallback simples (sem chardet para evitar dependência extra)
    raw = uploaded.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    # Se o usuário informou um marcador, e ele existir, começa a busca dali
    lines_all = text.splitlines()

    # Se o usuário pediu "manual_skip", aplique antes de qualquer heurística
    if manual_skip > 0:
        lines = lines_all[int(manual_skip):]
        base_offset = int(manual_skip)
    else:
        lines = lines_all
        base_offset = 0

    # Se há marcador customizado, traga o trecho a partir dele (se encontrado)
    if custom_marker and custom_marker.strip():
        lower_marker = custom_marker.lower()
        for i, ln in enumerate(lines):
            if lower_marker in ln.lower():
                lines = lines[i:]  # recorta a partir do marcador
                base_offset += i
                break

    h_idx, u_idx, d_idx = find_table_start(lines)

    if d_idx is None:
        st.error("Não consegui encontrar automaticamente o início da tabela. "
                 "Tente informar o 'Marcador antes da tabela' ou usar 'Ignorar N linhas'.")
    else:
        col_names, rows = build_dataframe_like(lines, h_idx, u_idx, d_idx)
        if not rows:
            st.warning("Tabela detectada, mas sem linhas válidas de dados. "
                       "Ajuste o marcador ou o 'Ignorar N linhas'.")
        else:
            st.success(f"Tabela detectada! Colunas: {len(col_names)} • Linhas (preview): {min(len(rows), 50)}")

            # Preview (limita a 50 linhas para não pesar)
            preview_rows = rows[:50]
            preview_text = make_txt(col_names, preview_rows, sep="\t", include_header=True)
            st.text_area("Prévia (primeiras linhas)", preview_text, height=220)

            # Gera saída final
            final_txt = make_txt(
                col_names,
                rows,
                sep=sep_map[output_sep_label],
                include_header=include_header,
                decimal_to_dot=decimal_to_dot,
            )

            # Nome do arquivo limpo
            base_name = os.path.splitext(uploaded.name)[0]
            out_name = f"{base_name}_limpo.txt"

            st.download_button(
                "⬇️ Baixar TXT limpo",
                data=final_txt.encode("utf-8"),
                file_name=out_name,
                mime="text/plain",
            )

st.caption(
    "Dica: se seu arquivo tem várias seções, use um **marcador** que antecede a tabela (ex.: `[step]`) "
    "ou ajuste **Ignorar N linhas** até a linha anterior aos nomes das colunas."
)
