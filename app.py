import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io

# Configuração da página do Streamlit
st.set_page_config(page_title="Auditor Fiscal Digital - XML & NCM", layout="wide", page_icon="📊")

# --- SIMULAÇÃO DE BANCO DE DADOS (Substitua por tabelas reais/banco de dados) ---
# Tabelas 4.3.10 e 4.3.11 do SPED (PIS/COFINS Monofásicos)
@st.cache_data
def carregar_dados_monofasicos():
    # Exemplo de NCMs monofásicos (Combustíveis, Bebidas, Autopeças, Medicamentos, etc.)
    return {
        "30041010": {"CST_PIS_CORRETO": "02", "CST_COFINS_CORRETO": "02", "Desc": "Medicamentos - Tabela 4.3.10"},
        "22030000": {"CST_PIS_CORRETO": "02", "CST_COFINS_CORRETO": "02", "Desc": "Cervejas - Tabela 4.3.11"},
        "40111000": {"CST_PIS_CORRETO": "04", "CST_COFINS_CORRETO": "04", "Desc": "Pneumáticos - Tabela 4.3.10"},
        "27101259": {"CST_PIS_CORRETO": "04", "CST_COFINS_CORRETO": "04", "Desc": "Gasolina - Tabela 4.3.10"}
    }

# Legislações de Substituição Tributária por NCM e UF
@st.cache_data
def carregar_legislacao_st():
    # Simulação de base de dados de ST por Estado e NCM
    return pd.DataFrame([
        {"NCM": "22030000", "UF": "SP", "ST_Aplicavel": "Sim", "MVA_Original": "70%", "Base_Legal": "Artigo 313-A do RICMS/SP"},
        {"NCM": "22030000", "UF": "RJ", "ST_Aplicavel": "Sim", "MVA_Original": "65%", "Base_Legal": "Decreto nº 44.444/RJ"},
        {"NCM": "30041010", "UF": "MG", "ST_Aplicavel": "Sim", "MVA_Original": "35%", "Base_Legal": "Anexo XV do RICMS/MG"},
        {"NCM": "40111000", "UF": "PR", "ST_Aplicavel": "Sim", "MVA_Original": "45%", "Base_Legal": "Artigo 120 do RICMS/PR"}
    ])

# --- FUNÇÃO DE ANÁLISE DOS XMLs ---
def analisar_xmls(arquivos_xml, db_monofasico):
    resultados = []
    
    for arquivo in arquivos_xml:
        try:
            # Ler conteúdo do XML carregado na memória
            conteudo = arquivo.read()
            root = ET.fromstring(conteudo)
            
            # Namespace padrão da NF-e
            ns = {'nfe': 'http://portalfiscal.inf.br'}
            
            # Identificação da Nota e UF do Emitente
            ide = root.find('.//nfe:ide', ns)
            emit = root.find('.//nfe:emit', ns)
            
            chNFe = root.find('.//nfe:infNFe', ns).attrib.get('Id', 'Desconhecido')[3:] if root.find('.//nfe:infNFe', ns) is not None else "Sem Chave"
            uf_emit = emit.find('nfe:enderEmit/nfe:UF', ns).text if emit is not None else "XX"
            
            # Percorrer produtos da nota
            for det in root.findall('.//nfe:det', ns):
                num_item = det.attrib.get('nItem')
                prod = det.find('nfe:prod', ns)
                imposto = det.find('nfe:imposto', ns)
                
                xProd = prod.find('nfe:xProd', ns).text
                ncm = prod.find('nfe:NCM', ns).text
                
                # Buscar tags de PIS / COFINS no XML
                pis = imposto.find('.//nfe:PIS', ns)
                cofins = imposto.find('.//nfe:COFINS', ns)
                
                cst_pis_atual = "N/A"
                cst_cofins_atual = "N/A"
                
                # Tenta capturar o CST de PIS enviado
                if pis is not None:
                    for child in pis:
                        cst_node = child.find('nfe:CST', ns)
                        if cst_node is not None: cst_pis_atual = cst_node.text
                
                # Tenta capturar o CST de COFINS enviado
                if cofins is not None:
                    for child in cofins:
                        cst_node = child.find('nfe:CST', ns)
                        if cst_node is not None: cst_cofins_atual = cst_node.text
                
                # --- VALIDAÇÃO MONOFÁSICA ---
                erro_encontrado = False
                motivo_erro = ""
                cst_pis_correto = cst_pis_atual
                cst_cofins_correto = cst_cofins_atual
                base_legal_sped = ""
                
                if ncm in db_monofasico:
                    cst_pis_correto = db_monofasico[ncm]["CST_PIS_CORRETO"]
                    cst_cofins_correto = db_monofasico[ncm]["CST_COFINS_CORRETO"]
                    base_legal_sped = db_monofasico[ncm]["Desc"]
                    
                    if cst_pis_atual != cst_pis_correto or cst_cofins_atual != cst_cofins_correto:
                        erro_encontrado = True
                        motivo_erro = f"NCM Monofásico. CST enviado ({cst_pis_atual}/{cst_cofins_atual}) diverge do correto."
                
                resultados.append({
                    "Chave NF-e": chNFe,
                    "Item": num_item,
                    "Produto": xProd,
                    "NCM": ncm,
                    "UF Origem": uf_emit,
                    "CST PIS Emitido": cst_pis_atual,
                    "CST PIS Correto": cst_pis_correto,
                    "CST COFINS Emitido": cst_cofins_atual,
                    "CST COFINS Correto": cst_cofins_correto,
                    "Possui Erro?": "⚠️ Sim" if erro_encontrado else "✅ Não",
                    "Diagnóstico / Legislação": motivo_erro if erro_encontrado else base_legal_sped
                })
                
        except Exception as e:
            st.error(f"Erro ao processar o arquivo {arquivo.name}: {e}")
            
    return pd.DataFrame(resultados)

