#!/bin/sh
# --- Configuração Kindleberry (zanivann) ---
VERSION="v2.0.3 (Zanivann Sync)"
IP_RPI="192.168.0.10"
PORT="5000"
FBINK="/mnt/us/extensions/kindleberry/fbink"

# Definição de URLs baseadas na estrutura do repositório
URL_BASE="http://$IP_RPI:$PORT"
IMG_URL="$URL_BASE/dashboard.png"
STATUS_URL="$URL_BASE/check_status"

OUTPUT="/tmp/dashboard.png"
HEADERS="/tmp/dash.headers"

# --- Inicialização ---
echo "Iniciando integração Kindleberry..."
lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.cmd wirelessEnable 1

# Notificação visual de início
$FBINK -c -f -m -q "Kindleberry $VERSION: Ligando ao Servidor..."

while true; do
    # 1. Verifica Status (Integração com a rota /check_status do projeto)
    STATUS=$(wget -q -T 5 -t 1 -O - "$STATUS_URL")

    if [ "$STATUS" == "STOP" ]; then
        echo "Comando STOP recebido. Desligando sistema..."
        $FBINK -c -f -m -q "Encerrando Kindleberry..."
        sleep 2
        lipc-set-prop com.lab126.powerd preventScreenSaver 0
        lipc-set-prop com.lab126.powerd powerOff 1
        exit 0
    fi

    # 2. Coleta de Bateria (Ajustado para o firmware: battLevel)
    BAT=$(lipc-get-prop com.lab126.powerd battLevel)
    if [ -z "$BAT" ]; then BAT=0; fi

    # 3. Download da Imagem (Compatível com o parâmetro ?kbat esperado pelo server)
    if curl -s -L -D "$HEADERS" -o "$OUTPUT" "$IMG_URL?kbat=$BAT"; then
        
        # 4. Renderização (FBInk é mais rápido que o eips padrão do repo)
        $FBINK -g file="$OUTPUT" -c -q
        
        # 5. Sincronização de Brilho (Opcional - via Header HTTP)
        NEW_BRIGHT=$(grep -i "X-Brightness:" "$HEADERS" | awk '{print $2}' | tr -d '\r' | tr -d '[:space:]')
        if [ "$NEW_BRIGHT" != "" ]; then
            lipc-set-prop com.lab126.powerd flIntensity "$NEW_BRIGHT"
        fi

        echo "[$(date +%H:%M:%S)] Dashboard Atualizado (Bat: $BAT%)"
    else
        echo "[$(date +%H:%M:%S)] Falha de rede. Servidor $IP_RPI inacessível."
        $FBINK -m -q "Erro: Sem ligação ao servidor"
        lipc-set-prop com.lab126.cmd wirelessEnable 1
    fi

    # O projeto zanivann sugere intervalos de 10s a 60s
    sleep 10
done