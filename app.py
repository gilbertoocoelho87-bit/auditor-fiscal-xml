import os
import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st
from typing import Dict, List, Any

st.set_page_config(page_title="Auditor Fiscal Avançado de XMLs", layout="wide")

class AuditarXMLFiscal:
    """Engine de Auditoria Fiscal de NF-e com regras Federais (EFD-Contribuições 4.3.10) e Estaduais (por UF)."""
    NS = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

    def __init__(self, matriz_tributaria: Dict[str, Any]):
        self.matriz_tributaria = matriz_tributaria

    def extrair_dados_xml_conteudo(self, conteudo_bytes: bytes, nome_arquivo: str) -> List[Dict[str, Any]]:
        itens = []
        try:
            root = ET.fromstring(conteudo_bytes)
            
            if root.tag.endswith('nfeProc'):
                infNfe = root.find('.//nfe:infNFe', self.NS)
            elif root.tag.endswith('NFe'):
                infNfe = root.find('.//nfe:infNFe', self.NS)
            else:
                infNfe = root
                
            if infNfe is None:
                return [{'arquivo': nome_arquivo, 'erro_xml': 'Estrutura de XML NFe inválida'}]

            ide = infNfe.find('nfe:ide', self.NS)
            uf_emit = infNfe.find('.//nfe:emit/nfe:enderEmit/nfe:UF', self.NS)
            uf_dest = infNfe.find('.//nfe:dest/nfe:enderDest/nfe:UF', self.NS)
            
            uf_origem = uf_emit.text if uf_emit is not None else 'SP'
            uf_destino = uf_dest.text if uf_dest is not None else 'PE'
            num_nota = ide.find('nfe:nNF', self.NS).text if ide is not None and ide.find('nfe:nNF', self.NS) is not None else 'N/A'

            for det in infNfe.findall('nfe:det', self.NS):
                num_item = det.attrib.get('nItem', '1')
                prod = det.find('nfe:prod', self.NS)
                imposto = det.find('nfe:imposto', self.NS)
                
                ncm = prod.find('nfe:NCM', self.NS).text if prod.find('nfe:NCM', self.NS) is not None else ''
                descricao = prod.find('nfe:xProd', self.NS).text if prod.find('nfe:xProd', self.NS) is not None else ''
                
                cst_pis, cst_cofins, cst_icms = '', '', ''
                
                if imposto is not None:
                    # PIS
                    pis = imposto.find('.//nfe:PIS', self.NS)
                    if pis is not None and len(pis) > 0:
                        cst_pis_el = pis[0].find('nfe:CST', self.NS)
                        cst_pis = cst_pis_el.text if cst_pis_el is not None else ''
                    
                    # COFINS
                    cofins = imposto.find('.//nfe:COFINS', self.NS)
                    if cofins is not None and len(cofins) > 0:
                        cst_cofins_el = cofins[0].find('nfe:CST', self.NS)
                        cst_cofins = cst_cofins_el.text if cst_cofins_el is not None else ''
                        
                    # ICMS
                    icms = imposto.find('.//nfe:ICMS', self.NS)
                    if icms is not None and len(icms) > 0:
                        cst_icms_el = icms[0].find('nfe:CST', self.NS)
                        if cst_icms_el is None:
                            cst_icms_el = icms[0].find('nfe:CSOSN', self.NS)
                        cst_icms = cst_icms_el.text if cst_icms_el is not None else ''

                itens.append({
                    'arquivo': nome_arquivo,
                    'numero_nota': num_nota,
                    'uf_origem': uf_origem,
                    'uf_destino': uf_destino,
                    'item': num_item,
                    'descricao': descricao,
                    'ncm': ncm,
                    'cst_pis_informado': cst_pis,
                    'cst_cofins_informado': cst_cofins,
                    'cst_icms_informado': cst_icms,
                    'erro_xml': ''
                })

        except ET.ParseError:
            return [{'arquivo': nome_arquivo, 'erro_xml': 'Arquivo XML corrompido ou malformado'}]
        except Exception as e:
            return [{'arquivo': nome_arquivo, 'erro_xml': f'Erro ao processar: {str(e)}'}]
            
        return itens

    def buscar_regra_ncm(self, ncm: str) -> Dict[str, Any]:
        """Busca a regra pelo NCM exato (8 dígitos) ou pela posição (primeiros 4 dígitos)."""
        if ncm in self.matriz_tributaria:
            return self.matriz_tributaria[ncm]
        
        # Busca por posição NCM (4 dígitos)
        posicao_ncm = ncm[:4] if len(ncm) >= 4 else ncm
        if posicao_ncm in self.matriz_tributaria:
            return self.matriz_tributaria[posicao_ncm]
            
        return {}

    def auditar_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        if item.get('erro_xml'):
            item['status_auditoria'] = 'ERRO_XML'
            item['inconsistencias'] = item['erro_xml']
            return item

        ncm = item['ncm']
        uf_dest = item['uf_destino']
        inconsistencias = []

        regra_ncm = self.buscar_regra_ncm(ncm)

        if not regra_ncm:
            item['status_auditoria'] = 'NCM_NAO_MAPEADA'
            item['inconsistencias'] = 'NCM não localizado na base legal de referência.'
            item['legislacao_aplicavel'] = 'N/A'
            item['tributacao_correta'] = 'Cadastrar NCM na Matriz Tributária'
            return item

        # 1. Auditoria PIS/COFINS (Tabela 4.3.10 EFD-Contribuições)
        cst_pis_esperado = regra_ncm.get('cst_pis_correto', '01')
        if regra_ncm.get('is_monofasico'):
            cst_pis_esperado = '04'
            if item['cst_pis_informado'] != cst_pis_esperado:
                inconsistencias.append(
                    f"PIS/COFINS Incorreto: Informado CST {item['cst_pis_informado']}, esperado CST 04 (Monofásico - Tabela 4.3.10 EFD)."
                )

        # 2. Auditoria ICMS/ST (Estadual por UF de Destino)
        regras_estaduais = regra_ncm.get('regras_estaduais', {})
        regra_uf = regras_estaduais.get(uf_dest, regras_estaduais.get('PADRAO', {}))
        
        cst_icms_esperado = regra_uf.get('cst_icms_correto', '00')
        tem_st = regra_uf.get('tem_st', False)

        if tem_st and item['cst_icms_informado'] not in ['60', '500', '10', '30', '70']:
            inconsistencias.append(
                f"ICMS ST Incorreto em {uf_dest}: Informado {item['cst_icms_informado']}, esperado CST 60/500 ou 10/30/70 (ST Estadual)."
            )
        elif not tem_st and item['cst_icms_informado'] in ['60', '500']:
            inconsistencias.append(
                f"ICMS Indevido de ST em {uf_dest}: Produto sem ST na UF, informado CST {item['cst_icms_informado']}."
            )

        # Base Legal Compilada
        leg_fed = regra_ncm.get('base_legal_federal', 'Tabela 4.3.10 EFD-Contribuições')
        leg_est = regra_uf.get('base_legal_estadual', f'RICMS/{uf_dest}')
        base_legal_completa = f"Federal: {leg_fed} | Estadual ({uf_dest}): {leg_est}"

        if inconsistencias:
            item['status_auditoria'] = 'INCONSISTENTE'
            item['inconsistencias'] = ' | '.join(inconsistencias)
            item['legislacao_aplicavel'] = base_legal_completa
            item['tributacao_correta'] = f"PIS/COFINS CST {cst_pis_esperado} | ICMS CST {cst_icms_esperado}"
        else:
            item['status_auditoria'] = 'CONFORME'
            item['inconsistencias'] = 'Nenhuma'
            item['legislacao_aplicavel'] = base_legal_completa
            item['tributacao_correta'] = 'Tributação declarada em conformidade'

        return item


