import os
import json
import logging
import base64
import boto3
import pandas as pd
import requests
from io import BytesIO
from datetime import datetime

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class B3Ingestion:
    def __init__(self, bucket_name: str, index_name: str = 'IBOV'):
        self.bucket_name = bucket_name
        self.index_name = index_name.upper()
        # Endpoint oficial que alimenta a página da B3 (retorna JSON)
        self.base_url = f"https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{self.base64_encode(self.index_name)}"
        self.s3_client = boto3.client('s3')

    @staticmethod
    def base64_encode(string_val: str) -> str:
        """A B3 as vezes requer encode em base64 na URL para alguns endpoints, 
           embora para o GetPortfolioDay o texto plano geralmente funcione, 
           manteremos simples a chamada direta primeiro."""
        # Nota: A URL atual da B3 aceita o ticker direto.
        return string_val

    def fetch_data(self) -> dict:
        """Realiza a requisição GET para a API da B3."""
        target_url = f"https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{self.index_name}"
        logger.info(f"Iniciando extração de dados para: {self.index_name}")
        logger.info(f"Endpoint: {target_url}")

        try:
            response = requests.get(target_url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao acessar API da B3: {e}")
            raise

    def process_data(self, raw_json: dict) -> pd.DataFrame:
        """
        Transforma o JSON bruto em DataFrame Pandas e ajusta tipagens.
        A B3 retorna números como strings '1.234,56'.
        """
        logger.info("Processando dados brutos...")
        
        results = raw_json.get('results', [])
        if not results:
            raise ValueError("Nenhum dado encontrado no retorno da API.")

        df = pd.DataFrame(results)

        # Seleção e Renomeação de colunas (Mapeamento Raw -> Bronze)
        # O JSON da B3 geralmente traz chaves como 'cod', 'asset', 'theoricalQty', 'part'
        df = df.rename(columns={
            'cod': 'codigo',
            'asset': 'acao',
            'type': 'tipo',
            'theoricalQty': 'qtd_teorica',
            'part': 'participacao'
        })

        # Tratamento de Tipos (Formato PT-BR para Float)
        cols_numericas = ['qtd_teorica', 'participacao'] # Adicionar 'price' se vier na API
        
        for col in cols_numericas:
            if col in df.columns:
                # Remove pontos de milhar e troca vírgula por ponto
                df[col] = df[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Adicionar coluna de data de referência (Partition Key)
        # A API traz o header com a data, mas para segurança usamos a data de ingestão ou a do header
        # Exemplo Header da B3: "header": {"date": "29/11/24", ...}
        data_pregao_str = raw_json.get('header', {}).get('date')
        if data_pregao_str:
            data_referencia = datetime.strptime(data_pregao_str, "%d/%m/%y").date()
        else:
            data_referencia = datetime.now().date()
            
        df['data_pregao'] = data_referencia
        
        logger.info(f"Dados processados. Total de registros: {len(df)}")
        return df

    def upload_to_s3(self, df: pd.DataFrame):
        """
        Converte para Parquet e faz upload para o S3 com partição.
        Atende Requisito 2.
        """
        # Define a partição baseada na data do pregão
        # Como o df tem a mesma data, pegamos o primeiro registro
        ref_date = df['data_pregao'].iloc[0]
        partition_path = f"year={ref_date.year}/month={ref_date.month:02d}/day={ref_date.day:02d}"
        
        filename = f"b3_ibov_{ref_date}.parquet"
        s3_key = f"raw/{partition_path}/{filename}"

        logger.info(f"Convertendo para Parquet e enviando para: s3://{self.bucket_name}/{s3_key}")

        # Buffer em memória
        out_buffer = BytesIO()
        df.to_parquet(out_buffer, index=False, engine='pyarrow')
        
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=out_buffer.getvalue()
        )
        logger.info("Upload concluído com sucesso.")

def lambda_handler(event, context):
    """
    Handler caso esse script seja executado via Lambda no futuro,
    ou chamado localmente.
    """
    BUCKET_NAME = os.environ.get('BUCKET_NAME', 'projeto-b3-datalake-dev') # Fallback para teste local
    
    ingestor = B3Ingestion(bucket_name=BUCKET_NAME)
    data = ingestor.fetch_data()
    df = ingestor.process_data(data)
    ingestor.upload_to_s3(df)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Ingestão B3 realizada com sucesso!')
    }

if __name__ == "__main__":
    # Execução Local para Teste
    # Certifique-se de ter credenciais AWS configuradas (aws configure)
    lambda_handler({}, {})