# --- REGRAS DO FRONT-END (STREAMLIT) ---

st.title("🏛️ Plataforma Fiscal Inteligente: XML, ST & Monofásico")
st.markdown("Análise inteligente de arquivos fiscais, validação de regimes monofásicos (SPED) e consulta de regras de Substituição Tributária.")

# Inicializar bases
db_monofasico = carregar_dados_monofasicos()
df_st = carregar_legislacao_st()

# Criar abas no site
aba1, aba2, aba3 = st.tabs(["🔍 Analisador de XML em Lote", "📚 Consulta de Legislação ST", "📋 Tabelas Monofásicas (SPED)"])

# --- ABA 1: ANALISADOR EM LOTE ---
with aba1:
    st.header("Análise de XML em Lote (NF-e)")
    st.write("Faça o upload de um ou mais arquivos XML de Notas Fiscais para identificar erros de emissão baseados nas tabelas 4.3.10 e 4.3.11 do SPED.")
    
    arquivos_carregados = st.file_uploader("Selecione os arquivos XML", type=["xml"], accept_multiple_files=True)
    
    if arquivos_carregados:
        st.success(f"{len(arquivos_carregados)} arquivos carregados com sucesso!")
        if st.button("Executar Auditoria Fiscal"):
            with st.spinner("Analisando tags e cruzando com as legislações vigentes..."):
                df_resultado = analisar_xmls(arquivos_carregados, db_monofasico)
                
                # Exibir métricas rápidas
                total_erros = df_resultado[df_resultado["Possui Erro?"] == "⚠️ Sim"].shape[0]
                st.metric(label="Inconsistências Fiscais Encontradas", value=total_erros, delta=f"{total_erros} erros detectados", delta_color="inverse")
                
                # Mostrar tabela com os dados
                st.dataframe(df_resultado, use_container_width=True)
                
                # Permitir download do relatório em Excel / CSV
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_resultado.to_excel(writer, index=False, sheet_name='Auditoria_XML')
                processed_data = output.getvalue()
                
                st.download_button(
                    label="📥 Baixar Relatório de Auditoria (Excel)",
                    data=processed_data,
                    file_name="relatorio_auditoria_xml.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# --- ABA 2: CONSULTA DE ST POR NCM E UF ---
with aba2:
    st.header("Consulta Geral de Substituição Tributária")
    st.write("Verifique a aplicabilidade da ST e sua respectiva MVA/Base Legal digitando o NCM do produto e o Estado de destino.")
    
    col1, col2 = st.columns(2)
    with col1:
        ncm_busca = st.text_input("Digite o NCM para consulta (ex: 22030000, 30041010):").strip()
    with col2:
        uf_busca = st.selectbox("Selecione o Estado (UF)", ["SP", "RJ", "MG", "PR", "BA", "RS", "SC", "PE"])
        
    if ncm_busca:
        filtro = df_st[(df_st["NCM"] == ncm_busca) & (df_st["UF"] == uf_busca)]
        if not filtro.empty:
            st.success("Regra de ST Encontrada!")
            st.table(filtro)
        else:
            st.info(f"Nenhuma regra específica de ST cadastrada para o NCM {ncm_busca} no estado de {uf_busca}. Certifique-se de que o produto não é tributado de forma geral ou Isento.")

# --- ABA 3: TABELAS DO SPED ---
with aba3:
    st.header("Tabelas Oficiais do SPED (Regime Monofásico)")
    st.write("Abaixo constam as bases configuradas para validação do PIS/COFINS Monofásico:")
    
    col_tabela1, col_tabela2 = st.columns(2)
    
    with col_tabela1:
        st.subheader("Tabela 4.3.10 / 4.3.11 Simplificada")
        df_view_mono = pd.DataFrame.from_dict(db_monofasico, orient='index').reset_index()
        df_view_mono.columns = ["NCM Alvo", "CST PIS Correto", "CST COFINS Correto", "Base Legal / Segmento"]
        st.dataframe(df_view_mono, use_container_width=True)