# --- MATRIZ TRIBUTÁRIA EFD-CONTRIBUIÇÕES TABELA 4.3.10 (TODOS OS GRUPOS MONOFÁSICOS) ---
MATRIZ_TABELA_4_3_10 = {
    # === GRUPO 1: COMBUSTÍVEIS E LUBRIFICANTES (Lei 9.990/00, Lei 10.336/01) ===
    '27101159': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 101 - Gasolinas (Lei 9.990/00)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '27101259': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 101 - Gasolinas (Lei 9.990/00)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '27101921': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 102 - Óleo Diesel (Lei 9.990/00)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '27111910': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 103 - GLP / Gás de Cozinha (Lei 9.990/00)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '27101932': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 104 - Óleos Lubrificantes', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '22071000': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 105 - Álcool Etílico Carburante (Lei 9.718/98)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},

    # === GRUPO 2: MEDICAMENTOS E PRODUTOS FARMACÊUTICOS (Lei 10.147/00) ===
    '3001': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 201 - Posição 3001 (Lei 10.147/00)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '3003': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 201 - Posição 3003 Medicamentos (Lei 10.147/00)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '3004': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 201 - Posição 3004 Medicamentos em Doses (Lei 10.147/00)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},

    # === GRUPO 3: PERFUMARIA, HIGIENE PESSOAL E COSMÉTICOS (Lei 10.147/00) ===
    '3303': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 202 - Perfumes e Águas de Colônia (Lei 10.147/00)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '3304': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 202 - Produtos de Maquiagem e Cuidados com a Pele', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '3305': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 202 - Preparações Capilares / Xampus', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '3307': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 202 - Desodorantes, Banhos e Barbeação', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '34011190': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 202 - Sabões de Toucador', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},

    # === GRUPO 4: VEÍCULOS, MÁQUINAS E AUTOPEÇAS (Lei 10.485/02) ===
    '8701': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 301 - Tratores (Lei 10.485/02)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '8702': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 301 - Ônibus e Micro-ônibus', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '8703': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 301 - Automóveis de Passageiros', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '8704': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 301 - Caminhões e Veículos de Carga', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '8708': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 303 - Partes e Acessórios de Automóveis (Autopeças)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '4011': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 302 - Pneus Novos de Borracha', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '4013': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 302 - Câmaras de Ar de Borracha', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},

    # === GRUPO 5: BEBIDAS FRIAS (Lei 13.097/15 - Águas, Refrigerantes, Cervejas, Energéticos) ===
    '2201': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 401/402 - Águas Minerais e Gaseificadas (Lei 13.097/15)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '2202': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 403 - Refrigerantes, Chás, Energéticos e Refrescos', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '2203': {'is_monofasico': True, 'cst_pis_correto': '04', 'base_legal_federal': 'Tabela 4.3.10 Cód 404 - Cervejas de Malte', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},

    # === OUTROS MATERIAIS DE CONSTRUÇÃO E INSUMOS COMUNS (ST ESTADUAL / TRIBUTAÇÃO NORMAL FEDERAL) ===
    '25232910': {'is_monofasico': False, 'cst_pis_correto': '01', 'base_legal_federal': 'Lei 10.833/2003 (Cimento)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '39174090': {'is_monofasico': False, 'cst_pis_correto': '01', 'base_legal_federal': 'Lei 10.833/2003 (Tubos/Conexões)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '32091010': {'is_monofasico': False, 'cst_pis_correto': '01', 'base_legal_federal': 'Lei 10.833/2003 (Tintas)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '35061090': {'is_monofasico': False, 'cst_pis_correto': '01', 'base_legal_federal': 'Lei 10.833/2003 (Massa Plástica)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '73170090': {'is_monofasico': False, 'cst_pis_correto': '01', 'base_legal_federal': 'Lei 10.833/2003 (Pregos)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '72142000': {'is_monofasico': False, 'cst_pis_correto': '01', 'base_legal_federal': 'Lei 10.833/2003 (Ferro/Aço)', 'regras_estaduais': {'PADRAO': {'tem_st': True, 'cst_icms_correto': '60'}}},
    '62101000': {'is_monofasico': False, 'cst_pis_correto': '01', 'base_legal_federal': 'Lei 10.833/2003 (Capa Chuva)', 'regras_estaduais': {'PADRAO': {'tem_st': False, 'cst_icms_correto': '00'}}},
    '68052000': {'is_monofasico': False, 'cst_pis_correto': '01', 'base_legal_federal': 'Lei 10.833/2003 (Lixas)', 'regras_estaduais': {'PADRAO': {'tem_st': False, 'cst_icms_correto': '00'}}}
}

# --- INTERFACE STREAMLIT ---
st.title("📊 Auditor Fiscal XML - Tabela 4.3.10 EFD-Contribuições + ST Estadual")

st.markdown("""
Esta versão inclui o mapeamento da **Tabela 4.3.10 da EFD-Contribuições (SPED)** para PIS/COFINS Monofásico (CST 04):
- **Combustíveis e Lubrificantes** (Gasolina, Diesel, GLP, Etanol)
- **Medicamentos e Fármacos** (Posições 3001, 3003, 3004)
- **Perfumaria e Cosméticos** (Posições 3303, 3304, 3305, 3307, Sabões)
- **Autopeças, Veículos e Pneus** (Posições 8701 a 8708, 4011, 4013)
- **Bebidas Frias** (Posições 2201, 2202, 2203 - Águas, Refrigerantes, Cervejas)
""")

arquivos_carregados = st.file_uploader("Selecione os arquivos XML para auditoria em lote", type=["xml"], accept_multiple_files=True)

if arquivos_carregados:
    auditor = AuditarXMLFiscal(matriz_tributaria=MATRIZ_TABELA_4_3_10)
    resultado_final = []

    for arq in arquivos_carregados:
        conteudo = arq.read()
        itens = auditor.extrair_dados_xml_conteudo(conteudo, arq.name)
        for item in itens:
            resultado_final.append(auditor.auditar_item(item))

    df_resultado = pd.DataFrame(resultado_final)

    st.subheader("Resultados da Auditoria Tributária")
    st.dataframe(df_resultado, use_container_width=True)

    # Botão para Download do Relatório em Excel
    excel_bytes = pd.ExcelWriter("relatorio_auditoria_efd.xlsx", engine="openpyxl")
    df_resultado.to_excel(excel_bytes, index=False)
    excel_bytes.close()

    with open("relatorio_auditoria_efd.xlsx", "rb") as f:
        st.download_button(
            label="📥 Baixar Relatório em Excel",
            data=f.read(),
            file_name="Relatorio_Auditoria_Monofasicos_EFD.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
