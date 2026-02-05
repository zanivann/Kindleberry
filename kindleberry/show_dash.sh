#!/bin/sh
# --- Configuração ---
VERSION="v1.1.0 (Remote Ctrl)"
IP_RPI="192.168.0.XXX"  # <--- SEU IP AQUI
FBINK="/mnt/us/extensions/kindleberry/fbink"
URL_BASE="http://$IP_RPI:5000"
IMG_URL="$URL_BASE/dashboard.png"
STATUS_URL="$URL_BASE/check_status"
OUTPUT="/tmp/dashboard.png"

# Configuração do Refresh Híbrido
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
        # --- MENSAGEM ATUALIZADA AQUI ---
        # O \n tenta quebrar a linha, mas dependendo da versão do fbink pode ficar na mesma linha.
        # O importante é a instrução.
        $FBINK -c -f -q "Encerrado pelo Servidor. Clique aqui para fechar."
        
        # Devolve controle de energia
        lipc-set-prop com.lab126.powerd preventScreenSaver 0
        
        # Encerra o script
        exit 0
    fi

    # 2. Se o status for "RUN", continua
    BAT=$(lipc-get-prop com.lab126.powerd capacity)
    
    if wget -q -T 3 -O "$OUTPUT" "$IMG_URL?kbat=$BAT"; then
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