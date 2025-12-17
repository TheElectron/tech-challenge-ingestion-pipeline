# 📖  📈 Data Pipeline: Ingestão e Análise de Dados | FIAP Tech Challenge #02

![PySpark]
![AWS]
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)

## 💻 Descrição do Projeto

Este projeto implementa um pipeline de dados *serverless* na AWS, e foi desenvolvido para o **Tech Challenge #02** da Pós-Graduação em  **Machine Learning Engineering** da FIAP.

Seu objetivo é extrair, processar e disponibilizar os dados da Carteira do Dia da bolsa de valores brasileira (B3), utilizando o AWS Glue e disponibilizá-los para consultas via Amazon Athena.

## 🏢 Arquitetura

A solução segue uma arquitetura *serverless* orientada a eventos, com foco no baixo custo e escalabilidade.

Fluxograma

                    !!!!FAZER A PORRA DO DESENHO!!!!!!

Ingestão: Um script Python extrai dados da B3 e salva em formato Parquet no S3 (Camada Raw).

Orquestração: O upload do arquivo no S3 dispara automaticamente uma função Lambda.

Processamento: A Lambda inicia um Job no AWS Glue (Visual), que realiza limpeza, cálculos de data e agregações.

Armazenamento: O Glue salva os dados refinados no S3 (Camada Refined), particionados por data e ticker.

Consumo: O Glue Catalog mantém os metadados atualizados, permitindo consultas SQL via Amazon Athena.


## 📂 Estrutura do Projeto


```
b3-data-pipeline/
├── docs/                   # Diagramas e documentação complementar
├── infrastructure/         # Infraestrutura como Código (IaC)
│   └── terraform/          # Scripts para provisionar S3, IAM, Glue e Lambda
├── src/
│   ├── ingestion/          # Scripts de extração (Scraper B3)
│   ├── lambdas/            # Código da Lambda Trigger
│   ├── glue/               # Definições do Job Visual e Scripts PySpark
│   └── sql/                # Queries de validação para o Athena
├── requirements.txt        # Dependências do projeto
└── README.md               # Documentação principal
```


## 🚀 Como Executar

1. Pré-requisitos
Conta AWS ativa.

AWS CLI configurado localmente.

Terraform instalado (v1.0+).

Python 3.9+.

2. Provisionamento da Infraestrutura
Utilizamos Terraform para criar todos os recursos necessários.

Bash

cd infrastructure/terraform
terraform init
terraform plan
terraform apply
Isso criará o Bucket S3, as Roles de IAM, a Lambda Trigger e o esqueleto do Job Glue.