# 📱 KindleBerry Dashboard v2.0.2

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
* **Interface Adaptativa Refinada (v2.0.2):** Gráficos, medidores e fontes ampliados no modo Dual-Monitor para garantir legibilidade superior em telas e-ink.

---

## 🛠️ Pré-requisitos

### Hardware
* **Kindle:** Qualquer modelo e-ink com **Jailbreak** e acesso **SSH** (USBNetwork).
* **Servidor:** Raspberry Pi (qualquer versão) ou PC rodando Docker.
* **Rede:** Kindle e Servidor devem estar no mesmo Wi-Fi.

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
├── server/                  # Backend (Raspberry Pi)
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── main.py
│   ├── dht_reader.py        # Driver do sensor
│   ├── requirements.txt
│   ├── config.json          # Configurações de brilho e clima
│   ├── locale/              # Ficheiros .json de tradução
│   ├── icons/               # Ícones de clima e lua (.png)
│   ├── fonts/               # Coloque sua fonte .ttf aqui
│   └── templates/
│       └── index.html
│
└── kindle/                  # Scripts para o Kindle (/mnt/us/extensions/kindleberry)
    ├── show_dash.sh         # Script principal (Loop de atualização)
    ├── stop_dash.sh         # Script para parar o processo
    ├── menu.json            # Configuração do botão KUAL
    └── fbink                # Binário executável

```
## 🚀 Instalação: Servidor (Raspberry Pi)

1.  **Prepare o Diretório:**
    No seu Raspberry Pi, crie a pasta do projeto e a estrutura necessária:
    ```bash
    mkdir -p kindleberry/server/fonts
    mkdir -p kindleberry/server/templates
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

```bash
#!/bin/sh
VERSION="v2.0.2 (UI Refinement)"
IP_RPI="192.168.0.10"
PORT="5000"
FBINK="/mnt/us/extensions/kindleberry/fbink"
URL_BASE="http://$IP_RPI:$PORT"

OUTPUT="/tmp/dashboard.png"
HEADERS="/tmp/dash.headers"

# Previne hibernação e ativa rede
lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.cmd wirelessEnable 1

$FBINK -c -f -m -q "KindleBerry $VERSION: Iniciando..."

while true; do
    # Verifica comando de parada remoto
    STATUS=$(wget -q -T 5 -t 1 -O - "$URL_BASE/check_status")
    if [ "$STATUS" == "STOP" ]; then
        $FBINK -c -f -q "Encerrado pelo Servidor."
        lipc-set-prop com.lab126.powerd preventScreenSaver 0
        exit 0
    fi

    # Coleta bateria local
    BAT=$(lipc-get-prop com.lab126.powerd battLevel)
    if [ -z "$BAT" ]; then BAT=0; fi

    # Download com telemetria de bateria
    if curl -s -L -D "$HEADERS" -o "$OUTPUT" "$URL_BASE/dashboard.png?kbat=$BAT"; then
        # Renderização com Flash Refresh
        $FBINK -g file="$OUTPUT" -c -q
        
        # Sincronização de Brilho via Header X-Brightness
        NEW_BRIGHT=$(grep -i "X-Brightness:" "$HEADERS" | awk '{print $2}' | tr -d '\r' | tr -d '[:space:]')
        if [ "$NEW_BRIGHT" != "" ]; then
            lipc-set-prop com.lab126.powerd flIntensity "$NEW_BRIGHT"
        fi
    else
        $FBINK -m -q "Erro: Sem ligação ao servidor"
        lipc-set-prop com.lab126.cmd wirelessEnable 1
    fi
    sleep 10
done
```
#### B. `stop_dash.sh` (Script de Parada)
Encerra o processo do dashboard, limpa a tela e devolve o controle de energia ao sistema (permitindo que o Kindle hiberne novamente).

```bash
#!/bin/sh
killall show_dash.sh
# Devolve o controle do descanso de tela ao sistema (Power Management)
lipc-set-prop com.lab126.powerd preventScreenSaver 0
/mnt/us/extensions/kindleberry/fbink -c -f -q "Dashboard Parado"
```
#### C. `menu.json` (Menu do KUAL)
Define a estrutura do botão dentro do KUAL. Cria uma pasta "KindleBerry" com opções para iniciar e parar o dashboard.

> **⚠️ Dica Crítica:** O KUAL é extremamente sensível à formatação JSON. Recomenda-se criar este arquivo usando o editor `vi` diretamente no terminal do Kindle para evitar que editores de texto comuns (Notepad, VSCode, TextEdit) insiram quebras de linha ou caracteres ocultos que impedem o KUAL de ler o arquivo.

```json
{
    "items": [
        {
            "name": "KindleBerry",
            "priority": 0,
            "items": [
                {
                    "name": "LIGAR Dashboard",
                    "priority": 1,
                    "action": "/mnt/us/extensions/kindleberry/show_dash.sh",
                    "params": ""
                },
                {
                    "name": "DESLIGAR Dashboard",
                    "priority": 2,
                    "action": "/mnt/us/extensions/kindleberry/stop_dash.sh",
                    "params": ""
                }
            ]
        }
    ]
}
```
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
| **Horário Errado** | Fuso horário do Docker. | O container roda em UTC por padrão. Configure o Timezone correto (ex: `America/Sao_Paulo`) na interface Web (`http://IP-DO-RPI:5000`) e clique em Salvar. |
| **Tela piscando muito** | Atualização completa (Full Refresh). | O script usa a flag `-f` para limpar resíduos (ghosting) a cada atualização. Isso é normal para garantir a nitidez da imagem e evitar borrões. Se incomodar, aumente o tempo do `sleep` no script `show_dash.sh`. |
| **Dados de CPU/RAM zerados** | Erro de conexão. | Verifique se o Kindle e o Raspberry Pi estão na mesma rede Wi-Fi e se o IP configurado no `show_dash.sh` está correto. |
| **Slave não aparece** | Agente offline ou Docker isolado. | Certifique-se de que o `agent.py` está rodando com `network_mode: host` para atravessar o isolamento do container. |

---

## 📄 Créditos

* **FBInk:** [NiLuJe](https://github.com/NiLuJe/FBInk) - Ferramenta essencial para desenhar na tela e-ink.
* **KUAL:** Comunidade MobileRead.
* **Open-Meteo:** API de clima gratuita e open-source.