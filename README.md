# 📱 KindleBerry Dashboard v4.7.1

![License](https://img.shields.io/badge/license-MIT-blue.svg) ![Platform](https://img.shields.io/badge/platform-Kindle%20%7C%20Raspberry%20Pi-orange)

Um dashboard de alta performance para Kindles (com Jailbreak), transformando o e-reader em um monitor de sistema e central de informações. O sistema utiliza um servidor **Python/Flask** (rodando em Docker no Raspberry Pi) para gerar as imagens e o **KUAL/FBInk** no Kindle para exibição.

---

## ✨ Funcionalidades

* **Monitoramento em Tempo Real:** Uso de CPU, RAM e Tráfego de Rede (Download/Upload com histórico gráfico).
* **Motor Híbrido de 15s:** Sensor DHT22 lido em segundo plano (thread dedicada). O dashboard entrega a imagem instantaneamente, evitando quedas de Wi-Fi no Kindle por latência de leitura.
* **Clima:** Temperatura atual, condição e ícones (Sol, Chuva, Nuvens) via Open-Meteo ou via sensor DFT22.
* **Sincronização de Brilho Real:** Ajuste a luminosidade do Kindle diretamente pela Web UI do Raspberry Pi. O valor (0-24) é enviado via Header HTTP e aplicado ao hardware do e-reader.
* **Busca Automática de Coordenadas: Botão "📍 Buscar":** integrado na UI que preenche Latitude e Longitude automaticamente via API do OpenStreetMap.
* **Feedback Bidirecional:** Exibe a bateria do próprio Kindle na tela.
* **Totalmente Configurável (Web UI):**
    * Alterar nome da cidade.
    * **Fuso Horário** ajustável.
    * **Rotação de Tela** (Retrato/Paisagem) via software.
    * **Dark Mode** (Modo Noturno) real.
* **Anti-Ghosting:** Atualização com flash de tela para garantir nitidez no e-ink.
* **Monitoramento de Cluster (Master/Slave):** Monitore múltiplos servidores simultaneamente. O layout se adapta automaticamente ao detectar agentes remotos.
* **Interface Adaptativa Refinada (v4.7.0):** Gráficos, medidores e fontes ampliados no modo Dual-Monitor para garantir legibilidade superior em telas e-ink.
* **Motor de Telemetria (SQLite):** Migração de logs em RAM para persistência em base de dados SQLite (telemetry.db).
* **Filtro de Anomalias Físicas:** Implementação de lógica no main.py para descartar flutuações de hardware impossíveis (Delta > 10°C) e limites absolutos (-20°C a 120°C).
* **Algoritmo Forward Fill:** Tratamento de dados nos gráficos para evitar quedas visuais causadas por falhas momentâneas de leitura dos sensores.
* **Controlo Térmico Inteligente:** Adição de suporte para gestão de ventoinhas via PWM, permitindo configurar temperaturas mínima e máxima de atuação.
* **Arquitetura Master/Slave:** Capacidade de orquestrar atuadores e ler telemetria de nós secundários (Slaves) através de uma API dedicada.
* **Painel Profissional v5:** Redesenho completo da index.html utilizando uma interface técnica organizada por abas (Dashboard, Hardware, System Records).
* **Internacionalização (i18n):** Implementação de suporte nativo a múltiplos idiomas através de dicionários JSON (pt_BR.json e en_US.json).
* **Estrutura de Dados:** Criação de volumes Docker específicos para a persistência da base de dados e configurações em /app/data.
* **Scripts do Kindle:** Atualização do script show_dash.sh para suportar as novas rotas de status e telemetria da versão BlackBox Core.

---

## 🛠️ Pré-requisitos

### Hardware
* **Kindle:** Qualquer modelo e-ink com **Jailbreak** e acesso **SSH** (USBNetwork).
* **Servidor Master:** Raspberry Pi ou Servidor Linux rodando Docker.
* **Agentes Slaves (Opcional):** Raspberry Pis adicionais para monitorização de cluster.
* **Sensores:** DHT22 (Interno) e DS18B20 (Externo). 
    * *Nota:* Para o DS18B20, o protocolo **1-Wire** deve estar ativo no Raspberry Pi (`dtoverlay=w1-gpio`).

### Software
* **No Kindle:**
    * [KUAL](https://www.mobileread.com/forums/showthread.php?t=203326) (Kindle Unified Application Launcher).
    * **FBInk** (Versão completa com suporte a imagens - geralmente encontrada no *MRInstaller* ou releases do NiLuJe).
* **No Servidor:**
    * Docker e Docker Compose.

---

## 📂 Estrutura de Arquivos

```text
kindleberry/
├── agent/                   # MONITORIZAÇÃO DISTRIBUÍDA (Slave Node)
│   ├── Dockerfile           # Imagem para execução em servidores secundários
│   ├── docker-compose.yml   # Definição do serviço (network_mode: host)
│   └── agent.py             # Script de coleta de métricas (CPU/RAM/Rede)
│
├── server/                  # NÚCLEO CENTRAL (Master Node)
│   ├── Dockerfile           # Imagem do servidor central Flask
│   ├── docker-compose.yml   # Orquestração (Volumes para base de dados)
│   ├── main.py              # Motor de Telemetria e Filtro de Anomalias
│   ├── requirements.txt     # Dependências (Flask, Pillow, w1thermsensor)
│   ├── config.json          # Variáveis de estado e Recordes Mín/Máx
│   ├── data/                # [PERSISTÊNCIA] Volume mapeado
│   │   └── telemetry.db     # Base de dados SQLite (Histórico de gráficos)
│   ├── locale/              # [i18n] Dicionários (pt_BR.json, en_US.json)
│   ├── icons/               # Assets visuais (.png)
│   ├── fonts/               # Tipografia (Roboto-Bold.ttf)
│   └── templates/           # [UI]
│       ├── index.html       # Interface Administrativa v5 (Abas)
│       └── history.html     # Visualização Analítica (Chart.js)
│
└── kindle/                  # TERMINAL E-INK (Scripts para o Kindle)
    ├── show_dash.sh         # Motor de renderização contínua
    ├── stop_dash.sh         # Procedimento de encerramento seguro
    ├── menu.json            # Configuração de interface KUAL
    └── fbink                # Binário executável gráfico (Versão KHF)

```

### 1. Núcleo Central (Raspberry Pi Master)

As configurações de lógica e interface residem na pasta `server/`:

-   **`server/main.py`**: É o cérebro do sistema. Aqui deve colocar toda a lógica de processamento, as rotas do Flask, o filtro de anomalias térmicas (Delta > 10°C) e a gestão da base de dados SQLite.
    
-   **`server/config.json`**: Este ficheiro armazena o estado persistente. É onde o sistema grava o nível de brilho, a rotação do ecrã, as coordenadas geográficas e os registos de recordes máximos e mínimos.
    
-   **`server/data/telemetry.db`**: Localizado dentro do volume de dados, este é o ficheiro da base de dados SQLite onde são armazenadas todas as leituras históricas de CPU, RAM e temperatura para gerar os gráficos.
    
-   **`server/locale/pt_BR.json`** e **`en_US.json`**: Coloque aqui os dicionários de tradução para que a interface técnica exiba os termos corretos conforme o idioma selecionado.
    
-   **`server/templates/index.html`**: Onde reside o código da nova interface profissional por abas (Dashboard, Hardware, Records).
    
-   **`server/templates/history.html`**: Onde reside a estrutura dos gráficos analíticos (Chart.js).
    

### 2. Monitorização Distribuída (Slave Node)

Se estiver a monitorizar múltiplos servidores, utilize a pasta `agent/`:

-   **`agent/agent.py`**: Coloque aqui o script leve que recolhe as métricas de CPU, RAM e rede do servidor secundário e as envia para o Master.
    
-   **`agent/docker-compose.yml`**: Certifique-se de definir `network_mode: host` neste ficheiro para permitir que o agente aceda às estatísticas de rede reais do hardware.
    

### 3. Terminal de Visualização (Kindle)

Os scripts de controlo do e-ink devem ser colocados em `/mnt/us/extensions/kindleberry/`:

-   **`show_dash.sh`**: O motor de renderização. Aqui deve configurar o `IP_RPI` do seu servidor Master para que o Kindle saiba onde descarregar a imagem do dashboard.
    
-   **`stop_dash.sh`**: Script de encerramento para devolver o controlo de energia ao sistema operativo do Kindle.
    
-   **`menu.json`**: O ficheiro de configuração do KUAL. Coloque aqui os nomes dos botões ("INICIAR Motor Gráfico") que aparecerão no menu do e-reader.
    
-   **`fbink`**: O binário executável (versão completa KHF) deve ser colocado na raiz desta pasta para permitir o desenho da imagem na framebuffer.
    

### 4. Configuração de Hardware (Sistema Operativo)

-   **`/boot/config.txt`**: Para utilizar o sensor DS18B20, deve adicionar a linha `dtoverlay=w1-gpio` neste ficheiro do Raspberry Pi e reiniciar o sistema para ativar o protocolo 1-Wire.

## 🚀 Instalação: Servidor (Raspberry Pi)

1.  **Prepare o Diretório:**
    No seu Raspberry Pi, crie a infraestrutura de pastas:
    ```bash
    mkdir -p kindleberry/server/fonts
    mkdir -p kindleberry/server/templates
    mkdir -p kindleberry/server/data
    chmod 777 kindleberry/server/data
    cd kindleberry/server
    ```

2.  **Adicione a Fonte:**
    Baixe uma fonte `.ttf` (ex: *Roboto-Bold.ttf*) e coloque dentro da pasta `server/fonts/`. O nome do arquivo deve bater com o configurado no `main.py`.

3.  **Arquivos do Servidor:**
    Certifique-se de que os arquivos `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `main.py` e `templates/index.html` estão na pasta `server/`.

4.  **Suba o Container:**
    ```bash
    docker compose up -d --build
    ```

5.  **Configuração Inicial:**
    Abra o navegador em `http://IP-DO-RPI:5000` e configure:
    * Nome da Cidade
    * Fuso Horário (Ex: `America/Sao_Paulo`)
    * Preferências de exibição

---
## 🛰️ Instalação: Agente (Slave Node)

Para monitorizar servidores secundários no cluster:
1. Copie a pasta `agent/` para o dispositivo escravo.
2. Certifique-se de que o `docker-compose.yml` do agente utiliza `network_mode: host`.
3. Inicie o serviço:
   ```bash
   docker compose up -d --build

---

## 📲 Instalação: Kindle

Acesse o Kindle via SSH (`ssh root@IP-DO-KINDLE`).

### 1. Preparar a Pasta da Extensão
Para garantir que o KUAL reconheça a pasta, recomenda-se clonar uma extensão existente (como *tailscale* ou *mrinstaller*) e limpar o conteúdo:

```bash
# Copia a estrutura de uma pasta funcional
cp -r /mnt/us/extensions/tailscale /mnt/us/extensions/kindleberry

# Remove os arquivos antigos
rm /mnt/us/extensions/kindleberry/*

### 2. Instalar o FBInk
O dashboard requer uma versão do `fbink` compilada com suporte a imagens. A versão padrão do KOReader é "lite" e não funcionará.

Recomendamos copiar o binário do pacote **MRInstaller**:

```bash
cp /mnt/us/extensions/MRInstaller/bin/KHF/fbink /mnt/us/extensions/kindleberry/fbink
chmod +x /mnt/us/extensions/kindleberry/fbink

### 3. Criar os Scripts
Crie os arquivos abaixo dentro da pasta `/mnt/us/extensions/kindleberry/`.

#### A. `show_dash.sh` (Script Principal)
Este script faz o loop infinito: busca a bateria local, baixa a imagem do servidor enviando a bateria na URL e atualiza a tela.
```
> **⚠️ Importante:** Edite a variável `IP_RPI` com o endereço IP do seu servidor.

#### B. `stop_dash.sh` (Script de Parada)
Encerra o processo do dashboard, limpa a tela e devolve o controle de energia ao sistema (permitindo que o Kindle hiberne novamente).

#### C. `menu.json` (Menu do KUAL)
Define a estrutura do botão dentro do KUAL. Cria uma pasta "KindleBerry" com opções para iniciar e parar o dashboard.

> **⚠️ Dica Crítica:** O KUAL é extremamente sensível à formatação JSON. Recomenda-se criar este arquivo usando o editor `vi` diretamente no terminal do Kindle para evitar que editores de texto comuns (Notepad, VSCode, TextEdit) insiram quebras de linha ou caracteres ocultos que impedem o KUAL de ler o arquivo.

### 4. Permissões Finais
Para que o KUAL consiga executar os scripts e ler os arquivos, precisamos garantir permissão total na pasta:

```bash
chmod 777 /mnt/us/extensions/kindleberry/*
```
## 🎮 Como Usar

1.  No Kindle, abra o **KUAL**.
2.  Você verá um botão (ou pasta) chamado **KindleBerry**. Entre nele.
3.  Toque em **LIGAR Dashboard**.
    * *Aguarde alguns segundos. A tela piscará e passará a atualizar automaticamente com os dados do servidor.*

### Como Sair (Parar o Dashboard)
Como o script toma conta da tela, você não verá os botões de navegação padrão, mas o sistema operacional continua rodando por trás.

1.  Toque na parte **superior** da tela (onde ficaria o relógio). A barra de tarefas do sistema deve aparecer.
2.  Toque no ícone **Home** (Casa) ou **Voltar**.
3.  Abra o **KUAL** novamente.
4.  Entre em **KindleBerry** e toque em **DESLIGAR Dashboard**.
    * *A tela exibirá a mensagem "Dashboard Parado" e o Kindle voltará a economizar energia normalmente.*

---

## 🆘 Solução de Problemas

| Problema | Causa Provável | Solução |
| :--- | :--- | :--- |
| **Botão não aparece no KUAL** | Erro de sintaxe no JSON. | O KUAL ignora o arquivo inteiro se houver uma vírgula fora do lugar. Valide o conteúdo do `menu.json` em sites como [jsonlint.com](https://jsonlint.com) ou recrie o arquivo usando o comando `vi` via SSH. |
| **Erro "Image support disabled"** | Versão incorreta do FBInk. | A versão do FBInk que vem nativa no KOReader é "lite" (apenas texto). Você precisa do binário completo. Copie o arquivo `fbink` da extensão **MRInstaller** se a tiver instalada ou baixe do repositório oficial. |
| **Tela piscando muito** | Atualização completa (Full Refresh). | O script usa a flag `-f` para limpar resíduos (ghosting) a cada atualização. Isso é normal para garantir a nitidez da imagem e evitar borrões. Se incomodar, aumente o tempo do `sleep` no script `show_dash.sh`. |
| **Dados de CPU/RAM zerados** | Erro de conexão. | Verifique se o Kindle e o Raspberry Pi estão na mesma rede Wi-Fi e se o IP configurado no `show_dash.sh` está correto. |
| **Slave não aparece** | Agente offline ou Docker isolado. | Certifique-se de que o `agent.py` está rodando com `network_mode: host` para atravessar o isolamento do container. |
| **Gráficos Vazios / Sem histórico** | Permissão na pasta de dados. | O SQLite não consegue gravar em `/app/data`. No seu Raspberry Pi Master, aplique: `chmod 777 kindleberry/server/data`. |
| **Sensor DS18B20 "No Data"** | Protocolo 1-Wire inativo. | O sensor externo exige ativação no SO. Use `sudo raspi-config` -> Interface Options -> 1-Wire -> Enable e reinicie. |
| **Picos impossíveis no gráfico** | Glitch de Hardware. | A v4.7.1 filtra saltos > 10°C. Se houver dados antigos ruidosos, use a aba "System Records" -> "PURGE VOLATILE RECORDS". |
| **Horário Desincronizado** | Timezone do Docker. | O container usa UTC por padrão. Configure o fuso horário (ex: `America/Sao_Paulo`) na interface Web e clique em "Salvar Alterações". |
| **Slave Node "Offline"** | Isolamento de rede Docker. | O Agente no servidor secundário deve rodar obrigatoriamente com `network_mode: host` no `docker-compose.yml`. |

---

## 📄 Créditos

* **FBInk:** [NiLuJe](https://github.com/NiLuJe/FBInk) - Ferramenta essencial para desenhar na tela e-ink.
* **KUAL:** Comunidade MobileRead.
* **Open-Meteo:** API de clima gratuita e open-source.