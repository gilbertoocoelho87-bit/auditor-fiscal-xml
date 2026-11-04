import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io

# Configuração da página para aproveitar melhor o espaço na tela
st.set_page_config(page_title="Auditor Fiscal XML", layout="wide", page_icon="📊")

# ==============================================================================
# 1. BANCO DE DATA MOCK (SIMULANDO REGRAS DA ECONET)
# ==============================================================================
# Em produção, você pode carregar essas tabelas a partir de planilhas Excel ou Banco de Dados.
@st.cache_data
def carregar_base_tributaria():
    # Simulação da Tabela de Monofásicos e Substituição Tributária por NCM/UF
    dados = [
        {
            "NCM": "62046900",
            "UF": "PE",
            "Descricao_NCM": "Fatos de treino, macacões, calças, bermudas (Vestuário Têxtil)",
            "Regime_ICMS": "NORMAL",
            "Aliquota_Interna": "20,5%",
            "CFOP_Saida_Correto": "5102",
            "CST_PIS_Correto": "01",  # Exemplo: Tributável normal se não for monofásico
            "Texto_Entrada": "CFOP Interno: 1102 | Interestadual: 2102. CST: 000 (Tributada integralmente). Sujeito a eventual antecipação sem ST (Decreto nº 44.650/2017).",
            "Texto_Saida": "CFOP Interno: 5102 | Interestadual: 6102. CST: 000 (Tributada integralmente). Produto não sujeito à Substituição Tributária em Pernambuco.",
            "PIS_COFINS_Regime": "Cumulativo (PIS: 0,65% | COFINS: 3,00%)",
            "IPI_Texto": "Alíquota: 0%. Fixada em 0% na TIPI (Decreto Federal nº 11.158/2022).",
            "Alertas": "• Em Pernambuco, a alíquota modal básica do ICMS é de 20,5% (Lei Estadual nº 18.305/2023).\n• Verificar se o estabelecimento está enquadrado no PRODEPE ou Polo Têxtil.",
            "Fundamentos": "• Lei nº 18.305/2023 (ICMS-PE)\n• Decreto nº 44.650/2017 (RICMS/PE)\n• Lei Federal nº 9.718/1998 (PIS/COFINS)"
        },
        {
            "NCM": "30049099",  # Medicamentos (Simulação de Monofásico/ST)
            "UF": "PE",
            "Descricao_NCM": "Outros medicamentos contendo produtos misturados",
            "Regime_ICMS": "SUBSTITUIÇÃO TRIBUTÁRIA (ST)",
            "Aliquota_Interna": "20,5%",
            "CFOP_Saida_Correto": "5405",  # Venda de mercadoria com ST retida anteriormente
            "CST_PIS_Correto": "04",  # Monofásico (Tabela 4.3.10 do SPED)
            "Texto_Entrada": "CFOP Interno: 1403 | CST: 060. Retido por Substituição Tributária.",
            "Texto_Saida": "CFOP Interno: 5405 | CST: 060. Venda de produto com ICMS ST já retido anteriormente.",
            "PIS_COFINS_Regime": "Alíquota Zero / Monofásico (CST 04 - Tabela 4.3.10 do SPED)",
            "IPI_Texto": "Alíquota zero ou Isento conforme TIPI.",
            "Alertas": "• Produto sujeito ao regime de Substituição Tributária.\n• PIS/COFINS Monofásico: Exija o CST 04 na emissão para não pagar imposto em duplicidade.",
            "Fundamentos": "• Lei nº 10.147/2000 (Medicamentos Monofásicos)\n• Tabela 4.3.10 do SPED"
        }
    ]
    return pd.DataFrame(dados)

base_tributaria = carregar_base_tributaria()

# ==============================================================================
# 2. FUNÇÃO DE PARSING DO XML
# ==============================================================================
def processar_arquivo_xml(conteudo_xml, nome_arquivo):
    try:
        tree = ET.parse(io.BytesIO(conteudo_xml))
        root = tree.getroot()
        ns = {'ns': 'http://portalfiscal.inf.br'}
        
        # Identifica a UF do destinatário da nota
        dest_uf = root.find('.//ns:dest/ns:enderDest/ns:UF', ns)
        uf_destino = dest_uf.text if dest_uf is not None else "PE"
        
        produtos = []
        for det in root.findall('.//ns:det', ns):
            n_item = det.attrib.get('nItem')
            prod = det.find('ns:prod', ns)
            
            c_prod = prod.find('ns:cProd', ns).text
            x_prod = prod.find('ns:xProd', ns).text
            ncm = prod.find('ns:NCM', ns).text
            cfop_emitido = prod.find('ns:CFOP', ns).text
            
            # PIS Emitido
            cst_pis = "01"
            pis_element = det.find('.//ns:PIS//ns:CST', ns)
            if pis_element is not None:
                cst_pis = pis_element.text
                
            produtos.append({
                "Arquivo": nome_arquivo,
                "Item": n_item,
                "Código": c_prod,
                "Descrição": x_prod,
                "NCM": ncm,
                "CFOP_Emitido": cfop_emitido,
                "CST_PIS_Emitido": cst_pis,
                "UF_Destino": uf_destino
            })
        return produtos
    except Exception as e:
        st.error(f"Erro ao ler o arquivo {nome_arquivo}: {e}")
        return []

