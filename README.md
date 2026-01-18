# 📈 B3 Data Pipeline: Ingestão e Análise de Dados | FIAP Tech Challenge #02

![AWS](https://img.shields.io/badge/AWS-232F3E?style=for-the-badge&logo=amazon-aws&logoColor=white)
![PySpark](https://img.shields.io/badge/PySpark-E25A1C?style=for-the-badge&logo=apache-spark&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-7B42BC?style=for-the-badge&logo=terraform&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-lightgrey.svg?style=for-the-badge)

## 💻 Descrição do Projeto

Este projeto consiste em um pipeline de engenharia de dados orientado a eventos (*event-driven* ) para extração, processamento e análise da composição do índice IBOVESPA (B3).

Desenvolvida como entrega final do **Tech Challenge #02** da Pós-Graduação em **Machine Learning Engineering** da FIAP, a solução utiliza o ecossistema AWS para criar um Data Lake escalável. O fluxo extrai diariamente a carteira teórica da B3, ingere os dados brutos, processa métricas financeiras complexas (como Média Móvel e Volatilidade) e disponibiliza as informações para consulta analítica via SQL.

## 🏢 Arquitetura

A solução segue uma arquitetura *serverless*, priorizando o desacoplamento de componentes, baixo custo operacional e escalabilidade automática.

### Fluxo de Dados

flowchart LR
    A[B3 Website] -->|Extração Diária| B(Glue Job: Extract)
    B -->|Parquet| C[(S3: Raw Zone)]
    C -->|Trigger Event| D(AWS Lambda)
    D -->|Start Job + Args| E(Glue Job: Transform)
    E -->|Read Window| C
    E -->|Parquet + Catalog| F[(S3: Refined Zone)]
    F -->|Query| G[Amazon Athena]


O fluxo de dados segue o padrão Medallion (Bronze/Silver):
'''
flowchart TD
    %% Definição de Estilos
    classDef aws fill:#FF9900,stroke:#232F3E,stroke-width:2px,color:white;
    classDef storage fill:#3F8624,stroke:#232F3E,stroke-width:2px,color:white;
    classDef external fill:#999999,stroke:#232F3E,stroke-width:2px,color:white;
    classDef trigger fill:#E7157B,stroke:#232F3E,stroke-width:2px,color:white;
    %% Fontes e Agendador
    subgraph Origem ["Fonte de Dados Externos"]
        B3[API Web B3\n(Hidden JSON)]:::external
    end
    Scheduler(EventBridge\nScheduler Diário):::trigger
    %% Camada de Ingestão
    subgraph Bronze ["Camada Raw (Bronze)"]
        GlueExt[Glue Job: Extração\nPython Shell]:::aws
        S3Raw[(S3 Bucket\n/raw\ndt=YYYY-MM-DD)]:::storage
    end
    %% Camada de Orquestração
    subgraph Orchestration ["Orquestração de Eventos"]
        S3Event>S3 Event PUT\nNotification]:::trigger
        Lambda[Lambda Function\nTrigger Glue]:::aws
    end
    %% Camada de Processamento
    subgraph Silver ["Camada Refined (Silver)"]
        GlueTrans[Glue Job: Transformação\nApache Spark ETL]:::aws
        S3Ref[(S3 Bucket\n/refined\ndt=, ticker=)]:::storage
        Catalog[Glue Data Catalog\nDatabase & Tables]:::aws
    end
    %% Camada de Consumo
    subgraph Serving ["Camada de Consumo"]
        Athena[Amazon Athena\nSQL Queries]:::aws
        Analista((Analista\nUsuário))
    end
    %% Fluxo Principal
    Scheduler -->|1. Dispara às 18h| GlueExt
    GlueExt -- "2. HTTPS GET" --> B3
    B3 -- JSON --> GlueExt
    GlueExt -- "3. Salva Parquet (Limpa & Escreve)" --> S3Raw
    S3Raw -.->|4. Detecta novo arquivo| S3Event
    S3Event -->|5. Aciona| Lambda
    Lambda -- "6. Inicia Job com Argumentos\n(--JOB_DATE, --BUCKET)" --> GlueTrans
    GlueTrans -- "7. Lê Janela Histórica\n(Dia atual + 6 dias anteriores)" --> S3Raw
    GlueTrans -- "8. Aplica Regras\n(Média Móvel, Volatilidade)" --> GlueTrans
    GlueTrans -- "9. Salva Parquet Particionado" --> S3Ref
    GlueTrans -- "10. Atualiza Metadados" --> Catalog
    %% Fluxo de Consulta
    Analista -->|SQL| Athena
    Athena -->|Consulta Esquema| Catalog
    Athena -->|Lê Dados| S3Ref
    %% Linkagem de Estilos
    linkStyle 0,3,5,6,7,9,10 stroke:#FF9900,stroke-width:2px;
    linkStyle 4,8 stroke:#3F8624,stroke-width:2px;
    linkStyle 11,12,13 stroke:#232F3E,stroke-width:1px,stroke-dasharray: 5 5;
'''

- Raw Layer (Bronze):
    Responsável pela ingestão. O Job Glue (extract_b3_data.py) realiza a engenharia reversa da API da B3, extraindo os dados da carteira do dia e armazenando-os em formato Parquet com particionamento diário (dt=YYYY-MM-DD).

    >💡 Optou-se pelo uso de um Jog Glue do tipo Python Shell nesta etapa. Como a tarefa simples, apenas requisições HTTP, não exige é necessário o uso de processamento distribuído. Essa escolha reduz drasticamente os custos operacionais (DPU) em comparação a um cluster Spark convencional.

- Orquestração:
    Utiliza-se o padrão Event Notification. Ao concluir a gravação do arquivo na Raw Layer, o S3 dispara uma AWS Lambda, que identifica a data da carga e aciona o job de transformação.

- Refined Layer (Silver):
    O Job Glue (transform_b3_data.py) utiliza Apache Spark para aplicar regras de negócio, limpeza e cálculos de janelamento (Window Functions).

    Os dados processados são catalogados automaticamente no AWS Glue Data Catalog, tornando-os imediatamente disponíveis para consultas SQL via Amazon Athena.

## 🛠️ Tecnologias Utilizadas

- Linguagens: Python 3.9, PySpark.
- Armazenamento: AWS S3 (com particionamento Hive).
- Computação (ETL):
    AWS Glue Python Shell (Extração).
    AWS Glue Spark (Transformação).
- Orquestração: AWS Lambda & Amazon EventBridge.
- Analytics: Amazon Athena.
- IaC: Terraform (Vëm ai, confia ...).

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

## ⚙️ Detalhes da Implementação

### 1. Camada de Extração (extract_b3_data.py)
- Tipo: Glue Job (Python Shell).
- Estratégia: Engenharia reversa da API oculta do site da B3 para obter dados limpos em JSON, evitando instabilidade de scraping HTML.
- Idempotência: Implementada lógica de "Limpeza prévia" (delete_objects) para garantir que reprocessamentos no mesmo dia não dupliquem dados.
- Saída: Arquivos Parquet na pasta s3://bucket/raw/dt=YYYY-MM-DD/.

### 2. Gatilho de Orquestração (trigger_transform.py)
- Tipo: AWS Lambda.
- Trigger: S3 PUT Event.
- Função: Detecta novos arquivos na pasta RAW, extrai a data da partição e injeta como argumento dinâmico (--JOB_DATE) no Job de Transformação.

### 3. Camada de Transformação (transform_b3_data.py)
- Tipo: Glue Job (Spark ETL).
- Lógica de Janela (Window Functions):
- Leitura: Carrega histórico (D-6) para permitir cálculos temporais.
- Média Móvel (7d): Suavização da participação do ativo.
- Volatilidade: Desvio padrão da participação no período.
- Otimização: Uso de .cache() e Filtros de Partição (Partition Pruning) para leitura eficiente.
- Saída: Tabela particionada (dt, ticker) registrada no Glue Catalog.

<!-- 🚀 Como Executar

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
Isso criará o Bucket S3, as Roles de IAM, a Lambda Trigger e o esqueleto do Job Glue. -->