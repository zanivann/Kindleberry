#!/bin/sh
# --- Configuração ---
VERSION="v1.2.0 (Luminosity Sync)"
IP_RPI="192.168.0.XXX"  # <--- SEU IP AQUI
FBINK="/mnt/us/extensions/kindleberry/fbink"
URL_BASE="http://$IP_RPI:5000"
IMG_URL="$URL_BASE/dashboard.png"
STATUS_URL="$URL_BASE/check_status"
OUTPUT="/tmp/dashboard.png"
HEADERS="/tmp/dash.headers"

# Configuração do Refresh Híbrido (Flash a cada X atualizações)
REFRESH_LIMIT=10  
COUNT=0

# Previne descanso de tela e mantém Wi-Fi ativo
lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.cmd wirelessEnable 1

$FBINK -c -f -m -q "KindleBerry $VERSION Aguardando Servidor..."

while true; do
    # 1. Checagem de Segurança (REMOTE STOP)
    STATUS=$(wget -q -O - "$STATUS_URL")
    
    if [ "$STATUS" == "STOP" ]; then
        $FBINK -c -f -q "Encerrado pelo Servidor. Clique aqui para fechar."
        lipc-set-prop com.lab126.powerd preventScreenSaver 0
        exit 0
    fi

    # 2. Busca bateria local
    BAT=$(lipc-get-prop com.lab126.powerd capacity)
    
    # 3. Download da Imagem + Captura de Headers (Brilho)
    # Usamos curl -D para salvar os headers no arquivo /tmp/dash.headers
    if curl -s -m 5 -D "$HEADERS" -o "$OUTPUT" "$IMG_URL?kbat=$BAT"; then
        
        # --- LÓGICA DE LUMINOSIDADE ---
        # Extrai o valor do header X-Brightness enviado pelo Python
        NEW_BRIGHT=$(grep -i "X-Brightness:" "$HEADERS" | awk '{print $2}' | tr -d '\r')
        
        if [ "$NEW_BRIGHT" != "" ]; then
            # Aplica o brilho ao hardware do Kindle (0 a 24)
            lipc-set-prop com.lab126.powerd flIntensity "$NEW_BRIGHT"
        fi
        # ------------------------------

        # 4. Atualização da Tela (Híbrida)
        if [ $COUNT -ge $REFRESH_LIMIT ]; then
            $FBINK -c -f -g file="$OUTPUT"
            COUNT=0
        else
            $FBINK -c -g file="$OUTPUT"
            COUNT=$((COUNT + 1))
        fi
    else
        $FBINK -c -q "Conectando..."
        lipc-set-prop com.lab126.cmd wirelessEnable 1
    fi

    sleep 5
done