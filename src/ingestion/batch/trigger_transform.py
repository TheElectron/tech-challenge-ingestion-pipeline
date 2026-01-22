import os
import json
import boto3
import logging
import urllib.parse

# Configuração de Logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Nome do Job Glue de Transformação
GLUE_JOB_NAME = os.environ.get('GLUE_JOB_NAME', 'transform_b3_data')

def lambda_handler(event, context):
    """
        Função acionada automaticamente quando um arquivo é salvo no S3.
        Ela identifica a data da partição e dispara o Job Glue de Transformação.
    """
    glue_client = boto3.client('glue')
    logger.info("Recebendo evento do S3...")
    for record in event['Records']:
        try:
            bucket_name = record['s3']['bucket']['name']
            file_key = urllib.parse.unquote_plus(record['s3']['object']['key'])
            
            logger.info(f"Arquivo detectado: s3://{bucket_name}/{file_key}")
            if "raw/dt=" not in file_key:
                logger.info("Arquivo ignorado: Não pertence à estrutura de partição 'raw/dt='.")
                continue
            path_parts = file_key.split('/')
            partition_part = next((p for p in path_parts if p.startswith('dt=')), None)
            
            if not partition_part:
                logger.error(f"Erro: Não foi possível extrair a data do caminho: {file_key}")
                continue
            job_date = partition_part.split('=')[1]
            logger.info(f"Disparando Job '{GLUE_JOB_NAME}' para a data: {job_date}")
            response = glue_client.start_job_run(
                JobName=GLUE_JOB_NAME,
                Arguments={
                    '--JOB_DATE': job_date,
                    '--TARGET_BUCKET': bucket_name
                }
            )
            job_run_id = response['JobRunId']
            logger.info(f"Job Glue iniciado com sucesso! Run ID: {job_run_id}")
        except Exception as e:
            logger.error(f"Erro fatal ao processar o registro: {str(e)}")
            raise e
    return {
        'statusCode': 200,
        'body': json.dumps('Trigger processado com sucesso.')
    }