# ==============================================================================
# 3. INTERFACE INTERATIVA DO STREAMLIT
# ==============================================================================
st.title("🛡️ Auditor Fiscal de XML - PIS/COFINS & ST")
st.write("Faça o upload dos seus arquivos XML em lote para analisar divergências de alíquotas, CFOP, CST Monofásicos e ST.")

# Componente de upload múltiplo
arquivos_carregados = st.file_uploader("Arraste e solte seus arquivos XML da NF-e aqui", type=["xml"], accept_multiple_files=True)

if arquivos_carregados:
    todos_produtos = []
    
    # Processa cada arquivo enviado
    for arquivo in arquivos_carregados:
        conteudo = arquivo.read()
        dados_itens = processar_arquivo_xml(conteudo, arquivo.name)
        todos_produtos.extend(dados_itens)
        
    if todos_produtos:
        df_xml = pd.DataFrame(todos_produtos)
        
        # Realiza o cruzamento com as regras do banco tributário
        df_auditado = pd.merge(df_xml, base_tributaria, on=["NCM", "UF_Destino"], how="left")
        
        st.success(f"Foram analisados {len(df_xml)} itens de produto no lote de XMLs.")
        
        # --- TABELA DE ERROS DETECTADOS ---
        st.subheader("🚨 Divergências e Erros de Emissão Encontrados")
        
        erros_encontrados = []
        for idx, row in df_auditado.iterrows():
            # Se o NCM não estiver mapeado na base mock
            if pd.isna(row['Regime_ICMS']):
                continue
                
            motivo_erro = []
            if row['CFOP_Emitido'] != row['CFOP_Saida_Correto']:
                motivo_erro.append(f"CFOP Incorreto (Emitido: {row['CFOP_Emitido']} | Esperado: {row['CFOP_Saida_Correto']})")
            if row['CST_PIS_Emitido'] != row['CST_PIS_Correto']:
                motivo_erro.append(f"CST de PIS Incorreto (Emitido: {row['CST_PIS_Emitido']} | Esperado Monofásico: {row['CST_PIS_Correto']})")
                
            if motivo_erro:
                erros_encontrados.append({
                    "Arquivo": row['Arquivo'],
                    "Item": row['Item'],
                    "Produto": row['Descrição'],
                    "NCM": row['NCM'],
                    "UF": row['UF_Destino'],
                    "Inconformidades": " / ".join(motivo_erro),
                    "index_auditado": idx
                })
                
        if erros_encontrados:
            df_erros = pd.DataFrame(erros_encontrados)
            st.dataframe(df_erros[["Arquivo", "Item", "Produto", "NCM", "UF", "Inconformidades"]], use_container_width=True)
            
            # --- SELETOR ESTILO ECONET PARA VER DETALHES ---
            st.markdown("---")
            st.subheader("🔍 Detalhamento Jurídico e Ficha Fiscal do Item")
            st.caption("Selecione um item abaixo para abrir a ficha completa no padrão Econet:")
            
            opcoes_selecao = {f"{r['Produto']} (NCM {r['NCM']}) - Nota: {r['Arquivo']}": r['index_auditado'] for r in erros_encontrados}
            item_selecionado = st.selectbox("Escolha o produto para ver a legislação corrigida:", list(opcoes_selecao.keys()))
            
            # Renderiza o layout da Econet com base no item selecionado
            idx_escolhido = opcoes_selecao[item_selecionado]
            dados_item = df_auditado.loc[idx_escolhido]
            
            # Cabeçalho da Ficha Fiscal
            st.markdown(f"### 📋 Ficha Fiscal - NCM {dados_item['NCM']}")
            st.info(f"**Descrição Comercial:** {dados_item['Descrição']}\n\n**Classificação Fiscal:** {dados_item['Descricao_NCM']}")
            
            # Layout em Colunas (Entrada e Saída)
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 📥 ENTRADA")
                st.write(dados_item['Texto_Entrada'])
            with col2:
                st.markdown("#### 📤 SAÍDA")
                st.write(dados_item['Texto_Saida'])
                
            # Layout de Impostos Federais
            col3, col4 = st.columns(2)
            with col3:
                st.markdown("#### 📦 PIS / COFINS")
                st.write(f"**Regime:** {dados_item['PIS_COFINS_Regime']}")
            with col4:
                st.markdown("#### ⚙️ IPI")
                st.write(dados_item['IPI_Texto'])
                
            # Alertas e Fundamentos Legais no rodapé
            st.error(f"⚠️ **Alertas Tributários**\n\n{dados_item['Alertas']}")
            
            with st.expander("📚 Fundamentos Legais e Dispositivos Decres/Leis"):
                st.markdown(dados_item['Fundamentos'])
                
        else:
            st.success("🎉 Nenhum erro de emissão de CFOP ou CST Monofásico foi encontrado nos arquivos validados!")
